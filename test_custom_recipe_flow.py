import urllib.request
import json

base_url = "http://127.0.0.1:8001"

def run_tests():
    print("\n--- 1. Testing Custom Recipe Creation (POST /api/recipes/) ---")
    custom_recipe_payload = {
        "title": "Crispy Pan-Seared Lemon Rosemary Salmon",
        "description": "Wild Pacific salmon fillets seared in olive oil with fragrant fresh rosemary sprigs, minced garlic, and fresh lemon juice.",
        "prep_time_minutes": 20,
        "difficulty_level": "quick",
        "dietary_tags": ["gluten-free", "dairy-free", "pescatarian", "high-protein"],
        "ingredients": [
            {"name": "Wild Salmon Fillets", "quantity": 1.5, "unit": "lbs"},
            {"name": "Fresh Rosemary Sprigs", "quantity": 3.0, "unit": "count"},
            {"name": "Garlic Cloves", "quantity": 4.0, "unit": "count"},
            {"name": "Fresh Lemon", "quantity": 1.0, "unit": "count"},
            {"name": "Extra Virgin Olive Oil", "quantity": 2.0, "unit": "tbsp"}
        ],
        "instructions": [
            "Pat salmon fillets dry with paper towels and season with sea salt.",
            "Heat olive oil in a heavy stainless steel or cast iron skillet over medium-high heat.",
            "Add salmon skin-side down with rosemary sprigs and crushed garlic; sear for 5 minutes.",
            "Flip fillets, squeeze fresh lemon juice over the fish, and baste for 2-3 minutes until flaky."
        ],
        "is_public": True
    }

    req = urllib.request.Request(
        f"{base_url}/api/recipes/",
        data=json.dumps(custom_recipe_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 201, f"Expected 201 Created, got {resp.status}"
        created_recipe = json.loads(resp.read().decode("utf-8"))

    recipe_id = created_recipe["recipe_id"]
    print(f"  ✓ Recipe Created Successfully! (ID: {recipe_id})")
    print(f"    - Title         : {created_recipe['title']}")
    print(f"    - Dietary Tags  : {created_recipe['dietary_tags']}")
    print(f"    - Has Embedding : {created_recipe['has_embedding']}")
    print(f"    - Ingredients   : {len(created_recipe['ingredients'])} items")
    print(f"    - Instructions  : {len(created_recipe['instructions'])} steps")

    print("\n--- 2. Testing Household Onboarding with Pescatarian & Gluten-Free ---")
    h_payload = {
        "household_name": "Seafood & Health Homelab",
        "dietary_preferences": ["gluten-free", "pescatarian"]
    }
    h_req = urllib.request.Request(
        f"{base_url}/api/households/",
        data=json.dumps(h_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(h_req) as resp:
        household = json.loads(resp.read().decode("utf-8"))
    h_id = household["household_id"]
    print(f"  ✓ Household Created: {household['household_name']} (ID: {h_id})")

    print("\n--- 3. Testing Meal Plan Generation Incorporating Custom Recipe ---")
    gen_payload = {
        "household_id": h_id,
        "dietary_tags": ["gluten-free", "pescatarian"],
        "days_count": 5
    }
    gen_req = urllib.request.Request(
        f"{base_url}/api/meal-plans/generate",
        data=json.dumps(gen_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(gen_req) as resp:
        plan = json.loads(resp.read().decode("utf-8"))

    plan_id = plan["plan_id"]
    print(f"  ✓ Plan ID: {plan_id} (Week: {plan['week_start_date']})")
    titles = [m["title"] for m in plan["meals"].values()]
    print("    Scheduled Meals:")
    for day, meal in plan["meals"].items():
        print(f"      * {day:<9}: {meal['title']}")

    print("\n--- 4. Testing Grocery Aggregation on Generated Plan ---")
    g_req = urllib.request.Request(f"{base_url}/api/meal-plans/{plan_id}/grocery-list", method="GET")
    with urllib.request.urlopen(g_req) as resp:
        groceries = json.loads(resp.read().decode("utf-8"))

    print(f"  ✓ Total Unique Ingredients: {groceries['total_unique_ingredients']}")
    print(f"  ✓ Optimal Split Cost      : ${groceries['optimal_split_total_cost']:.2f}")
    print(f"  ✓ Potential Split Savings : ${groceries['potential_split_savings']:.2f}")

    print("\n--- 5. Verifying Static Web Dashboard ---")
    dash_req = urllib.request.Request(f"{base_url}/dashboard", method="GET")
    with urllib.request.urlopen(dash_req) as resp:
        html_content = resp.read().decode("utf-8")
        assert "Upload Custom Recipe" in html_content
        assert "Live In-Store Shopping Columns" in html_content
        assert "splitbites.tbannon80-hp-mini.stream" in html_content
        print("  ✓ Web dashboard contains Custom Recipe Form, Checkable Shopping List, and domain badge!")

    print("\n✅ All Custom Recipe & Dashboard Tests Passed Successfully!")

if __name__ == "__main__":
    run_tests()
