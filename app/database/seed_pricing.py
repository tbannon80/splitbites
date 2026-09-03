import asyncio
import os
import random
import sys
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, text
from app.models import Ingredient, RetailerPricing

DEFAULT_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@splitbites-postgres:5432/splitbites"
    if os.path.exists("/.dockerenv")
    else "postgresql+asyncpg://postgres:postgres@localhost:5433/splitbites"
)

# Base baseline prices for common ingredient categories
RETAILER_PROFILES = {
    "Aldi": {"price_mult": 0.88, "availability_rate": 0.92},
    "Walmart": {"price_mult": 0.95, "availability_rate": 0.98},
    "Meijer": {"price_mult": 1.04, "availability_rate": 0.95},
    "Amazon": {"price_mult": 1.18, "availability_rate": 0.90},
}

def estimate_base_price(ingredient_name: str, default_unit: str) -> float:
    name = ingredient_name.lower()
    if any(k in name for k in ("salmon", "cod", "halibut", "white fish")):
        return 9.99
    elif "shrimp" in name:
        return 8.49
    elif any(k in name for k in ("beef", "steak")):
        return 6.99
    elif any(k in name for k in ("chicken", "turkey", "pork")):
        return 4.99
    elif any(k in name for k in ("cheese", "mozzarella", "parmesan", "feta")):
        return 3.99
    elif any(k in name for k in ("olive oil", "sesame oil", "balsamic")):
        return 5.99
    elif any(k in name for k in ("rice", "quinoa", "lentils", "pasta", "soba")):
        return 2.49
    elif any(k in name for k in ("beans", "tomatoes", "coconut milk", "chickpeas")):
        return 1.49
    elif any(k in name for k in ("spinach", "lettuce", "broccoli", "asparagus", "peppers")):
        return 2.29
    elif any(k in name for k in ("garlic", "ginger", "lemon", "lime", "onion", "shallot")):
        return 0.99
    elif any(k in name for k in ("seasoning", "spice", "paprika", "cumin", "garam masala")):
        return 2.99
    elif "butter" in name:
        return 3.49
    elif "tofu" in name:
        return 2.19
    else:
        return 2.49

async def seed_pricing(db_url: str = DEFAULT_DB_URL):
    print(f"[seed_pricing] Connecting to: {db_url}")
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        async with session.begin():
            ing_stmt = select(Ingredient)
            ing_res = await session.execute(ing_stmt)
            ingredients = ing_res.scalars().all()

            if not ingredients:
                print("[seed_pricing] No ingredients found in database! Run seed_recipes first.")
                return

            print(f"[seed_pricing] Generating multi-store pricing for {len(ingredients)} catalog ingredients...")
            random.seed(42) # Deterministic for consistent testing
            pricing_entries = 0

            # Clear existing pricing to ensure clean seed
            await session.execute(text("TRUNCATE TABLE retailer_pricing CASCADE"))

            for ing in ingredients:
                base_price = estimate_base_price(ing.ingredient_name, ing.default_unit or "unit")

                for retailer, profile in RETAILER_PROFILES.items():
                    # Check availability based on store profile
                    if random.random() > profile["availability_rate"]:
                        continue # Simulated stockout / uncarried item

                    # Add minor random noise (±8%)
                    noise = random.uniform(0.92, 1.08)
                    price = round(base_price * profile["price_mult"] * noise, 2)
                    price = max(price, 0.49) # Minimum price floor

                    pkg_size = f"1 {ing.default_unit or 'ea'}"

                    rp = RetailerPricing(
                        ingredient_id=ing.ingredient_id,
                        retailer_name=retailer,
                        price=Decimal(str(price)),
                        package_size=pkg_size
                    )
                    session.add(rp)
                    pricing_entries += 1

            await session.flush()
            print(f"[seed_pricing] Successfully populated {pricing_entries} retailer pricing entries across {len(RETAILER_PROFILES)} stores.")

        # Verification check
        count_res = await session.execute(text("SELECT retailer_name, count(*), round(avg(price), 2) FROM retailer_pricing GROUP BY retailer_name ORDER BY retailer_name"))
        rows = count_res.fetchall()
        print("\n[seed_pricing] Pricing breakdown per retailer:")
        for r in rows:
            print(f"  * {r[0]}: {r[1]} items priced (avg price: ${r[2]})")

    await engine.dispose()

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_URL
    asyncio.run(seed_pricing(target))
