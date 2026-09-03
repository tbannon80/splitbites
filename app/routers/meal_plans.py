import random
from datetime import date
from typing import Optional, List, Dict, Set
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.database.session import AsyncSessionLocal
from app.models import MealPlan, MealPlanItem, Recipe, Household, DietaryPreference, HouseholdRecipe
from app.schemas.meal_plan import (
    MealPlanGenerateRequest,
    MealPlanSwapRequest,
    MealPlanLockRequest,
    MealPlanShuffleRequest,
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
                "is_modified": item.is_modified
            }
    return {
        "status": "success",
        "plan_id": str(plan.plan_id),
        "plan_type": "Monday-Friday Workweek",
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
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    start_date = payload.target_date if payload and payload.target_date else date.today()
    household: Optional[Household] = None
    required_tags: Set[str] = set()

    # 1. Resolve household dietary restrictions if household_id is provided
    if payload and payload.household_id:
        h_stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == payload.household_id)
        h_res = await db.execute(h_stmt)
        household = h_res.scalar_one_or_none()
        if household and household.dietary_preferences:
            for pref in household.dietary_preferences:
                required_tags.add(pref.preference_name.lower())

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
        # If strict matching has fewer than 5 recipes, fall back to ranking by most matched tags
        if len(matching_candidates) < 5:
            matching_candidates = sorted(
                all_recipes,
                key=lambda r: len(required_tags.intersection({p.preference_name.lower() for p in r.dietary_preferences})),
                reverse=True
            )[:15]
    else:
        matching_candidates = all_recipes

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
        ranked_pool = matching_candidates

    # Select top 5 distinct meals for the week
    selected_recipes = list(ranked_pool[:5])
    while len(selected_recipes) < 5:
        for cand in matching_candidates:
            if cand not in selected_recipes:
                selected_recipes.append(cand)
            if len(selected_recipes) == 5:
                break
        if len(selected_recipes) < 5:
            selected_recipes.append(matching_candidates[0])

    # 5. Persist MealPlan and Items
    new_plan = MealPlan(
        household_id=household.household_id if household else (payload.household_id if payload else None),
        week_start_date=start_date,
        is_locked=False
    )
    db.add(new_plan)
    await db.flush()

    for i, day in enumerate(days):
        chosen_recipe = selected_recipes[i]
        item = MealPlanItem(
            meal_plan_id=new_plan.plan_id,
            recipe_id=chosen_recipe.recipe_id,
            day_of_week=day,
            is_modified=False
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

    # Load household dietary restrictions if available
    household_tags: Set[str] = set()
    if plan.household_id:
        h_stmt = select(Household).options(selectinload(Household.dietary_preferences)).where(Household.household_id == plan.household_id)
        h_res = await db.execute(h_stmt)
        h = h_res.scalar_one_or_none()
        if h and h.dietary_preferences:
            household_tags = {p.preference_name.lower() for p in h.dietary_preferences}

    if payload.new_recipe_id:
        rec_stmt = select(Recipe).where(Recipe.recipe_id == payload.new_recipe_id)
        rec_res = await db.execute(rec_stmt)
        new_recipe = rec_res.scalar_one_or_none()
        if not new_recipe:
            raise HTTPException(status_code=404, detail=f"Recipe {payload.new_recipe_id} not found.")
        target_item.recipe = new_recipe
        target_item.is_modified = True
    else:
        current_recipe = target_item.recipe
        if payload.use_vector_similarity and current_recipe and current_recipe.embedding is not None:
            vec_list = [float(x) for x in current_recipe.embedding]
            vec_str = "[" + ",".join(str(x) for x in vec_list) + "]"

            # Query candidate recipes from this household's recipe book if available
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
            eligible_ids = [
                r.recipe_id for r in candidates
                if r.recipe_id not in scheduled_ids and household_tags.issubset({p.preference_name.lower() for p in r.dietary_preferences})
            ]

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
            else:
                # Fallback without dietary filter if too strict
                stmt_alt = (
                    select(Recipe)
                    .where(~Recipe.recipe_id.in_(scheduled_ids))
                    .where(Recipe.embedding.isnot(None))
                    .order_by(text("embedding <=> CAST(:vec AS vector)"))
                    .params(vec=vec_str)
                    .limit(1)
                )
                sim_res = await db.execute(stmt_alt)
                alt = sim_res.scalar_one_or_none()

            if alt:
                target_item.recipe = alt
                target_item.is_modified = True
        else:
            alt_res = await db.execute(select(Recipe).where(~Recipe.recipe_id.in_(scheduled_ids)))
            available = alt_res.scalars().all()
            if available:
                chosen = random.choice(available)
                target_item.recipe = chosen
                target_item.is_modified = True

    await db.commit()

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
    Respects locked status and optionally preserves manually modified slots.
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

    cand_idx = 0
    for item in plan.items:
        if preserve_modified and item.is_modified:
            continue
        if cand_idx < len(candidate_pool):
            item.recipe = candidate_pool[cand_idx]
            cand_idx += 1

    await db.commit()

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
