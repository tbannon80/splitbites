#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error
import argparse

DEFAULT_API_URL = "http://127.0.0.1:8001"

AVAILABLE_DIETARY_TAGS = [
    "gluten-free",
    "dairy-free",
    "high-protein",
    "vegetarian",
    "vegan",
    "keto",
    "low-carb",
    "pescatarian",
    "quick",
]

def print_header(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)

def api_post(endpoint, payload, base_url=DEFAULT_API_URL):
    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def api_get(endpoint, base_url=DEFAULT_API_URL):
    url = f"{base_url}{endpoint}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def run_loop(interactive=False, base_url=DEFAULT_API_URL):
    print_header("🥑 SplitBites End-to-End Meal Planning & Grocery Aggregator")
    print(f"Target API Endpoint: {base_url}")

    # 1. Onboarding Household
    print_header("Step 1: Household Onboarding & Dietary Preferences")
    if interactive:
        name_input = input("Enter Household Name [default: The Bannon Homelab]: ").strip()
        h_name = name_input if name_input else "The Bannon Homelab"

        print("\nAvailable Dietary Preferences:")
        for idx, tag in enumerate(AVAILABLE_DIETARY_TAGS, 1):
            print(f"  [{idx}] {tag}")
        selected_input = input("\nEnter comma-separated numbers (e.g. 1,2 for gluten-free, dairy-free) [default: 1,2]: ").strip()

        if selected_input:
            chosen_indices = [int(i.strip()) for i in selected_input.split(",") if i.strip().isdigit()]
            prefs = [AVAILABLE_DIETARY_TAGS[i - 1] for i in chosen_indices if 1 <= i <= len(AVAILABLE_DIETARY_TAGS)]
        else:
            prefs = ["gluten-free", "dairy-free"]
    else:
        h_name = "The Bannon Homelab"
        prefs = ["gluten-free", "dairy-free"]

    print(f"\n[+] Registering household: '{h_name}' with dietary preferences: {prefs}...")
    h_data = api_post("/api/households/", {"household_name": h_name, "dietary_preferences": prefs}, base_url)
    h_id = h_data["household_id"]
    print(f"  ✓ Household Created: {h_data['household_name']} (ID: {h_id})")
    print(f"  ✓ Registered Dietary Constraints: {h_data['dietary_preferences']}")

    # 2. Generating Meal Plan
    print_header("Step 2: Monday-Friday Meal Plan (pgvector Semantic Optimization)")
    print(f"[+] Querying /api/meal-plans/generate with restrictions: {prefs}...")
    gen_payload = {
        "household_id": h_id,
        "dietary_tags": prefs,
        "days_count": 5
    }
    plan = api_post("/api/meal-plans/generate", gen_payload, base_url)
    plan_id = plan["plan_id"]
    print(f"  ✓ Plan ID: {plan_id} (Week: {plan['week_start_date']}, Locked: {plan['is_locked']})")
    print("\n  Generated Schedule (Respecting Dietary Restrictions):")
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    for day in days:
        meal = plan["meals"].get(day)
        if meal:
            print(f"    * {day:<9} | {meal['title']:<38} | {meal['prep_time_minutes']}m | {meal['difficulty_level']}")

    # 3. Swapping a Meal
    print_header("Step 3: Recipe Swapping (pgvector Cosine Similarity Match)")
    swap_day = "Wednesday"
    if interactive:
        day_input = input(f"Select day to swap (Monday-Friday) [default: {swap_day}]: ").strip().capitalize()
        if day_input in days:
            swap_day = day_input

    orig_meal = plan["meals"][swap_day]["title"]
    print(f"\n[+] Swapping {swap_day} meal from '{orig_meal}' using pgvector alternative...")
    swap_res = api_post(f"/api/meal-plans/{plan_id}/swap", {"day_of_week": swap_day, "use_vector_similarity": True}, base_url)
    new_meal = swap_res["meals"][swap_day]["title"]
    print(f"  ✓ {swap_day} swapped successfully!")
    print(f"    - Original: '{orig_meal}'")
    print(f"    - New     : '{new_meal}' (Modified Flag: {swap_res['meals'][swap_day]['is_modified']})")

    # 4. Locking the Meal Plan
    print_header("Step 4: Locking Meal Plan for Procurement")
    print(f"[+] Freezing meal plan {plan_id}...")
    locked_plan = api_post(f"/api/meal-plans/{plan_id}/lock", {"lock": True}, base_url)
    print(f"  ✓ Plan Locked: is_locked = {locked_plan['is_locked']}")

    # Verify locked constraint
    print("[+] Verifying locked immutability: attempting swap on locked plan...")
    try:
        api_post(f"/api/meal-plans/{plan_id}/swap", {"day_of_week": "Friday"}, base_url)
        print("  ✗ Warning: Swap should have been blocked on locked plan!")
    except urllib.error.HTTPError as e:
        print(f"  ✓ Immutability Verified: HTTP {e.code} correctly rejected swap ({e.reason})")

    # 5. Multi-Store Grocery Aggregation
    print_header("Step 5: Multi-Store Grocery Aggregation & Price Arbitrage")
    print(f"[+] Aggregating required ingredients for plan {plan_id} across Aldi, Walmart, Meijer, Amazon...")
    groceries = api_get(f"/api/meal-plans/{plan_id}/grocery-list", base_url)

    print(f"\n  Summary Metrics:")
    print(f"    * Total Unique Ingredients Needed : {groceries['total_unique_ingredients']}")
    print(f"    * Optimal Multi-Store Split Cost  : ${groceries['optimal_split_total_cost']:.2f}")
    print(f"    * Best 1-Stop Store Pick          : {groceries['recommended_single_store']} (${groceries['single_store_cost']:.2f})")
    print(f"    * Potential Multi-Store Savings   : \033[92m${groceries['potential_split_savings']:.2f}\033[0m")

    print("\n  Retailer Comparison Overview:")
    print(f"    {'Retailer':<10} | {'Est. Cost':<10} | {'Fulfillment':<12} | {'Items In Stock':<15}")
    print("    " + "-" * 55)
    for store, data in groceries["store_baskets"].items():
        print(f"    {store:<10} | ${data['total_estimated_cost']:>8.2f} | {data['fulfillment_percentage']:>10.1f}% | {data['items_available_count']}/{data['total_needed_count']}")

    print("\n  Optimal Split-Basket Shopping Breakdown:")
    for store, items in groceries["optimal_split_basket"].items():
        subtotal = sum(it["cost"] for it in items)
        print(f"\n    🏬 Buy at {store.upper()} ({len(items)} items - Subtotal: ${subtotal:.2f}):")
        for item in items[:6]:
            print(f"       • {item['name']} ({item['quantity']} {item['unit']}) - ${item['cost']:.2f}")
        if len(items) > 6:
            print(f"       ... and {len(items) - 6} more items")

    print_header("✅ End-to-End Loop Complete!")
    print(f"Web Dashboard available at: {base_url}/dashboard")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SplitBites Homelab CLI Client")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive prompt mode")
    parser.add_argument("--url", default=DEFAULT_API_URL, help=f"Backend API URL (default: {DEFAULT_API_URL})")
    args = parser.parse_args()

    run_loop(interactive=args.interactive, base_url=args.url)
