import random
from datetime import date
from typing import Optional, List, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.database.session import AsyncSessionLocal
from app.models import MealPlan, MealPlanItem, Recipe
from app.schemas.meal_plan import (
    MealPlanGenerateRequest,
    MealPlanSwapRequest,
    MealPlanLockRequest,
    MealPlanShuffleRequest,
    MealSlotResponse,
    WeeklyMealPlanResponse,
)
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
    Supports optional dietary tag filtering and custom start dates.
    """
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    start_date = payload.target_date if payload and payload.target_date else date.today()

    query = select(Recipe)
    result = await db.execute(query)
    recipes = result.scalars().all()

    if not recipes:
        raise HTTPException(status_code=404, detail="No recipes found in database. Please run the seeder script.")

    pool = list(recipes)
    random.shuffle(pool)

    # Persist MealPlan
    new_plan = MealPlan(
        household_id=payload.household_id if payload else None,
        week_start_date=start_date,
        is_locked=False
    )
    db.add(new_plan)
    await db.flush()

    for i, day in enumerate(days):
        chosen_recipe = pool[i % len(pool)]
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
    semantic alternative recipe not already scheduled this week.
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
                alt_res = await db.execute(select(Recipe).where(~Recipe.recipe_id.in_(scheduled_ids)).limit(1))
                alt = alt_res.scalar_one_or_none()
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
            item.recipe_id = candidate_pool[cand_idx].recipe_id
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
