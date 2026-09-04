import math
import re
from typing import Dict, Any, List
from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models import MealPlan, MealPlanItem, Recipe, Ingredient, RetailerPricing, PantryItem

TARGET_RETAILERS = ["Aldi", "Walmart", "Meijer", "Amazon"]

def is_pantry_staple_match(ingredient_name: str, staple_name: str) -> bool:
    """
    Perform case-insensitive fuzzy containment matching on ingredient names
    against a pantry staple name.
    Avoids false positives like matching 'Salt' to 'Salted Butter' or 'Garlic Powder' to 'Garlic Cloves'.
    """
    ing = ingredient_name.lower().strip()
    staple = staple_name.lower().strip()

    if not ing or not staple:
        return False

    # 1. Exact match
    if ing == staple:
        return True

    # 2. Direct whole-word containment of staple in ingredient
    pattern = rf"\b{re.escape(staple)}\b"
    if re.search(pattern, ing):
        return True

    # 3. Handle specific well-known equivalents / staples
    # Granulated sugar / white sugar / sugar
    if staple in ["granulated sugar", "white sugar", "sugar"]:
        if ing in ["sugar", "granulated sugar", "white sugar"] or re.search(r"\b(granulated|white)\s+sugar\b", ing):
            return True

    # Black pepper / pepper
    if staple in ["black pepper", "ground black pepper"]:
        if ing in ["pepper", "black pepper", "ground black pepper", "cracked black pepper"]:
            return True
        if re.search(r"\b(black|cracked)\s+pepper\b", ing):
            return True

    # All-purpose flour / flour
    if staple in ["all-purpose flour", "all purpose flour", "flour"]:
        clean_ing = ing.replace("-", " ")
        if clean_ing in ["flour", "all purpose flour"] or re.search(r"\ball\s+purpose\s+flour\b", clean_ing):
            return True

    # 4. Normalized punctuation containment
    clean_ing_nopunc = re.sub(r"[^\w\s]", " ", ing)
    clean_staple_nopunc = re.sub(r"[^\w\s]", " ", staple)
    clean_ing_str = " ".join(clean_ing_nopunc.split())
    clean_staple_str = " ".join(clean_staple_nopunc.split())

    if clean_ing_str == clean_staple_str:
        return True

    if clean_staple_str and re.search(rf"\b{re.escape(clean_staple_str)}\b", clean_ing_str):
        return True

    return False

