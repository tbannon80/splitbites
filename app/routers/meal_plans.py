import logging
import random
from datetime import date
from typing import Optional, List, Dict, Set
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.database.session import AsyncSessionLocal
from app.models import MealPlan, MealPlanItem, Recipe, Household, DietaryPreference, HouseholdRecipe
from app.schemas.meal_plan import (
    DEFAULT_7_DAYS,
    MealPlanGenerateRequest,
    MealPlanSwapRequest,
    MealPlanLockRequest,
    MealPlanShuffleRequest,
    MealPlanAddDayRequest,
    MealPlanSubtractDayRequest,
    MealPlanDaysUpdateRequest,
    MealSlotResponse,
    WeeklyMealPlanResponse,
)
from app.services.embedding import get_embedding
from app.services.grocery_aggregation import aggregate_groceries_for_plan

router = APIRouter(prefix="/api/meal-plans", tags=["meal-plans"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

def format_plan_response(plan: MealPlan) -> Dict:
    meals = {}
    for item in plan.items:
        if item.recipe:
            meals[item.day_of_week] = {
                "recipe_id": str(item.recipe.recipe_id),
                "title": item.recipe.title,
                "description": item.recipe.description,
                "prep_time_minutes": item.recipe.prep_time_minutes,
                "difficulty_level": item.recipe.difficulty_level,
                "is_modified": item.is_modified,
                "fallback_applied": bool(getattr(item, "fallback_applied", False))
            }
    count = len(meals)
    plan_type = "Standard 7-Day Week" if count == 7 else f"{count}-Day Schedule"
    return {
        "status": "success",
        "plan_id": str(plan.plan_id),
        "plan_type": plan_type,
        "week_start_date": str(plan.week_start_date),
        "is_locked": plan.is_locked,
        "meals": meals
    }

@router.get("/generate", response_model=WeeklyMealPlanResponse)
@router.post("/generate", response_model=WeeklyMealPlanResponse)
async def generate_weekly_plan(
    payload: Optional[MealPlanGenerateRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Generates and persists a 5-day Monday-Friday meal plan.
    Filters recipes by household dietary restrictions (e.g. gluten-free, dairy-free)
    and leverages pgvector semantic similarity for preference matching.
    """
    # 1. Determine target_days dynamically (defaults to standard 7-day week: Mon-Sun)
    if payload and payload.target_days:
        days = [d.strip().capitalize() for d in payload.target_days if d.strip()]
        if not days:
            days = list(DEFAULT_7_DAYS)
    elif payload and payload.days_count:
        days = list(DEFAULT_7_DAYS[:payload.days_count])
    else:
        days = list(DEFAULT_7_DAYS)

    start_date = payload.target_date if payload and payload.target_date else date.today()
    household: Optional[Household] = None
    required_tags: Set[str] = set()

    # 1. Resolve household dietary restrictions and busy schedule if household_id is provided
    busy_days_list: List[str] = []
    busy_max_prep: int = 20

    if payload and payload.household_id:
        h_stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == payload.household_id)
        h_res = await db.execute(h_stmt)
        household = h_res.scalar_one_or_none()
        if household and household.dietary_preferences:
            for pref in household.dietary_preferences:
                required_tags.add(pref.preference_name.lower())
        if household and household.busy_days:
            busy_days_list = household.busy_days
        if household and household.busy_max_prep_minutes is not None:
            busy_max_prep = household.busy_max_prep_minutes

    # Override busy weeknights and prep ceiling from payload if explicitly provided
    if payload and payload.busy_days is not None:
        busy_days_list = payload.busy_days
    if payload and payload.busy_max_prep_minutes is not None:
        busy_max_prep = payload.busy_max_prep_minutes

    busy_days_set = {d.strip().capitalize() for d in busy_days_list}

    # Merge explicit dietary tags from payload
    if payload and payload.dietary_tags:
        for tag in payload.dietary_tags:
            required_tags.add(tag.lower())

    # 2. Fetch recipes: strictly restrict to this household's recipe book if household is known
    if household:
        rec_stmt = (
            select(Recipe)
            .join(HouseholdRecipe, Recipe.recipe_id == HouseholdRecipe.recipe_id)
            .where(HouseholdRecipe.household_id == household.household_id)
            .options(selectinload(Recipe.dietary_preferences))
        )
        result = await db.execute(rec_stmt)
        all_recipes = result.scalars().all()
        # If household has no recipes in their book yet, fall back to baseline catalog
        if not all_recipes:
            rec_stmt = select(Recipe).options(selectinload(Recipe.dietary_preferences)).where(Recipe.creator_id == None)
            result = await db.execute(rec_stmt)
            all_recipes = result.scalars().all()
    else:
        rec_stmt = select(Recipe).options(selectinload(Recipe.dietary_preferences))
        result = await db.execute(rec_stmt)
        all_recipes = result.scalars().all()

    if not all_recipes:
        raise HTTPException(status_code=404, detail="No recipes found in database. Please run the seeder script.")

    # 3. Filter candidates strictly by dietary restrictions
    if required_tags:
        matching_candidates = [
            r for r in all_recipes
            if required_tags.issubset({p.preference_name.lower() for p in r.dietary_preferences})
        ]
        # If strict matching has fewer recipes than active days, fall back to ranking by most matched tags
        if len(matching_candidates) < len(days):
            matching_candidates = sorted(
                all_recipes,
                key=lambda r: len(required_tags.intersection({p.preference_name.lower() for p in r.dietary_preferences})),
                reverse=True
            )
    else:
        matching_candidates = list(all_recipes)

    # 4. Leverage pgvector similarity for preference matching
    # Construct household preference embedding query text
    if household:
        tag_desc = f"with dietary restrictions: {', '.join(sorted(required_tags))}" if required_tags else "healthy family dinners"
        pref_query = f"Delicious chef-crafted dinner recipes for {household.household_name} {tag_desc}. Balanced, wholesome, high-quality meals."
    elif required_tags:
        pref_query = f"Wholesome chef-crafted dinner meals respecting dietary restrictions: {', '.join(sorted(required_tags))}."
    else:
        pref_query = "Diverse, delicious, chef-crafted dinner recipes for weekly meal plan."

    pref_vec = await get_embedding(pref_query)
    vec_str = "[" + ",".join(str(float(x)) for x in pref_vec) + "]"

    cand_ids = [r.recipe_id for r in matching_candidates]
    stmt_ranked = (
        select(Recipe)
        .options(selectinload(Recipe.dietary_preferences))
        .where(Recipe.recipe_id.in_(cand_ids))
        .where(Recipe.embedding.isnot(None))
        .order_by(text("embedding <=> CAST(:vec AS vector)"))
        .params(vec=vec_str)
    )
    ranked_res = await db.execute(stmt_ranked)
    ranked_pool = ranked_res.scalars().all()

    if not ranked_pool:
        ranked_pool = list(matching_candidates)

    # Day-by-Day Generation respecting busy days & prep time ceilings
    assigned_recipes: Dict[str, Recipe] = {}
    fallback_map: Dict[str, bool] = {}
    used_recipe_ids: Set[UUID] = set()

    # Pass 1: Assign busy days first to ensure low prep time constraint is prioritized
    for day in days:
        if day.capitalize() in busy_days_set:
            busy_candidates = [
                r for r in matching_candidates
                if r.prep_time_minutes is not None and r.prep_time_minutes <= busy_max_prep
            ]

            unassigned = [r for r in ranked_pool if r in busy_candidates and r.recipe_id not in used_recipe_ids]
            if not unassigned:
                unassigned = [r for r in busy_candidates if r.recipe_id not in used_recipe_ids]

            fallback_applied = False
            if unassigned:
                chosen = unassigned[0]
            elif busy_candidates:
                chosen = busy_candidates[len(used_recipe_ids) % len(busy_candidates)]
            else:
                # Fallback degradation: If zero recipes meet both dietary restrictions and prep time ceiling,
                # pick the compliant recipe with the lowest prep_time_minutes and mark fallback_applied: true.
                fallback_applied = True
                logger.warning(
                    f"No recipes match both dietary restrictions and prep time ceiling ({busy_max_prep} min) "
                    f"for busy day {day}. Gracefully falling back to recipe with lowest prep time."
                )
                pool_for_fallback = [r for r in matching_candidates if r.recipe_id not in used_recipe_ids]
                if not pool_for_fallback:
                    pool_for_fallback = matching_candidates if matching_candidates else all_recipes

                chosen = min(
                    pool_for_fallback,
                    key=lambda r: r.prep_time_minutes if r.prep_time_minutes is not None else 9999
                )
                logger.warning(
                    f"Selected fallback recipe for {day}: '{chosen.title}' with prep time {chosen.prep_time_minutes} min."
                )

            assigned_recipes[day] = chosen
            fallback_map[day] = fallback_applied
            used_recipe_ids.add(chosen.recipe_id)

    # Pass 2: Assign non-busy days from remaining ranked pool
    for day in days:
        if day.capitalize() not in busy_days_set:
            unassigned = [r for r in ranked_pool if r.recipe_id not in used_recipe_ids]
            if not unassigned:
                unassigned = [r for r in matching_candidates if r.recipe_id not in used_recipe_ids]
            if not unassigned:
                unassigned = [r for r in all_recipes if r.recipe_id not in used_recipe_ids]

            if unassigned:
                chosen = unassigned[0]
            else:
                # If compliant pool is smaller than active days, cycle through matching pool
                cycle_pool = matching_candidates if matching_candidates else all_recipes
                chosen = cycle_pool[len(used_recipe_ids) % len(cycle_pool)]

            assigned_recipes[day] = chosen
            fallback_map[day] = False
            used_recipe_ids.add(chosen.recipe_id)

    # 5. Persist MealPlan and Items
    new_plan = MealPlan(
        household_id=household.household_id if household else (payload.household_id if payload else None),
        week_start_date=start_date,
        is_locked=False
    )
    db.add(new_plan)
    await db.flush()

    for day in days:
        chosen_recipe = assigned_recipes[day]
        item = MealPlanItem(
            meal_plan_id=new_plan.plan_id,
            recipe_id=chosen_recipe.recipe_id,
            day_of_week=day,
            is_modified=False,
            fallback_applied=fallback_map.get(day, False)
        )
        db.add(item)

    await db.commit()

    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.plan_id == new_plan.plan_id)
    )
    res = await db.execute(stmt)
    full_plan = res.scalar_one()

    return format_plan_response(full_plan)

@router.get("/household/{household_id}/latest", response_model=WeeklyMealPlanResponse)
async def get_latest_household_meal_plan(household_id: UUID, db: AsyncSession = Depends(get_db)):
    """Fetch the latest active meal plan for a household."""
    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.household_id == household_id)
        .order_by(MealPlan.created_at.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No meal plan found for this household.")
    return format_plan_response(plan)

@router.get("/{plan_id}", response_model=WeeklyMealPlanResponse)
async def get_meal_plan(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    """Fetch an existing meal plan by ID."""
    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.plan_id == plan_id)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail=f"Meal plan {plan_id} not found.")

    return format_plan_response(plan)

@router.post("/{plan_id}/swap", response_model=WeeklyMealPlanResponse)
async def swap_meal(
    plan_id: UUID,
    payload: MealPlanSwapRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Swaps a meal on a given day.
    If new_recipe_id is provided, swaps to that recipe.
    Otherwise, intelligently uses pgvector cosine distance to find the nearest
    semantic alternative recipe respecting household dietary restrictions.
    """
    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.plan_id == plan_id)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail=f"Meal plan {plan_id} not found.")

    if plan.is_locked:
        raise HTTPException(status_code=400, detail="Cannot swap meals in a locked meal plan. Unlock first.")

    target_day = payload.day_of_week.capitalize()
    target_item = next((it for it in plan.items if it.day_of_week.capitalize() == target_day), None)

    if not target_item:
        raise HTTPException(status_code=404, detail=f"Day '{payload.day_of_week}' not found in meal plan.")

    scheduled_ids = [it.recipe_id for it in plan.items if it.recipe_id]

    # Load household dietary restrictions & busy weeknight schedule if available
    household: Optional[Household] = None
    household_tags: Set[str] = set()
    busy_days_set: Set[str] = set()
    busy_max_prep: int = 20

    if plan.household_id:
        h_stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == plan.household_id)
        h_res = await db.execute(h_stmt)
        household = h_res.scalar_one_or_none()
        if household:
            if household.dietary_preferences:
                household_tags = {p.preference_name.lower() for p in household.dietary_preferences}
            if household.busy_days:
                busy_days_set = {d.strip().capitalize() for d in household.busy_days}
            if household.busy_max_prep_minutes is not None:
                busy_max_prep = household.busy_max_prep_minutes

    is_busy_day = target_day in busy_days_set

    if payload.new_recipe_id:
        rec_stmt = select(Recipe).where(Recipe.recipe_id == payload.new_recipe_id)
        rec_res = await db.execute(rec_stmt)
        new_recipe = rec_res.scalar_one_or_none()
        if not new_recipe:
            raise HTTPException(status_code=404, detail=f"Recipe {payload.new_recipe_id} not found.")

        # Invariant: preserve household recipe book data isolation
        if plan.household_id:
            iso_stmt = select(HouseholdRecipe).where(
                HouseholdRecipe.household_id == plan.household_id,
                HouseholdRecipe.recipe_id == new_recipe.recipe_id
            )
            iso_res = await db.execute(iso_stmt)
            if not iso_res.scalar_one_or_none():
                if not new_recipe.is_public and new_recipe.household_id != plan.household_id:
                    raise HTTPException(status_code=403, detail="Recipe does not belong to household recipe book.")

        # Invariant: enforce prep time ceiling on busy weeknights
        if is_busy_day:
            if new_recipe.prep_time_minutes is not None and new_recipe.prep_time_minutes > busy_max_prep:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot swap meal on {target_day}: recipe prep time ({new_recipe.prep_time_minutes}m) exceeds the busy night ceiling ({busy_max_prep}m)."
                )

        target_item.recipe = new_recipe
        target_item.is_modified = True
        target_item.fallback_applied = False
    else:
        current_recipe = target_item.recipe

        # Query candidate recipes strictly from household's recipe book
        if plan.household_id:
            cand_stmt = (
                select(Recipe)
                .join(HouseholdRecipe, Recipe.recipe_id == HouseholdRecipe.recipe_id)
                .where(HouseholdRecipe.household_id == plan.household_id)
                .options(selectinload(Recipe.dietary_preferences))
            )
            all_rec_res = await db.execute(cand_stmt)
            candidates = all_rec_res.scalars().all()
            if not candidates:
                all_rec_res = await db.execute(select(Recipe).options(selectinload(Recipe.dietary_preferences)))
                candidates = all_rec_res.scalars().all()
        else:
            all_rec_res = await db.execute(select(Recipe).options(selectinload(Recipe.dietary_preferences)))
            candidates = all_rec_res.scalars().all()

        available_candidates = [r for r in candidates if r.recipe_id not in scheduled_ids]
        if not available_candidates:
            available_candidates = [r for r in candidates if r.recipe_id != target_item.recipe_id]
        if not available_candidates:
            available_candidates = candidates

        # Filter by household dietary restrictions
        dietary_matching = [
            r for r in available_candidates
            if household_tags.issubset({p.preference_name.lower() for p in r.dietary_preferences})
        ]
        if not dietary_matching:
            dietary_matching = available_candidates

        alt: Optional[Recipe] = None
        swap_fallback_applied = False

        if is_busy_day:
            busy_matching = [
                r for r in dietary_matching
                if r.prep_time_minutes is not None and r.prep_time_minutes <= busy_max_prep
            ]

            if busy_matching:
                if payload.use_vector_similarity and current_recipe and current_recipe.embedding is not None:
                    vec_list = [float(x) for x in current_recipe.embedding]
                    vec_str = "[" + ",".join(str(x) for x in vec_list) + "]"
                    busy_ids = [r.recipe_id for r in busy_matching]
                    stmt_alt = (
                        select(Recipe)
                        .where(Recipe.recipe_id.in_(busy_ids))
                        .where(Recipe.embedding.isnot(None))
                        .order_by(text("embedding <=> CAST(:vec AS vector)"))
                        .params(vec=vec_str)
                        .limit(1)
                    )
                    sim_res = await db.execute(stmt_alt)
                    alt = sim_res.scalar_one_or_none()

                if not alt:
                    alt = random.choice(busy_matching)
            else:
                # Graceful fallback: if no recipes match both dietary restrictions and prep time ceiling,
                # pick the recipe with the lowest prep_time_minutes and log a fallback warning.
                swap_fallback_applied = True
                logger.warning(
                    f"No recipes match both dietary restrictions and prep time ceiling ({busy_max_prep} min) "
                    f"for swap on busy day {target_day}. Gracefully falling back to recipe with lowest prep time."
                )
                fallback_pool = dietary_matching if dietary_matching else available_candidates
                alt = min(
                    fallback_pool,
                    key=lambda r: r.prep_time_minutes if r.prep_time_minutes is not None else 9999
                )
                logger.warning(
                    f"Selected fallback recipe for {target_day} swap: '{alt.title}' with prep time {alt.prep_time_minutes} min."
                )
        else:
            if payload.use_vector_similarity and current_recipe and current_recipe.embedding is not None:
                vec_list = [float(x) for x in current_recipe.embedding]
                vec_str = "[" + ",".join(str(x) for x in vec_list) + "]"
                eligible_ids = [r.recipe_id for r in dietary_matching]
                if eligible_ids:
                    stmt_alt = (
                        select(Recipe)
                        .where(Recipe.recipe_id.in_(eligible_ids))
                        .where(Recipe.embedding.isnot(None))
                        .order_by(text("embedding <=> CAST(:vec AS vector)"))
                        .params(vec=vec_str)
                        .limit(1)
                    )
                    sim_res = await db.execute(stmt_alt)
                    alt = sim_res.scalar_one_or_none()

            if not alt:
                alt = random.choice(dietary_matching if dietary_matching else available_candidates)

        if alt:
            target_item.recipe = alt
            target_item.is_modified = True
            target_item.fallback_applied = swap_fallback_applied

    await db.commit()
    db.expire_all()

    res = await db.execute(stmt)
    full_plan = res.scalar_one()
    return format_plan_response(full_plan)

