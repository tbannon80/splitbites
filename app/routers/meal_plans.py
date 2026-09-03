from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.session import AsyncSessionLocal
from app.models.recipe import Recipe
import random

router = APIRouter(prefix="/api/meal-plans", tags=["meal-plans"])

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

@router.get("/generate")
async def generate_weekly_plan(db: AsyncSession = Depends(get_db)):
    # Query seeded recipes from the database
    result = await db.execute(select(Recipe))
    recipes = result.scalars().all()
    
    if not recipes:
        raise HTTPException(status_code=404, detail="No recipes found in database. Please run the seeder script.")
    
    # Generate a Monday-Friday draft plan
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    weekly_plan = {}
    
    pool = list(recipes)
    random.shuffle(pool)
    
    for i, day in enumerate(days):
        recipe = pool[i % len(pool)]
        weekly_plan[day] = {
            "recipe_id": str(recipe.recipe_id),
            "title": recipe.title,
            "description": recipe.description,
            "prep_time_minutes": recipe.prep_time_minutes,
            "difficulty_level": recipe.difficulty_level
        }
        
    return {
        "status": "success",
        "plan_type": "Monday-Friday Workweek",
        "meals": weekly_plan
    }