async def aggregate_groceries_for_plan(plan_id: UUID, db: AsyncSession) -> Dict[str, Any]:
    """
    Extracts required ingredients from a meal plan and maps them against pricing
    and availability metrics across targeted retailers (Aldi, Walmart, Meijer, Amazon),
    filtering out in-stock pantry staples for the plan's household.
    """
    # 1. Fetch Meal Plan with Items & Recipes
    stmt = select(MealPlan).where(MealPlan.plan_id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail=f"Meal plan {plan_id} not found.")

    if not plan.items:
        raise HTTPException(status_code=400, detail="Meal plan has no assigned meals.")

    # 2. Extract and consolidate ingredients across all scheduled meals
    raw_ingredients: Dict[str, Dict[str, Any]] = {}

    for item in plan.items:
        if not item.recipe:
            continue

        recipe = item.recipe
        ingredients_list = recipe.ingredients or []

        if not ingredients_list:
            continue

        for ing in ingredients_list:
            name = ing.get("name", "").strip()
            if not name:
                continue

            unit = ing.get("unit", "ea")
            qty = float(ing.get("quantity", 1.0))
            key = name.lower()

            if key not in raw_ingredients:
                raw_ingredients[key] = {
                    "name": name,
                    "unit": unit,
                    "total_quantity": qty,
                    "used_in_recipes": [recipe.title]
                }
            else:
                raw_ingredients[key]["total_quantity"] = round(
                    raw_ingredients[key]["total_quantity"] + qty, 2
                )
                if recipe.title not in raw_ingredients[key]["used_in_recipes"]:
                    raw_ingredients[key]["used_in_recipes"].append(recipe.title)

    if not raw_ingredients:
        raise HTTPException(status_code=400, detail="No ingredients could be extracted from the scheduled meals.")

    # 3. Query in-stock household pantry staples & filter them out
    pantry_suppressed_items: List[str] = []
    in_stock_staples: List[str] = []
    if plan.household_id:
        pantry_stmt = select(PantryItem).where(
            PantryItem.household_id == plan.household_id,
            PantryItem.is_in_stock == True
        )
        p_res = await db.execute(pantry_stmt)
        in_stock_staples = [p.item_name for p in p_res.scalars().all()]

    aggregated_ingredients: Dict[str, Dict[str, Any]] = {}
    for key, ing_data in raw_ingredients.items():
        if any(is_pantry_staple_match(ing_data["name"], s) for s in in_stock_staples):
            pantry_suppressed_items.append(ing_data["name"])
        else:
            aggregated_ingredients[key] = ing_data

    pantry_suppressed_items = sorted(list(set(pantry_suppressed_items)))

    # 4. Match ingredients to database Ingredient IDs and fetch pricing
    ing_names = list(aggregated_ingredients.keys())
    db_ing_stmt = select(Ingredient)
    db_ing_res = await db.execute(db_ing_stmt)
    all_db_ings = db_ing_res.scalars().all()

    # Map lowercase name -> Ingredient record
    ing_lookup = {i.ingredient_name.lower(): i for i in all_db_ings}

    matched_ingredient_ids = []
    id_to_key = {}
    for key in ing_names:
        db_ing = ing_lookup.get(key)
        if db_ing:
            matched_ingredient_ids.append(db_ing.ingredient_id)
            id_to_key[db_ing.ingredient_id] = key

    # Fetch Retailer Pricing
    pricing_map: Dict[str, Dict[str, float]] = {r: {} for r in TARGET_RETAILERS}
    if matched_ingredient_ids:
        price_stmt = select(RetailerPricing).where(
            RetailerPricing.ingredient_id.in_(matched_ingredient_ids),
            RetailerPricing.retailer_name.in_(TARGET_RETAILERS)
        )
        price_res = await db.execute(price_stmt)
        for p in price_res.scalars().all():
            key = id_to_key.get(p.ingredient_id)
            if key:
                pricing_map[p.retailer_name][key] = float(p.price)

    # 5. Calculate Single-Store Basket Totals & Availability
    total_needed_items = len(aggregated_ingredients)
    store_baskets: Dict[str, Dict[str, Any]] = {}

    for retailer in TARGET_RETAILERS:
        retailer_prices = pricing_map[retailer]
        available_items = []
        missing_items = []
        total_cost = 0.0

        for key, ing_data in aggregated_ingredients.items():
            if key in retailer_prices:
                unit_price = retailer_prices[key]
                packs_needed = max(1, math.ceil(ing_data["total_quantity"]))
                item_cost = round(unit_price * packs_needed, 2)
                total_cost += item_cost
                available_items.append({
                    "name": ing_data["name"],
                    "quantity": ing_data["total_quantity"],
                    "unit": ing_data["unit"],
                    "unit_price": unit_price,
                    "estimated_cost": item_cost
                })
            else:
                missing_items.append(ing_data["name"])

        fulfillment = round((len(available_items) / total_needed_items) * 100, 1) if total_needed_items > 0 else 100.0

        store_baskets[retailer] = {
            "retailer_name": retailer,
            "items_available_count": len(available_items),
            "total_needed_count": total_needed_items,
            "fulfillment_percentage": fulfillment,
            "total_estimated_cost": round(total_cost, 2),
            "missing_items": missing_items,
            "available_items_sample": available_items[:5]
        }

    # 6. Compute Optimal Multi-Store Split Basket
    split_basket_by_store: Dict[str, List[Dict[str, Any]]] = {r: [] for r in TARGET_RETAILERS}
    split_total_cost = 0.0
    unpriced_items = []

    for key, ing_data in aggregated_ingredients.items():
        best_price = float("inf")
        best_store = None

        for retailer in TARGET_RETAILERS:
            if key in pricing_map[retailer]:
                p = pricing_map[retailer][key]
                if p < best_price:
                    best_price = p
                    best_store = retailer

        if best_store:
            packs_needed = max(1, math.ceil(ing_data["total_quantity"]))
            item_cost = round(best_price * packs_needed, 2)
            split_total_cost += item_cost
            split_basket_by_store[best_store].append({
                "name": ing_data["name"],
                "quantity": ing_data["total_quantity"],
                "unit": ing_data["unit"],
                "unit_price": best_price,
                "cost": item_cost
            })
        else:
            unpriced_items.append(ing_data["name"])

    # 7. Recommendation and Savings Analysis
    sorted_stores = sorted(
        store_baskets.values(),
        key=lambda s: (-s["fulfillment_percentage"], s["total_estimated_cost"])
    )
    recommended_single = sorted_stores[0]["retailer_name"] if sorted_stores else TARGET_RETAILERS[0]
    single_store_cost = sorted_stores[0]["total_estimated_cost"] if sorted_stores else 0.0
    split_total_cost = round(split_total_cost, 2)
    potential_savings = max(0.0, round(single_store_cost - split_total_cost, 2))

    return {
        "plan_id": str(plan.plan_id),
        "week_start_date": str(plan.week_start_date),
        "is_locked": plan.is_locked,
        "total_unique_ingredients": total_needed_items,
        "recommended_single_store": recommended_single,
        "single_store_cost": single_store_cost,
        "optimal_split_total_cost": split_total_cost,
        "potential_split_savings": potential_savings,
        "store_baskets": store_baskets,
        "optimal_split_basket": {
            store: items for store, items in split_basket_by_store.items() if items
        },
        "unpriced_items": unpriced_items,
        "pantry_suppressed_items": pantry_suppressed_items,
    }
