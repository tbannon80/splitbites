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

SUPERMARKET_DEPARTMENTS = [
    "Produce",
    "Meat & Seafood",
    "Dairy & Refrigerated",
    "Bakery",
    "Pantry & Dry Goods",
    "Spices & Baking",
    "Frozen",
    "Other",
]

DEPARTMENT_ICONS = {
    "Produce": "🥦",
    "Meat & Seafood": "🥩",
    "Dairy & Refrigerated": "🧀",
    "Bakery": "🍞",
    "Pantry & Dry Goods": "🥫",
    "Spices & Baking": "🧂",
    "Frozen": "🧊",
    "Other": "📦",
}

def classify_ingredient_department(name: str) -> str:
    """
    Deterministically maps an ingredient name into its primary supermarket department
    using keyword and culinary heuristics.
    Standard sequence:
    Produce -> Meat & Seafood -> Dairy & Refrigerated -> Bakery -> Pantry & Dry Goods -> Spices & Baking -> Frozen -> Other
    """
    n = name.lower().strip()
    if not n:
        return "Other"

    # 1. Frozen
    if re.search(r"\b(frozen|ice cream|popsicle|sorbet|gelato)\b", n):
        return "Frozen"

    # 2. Bakery
    if re.search(r"\b(bread|buns?|tortillas?|bagels?|pitas?|croissants?|rolls?|naan|wraps?|baguettes?|pizza crust|crust|english muffins?|sourdough|ciabatta|brioche)\b", n):
        return "Bakery"

    # Special fresh produce items that might otherwise collide with dry goods keywords (e.g. beans, noodles)
    if re.search(r"\b(green beans?|string beans?|snap peas?|snow peas?|zucchini noodles?)\b", n):
        return "Produce"

    # 3. Spices & Baking (specific powdered, ground, dried spices, sugars, flours, seasonings, extracts)
    # Check before Pantry & Produce so "Garlic Powder", "Onion Powder", "Ground Cumin", "Black Pepper" are spices.
    if re.search(r"\b(powder|ground (cinnamon|cumin|ginger|nutmeg|turmeric|allspice|black pepper|cloves|cardamom|coriander)|smoked paprika|paprika|cumin|oregano|crushed red pepper|pepper flakes|chili powder|curry powder|garam masala|cayenne|fajita seasoning|taco seasoning|italian seasoning|seasoning|sesame seeds|poppy seeds|cornstarch|baking powder|baking soda|yeast|vanilla extract|cocoa powder|chocolate chips?)\b", n):
        return "Spices & Baking"
    if re.search(r"\b(salt|sea salt|kosher salt)\b", n) and not re.search(r"\b(salted butter|saltines)\b", n):
        return "Spices & Baking"
    if re.search(r"\b(brown sugar|granulated sugar|white sugar|powdered sugar|confectioners sugar)\b", n) or (re.search(r"\bsugar\b", n) and not re.search(r"\b(snap peas?)\b", n)):
        return "Spices & Baking"
    if re.search(r"\b(all-purpose flour|all purpose flour|flour|bread flour|almond flour|whole wheat flour)\b", n):
        return "Spices & Baking"
    if re.search(r"\b(black pepper|cracked black pepper|dry mustard powder)\b", n):
        return "Spices & Baking"
    if re.fullmatch(r"pepper(\s*,\s*.*)?", n) or n in ["pepper", "black pepper", "cracked black pepper", "cayenne", "cayenne pepper"]:
        return "Spices & Baking"

    # 4. Pantry & Dry Goods (broths, oils, sauces, pastes, vinegars, canned goods, grains, pasta, legumes, condiments)
    # Checked before fresh Produce & Meat so "Chicken Broth", "Apple Cider Vinegar", "San Marzano Pizza Sauce" route to Pantry.
    if re.search(r"\b(broth|stock|bouillon|vinegar|pesto|glaze|dressing|sauces?|mustard|mayo|mayonnaise|ketchup|salsa|pickles?|olives?|capers|raw honey|honey|maple syrup|peanut butter|almond butter|coconut milk|soy sauce|tamari|teriyaki|worcestershire|paste|puree|nori|soba|noodles?|pasta|penne|spaghetti|macaroni|fettuccine|linguine|rotini|rigatoni|lasagna|orzo|rice|quinoa|couscous|oats|oatmeal|lentils?|canned|beans?|chickpeas?|cannellini|kidney beans?|black beans?|pinto beans?|wine)\b", n):
        return "Pantry & Dry Goods"
    if re.search(r"\b(oil|olive oil|vegetable oil|sesame oil|canola oil|avocado oil)\b", n):
        return "Pantry & Dry Goods"
    if re.search(r"\b(tomato sauce|pizza sauce|crushed tomatoes|diced tomatoes|plum tomatoes|sun-dried tomatoes|canned tomatoes)\b", n):
        return "Pantry & Dry Goods"

    # 5. Meat & Seafood
    if re.search(r"\b(chicken|beef|pork|turkey|salmon|shrimp|fish|cod|halibut|bacon|sausage|steak|lamb|tuna|tilapia|trout|scallops?|prawns?|lobster|crab|brisket|ham|prosciutto|meatballs?|veal|duck|ribs|pancetta|clams?|mussels?|oysters?|calamari)\b", n):
        return "Meat & Seafood"

    # 6. Dairy & Refrigerated
    if re.search(r"\b(cheese|cheddar|mozzarella|feta|parmesan|gouda|swiss|provolone|ricotta|brie|blue cheese|pecorino|goat cheese|cottage cheese)\b", n):
        return "Dairy & Refrigerated"
    if re.search(r"\b(butter|ghee)\b", n) and not re.search(r"\b(peanut|almond|apple|butter lettuce|butternut)\b", n):
        return "Dairy & Refrigerated"
    if re.search(r"\b(cream|heavy cream|whipping cream|sour cream|cream cheese|yogurt|greek yogurt|milk|half and half|buttermilk)\b", n) and not re.search(r"\b(coconut|ice cream)\b", n):
        return "Dairy & Refrigerated"
    if re.search(r"\b(eggs?|egg whites?|tofu|tempeh)\b", n):
        return "Dairy & Refrigerated"

    # 7. Produce
    if re.search(r"\b(lettuce|spinach|kale|cabbage|greens?|arugula|romaine|chard|collard)\b", n):
        return "Produce"
    if re.search(r"\b(tomato|tomatoes|onion|onions|shallots?|scallions?|garlic|ginger|potato|potatoes|carrot|carrots|celery|cucumber|cucumbers|zucchini|squash|broccoli|cauliflower|asparagus|mushroom|mushrooms|avocado|avocados|peppers?|bell peppers?|jalapeno|chili|chilies|lime|limes|lemon|lemons|apple|apples|banana|bananas|orange|oranges|berries|strawberry|strawberries|blueberry|blueberries|blackberry|blackberries|raspberry|raspberries|edamame|radish|radishes|beets?|leeks?|eggplant)\b", n):
        return "Produce"
    if re.search(r"\b(fresh|herbs?|parsley|cilantro|basil|dill|rosemary|thyme|sage|mint|chives)\b", n):
        return "Produce"

    return "Other"

