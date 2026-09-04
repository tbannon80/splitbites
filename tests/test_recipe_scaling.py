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

def register_test_user(prefix="scale_test"):
    unique_email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    status, data = make_request(
        f"{BASE_URL}/api/auth/register",
        method="POST",
        payload={
            "email": unique_email,
            "password": "password123",
            "confirm_password": "password123",
            "full_name": "Scale Test User",
            "household_name": "Scale Test Family"
        }
    )
    assert status == 200
    return data["access_token"], data["user"], data["household"]

def test_update_slot_servings_adjusts_db_and_sets_is_modified():
    """a) Test updating slot servings adjusts database record and flags is_modified = True."""
    token, user, household = register_test_user("slot_servings")
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

    first_day = next(iter(plan["meals"]))
    slot = plan["meals"][first_day]
    item_id = slot["item_id"]
    assert item_id is not None
    assert slot.get("servings", 4) == 4

    # Update servings to 6
    status, updated_plan = make_request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/slots/{item_id}/servings",
        method="PATCH",
        payload={"servings": 6},
        token=token
    )
    assert status == 200
    updated_slot = updated_plan["meals"][first_day]
    assert updated_slot["servings"] == 6
    assert updated_slot["is_modified"] is True

    # Test invalid range (servings < 1 or > 20) -> HTTP 422
    for bad_val in [0, -1, 21, 50]:
        req_bad = urllib.request.Request(
            f"{BASE_URL}/api/meal-plans/{plan_id}/slots/{item_id}/servings",
            data=json.dumps({"servings": bad_val}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="PATCH"
        )
        try:
            urllib.request.urlopen(req_bad)
            assert False, f"Expected 422 for servings={bad_val}"
        except urllib.error.HTTPError as e:
            assert e.code == 422

def test_locked_plan_rejects_serving_mutations():
    """b) Test locked plans reject serving mutations with HTTP 400."""
    token, user, household = register_test_user("locked_scale")
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
    first_day = next(iter(plan["meals"]))
    item_id = plan["meals"][first_day]["item_id"]

    # Lock the plan
    status, lock_res = make_request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/lock",
        method="POST",
        payload={"lock": True},
        token=token
    )
    assert status == 200
    assert lock_res["is_locked"] is True

    # Attempt to adjust servings on locked plan -> HTTP 400
    req_locked = urllib.request.Request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/slots/{item_id}/servings",
        data=json.dumps({"servings": 8}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="PATCH"
    )
    try:
        urllib.request.urlopen(req_locked)
        assert False, "Expected HTTP 400 when mutating locked plan servings"
    except urllib.error.HTTPError as e:
        assert e.code == 400

def test_grocery_aggregation_scales_ingredient_quantities_and_costs():
    """c) Test grocery aggregation scales ingredient quantities and store package purchases proportionately."""
    token, user, household = register_test_user("grocery_scale")
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

    # Baseline grocery aggregation (at default 4 servings)
    status, base_groceries = make_request(f"{BASE_URL}/api/meal-plans/{plan_id}/grocery-list")
    assert status == 200
    base_split_cost = base_groceries["optimal_split_total_cost"]

    # Double servings on all slots (from 4 to 8)
    for day, slot in plan["meals"].items():
        make_request(
            f"{BASE_URL}/api/meal-plans/{plan_id}/slots/{slot['item_id']}/servings",
            method="PATCH",
            payload={"servings": 8},
            token=token
        )

    # Scaled grocery aggregation (at 8 servings)
    status, scaled_groceries = make_request(f"{BASE_URL}/api/meal-plans/{plan_id}/grocery-list")
    assert status == 200
    scaled_split_cost = scaled_groceries["optimal_split_total_cost"]

    # Doubled portions require equal or more packages and higher or equal total cost
    assert scaled_split_cost >= base_split_cost

def test_pantry_staple_suppression_remains_accurate_after_scaling():
    """d) Test pantry staple suppression remains accurate after recipe scaling."""
    token, user, household = register_test_user("pantry_scale")
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

    # Baseline groceries
    status, base_groceries = make_request(f"{BASE_URL}/api/meal-plans/{plan_id}/grocery-list")
    assert status == 200
    suppressed_baseline = base_groceries.get("pantry_suppressed_items", [])
    assert len(suppressed_baseline) > 0, "Default staples should be suppressed"

    # Scale first day to 12 servings
    first_day = next(iter(plan["meals"]))
    item_id = plan["meals"][first_day]["item_id"]
    make_request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/slots/{item_id}/servings",
        method="PATCH",
        payload={"servings": 12},
        token=token
    )

    # Check scaled groceries
    status, scaled_groceries = make_request(f"{BASE_URL}/api/meal-plans/{plan_id}/grocery-list")
    assert status == 200
    suppressed_scaled = scaled_groceries.get("pantry_suppressed_items", [])

    # Suppression set must remain preserved
    for item in suppressed_baseline:
        assert item in suppressed_scaled

def test_frontend_serving_stepper_elements():
    """Verify frontend serving stepper controls exist in index.html."""
    req = urllib.request.Request(f"{BASE_URL}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "adjustSlotServings" in html
        assert "servings" in html
        assert "Portion size" in html
        assert "Decrease servings" in html
        assert "Increase servings" in html
