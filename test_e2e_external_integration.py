#!/usr/bin/env python3
import urllib.request
import ssl
import json
import time
import sys

TARGET_ENDPOINT = "https://splitbites.tbannon80-hp-mini.stream"
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 SplitBitesIntegrationSuite/1.0"
ORIGIN = "https://splitbites.tbannon80-hp-mini.stream"

ctx = ssl.create_default_context()

def api_call(path, method="GET", payload=None):
    url = f"{TARGET_ENDPOINT}{path}"
    headers = {
        "User-Agent": USER_AGENT,
        "Origin": ORIGIN,
        "Accept": "application/json"
    }
    body_bytes = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    start = time.time()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            dur = round((time.time() - start) * 1000, 1)
            raw = resp.read()
            data = None
            if method != "HEAD" and resp.headers.get_content_type() == "application/json" and raw:
                data = json.loads(raw.decode("utf-8"))
            elif "text" in resp.headers.get_content_type():
                data = raw.decode("utf-8")
            return resp.status, data, dur, None
    except urllib.error.HTTPError as e:
        dur = round((time.time() - start) * 1000, 1)
        raw = e.read()
        try:
            err_data = json.loads(raw.decode("utf-8"))
        except Exception:
            err_data = raw.decode("utf-8")
        return e.code, err_data, dur, str(e)
    except Exception as e:
        dur = round((time.time() - start) * 1000, 1)
        return 0, None, dur, str(e)