@router.post("/{plan_id}/lock", response_model=WeeklyMealPlanResponse)
async def lock_meal_plan(
    plan_id: UUID,
    payload: Optional[MealPlanLockRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Locks or unlocks a weekly meal plan.
    Locking freezes the meal plan so ingredients can be finalized for grocery procurement.
    """
    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.plan_id == plan_id)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail=f"Meal plan {plan_id} not found.")

    should_lock = payload.lock if payload is not None else True
    plan.is_locked = should_lock
    await db.commit()

    res = await db.execute(stmt)
    full_plan = res.scalar_one()
    return format_plan_response(full_plan)

@router.post("/{plan_id}/shuffle", response_model=WeeklyMealPlanResponse)
async def shuffle_meal_plan(
    plan_id: UUID,
    payload: Optional[MealPlanShuffleRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Shuffles meal plan recipes across available days.
    Respects locked status, busy night prep time ceilings, and optionally preserves manually modified slots.
    """
    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.plan_id == plan_id)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail=f"Meal plan {plan_id} not found.")

    if plan.is_locked:
        raise HTTPException(status_code=400, detail="Cannot shuffle a locked meal plan. Unlock first.")

    preserve_modified = payload.preserve_modified if payload else True

    household: Optional[Household] = None
    busy_days_set: Set[str] = set()
    busy_max_prep: int = 20

    if plan.household_id:
        h_res = await db.execute(select(Household).where(Household.household_id == plan.household_id))
        household = h_res.scalar_one_or_none()
        if household:
            if household.busy_days:
                busy_days_set = {d.strip().capitalize() for d in household.busy_days}
            if household.busy_max_prep_minutes is not None:
                busy_max_prep = household.busy_max_prep_minutes

    if plan.household_id:
        cand_stmt = (
            select(Recipe)
            .join(HouseholdRecipe, Recipe.recipe_id == HouseholdRecipe.recipe_id)
            .where(HouseholdRecipe.household_id == plan.household_id)
        )
        all_res = await db.execute(cand_stmt)
        all_recipes = all_res.scalars().all()
        if not all_recipes:
            all_res = await db.execute(select(Recipe))
            all_recipes = all_res.scalars().all()
    else:
        all_res = await db.execute(select(Recipe))
        all_recipes = all_res.scalars().all()

    assigned_ids = {it.recipe_id for it in plan.items if it.is_modified and preserve_modified}
    candidate_pool = [r for r in all_recipes if r.recipe_id not in assigned_ids]
    random.shuffle(candidate_pool)

    # Assign busy days first
    for item in plan.items:
        if preserve_modified and item.is_modified:
            continue
        if item.day_of_week.capitalize() in busy_days_set:
            busy_cands = [r for r in candidate_pool if r.prep_time_minutes is not None and r.prep_time_minutes <= busy_max_prep]
            if busy_cands:
                chosen = busy_cands[0]
                item.fallback_applied = False
            elif candidate_pool:
                chosen = min(candidate_pool, key=lambda r: r.prep_time_minutes if r.prep_time_minutes is not None else 9999)
                item.fallback_applied = True
            else:
                chosen = all_recipes[0]
                item.fallback_applied = False
            item.recipe = chosen
            if chosen in candidate_pool:
                candidate_pool.remove(chosen)

    # Assign non-busy days
    for item in plan.items:
        if preserve_modified and item.is_modified:
            continue
        if item.day_of_week.capitalize() not in busy_days_set:
            if candidate_pool:
                item.recipe = candidate_pool.pop(0)
            else:
                item.recipe = all_recipes[0]
            item.fallback_applied = False

    await db.commit()
    db.expire_all()

    res = await db.execute(stmt)
    full_plan = res.scalar_one()
    return format_plan_response(full_plan)

