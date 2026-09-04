import json
import urllib.request
import urllib.error
import pytest
from uuid import uuid4

BASE_URL = "http://127.0.0.1:8001"

def make_request(url, method="GET", payload=None, token=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def register_user(email_prefix="pantry_user"):
    unique_email = f"{email_prefix}_{uuid4().hex[:8]}@example.com"
    status, data = make_request(
        f"{BASE_URL}/api/auth/register",
        method="POST",
        payload={
            "email": unique_email,
            "password": "password123",
            "confirm_password": "password123",
            "full_name": "Pantry Test User",
            "household_name": "Pantry Test Family"
        }
    )
    assert status == 200
    return data["access_token"], data["user"], data["household"]

def test_default_pantry_staples_seeded_on_registration():
    """Verify that 7 default staples are seeded for newly registered households."""
    token, user, household = register_user("seed_test")
    status, staples = make_request(f"{BASE_URL}/api/pantry/", token=token)
    assert status == 200
    assert len(staples) == 7

    names = [s["item_name"] for s in staples]
    expected = ["All-Purpose Flour", "Black Pepper", "Garlic Powder", "Granulated Sugar", "Olive Oil", "Salt", "Vegetable Oil"]
    for exp in expected:
        assert exp in names
    for s in staples:
        assert s["is_in_stock"] is True

def test_pantry_staples_crud():
    """a) Test CRUD operations on household pantry items."""
    token, user, household = register_user("crud_test")

    # 1. Add new staple
    status, new_item = make_request(
        f"{BASE_URL}/api/pantry/",
        method="POST",
        payload={"item_name": "Dijon Mustard", "is_in_stock": True},
        token=token
    )
    assert status == 201
    assert new_item["item_name"] == "Dijon Mustard"
    assert new_item["is_in_stock"] is True
    pantry_id = new_item["pantry_id"]

    # 2. Verify list contains new item
    status, staples = make_request(f"{BASE_URL}/api/pantry/", token=token)
    assert status == 200
    assert any(s["pantry_id"] == pantry_id and s["item_name"] == "Dijon Mustard" for s in staples)

    # 3. Toggle stock status to False
    status, updated = make_request(
        f"{BASE_URL}/api/pantry/{pantry_id}",
        method="PATCH",
        payload={"is_in_stock": False},
        token=token
    )
    assert status == 200
    assert updated["is_in_stock"] is False

    # 4. Toggle back to True
    status, toggled = make_request(
        f"{BASE_URL}/api/pantry/{pantry_id}",
        method="PATCH",
        payload={"is_in_stock": True},
        token=token
    )
    assert status == 200
    assert toggled["is_in_stock"] is True

    # 5. Delete staple
    status, del_res = make_request(
        f"{BASE_URL}/api/pantry/{pantry_id}",
        method="DELETE",
        token=token
    )
    assert status == 200
    assert del_res["pantry_id"] == pantry_id

    # 6. Verify item is removed
    status, remaining = make_request(f"{BASE_URL}/api/pantry/", token=token)
    assert not any(s["pantry_id"] == pantry_id for s in remaining)

def test_pantry_multi_tenant_isolation():
    """d) Multi-tenant isolation: User A cannot view, update, or delete User B's pantry items."""
    token_a, user_a, household_a = register_user("user_a")
    token_b, user_b, household_b = register_user("user_b")

    # User A creates a unique staple
    status, item_a = make_request(
        f"{BASE_URL}/api/pantry/",
        method="POST",
        payload={"item_name": "User A Private Sauce", "is_in_stock": True},
        token=token_a
    )
    assert status == 201
    pantry_id_a = item_a["pantry_id"]

    # User B lists pantry - User A's staple must not appear
    status, staples_b = make_request(f"{BASE_URL}/api/pantry/", token=token_b)
    assert not any(s["pantry_id"] == pantry_id_a for s in staples_b)
    assert not any(s["item_name"] == "User A Private Sauce" for s in staples_b)

    # User B attempts to patch User A's item -> 404
    req_patch = urllib.request.Request(
        f"{BASE_URL}/api/pantry/{pantry_id_a}",
        data=json.dumps({"is_in_stock": False}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token_b}"},
        method="PATCH"
    )
    try:
        urllib.request.urlopen(req_patch)
        assert False, "Expected 404 for cross-tenant patch"
    except urllib.error.HTTPError as e:
        assert e.code == 404

    # User B attempts to delete User A's item -> 404
    req_del = urllib.request.Request(
        f"{BASE_URL}/api/pantry/{pantry_id_a}",
        headers={"Authorization": f"Bearer {token_b}"},
        method="DELETE"
    )
    try:
        urllib.request.urlopen(req_del)
        assert False, "Expected 404 for cross-tenant delete"
    except urllib.error.HTTPError as e:
        assert e.code == 404

def test_in_stock_pantry_suppression_and_reappearance():
    """b & c) In-stock pantry items are excluded from grocery list & baskets, and reappear when marked out of stock."""
    token, user, household = register_user("grocery_suppress")
    household_id = household["household_id"]

    # Generate a meal plan for this household
    status, plan = make_request(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": household_id},
        token=token
    )
    assert status == 200
    plan_id = plan["plan_id"]

    # 1. Fetch groceries with all default staples in stock
    status, grocery_data_in_stock = make_request(f"{BASE_URL}/api/meal-plans/{plan_id}/grocery-list")
    assert status == 200
    suppressed_in_stock = grocery_data_in_stock.get("pantry_suppressed_items", [])
    assert len(suppressed_in_stock) > 0, "Expected at least one ingredient (e.g. Salt, Olive Oil) to be suppressed"

    # Verify none of the suppressed items appear in any store basket or optimal split basket
    for store, basket in grocery_data_in_stock["store_baskets"].items():
        available_names = [it["name"].lower() for it in basket.get("available_items_sample", [])]
        for sup in suppressed_in_stock:
            assert sup.lower() not in available_names

    for store, items in grocery_data_in_stock["optimal_split_basket"].items():
        split_names = [it["name"].lower() for it in items]
        for sup in suppressed_in_stock:
            assert sup.lower() not in split_names

    cost_in_stock = grocery_data_in_stock["optimal_split_total_cost"]

    # 2. Find "Salt" or "Olive Oil" in the household's pantry and mark it is_in_stock = False
    status, staples = make_request(f"{BASE_URL}/api/pantry/", token=token)
    salt_staple = next((s for s in staples if s["item_name"].lower() == "salt"), None)
    assert salt_staple is not None

    make_request(
        f"{BASE_URL}/api/pantry/{salt_staple['pantry_id']}",
        method="PATCH",
        payload={"is_in_stock": False},
        token=token
    )

    # 3. Re-fetch groceries: Salt should now NOT be suppressed if used in the meals
    status, grocery_data_out_of_stock = make_request(f"{BASE_URL}/api/meal-plans/{plan_id}/grocery-list")
    assert status == 200
    suppressed_out = grocery_data_out_of_stock.get("pantry_suppressed_items", [])

    # If the recipes contained "Salt", it must now be un-suppressed and appear in the list
    if any(s.lower() == "salt" for s in suppressed_in_stock):
        assert not any(s.lower() == "salt" for s in suppressed_out)
        # Cost with Salt needing to be purchased should be >= cost when suppressed
        assert grocery_data_out_of_stock["optimal_split_total_cost"] >= cost_in_stock

def test_frontend_pantry_ui_elements():
    """Verify frontend pantry elements and functions exist in index.html."""
    req = urllib.request.Request(f"{BASE_URL}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert 'id="btnPantryModal"' in html
        assert 'id="pantryModal"' in html
        assert 'id="pantrySuppressedNotice"' in html
        assert 'id="pantrySuppressedCountText"' in html
        assert 'id="pantrySuppressedList"' in html
        assert 'id="pantryItemsContainer"' in html
        assert 'openPantryModal' in html
        assert 'closePantryModal' in html
        assert 'loadPantryItems' in html
        assert 'togglePantryItem' in html
        assert 'deletePantryItem' in html
        assert 'handleAddPantryItem' in html
