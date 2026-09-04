import json
import urllib.request
import urllib.error
import pytest
from uuid import uuid4

from app.services.grocery_aggregation import (
    SUPERMARKET_DEPARTMENTS,
    DEPARTMENT_ICONS,
    classify_ingredient_department,
    group_items_by_department,
)

BASE_URL = "http://127.0.0.1:8001"

def make_request(url, method="GET", payload=None, token=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def register_test_user(prefix="dept_test"):
    unique_email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    status, data = make_request(
        f"{BASE_URL}/api/auth/register",
        method="POST",
        payload={
            "email": unique_email,
            "password": "password123",
            "confirm_password": "password123",
            "full_name": "Department Test User",
            "household_name": "Department Test Family"
        }
    )
    assert status == 200
    return data["access_token"], data["user"], data["household"]

def test_classify_ingredient_department_all_departments():
    """Verify taxonomy classifier deterministically categorizes diverse ingredients across all 8 departments."""
    test_cases = [
        # Produce
        ("Romaine Lettuce", "Produce"),
        ("Baby Spinach", "Produce"),
        ("Cherry Tomatoes", "Produce"),
        ("Fresh Basil Leaves", "Produce"),
        ("Fresh Cilantro Leaves", "Produce"),
        ("Fresh Green Beans", "Produce"),
        ("Zucchini Noodles", "Produce"),
        ("Garlic Cloves", "Produce"),
        ("Yellow Onion", "Produce"),
        ("Honeycrisp Apples", "Produce"),
        ("English Cucumber", "Produce"),
        ("Avocado", "Produce"),
        ("Matchstick Carrots", "Produce"),
        ("Fresh Lemon Juice", "Produce"),

        # Meat & Seafood
        ("Chicken Breast", "Meat & Seafood"),
        ("Boneless Skinless Chicken Thighs", "Meat & Seafood"),
        ("Ground Beef (80/20)", "Meat & Seafood"),
        ("Lean Ground Turkey (93/7)", "Meat & Seafood"),
        ("Salmon Fillets", "Meat & Seafood"),
        ("Jumbo Raw Shrimp", "Meat & Seafood"),
        ("Pacific Cod Fillets", "Meat & Seafood"),
        ("Pork Tenderloin", "Meat & Seafood"),
        ("Bacon", "Meat & Seafood"),

        # Dairy & Refrigerated
        ("Cheddar Cheese", "Dairy & Refrigerated"),
        ("Sharp Cheddar Cheese", "Dairy & Refrigerated"),
        ("Fresh Mozzarella", "Dairy & Refrigerated"),
        ("Heavy Whipping Cream", "Dairy & Refrigerated"),
        ("Unsalted Butter", "Dairy & Refrigerated"),
        ("Whole Eggs", "Dairy & Refrigerated"),
        ("Extra-Firm Tofu", "Dairy & Refrigerated"),
        ("Greek Yogurt", "Dairy & Refrigerated"),

        # Bakery
        ("Brioche Buns", "Bakery"),
        ("Corn Tortillas (Gluten-Free)", "Bakery"),
        ("Cauliflower Pizza Crust", "Bakery"),
        ("Sourdough Bread", "Bakery"),
        ("Pita Bread", "Bakery"),

        # Pantry & Dry Goods
        ("Apple Cider Vinegar", "Pantry & Dry Goods"),
        ("Chicken Broth", "Pantry & Dry Goods"),
        ("Vegetable Stock", "Pantry & Dry Goods"),
        ("Basil Pesto", "Pantry & Dry Goods"),
        ("Olive Oil", "Pantry & Dry Goods"),
        ("Extra Virgin Olive Oil", "Pantry & Dry Goods"),
        ("Black Beans (Canned)", "Pantry & Dry Goods"),
        ("Chickpeas (Canned)", "Pantry & Dry Goods"),
        ("Jasmine Rice", "Pantry & Dry Goods"),
        ("Penne Pasta", "Pantry & Dry Goods"),
        ("Buffalo Wing Sauce", "Pantry & Dry Goods"),
        ("San Marzano Pizza Sauce", "Pantry & Dry Goods"),
        ("Soy Sauce", "Pantry & Dry Goods"),
        ("Peanut Butter", "Pantry & Dry Goods"),
        ("Dry Red Lentils", "Pantry & Dry Goods"),

        # Spices & Baking
        ("Garlic Powder", "Spices & Baking"),
        ("Onion Powder", "Spices & Baking"),
        ("Ground Cumin", "Spices & Baking"),
        ("Smoked Paprika", "Spices & Baking"),
        ("Cracked Black Pepper", "Spices & Baking"),
        ("Pepper", "Spices & Baking"),
        ("Salt", "Spices & Baking"),
        ("Sea Salt", "Spices & Baking"),
        ("Brown Sugar", "Spices & Baking"),
        ("Granulated Sugar", "Spices & Baking"),
        ("All-Purpose Flour", "Spices & Baking"),
        ("Baking Powder", "Spices & Baking"),
        ("Vanilla Extract", "Spices & Baking"),
        ("Fajita Seasoning", "Spices & Baking"),

        # Frozen
        ("Frozen Peas and Carrots", "Frozen"),
        ("Vanilla Ice Cream", "Frozen"),
        ("Frozen Mixed Berries", "Frozen"),

        # Other
        ("Aluminum Foil", "Other"),
        ("Paper Towels", "Other"),
    ]

    for ing, expected_dept in test_cases:
        actual = classify_ingredient_department(ing)
        assert actual == expected_dept, f"Ingredient '{ing}' expected '{expected_dept}', got '{actual}'"

def test_group_items_by_department_sequence_and_totals():
    """Verify group_items_by_department maintains supermarket aisle ordering, computes subtotals, and sorts items alphabetically."""
    items = [
        {"name": "Garlic Powder", "cost": 1.99},
        {"name": "Chicken Breast", "cost": 8.50},
        {"name": "Romaine Lettuce", "cost": 2.29},
        {"name": "Brioche Buns", "cost": 3.49},
        {"name": "Cheddar Cheese", "cost": 4.19},
        {"name": "Frozen Peas and Carrots", "cost": 1.79},
        {"name": "Olive Oil", "cost": 6.99},
        {"name": "Apple Cider Vinegar", "cost": 3.29},
        {"name": "Avocado", "cost": 1.50},
    ]

    grouped = group_items_by_department(items)

    # 1. Check departments order matches SUPERMARKET_DEPARTMENTS
    dept_names = [g["department_name"] for g in grouped]
    expected_order = [d for d in SUPERMARKET_DEPARTMENTS if d in dept_names]
    assert dept_names == expected_order

    # Expected non-empty departments
    assert "Produce" in dept_names
    assert "Meat & Seafood" in dept_names
    assert "Dairy & Refrigerated" in dept_names
    assert "Bakery" in dept_names
    assert "Pantry & Dry Goods" in dept_names
    assert "Spices & Baking" in dept_names
    assert "Frozen" in dept_names

    # 2. Check total cost
    total_grouped_cost = round(sum(g["total_cost"] for g in grouped), 2)
    expected_total_cost = round(sum(it["cost"] for it in items), 2)
    assert total_grouped_cost == expected_total_cost

    # 3. Check item counts
    total_grouped_items = sum(g["item_count"] for g in grouped)
    assert total_grouped_items == len(items)

    # 4. Check internal alphabetical sort in Produce
    produce_group = next(g for g in grouped if g["department_name"] == "Produce")
    produce_item_names = [it["name"] for it in produce_group["items"]]
    assert produce_item_names == ["Avocado", "Romaine Lettuce"]
    assert produce_group["department_icon"] == DEPARTMENT_ICONS["Produce"]

    # 5. Check Pantry & Dry Goods
    pantry_group = next(g for g in grouped if g["department_name"] == "Pantry & Dry Goods")
    pantry_item_names = [it["name"] for it in pantry_group["items"]]
    assert pantry_item_names == ["Apple Cider Vinegar", "Olive Oil"]
    assert pantry_group["department_icon"] == DEPARTMENT_ICONS["Pantry & Dry Goods"]

def test_api_grocery_departments_payload_structure_and_consistency():
    """Verify GET /api/meal-plans/{plan_id}/grocery-list returns aisle-ordered baskets and department breakdowns."""
    token, user, household = register_test_user("api_dept")
    household_id = household["household_id"]

    # Generate plan
    status, plan = make_request(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": household_id},
        token=token
    )
    assert status == 200
    plan_id = plan["plan_id"]

    # Fetch groceries
    status, groceries = make_request(f"{BASE_URL}/api/meal-plans/{plan_id}/grocery-list", token=token)
    assert status == 200

    # 1. Verify root department metadata
    assert "departments" in groceries
    assert groceries["departments"] == SUPERMARKET_DEPARTMENTS
    assert "optimal_split_departments" in groceries

    # 2. Verify store_baskets department groupings
    for store_name, basket in groceries["store_baskets"].items():
        assert "departments" in basket
        depts = basket["departments"]
        assert isinstance(depts, list)

        # Department sequence check
        dept_names = [d["department_name"] for d in depts]
        expected_seq = [d for d in SUPERMARKET_DEPARTMENTS if d in dept_names]
        assert dept_names == expected_seq

        # Subtotals match
        sum_items = sum(d["item_count"] for d in depts)
        assert sum_items == basket["items_available_count"]

        sum_cost = round(sum(d["total_cost"] for d in depts), 2)
        assert sum_cost == basket["total_estimated_cost"]

        # Check available items aisle order
        if basket.get("available_items"):
            item_depts = [it["department"] for it in basket["available_items"]]
            dept_indices = [SUPERMARKET_DEPARTMENTS.index(d) for d in item_depts]
            assert dept_indices == sorted(dept_indices)

    # 3. Verify optimal_split_basket department groupings
    optimal_split = groceries["optimal_split_basket"]
    optimal_split_depts = groceries["optimal_split_departments"]

    split_item_sum = 0
    split_cost_sum = 0.0

    for store_name, items in optimal_split.items():
        assert store_name in optimal_split_depts
        store_dept_groups = optimal_split_depts[store_name]

        # Verify each item in items has "department"
        for it in items:
            assert "department" in it
            assert it["department"] in SUPERMARKET_DEPARTMENTS

        # Verify items in optimal split are sorted by supermarket department sequence
        item_depts = [it["department"] for it in items]
        dept_indices = [SUPERMARKET_DEPARTMENTS.index(d) for d in item_depts]
        assert dept_indices == sorted(dept_indices)

        # Verify departments structure
        sum_dept_items = sum(d["item_count"] for d in store_dept_groups)
        assert sum_dept_items == len(items)

        sum_dept_cost = round(sum(d["total_cost"] for d in store_dept_groups), 2)
        store_items_cost = round(sum(it["cost"] for it in items), 2)
        assert sum_dept_cost == store_items_cost

        split_item_sum += len(items)
        split_cost_sum += store_items_cost

    assert round(split_cost_sum, 2) == groceries["optimal_split_total_cost"]

def test_frontend_clipboard_and_grouping_helpers():
    """Verify that index.html contains groupItemsForExport and department grouping in clipboard exports."""
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    # Check that department icons and sequence are defined in index.html
    assert "function groupItemsForExport" in html_content
    assert "optimal_split_departments" in html_content
    assert "dept-section" in html_content

    # Check clipboard functions format department headers
    assert "dept.department_icon" in html_content
    assert "dept.department_name" in html_content
    assert "copyFullShoppingList" in html_content
    assert "copyStoreShoppingList" in html_content
