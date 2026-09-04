import asyncio
import json
import os
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, delete, text
from app.models.recipe import Recipe, Ingredient, RecipeIngredient, DietaryPreference
from app.services.embedding import get_embedding

DEFAULT_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@splitbites-postgres:5432/splitbites"
    if os.path.exists("/.dockerenv")
    else "postgresql+asyncpg://postgres:postgres@localhost:5433/splitbites"
)

FIXTURE_CANDIDATES = [
    Path(__file__).parent / "fixtures" / "starter_recipes.json",
    Path("/app/app/database/fixtures/starter_recipes.json"),
    Path("/app/database/fixtures/starter_recipes.json"),
    Path(__file__).resolve().parents[2] / "app" / "database" / "fixtures" / "starter_recipes.json",
    Path("/home/tbannon80/splitbites/app/database/fixtures/starter_recipes.json"),
]

def load_fixtures() -> list[dict]:
    for cand in FIXTURE_CANDIDATES:
        if cand.is_file():
            print(f"[seed_recipes] Reading starter recipes fixture from: {cand}")
            with open(cand, "r", encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError(f"Could not locate starter_recipes.json in: {FIXTURE_CANDIDATES}")

async def seed_recipes(db_url: str = DEFAULT_DB_URL):
    print(f"[seed_recipes] Connecting to database: {db_url}")
    recipes_data = load_fixtures()
    print(f"[seed_recipes] Loaded {len(recipes_data)} recipes from fixture.")

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        async with session.begin():
            # 1. Cache existing dietary preferences
            pref_stmt = select(DietaryPreference)
            pref_res = await session.execute(pref_stmt)
            pref_map = {p.preference_name: p for p in pref_res.scalars().all()}

            # 2. Cache existing ingredients
            ing_stmt = select(Ingredient)
            ing_res = await session.execute(ing_stmt)
            ing_map = {i.ingredient_name: i for i in ing_res.scalars().all()}

            print(f"[seed_recipes] Processing and generating embeddings for {len(recipes_data)} recipes...")
            seeded_count = 0

            for r_data in recipes_data:
                # Generate 1536-dimensional embedding vector
                embed_text = f"{r_data['title']}. {r_data['description']}. Tags: {', '.join(r_data.get('dietary_tags', []))}."
                embedding_vector = await get_embedding(embed_text)

                # Find or create recipe
                rec_stmt = select(Recipe).where(Recipe.title == r_data["title"])
                rec_res = await session.execute(rec_stmt)
                recipe = rec_res.scalar_one_or_none()

                nutrition = r_data.get("nutrition_per_serving") or {
                    "calories": 520, "protein_g": 38.0, "carbs_g": 42.0, "fat_g": 18.0
                }

                if recipe:
                    recipe.description = r_data["description"]
                    recipe.prep_time_minutes = r_data["prep_time_minutes"]
                    recipe.difficulty_level = r_data["difficulty_level"]
                    recipe.instructions = r_data["instructions"]
                    recipe.ingredients = r_data["ingredients"]
                    recipe.nutrition_per_serving = nutrition
                    recipe.embedding = embedding_vector
                else:
                    recipe = Recipe(
                        title=r_data["title"],
                        description=r_data["description"],
                        prep_time_minutes=r_data["prep_time_minutes"],
                        difficulty_level=r_data["difficulty_level"],
                        instructions=r_data["instructions"],
                        ingredients=r_data["ingredients"],
                        nutrition_per_serving=nutrition,
                        is_public=True,
                        embedding=embedding_vector
                    )
                    session.add(recipe)
                await session.flush()

                # Handle dietary tags
                for tag in r_data.get("dietary_tags", []):
                    if tag not in pref_map:
                        new_pref = DietaryPreference(preference_name=tag)
                        session.add(new_pref)
                        await session.flush()
                        pref_map[tag] = new_pref

                    # Insert into recipe_dietary_tags
                    await session.execute(
                        text(
                            "INSERT INTO recipe_dietary_tags (recipe_id, preference_id) "
                            "VALUES (:rid, :pid) ON CONFLICT DO NOTHING"
                        ),
                        {"rid": recipe.recipe_id, "pid": pref_map[tag].preference_id}
                    )

                # Handle ingredients
                for item in r_data.get("ingredients", []):
                    ing_name = item["name"]
                    unit = item.get("unit", "units")
                    default_unit = item.get("default_unit", unit)
                    qty = item.get("quantity", 1.0)

                    if ing_name not in ing_map:
                        new_ing = Ingredient(ingredient_name=ing_name, default_unit=default_unit)
                        session.add(new_ing)
                        await session.flush()
                        ing_map[ing_name] = new_ing

                    # Insert into recipe_ingredients
                    await session.execute(
                        text(
                            "INSERT INTO recipe_ingredients (recipe_id, ingredient_id, quantity, unit) "
                            "VALUES (:rid, :iid, :qty, :unit) "
                            "ON CONFLICT (recipe_id, ingredient_id) DO UPDATE SET quantity = :qty, unit = :unit"
                        ),
                        {"rid": recipe.recipe_id, "iid": ing_map[ing_name].ingredient_id, "qty": qty, "unit": unit}
                    )

                seeded_count += 1
                if seeded_count % 10 == 0 or seeded_count == len(recipes_data):
                    print(f"  [+] Seeded {seeded_count}/{len(recipes_data)} recipes with 1536-dim embeddings...")

            # Link all baseline recipes to existing household recipe books (e.g. The Bannon Family)
            print("[seed_recipes] Linking baseline recipes to existing household recipe books...")
            await session.execute(text("""
                INSERT INTO household_recipes (household_id, recipe_id)
                SELECT h.household_id, r.recipe_id
                FROM households h
                CROSS JOIN recipes r
                WHERE r.creator_id IS NULL
                ON CONFLICT DO NOTHING;
            """))

        # Run validation
        await verify_seed(session_factory)

    # Auto-provision baseline retailer pricing across Aldi, Walmart, Meijer, Amazon
    print("\n[seed_recipes] Auto-provisioning retailer pricing for all catalog ingredients...")
    from app.database.seed_pricing import seed_pricing
    await seed_pricing(db_url)

    await engine.dispose()

async def verify_seed(session_factory):
    print("\n[seed_recipes] ========================================")
    print("[seed_recipes] === Seeded Data & pgvector Validation ===")
    print("[seed_recipes] ========================================")
    async with session_factory() as session:
        # 1. Total count
        total_res = await session.execute(text("SELECT count(*) FROM recipes"))
        total = total_res.scalar()
        print(f"  [+] Total recipes in database        : {total}")

        # 2. Embedded count
        embed_res = await session.execute(text("SELECT count(*) FROM recipes WHERE embedding IS NOT NULL"))
        embedded = embed_res.scalar()
        print(f"  [+] Recipes with active pgvector embeddings : {embedded}")

        # 3. Dietary preferences
        pref_res = await session.execute(text("SELECT count(*) FROM dietary_preferences"))
        prefs = pref_res.scalar()
        print(f"  [+] Unique dietary preference tags   : {prefs}")

        # 4. Ingredients
        ing_res = await session.execute(text("SELECT count(*) FROM ingredients"))
        ings = ing_res.scalar()
        print(f"  [+] Unique ingredients cataloged     : {ings}")

        # 5. Household recipe links
        hlink_res = await session.execute(text("SELECT count(*) FROM household_recipes"))
        hlinks = hlink_res.scalar()
        print(f"  [+] Household recipe book links      : {hlinks}")

        # 6. Vector cosine similarity search test using pgvector operator (<=>)
        print("\n[seed_recipes] Testing pgvector semantic similarity search...")
        query_text = "quick weeknight chicken dinner with vegetables"
        q_vec = await get_embedding(query_text)
        vec_str = "[" + ",".join(str(x) for x in q_vec) + "]"

        sim_res = await session.execute(
            text(
                "SELECT title, prep_time_minutes, difficulty_level, (embedding <=> :qvec) as cosine_distance "
                "FROM recipes ORDER BY cosine_distance ASC LIMIT 3"
            ),
            {"qvec": vec_str}
        )
        matches = sim_res.fetchall()
        print(f"  Query: '{query_text}'")
        print("  Top 3 Nearest Semantic Matches (via pgvector <=>):")
        for i, m in enumerate(matches, 1):
            print(f"    {i}. {m[0]} (prep: {m[1]}m, level: {m[2]}) -> cosine distance: {round(float(m[3]), 4)}")

        if embedded >= 100:
            print(f"\n[seed_recipes] SUCCESS: {embedded} baseline starter recipes loaded with active pgvector embeddings (>= 100)!")
        else:
            print(f"\n[seed_recipes] WARNING: Expected >= 100 embedded recipes, found {embedded}.")

if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_URL
    asyncio.run(seed_recipes(target_url))
