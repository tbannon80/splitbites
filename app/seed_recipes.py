import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, Recipe

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://secondbrain:secondbrainpass@localhost:5432/secondbrain')

STARTER_RECIPES = [
    {
        'title': 'Sheet Pan Chicken and Broccoli',
        'description': 'Quick weeknight chicken breasts roasted with fresh broccoli florets and garlic olive oil.',
        'prep_time_minutes': 25,
        'difficulty': 'easy',
        'dietary_tags': ['gluten-free', 'dairy-free', 'high-protein'],
        'ingredients': ['chicken breasts', 'broccoli florets', 'olive oil', 'garlic powder', 'salt', 'black pepper'],
        'instructions': 'Preheat oven to 400°F (200°C). Toss chicken and broccoli with olive oil and seasonings on a sheet pan. Roast for 20-25 minutes until chicken is cooked through.'
    },
    {
        'title': 'Quick Turkey Burgers',
        'description': 'Juicy lean turkey patties pan-seared and served with lettuce, tomato, and avocado.',
        'prep_time_minutes': 20,
        'difficulty': 'easy',
        'dietary_tags': ['high-protein', 'dairy-free'],
        'ingredients': ['ground turkey', 'salt', 'black pepper', 'garlic powder', 'hamburger buns', 'lettuce', 'tomato', 'avocado'],
        'instructions': 'Season ground turkey and form into patties. Cook in a skillet over medium-high heat for 5-6 minutes per side. Serve on buns with desired toppings.'
    },
    {
        'title': '15-Minute Vegetarian Pasta',
        'description': 'Fast penne pasta tossed with cherry tomatoes, fresh basil, garlic, and parmesan cheese.',
        'prep_time_minutes': 15,
        'difficulty': 'easy',
        'dietary_tags': ['vegetarian'],
        'ingredients': ['penne pasta', 'cherry tomatoes', 'garlic', 'fresh basil', 'olive oil', 'parmesan cheese'],
        'instructions': 'Boil pasta until al dente. Sauté minced garlic and halved cherry tomatoes in olive oil. Toss pasta with the tomato mixture, fresh basil, and grated parmesan.'
    },
    {
        'title': 'Salmon Rice Bowl',
        'description': 'Pan-seared salmon fillet served over fluffy jasmine rice with cucumber slices and soy glaze.',
        'prep_time_minutes': 20,
        'difficulty': 'medium',
        'dietary_tags': ['pescatarian', 'gluten-free', 'dairy-free'],
        'ingredients': ['salmon fillet', 'jasmine rice', 'cucumber', 'soy sauce', 'honey', 'sesame oil'],
        'instructions': 'Cook jasmine rice. Pan-sear salmon skin-side down until crispy, then flip. Mix soy sauce, honey, and sesame oil to drizzle over the bowl.'
    },
    {
        'title': 'Custom Friday Pizza Night',
        'description': 'Handmade or store-bought dough topped with marinara, mozzarella, and family-favorite toppings.',
        'prep_time_minutes': 30,
        'difficulty': 'easy',
        'dietary_tags': ['vegetarian'],
        'ingredients': ['pizza dough', 'marinara sauce', 'mozzarella cheese', 'olive oil', 'optional toppings'],
        'instructions': 'Roll out pizza dough, spread marinara sauce, top with cheese and preferred toppings. Bake at 450°F (230°C) for 12-15 minutes until crust is golden.'
    }
]

async def seed_recipes():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        async with session.begin():
            for r_data in STARTER_RECIPES:
                recipe = Recipe(
                    title=r_data['title'],
                    description=r_data['description'],
                    prep_time_minutes=r_data['prep_time_minutes'],
                    difficulty=r_data['difficulty'],
                    dietary_tags=r_data['dietary_tags'],
                    ingredients=r_data['ingredients'],
                    instructions=r_data['instructions']
                )
                session.add(recipe)
        await session.commit()
    print('Starter recipe library seeded successfully.')
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(seed_recipes())
