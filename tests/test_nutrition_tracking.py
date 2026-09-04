import json
import urllib.request
import urllib.error
import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock

from app.services.recipe_scraper import parse_nutrition_dict

BASE_URL = "http://127.0.0.1:8001"

def make_request(url, method="GET", payload=None, token=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def register_test_user(prefix="nutr_test"):
    unique_email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    status, data = make_request(
        f"{BASE_URL}/api/auth/register",
        method="POST",
        payload={
            "email": unique_email,
            "password": "password123",
            "confirm_password": "password123",
            "full_name": "Nutrition Test User",
            "household_name": "Nutrition Test Family"
        }
    )
    assert status == 200
    return data["access_token"], data["user"], data["household"]

def test_parse_nutrition_dict_various_formats():
    """b) Test URL scraper extracts nutrition when present in JSON-LD formats."""
    # Standard numbers
    d1 = {"calories": 520, "proteinContent": 38.0, "carbohydrateContent": 42.0, "fatContent": 18.0}
    p1 = parse_nutrition_dict(d1)
    assert p1 == {"calories": 520, "protein_g": 38.0, "carbs_g": 42.0, "fat_g": 18.0}

    # Text strings with units
    d2 = {
        "calories": "650 calories",
        "proteinContent": "45.5 g",
        "carbohydrateContent": "50 grams",
        "fatContent": "22.3g"
    }
    p2 = parse_nutrition_dict(d2)
    assert p2["calories"] == 650
    assert p2["protein_g"] == 45.5
    assert p2["carbs_g"] == 50.0
    assert p2["fat_g"] == 22.3

    # Partial / missing fields
    d3 = {"calories": "300 kcal", "proteinContent": "20g"}
    p3 = parse_nutrition_dict(d3)
    assert p3["calories"] == 300
    assert p3["protein_g"] == 20.0
    assert "carbs_g" not in p3
    assert "fat_g" not in p3

    # Empty / non-dict
    assert parse_nutrition_dict(None) == {}
    assert parse_nutrition_dict("invalid") == {}

def test_recipe_nutrition_schema_and_persistence():
    """a) Test recipe nutrition schema and database persistence via API."""
    token, user, household = register_test_user("schema_pers")

    custom_nutrition = {
        "calories": 620,
        "protein_g": 45.0,
        "carbs_g": 55.0,
        "fat_g": 20.0
    }

    # Create recipe with nutrition
    status, recipe = make_request(
        f"{BASE_URL}/api/recipes/",
        method="POST",
        payload={
            "title": f"High-Protein Quinoa Bowl {uuid4().hex[:6]}",
            "description": "Nutritious bowl packed with macros",
            "prep_time_minutes": 25,
            "difficulty_level": "easy",
            "default_servings": 2,
            "ingredients": [
                {"name": "Cooked Quinoa", "quantity": 1.0, "unit": "cups"},
                {"name": "Chicken Breast", "quantity": 0.5, "unit": "lbs"}
            ],
            "instructions": ["Cook quinoa", "Sauté chicken", "Combine and serve"],
            "dietary_tags": ["high-protein", "gluten-free"],
            "nutrition_per_serving": custom_nutrition
        },
        token=token
    )
    assert status in [200, 201]
    recipe_id = recipe["recipe_id"]
    assert "nutrition_per_serving" in recipe
    assert recipe["nutrition_per_serving"]["calories"] == 620
    assert recipe["nutrition_per_serving"]["protein_g"] == 45.0
    assert recipe["nutrition_per_serving"]["carbs_g"] == 55.0
    assert recipe["nutrition_per_serving"]["fat_g"] == 20.0

    # Retrieve recipe by ID
    status, fetched = make_request(f"{BASE_URL}/api/recipes/{recipe_id}", token=token)
    assert status == 200
    assert fetched["nutrition_per_serving"]["calories"] == 620
    assert fetched["nutrition_per_serving"]["protein_g"] == 45.0

def test_daily_and_weekly_macro_scaling_proportionately():
    """c) Test daily and weekly macro calculations scale proportionately with slot servings."""
    token, user, household = register_test_user("macro_scale")
    household_id = household["household_id"]

    # Generate plan
    status, plan = make_request(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": household_id},
        token=token
    )
    assert status == 200

    # 1. Verify daily_nutrition and weekly averages in payload
    assert "daily_nutrition" in plan
    assert "weekly_avg_daily_calories" in plan
    assert "weekly_avg_protein_g" in plan
    assert "weekly_avg_carbs_g" in plan
    assert "weekly_avg_fat_g" in plan
    assert "weekly_macro_averages" in plan

    first_day = next(iter(plan["meals"]))
    slot = plan["meals"][first_day]
    item_id = slot["item_id"]
    initial_servings = slot.get("servings", 4) or 4

    day_nutr = plan["daily_nutrition"][first_day]
    per_serv = day_nutr["per_serving"]
    total_nutr = day_nutr["total"]

    # Verify per_serving and total calculations
    assert total_nutr["calories"] == round(per_serv["calories"] * initial_servings, 1)
    assert total_nutr["protein_g"] == round(per_serv["protein_g"] * initial_servings, 1)
    assert total_nutr["carbs_g"] == round(per_serv["carbs_g"] * initial_servings, 1)
    assert total_nutr["fat_g"] == round(per_serv["fat_g"] * initial_servings, 1)

    initial_weekly_avg_cal = plan["weekly_avg_daily_calories"]

    # 2. Scale servings from 4 to 6 (1.5x)
    new_servings = initial_servings + 2
    status, updated_plan = make_request(
        f"{BASE_URL}/api/meal-plans/{plan['plan_id']}/slots/{item_id}/servings",
        method="PATCH",
        payload={"servings": new_servings},
        token=token
    )
    assert status == 200

    updated_slot = updated_plan["meals"][first_day]
    assert updated_slot["servings"] == new_servings

    updated_day_nutr = updated_plan["daily_nutrition"][first_day]
    assert updated_day_nutr["servings"] == new_servings
    assert updated_day_nutr["total"]["calories"] == round(per_serv["calories"] * new_servings, 1)
    assert updated_day_nutr["total"]["protein_g"] == round(per_serv["protein_g"] * new_servings, 1)

    # Weekly average calories must have increased
    assert updated_plan["weekly_avg_daily_calories"] > initial_weekly_avg_cal

def test_frontend_nutrition_elements_present():
    """d) Test frontend contains nutritional badges and summary bar."""
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        content = f.read()

    # Weekly Macro Average Bar
    assert "id=\"weeklyMacroBar\"" in content
    assert "Weekly Macro Average" in content
    assert "id=\"macroAvgCalories\"" in content
    assert "id=\"macroAvgProtein\"" in content
    assert "id=\"macroAvgCarbs\"" in content
    assert "id=\"macroAvgFat\"" in content

    # Macro badges strip inside renderPlan
    assert "kcal" in content
    assert "g P" in content
    assert "g C" in content
    assert "g F" in content
    assert "weekly_avg_daily_calories" in content