def run_integration_suite():
    print("=" * 75)
    print("  SplitBites Complete End-to-End External Integration Test Suite")
    print(f"  Target HTTPS Host: {TARGET_ENDPOINT}")
    print("=" * 75)

    tests_run = 0
    tests_passed = 0

    def assert_test(desc, condition, detail=""):
        nonlocal tests_run, tests_passed
        tests_run += 1
        if condition:
            tests_passed += 1
            print(f"  \033[92m[PASS]\033[0m {desc}: {detail}")
        else:
            print(f"  \033[91m[FAIL]\033[0m {desc}: {detail}")
            print("\n❌ Integration Test Failed. Aborting release.")
            sys.exit(1)

    # 1. Health Probe
    print("\n--- 1. External Infrastructure Health & Tunnel Connectivity ---")
    st, data, dur, _ = api_call("/healthz", method="GET")
    assert_test("GET /healthz Status", st == 200, f"HTTP {st} in {dur}ms")
    assert_test("Health Service Response", data.get("service") == "splitbites-backend", f"{data}")

    st_head, _, dur_head, _ = api_call("/healthz", method="HEAD")
    assert_test("HEAD /healthz Status", st_head == 200, f"HTTP {st_head} in {dur_head}ms")

    # 2. Household Onboarding
    print("\n--- 2. Household Profile Onboarding with Dietary Constraints ---")
    h_payload = {
        "household_name": "Bannon Homelab Culinary Collective",
        "dietary_preferences": ["gluten-free", "pescatarian", "high-protein"]
    }
    st, h_data, dur, _ = api_call("/api/households/", method="POST", payload=h_payload)
    assert_test("POST /api/households/ Status", st == 200, f"HTTP {st} in {dur}ms")
    household_id = h_data["household_id"]
    assert_test("Household Created ID", bool(household_id), f"ID: {household_id}")
    assert_test(
        "Household Constraints Registered",
        set(h_data["dietary_preferences"]) == {"gluten-free", "pescatarian", "high-protein"},
        f"Preferences: {h_data['dietary_preferences']}"
    )

    # 3. Custom Recipe Creation with Automated pgvector Embeddings
    print("\n--- 3. Custom Recipe Upload & Automated 1536-dim pgvector Embedding ---")
    custom_recipe = {
        "title": "Wild Pacific Halibut with Mediterranean Herb Chimichurri",
        "description": "Pan-seared wild halibut fillet topped with a vibrant chimichurri of fresh parsley, cilantro, garlic, extra virgin olive oil, and red wine vinegar.",
        "prep_time_minutes": 25,
        "difficulty_level": "medium",
        "dietary_tags": ["gluten-free", "dairy-free", "pescatarian", "high-protein"],
        "ingredients": [
            {"name": "Wild Pacific Halibut Fillet", "quantity": 1.25, "unit": "lbs"},
            {"name": "Fresh Flat-Leaf Parsley", "quantity": 1.0, "unit": "cup"},
            {"name": "Fresh Cilantro Leaves", "quantity": 0.5, "unit": "cup"},
            {"name": "Garlic Cloves (Minced)", "quantity": 4.0, "unit": "count"},
            {"name": "Red Wine Vinegar", "quantity": 2.0, "unit": "tbsp"},
            {"name": "Extra Virgin Olive Oil", "quantity": 4.0, "unit": "tbsp"},
            {"name": "Crushed Red Pepper Flakes", "quantity": 0.5, "unit": "tsp"}
        ],
        "instructions": [
            "Finely mince parsley, cilantro, and garlic; whisk together with olive oil, red wine vinegar, and red pepper flakes.",
            "Pat halibut fillets thoroughly dry with paper towels; season both sides with sea salt and cracked black pepper.",
            "Heat a skillet over medium-high heat with a splash of oil until shimmering; sear halibut skin-side down for 4 minutes.",
            "Gently flip the halibut fillets and cook for 3 additional minutes until flaky.",
            "Transfer fish to serving plates and generously spoon fresh herb chimichurri over the top."
        ],
        "is_public": True
    }
    st, r_data, dur, _ = api_call("/api/recipes/", method="POST", payload=custom_recipe)
    assert_test("POST /api/recipes/ Status", st == 201, f"HTTP {st} in {dur}ms")
    custom_recipe_id = r_data["recipe_id"]
    assert_test("Custom Recipe Title", r_data["title"] == custom_recipe["title"], f"{r_data['title']}")
    assert_test("1536-dim Embedding Generated", r_data["has_embedding"] is True, f"Active vector embedding indexed")

    # 4. Meal Plan Generation with Constraint & pgvector Preference Matching
    print("\n--- 4. Weekly Meal Plan Generation (pgvector Semantic Preference Matching) ---")
    gen_payload = {
        "household_id": household_id,
        "dietary_tags": ["gluten-free", "pescatarian"],
        "days_count": 5
    }
    st, plan_data, dur, _ = api_call("/api/meal-plans/generate", method="POST", payload=gen_payload)
    assert_test("POST /api/meal-plans/generate Status", st == 200, f"HTTP {st} in {dur}ms")
    plan_id = plan_data["plan_id"]
    assert_test("5-Day Plan Provisioned", len(plan_data["meals"]) == 5, f"Plan ID: {plan_id}")

    print("    Scheduled 5-Day Roster:")
    for d, m in plan_data["meals"].items():
        print(f"      * {d:<9} | {m['title']:<50} | {m['prep_time_minutes']}m | {m['difficulty_level']}")

    # 5. Recipe Swapping via pgvector Semantic Alternative
    print("\n--- 5. Recipe Swapping via pgvector Cosine Distance ---")
    orig_wed = plan_data["meals"]["Wednesday"]["title"]
    swap_payload = {"day_of_week": "Wednesday", "use_vector_similarity": True}
    st, swapped_plan, dur, _ = api_call(f"/api/meal-plans/{plan_id}/swap", method="POST", payload=swap_payload)
    assert_test("POST /api/meal-plans/{id}/swap Status", st == 200, f"HTTP {st} in {dur}ms")
    new_wed = swapped_plan["meals"]["Wednesday"]["title"]
    assert_test("Meal Successfully Swapped", orig_wed != new_wed or swapped_plan["meals"]["Wednesday"]["is_modified"], f"Original: '{orig_wed}' -> Swapped: '{new_wed}'")

    # 6. Meal Plan Locking & Immutability Enforcement
    print("\n--- 6. Meal Plan Freezing (Locking) & Immutability Verification ---")
    st, locked_plan, dur, _ = api_call(f"/api/meal-plans/{plan_id}/lock", method="POST", payload={"lock": True})
    assert_test("POST /api/meal-plans/{id}/lock Status", st == 200, f"HTTP {st} in {dur}ms")
    assert_test("Plan Status Frozen", locked_plan["is_locked"] is True, "is_locked = True")

    # Attempt mutation on locked plan
    st_err, err_body, dur, _ = api_call(f"/api/meal-plans/{plan_id}/swap", method="POST", payload={"day_of_week": "Monday"})
    assert_test("Locked Plan Swap Rejection", st_err == 400, f"HTTP {st_err} correctly rejected modification: {err_body}")

    # 7. Multi-Store Grocery Arbitrage across Aldi, Walmart, Meijer, Amazon
    print("\n--- 7. Multi-Store Grocery Aggregation & Price Arbitrage ---")
    st, groc_data, dur, _ = api_call(f"/api/meal-plans/{plan_id}/grocery-list", method="GET")
    assert_test("GET /api/meal-plans/{id}/grocery-list Status", st == 200, f"HTTP {st} in {dur}ms")
    
    unique_items = groc_data["total_unique_ingredients"]
    single_cost = groc_data["single_store_cost"]
    split_cost = groc_data["optimal_split_total_cost"]
    savings = groc_data["potential_split_savings"]
    rec_store = groc_data["recommended_single_store"]

    assert_test("Unique Ingredients Extracted", unique_items > 0, f"{unique_items} ingredients consolidated")
    assert_test("All 4 Target Retailers Present", set(groc_data["store_baskets"].keys()) == {"Aldi", "Walmart", "Meijer", "Amazon"}, f"{list(groc_data['store_baskets'].keys())}")
    assert_test("Optimal Split Cost Computed", split_cost > 0, f"${split_cost:.2f}")
    assert_test("Single-Store Recommendation Computed", bool(rec_store) and single_cost > 0, f"{rec_store} (${single_cost:.2f})")
    assert_test("Arbitrage Savings Computed", savings >= 0, f"Savings: ${savings:.2f}")

    print("\n    Store Comparisons:")
    for s, b in groc_data["store_baskets"].items():
        print(f"      * {s:<8}: ${b['total_estimated_cost']:>7.2f} | {b['fulfillment_percentage']:>5.1f}% fulfillment ({b['items_available_count']}/{b['total_needed_count']} in stock)")

    print("\n    Optimal Split Basket Allocation:")
    for s, itms in groc_data["optimal_split_basket"].items():
        sub = sum(x["cost"] for x in itms)
        print(f"      * {s:<8} ({len(itms):>2} items - ${sub:>6.2f}): {', '.join(x['name'] for x in itms[:3])}...")

    # 8. Web Dashboard & Checkable Shopping List Verification
    print("\n--- 8. Web Dashboard Frontend Delivery & Interactive Components ---")
    st_dash, html_body, dur, _ = api_call("/dashboard", method="GET")
    assert_test("GET /dashboard Status", st_dash == 200, f"HTTP {st_dash} ({len(html_body)} bytes) in {dur}ms")
    assert_test("Checkable Live Shopping List Present", "Checkable Live Multi-Store Shopping List" in html_body, "Interactive retail columns")
    assert_test("Persistent LocalStorage Present", "splitbites_checks_" in html_body, "Client-side state sync")
    assert_test("Mobile Notes Clipboard Handlers Present", "copyFullShoppingList" in html_body and "copyStoreShoppingList" in html_body, "One-click copy tools")
    assert_test("Aisle Hide Completed Filter Present", "Hide Completed" in html_body, "Aisle navigation toggle")

    print("\n" + "=" * 75)
    print(f"  🎉 ALL {tests_passed}/{tests_run} INTEGRATION TESTS PASSED OVER HTTPS!")
    print(f"  Host: {TARGET_ENDPOINT}")
    print("=" * 75)

if __name__ == "__main__":
    run_integration_suite()