@router.post("/{plan_id}/add-day", response_model=WeeklyMealPlanResponse)
async def add_day_to_meal_plan(
    plan_id: UUID,
    payload: MealPlanAddDayRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Dynamically adds a day to an active draft meal plan.
    Enforces that locked plans cannot be modified (HTTP 400).
    Respects household dietary restrictions and busy-night prep time ceilings.
    """
    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.plan_id == plan_id)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail=f"Meal plan {plan_id} not found.")

    if plan.is_locked:
        raise HTTPException(status_code=400, detail="Cannot add day to a locked meal plan. Unlock first.")

    day = payload.day_of_week.strip().capitalize()
    existing_days = {it.day_of_week.capitalize() for it in plan.items}
    if day in existing_days:
        raise HTTPException(status_code=400, detail=f"Day '{day}' is already scheduled in this meal plan.")

    household: Optional[Household] = None
    household_tags: Set[str] = set()
    busy_days_set: Set[str] = set()
    busy_max_prep: int = 20

    if plan.household_id:
        h_stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == plan.household_id)
        h_res = await db.execute(h_stmt)
        household = h_res.scalar_one_or_none()
        if household:
            if household.dietary_preferences:
                household_tags = {p.preference_name.lower() for p in household.dietary_preferences}
            if household.busy_days:
                busy_days_set = {d.strip().capitalize() for d in household.busy_days}
            if household.busy_max_prep_minutes is not None:
                busy_max_prep = household.busy_max_prep_minutes

    is_busy_day = day in busy_days_set
    fallback_applied = False
    chosen_recipe: Optional[Recipe] = None

    if payload.recipe_id:
        rec_stmt = select(Recipe).where(Recipe.recipe_id == payload.recipe_id)
        rec_res = await db.execute(rec_stmt)
        chosen_recipe = rec_res.scalar_one_or_none()
        if not chosen_recipe:
            raise HTTPException(status_code=404, detail=f"Recipe {payload.recipe_id} not found.")

        if plan.household_id:
            iso_stmt = select(HouseholdRecipe).where(
                HouseholdRecipe.household_id == plan.household_id,
                HouseholdRecipe.recipe_id == chosen_recipe.recipe_id
            )
            iso_res = await db.execute(iso_stmt)
            if not iso_res.scalar_one_or_none():
                if not chosen_recipe.is_public and chosen_recipe.household_id != plan.household_id:
                    raise HTTPException(status_code=403, detail="Recipe does not belong to household recipe book.")

        if is_busy_day:
            if chosen_recipe.prep_time_minutes is not None and chosen_recipe.prep_time_minutes > busy_max_prep:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot assign '{chosen_recipe.title}' to busy day {day}: prep time ({chosen_recipe.prep_time_minutes}m) exceeds ceiling ({busy_max_prep}m)."
                )
    else:
        if plan.household_id:
            cand_stmt = (
                select(Recipe)
                .join(HouseholdRecipe, Recipe.recipe_id == HouseholdRecipe.recipe_id)
                .where(HouseholdRecipe.household_id == plan.household_id)
                .options(selectinload(Recipe.dietary_preferences))
            )
            cand_res = await db.execute(cand_stmt)
            candidates = cand_res.scalars().all()
            if not candidates:
                cand_res = await db.execute(select(Recipe).options(selectinload(Recipe.dietary_preferences)))
                candidates = cand_res.scalars().all()
        else:
            cand_res = await db.execute(select(Recipe).options(selectinload(Recipe.dietary_preferences)))
            candidates = cand_res.scalars().all()

        scheduled_ids = {it.recipe_id for it in plan.items if it.recipe_id}
        available = [r for r in candidates if r.recipe_id not in scheduled_ids]
        if not available:
            available = candidates

        dietary_pool = [
            r for r in available
            if household_tags.issubset({p.preference_name.lower() for p in r.dietary_preferences})
        ]
        if not dietary_pool:
            dietary_pool = available

        if is_busy_day:
            busy_pool = [
                r for r in dietary_pool
                if r.prep_time_minutes is not None and r.prep_time_minutes <= busy_max_prep
            ]
            if busy_pool:
                chosen_recipe = busy_pool[0]
            else:
                fallback_applied = True
                logger.warning(
                    f"No recipes match both dietary restrictions and prep time ceiling ({busy_max_prep} min) "
                    f"for new day {day}. Gracefully falling back to recipe with lowest prep time."
                )
                chosen_recipe = min(
                    dietary_pool,
                    key=lambda r: r.prep_time_minutes if r.prep_time_minutes is not None else 9999
                )
        else:
            chosen_recipe = dietary_pool[0]

    new_item = MealPlanItem(
        meal_plan_id=plan.plan_id,
        recipe_id=chosen_recipe.recipe_id,
        day_of_week=day,
        is_modified=True,
        fallback_applied=fallback_applied
    )
    db.add(new_item)
    await db.commit()
    db.expire_all()

    res = await db.execute(stmt)
    full_plan = res.scalar_one()
    return format_plan_response(full_plan)

@router.post("/{plan_id}/subtract-day", response_model=WeeklyMealPlanResponse)
@router.post("/{plan_id}/remove-day", response_model=WeeklyMealPlanResponse)
async def subtract_day_from_meal_plan(
    plan_id: UUID,
    payload: MealPlanSubtractDayRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Dynamically removes a day from an active draft meal plan.
    Enforces that locked plans cannot be modified (HTTP 400).
    """
    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.plan_id == plan_id)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail=f"Meal plan {plan_id} not found.")

    if plan.is_locked:
        raise HTTPException(status_code=400, detail="Cannot modify a locked meal plan. Unlock first.")

    target_day = payload.day_of_week.strip().capitalize()
    target_item = next((it for it in plan.items if it.day_of_week.capitalize() == target_day), None)

    if not target_item:
        raise HTTPException(status_code=404, detail=f"Day '{payload.day_of_week}' not found in meal plan.")

    if len(plan.items) <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove all days from meal plan. At least 1 day must remain.")

    await db.delete(target_item)
    await db.commit()
    db.expire_all()

    res = await db.execute(stmt)
    full_plan = res.scalar_one()
    return format_plan_response(full_plan)

