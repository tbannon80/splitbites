import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database.session import Base
from app.models import Recipe, Ingredient, RecipeIngredient, DietaryPreference

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@splitbites-postgres:5432/splitbites")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

SAMPLE_RECIPES = [
    {
        "title": "Classic Smash Burgers",
        "description": "Crispy edges with melted cheese on brioche buns.",
        "prep_time_minutes": 20,
        "difficulty_level": "quick",
        "instructions": [{"step": 1, "text": "Heat skillet to high."}, {"step": 2, "text": "Press beef balls flat, season, flip, and add cheese."}],
        "ingredients": [
            {"name": "Ground Beef", "quantity": 1.0, "unit": "lbs", "default_unit": "lbs"},
            {"name": "Brioche Buns", "quantity": 4.0, "unit": "count", "default_unit": "count"},
            {"name": "Cheddar Cheese", "quantity": 4.0, "unit": "slices", "default_unit": "slices"}
        ],
        "tags": ["quick"]
    },
    {
        "title": "Chicken & Broccoli Stir-Fry",
        "description": "Tender chicken breast tossed with fresh broccoli and garlic soy sauce.",
        "prep_time_minutes": 25,
        "difficulty_level": "medium",
        "instructions": [{"step": 1, "text": "Sauté chicken chunks until golden."}, {"step": 2, "text": "Add broccoli and stir-fry sauce, simmer until tender."}],
        "ingredients": [
            {"name": "Chicken Breast", "quantity": 1.0, "unit": "lbs", "default_unit": "lbs"},
            {"name": "Broccoli", "quantity": 2.0, "unit": "heads", "default_unit": "heads"},
            {"name": "Soy Sauce", "quantity": 0.25, "unit": "cups", "default_unit": "cups"}
        ],
        "tags": ["gluten-free", "quick"]
    }
]

async def seed_data():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            pref_gluten = DietaryPreference(preference_name="gluten-free")
            pref_quick = DietaryPreference(preference_name="quick")
            session.add_all([pref_gluten, pref_quick])
            await session.flush()

            for r_data in SAMPLE_RECIPES:
                recipe = Recipe(
                    title=r_data["title"],
                    description=r_data["description"],
                    prep_time_minutes=r_data["prep_time_minutes"],
                    difficulty_level=r_data["difficulty_level"],
                    instructions=r_data["instructions"],
                    is_public=True
                )
                session.add(recipe)
                await session.flush()

                for ing_data in r_data["ingredients"]:
                    ingredient = Ingredient(
                        ingredient_name=ing_data["name"],
                        default_unit=ing_data["default_unit"]
                    )
                    session.add(ingredient)
                    await session.flush()

                    ri = RecipeIngredient(
                        recipe_id=recipe.recipe_id,
                        ingredient_id=ingredient.ingredient_id,
                        quantity=ing_data["quantity"],
                        unit=ing_data["unit"]
                    )
                    session.add(ri)
        print("Database successfully seeded with starter recipes!")

if __name__ == "__main__":
    asyncio.run(seed_data())