def group_items_by_department(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups a list of grocery item dicts by the standard supermarket department sequence.
    Returns a list of department dicts:
      {
        "department_name": dept,
        "department_icon": DEPARTMENT_ICONS.get(dept, "📦"),
        "item_count": len(dept_items),
        "total_cost": round(sum(it.get("cost", it.get("estimated_cost", 0.0)) for it in dept_items), 2),
        "items": dept_items
      }
    """
    groups: Dict[str, List[Dict[str, Any]]] = {dept: [] for dept in SUPERMARKET_DEPARTMENTS}

    for it in items:
        dept = it.get("department") or classify_ingredient_department(it.get("name", ""))
        if dept not in groups:
            dept = "Other"
        it["department"] = dept
        groups[dept].append(it)

    result = []
    for dept in SUPERMARKET_DEPARTMENTS:
        dept_items = groups[dept]
        if dept_items:
            sorted_items = sorted(dept_items, key=lambda x: x.get("name", "").lower())
            cost_sum = round(sum(float(it.get("cost", it.get("estimated_cost", 0.0))) for it in sorted_items), 2)
            result.append({
                "department_name": dept,
                "department_icon": DEPARTMENT_ICONS.get(dept, "📦"),
                "item_count": len(sorted_items),
                "total_cost": cost_sum,
                "items": sorted_items,
            })
    return result

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

        default_servings = getattr(recipe, "default_servings", 4) or 4
        slot_servings = getattr(item, "servings", 4) or 4
        scale = float(slot_servings) / float(default_servings)

        for ing in ingredients_list:
            name = ing.get("name", "").strip()
            if not name:
                continue

            unit = ing.get("unit", "ea")
            base_qty = float(ing.get("quantity", 1.0))
            qty = round(base_qty * scale, 2)
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
            dept = classify_ingredient_department(ing_data["name"])
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
                    "estimated_cost": item_cost,
                    "department": dept,
                })
            else:
                missing_items.append(ing_data["name"])

        # Sort available items by standard supermarket aisle sequence, then by name
        available_items.sort(
            key=lambda x: (
                SUPERMARKET_DEPARTMENTS.index(x.get("department", "Other")) if x.get("department") in SUPERMARKET_DEPARTMENTS else 999,
                x.get("name", "").lower()
            )
        )
        grouped_depts = group_items_by_department(available_items)

        fulfillment = round((len(available_items) / total_needed_items) * 100, 1) if total_needed_items > 0 else 100.0

        store_baskets[retailer] = {
            "retailer_name": retailer,
            "items_available_count": len(available_items),
            "total_needed_count": total_needed_items,
            "fulfillment_percentage": fulfillment,
            "total_estimated_cost": round(total_cost, 2),
            "missing_items": missing_items,
            "available_items_sample": available_items[:5],
            "available_items": available_items,
            "departments": grouped_depts,
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
            dept = classify_ingredient_department(ing_data["name"])
            split_basket_by_store[best_store].append({
                "name": ing_data["name"],
                "quantity": ing_data["total_quantity"],
                "unit": ing_data["unit"],
                "unit_price": best_price,
                "cost": item_cost,
                "department": dept,
            })
        else:
            unpriced_items.append(ing_data["name"])

    # Sort each store's items by supermarket department sequence, then name
    optimal_split_departments = {}
    for store, items in split_basket_by_store.items():
        if items:
            items.sort(
                key=lambda x: (
                    SUPERMARKET_DEPARTMENTS.index(x.get("department", "Other")) if x.get("department") in SUPERMARKET_DEPARTMENTS else 999,
                    x.get("name", "").lower()
                )
            )
            optimal_split_departments[store] = group_items_by_department(items)

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
        "optimal_split_departments": optimal_split_departments,
        "departments": SUPERMARKET_DEPARTMENTS,
        "unpriced_items": unpriced_items,
        "pantry_suppressed_items": pantry_suppressed_items,
    }