@router.delete("/{plan_id}/days/{day_of_week}", response_model=WeeklyMealPlanResponse)
async def delete_day_from_meal_plan(
    plan_id: UUID,
    day_of_week: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a day from an active draft meal plan by path parameter.
    Enforces that locked plans cannot be modified (HTTP 400).
    """
    return await subtract_day_from_meal_plan(plan_id, MealPlanSubtractDayRequest(day_of_week=day_of_week), db)

@router.post("/{plan_id}/days", response_model=WeeklyMealPlanResponse)
@router.put("/{plan_id}/days", response_model=WeeklyMealPlanResponse)
async def update_meal_plan_days(
    plan_id: UUID,
    payload: MealPlanDaysUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Dynamically adjusts the days scheduled in an active draft meal plan.
    Adds missing days and removes excluded days.
    Enforces that locked plans cannot be modified (HTTP 400).
    """
    stmt = (
        select(MealPlan)
        .options(selectinload(MealPlan.items).selectinload(MealPlanItem.recipe))
        .where(MealPlan.plan_id == plan_id)
    )
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail=f"Meal plan {plan_id} not found.")

    if plan.is_locked:
        raise HTTPException(status_code=400, detail="Cannot modify days in a locked meal plan. Unlock first.")

    desired_days = [d.strip().capitalize() for d in payload.target_days if d.strip()]
    if not desired_days:
        raise HTTPException(status_code=400, detail="At least 1 day must be specified.")

    current_days_map = {it.day_of_week.capitalize(): it for it in plan.items}

    # 1. Remove days not in desired_days
    for d, it in list(current_days_map.items()):
        if d not in desired_days:
            await db.delete(it)

    # 2. Add days in desired_days not currently in plan
    missing_days = [d for d in desired_days if d not in current_days_map]
    if missing_days:
        household: Optional[Household] = None
        household_tags: Set[str] = set()
        busy_days_set: Set[str] = set()
        busy_max_prep: int = 20

        if plan.household_id:
            h_stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == plan.household_id)
            h_res = await db.execute(h_stmt)
            household = h_res.scalar_one_or_none()
            if household:
                if household.dietary_preferences:
                    household_tags = {p.preference_name.lower() for p in household.dietary_preferences}
                if household.busy_days:
                    busy_days_set = {d.strip().capitalize() for d in household.busy_days}
                if household.busy_max_prep_minutes is not None:
                    busy_max_prep = household.busy_max_prep_minutes

        if plan.household_id:
            cand_stmt = (
                select(Recipe)
                .join(HouseholdRecipe, Recipe.recipe_id == HouseholdRecipe.recipe_id)
                .where(HouseholdRecipe.household_id == plan.household_id)
                .options(selectinload(Recipe.dietary_preferences))
            )
            cand_res = await db.execute(cand_stmt)
            candidates = cand_res.scalars().all()
            if not candidates:
                cand_res = await db.execute(select(Recipe).options(selectinload(Recipe.dietary_preferences)))
                candidates = cand_res.scalars().all()
        else:
            cand_res = await db.execute(select(Recipe).options(selectinload(Recipe.dietary_preferences)))
            candidates = cand_res.scalars().all()

        scheduled_ids = {it.recipe_id for it in plan.items if it.day_of_week.capitalize() in desired_days and it.recipe_id}

        for day in missing_days:
            is_busy = day in busy_days_set
            available = [r for r in candidates if r.recipe_id not in scheduled_ids]
            if not available:
                available = candidates
            dietary_pool = [
                r for r in available
                if household_tags.issubset({p.preference_name.lower() for p in r.dietary_preferences})
            ]
            if not dietary_pool:
                dietary_pool = available

            fallback_applied = False
            if is_busy:
                busy_pool = [r for r in dietary_pool if r.prep_time_minutes is not None and r.prep_time_minutes <= busy_max_prep]
                if busy_pool:
                    chosen = busy_pool[0]
                else:
                    fallback_applied = True
                    chosen = min(dietary_pool, key=lambda r: r.prep_time_minutes if r.prep_time_minutes is not None else 9999)
            else:
                chosen = dietary_pool[0]

            scheduled_ids.add(chosen.recipe_id)
            new_item = MealPlanItem(
                meal_plan_id=plan.plan_id,
                recipe_id=chosen.recipe_id,
                day_of_week=day,
                is_modified=True,
                fallback_applied=fallback_applied
            )
            db.add(new_item)

    await db.commit()
    db.expire_all()
    res = await db.execute(stmt)
    full_plan = res.scalar_one()
    return format_plan_response(full_plan)

@router.get("/{plan_id}/grocery-list")
async def get_plan_grocery_list(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Multi-store grocery aggregation endpoint.
    Extracts required ingredients from the weekly plan and returns price comparisons
    and availability metrics across targeted local retailers (Aldi, Walmart, Meijer, Amazon).
    """
    return await aggregate_groceries_for_plan(plan_id, db)
