import urllib.request
import json

base_url = "http://127.0.0.1:8001/api/meal-plans"

def test_customization_and_groceries():
    print("--- Testing Meal Plan Customization & Multi-Store Grocery Aggregation ---")
    
    # 1. Generate meal plan
    req = urllib.request.Request(f"{base_url}/generate", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        plan = json.loads(resp.read().decode())

    plan_id = plan["plan_id"]
    print(f"1. Generated Plan ID: {plan_id}")
    print(f"   Original Wednesday Meal: {plan['meals']['Wednesday']['title']}")
    print(f"   Is Locked: {plan['is_locked']}")

    # 2. Swap Wednesday meal using pgvector semantic alternative
    swap_payload = json.dumps({"day_of_week": "Wednesday", "use_vector_similarity": True}).encode()
    req = urllib.request.Request(f"{base_url}/{plan_id}/swap", data=swap_payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        swapped_plan = json.loads(resp.read().decode())

    print(f"2. Swapped Wednesday Meal: {swapped_plan['meals']['Wednesday']['title']}")
    print(f"   Is Modified Flag: {swapped_plan['meals']['Wednesday']['is_modified']}")

    # 3. Lock meal plan
    lock_payload = json.dumps({"lock": True}).encode()
    req = urllib.request.Request(f"{base_url}/{plan_id}/lock", data=lock_payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        locked_plan = json.loads(resp.read().decode())

    print(f"3. Locked Plan Status: is_locked = {locked_plan['is_locked']}")

    # 4. Attempt to swap on locked plan (expect 400 Bad Request)
    try:
        req = urllib.request.Request(f"{base_url}/{plan_id}/swap", data=swap_payload, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req)
        print("4. ERROR: Swap on locked plan should have failed!")
    except urllib.error.HTTPError as e:
        print(f"4. Expected Error on Locked Swap: HTTP {e.code} - {e.read().decode()}")

    # 5. Grocery Aggregation across Aldi, Walmart, Meijer, Amazon
    req = urllib.request.Request(f"{base_url}/{plan_id}/grocery-list", method="GET")
    with urllib.request.urlopen(req) as resp:
        groceries = json.loads(resp.read().decode())

    print(f"\n5. Multi-Store Grocery Aggregation Results:")
    print(f"   Total Unique Ingredients: {groceries['total_unique_ingredients']}")
    print(f"   Recommended Single Store: {groceries['recommended_single_store']} (${groceries['single_store_cost']:.2f})")
    print(f"   Optimal Split Basket Cost: ${groceries['optimal_split_total_cost']:.2f}")
    print(f"   Potential Multi-Store Savings: ${groceries['potential_split_savings']:.2f}")
    print(f"\n   Store-by-Store Comparison:")
    for store, data in groceries['store_baskets'].items():
        print(f"     * {store:<7}: ${data['total_estimated_cost']:>6.2f} | {data['fulfillment_percentage']}% fulfillment ({data['items_available_count']}/{data['total_needed_count']} items in stock)")

    print(f"\n   Optimal Multi-Store Split Basket Summary:")
    for store, items in groceries['optimal_split_basket'].items():
        item_names = [it['name'] for it in items[:3]]
        sample_str = ", ".join(item_names) + ("..." if len(items) > 3 else "")
        store_subtotal = sum(it['cost'] for it in items)
        print(f"     * Buy at {store:<7} ({len(items):>2} items, subtotal: ${store_subtotal:>5.2f}): {sample_str}")

def test_shuffle():
    print("\n--- Testing Meal Plan Shuffle ---")
    req = urllib.request.Request(f"{base_url}/generate", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        plan = json.loads(resp.read().decode())
    plan_id = plan["plan_id"]
    
    # Swap Friday
    swap_payload = json.dumps({"day_of_week": "Friday", "use_vector_similarity": True}).encode()
    req = urllib.request.Request(f"{base_url}/{plan_id}/swap", data=swap_payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        swapped = json.loads(resp.read().decode())
    friday_title = swapped["meals"]["Friday"]["title"]
    print(f"Friday modified to: {friday_title}")

    # Shuffle with preserve_modified=True
    shuf_payload = json.dumps({"preserve_modified": True}).encode()
    req = urllib.request.Request(f"{base_url}/{plan_id}/shuffle", data=shuf_payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        shuffled = json.loads(resp.read().decode())
    
    assert shuffled["meals"]["Friday"]["title"] == friday_title, "Modified Friday meal should be preserved during shuffle"
    print(f"Shuffle succeeded! Friday preserved: {shuffled['meals']['Friday']['title']}")

if __name__ == "__main__":
    test_customization_and_groceries()
    test_shuffle()

