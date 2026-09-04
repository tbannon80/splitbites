import json
import urllib.request
import urllib.error
import pytest
from uuid import uuid4
from app.services.auth import create_access_token

BASE_URL = "http://127.0.0.1:8001"
TEST_USER_ID = "0d38cb28-71ef-4a71-9650-6943f49e6b48"
TEST_USER_EMAIL = "timothy.bannon@gmail.com"
TEST_HOUSEHOLD_ID = "0cd6b528-48ac-4b49-b3aa-1c27ef410479"

QUICK_RECIPE_ID = "928e2265-1cad-4cc7-a467-081176438c9a"  # 15m prep <= 20m ceiling
LONG_RECIPE_ID = "b1c3d301-5982-4a6e-afc2-8d905ade0048"   # 35m prep > 20m ceiling

def get_auth_token():
    return create_access_token({
        "sub": TEST_USER_ID,
        "email": TEST_USER_EMAIL,
        "hid": TEST_HOUSEHOLD_ID
    })

def make_request(url, method="GET", payload=None, token=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def ensure_test_household_schedule():
    # Ensure test household has Tuesday & Thursday busy with 20m max prep
    token = get_auth_token()
    make_request(
        f"{BASE_URL}/api/households/{TEST_HOUSEHOLD_ID}/schedule",
        method="PUT",
        payload={"busy_days": ["Tuesday", "Thursday"], "busy_max_prep_minutes": 20},
        token=token
    )

def test_assign_valid_recipe_sets_is_modified():
    """a) Test assigning a valid recipe to a scheduled day sets is_modified = True."""
    ensure_test_household_schedule()
    token = get_auth_token()

    # Generate active meal plan for household
    status, plan = make_request(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": TEST_HOUSEHOLD_ID},
        token=token
    )
    assert status == 200
    plan_id = plan["plan_id"]

    # Assign quick recipe to Monday (non-busy day)
    assign_payload = [{
        "day_of_week": "Monday",
        "recipe_id": QUICK_RECIPE_ID,
        "force": False
    }]
    status, updated = make_request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/assign-slots",
        method="POST",
        payload=assign_payload,
        token=token
    )
    assert status == 200
    monday_slot = updated["meals"]["Monday"]
    assert monday_slot["recipe_id"] == QUICK_RECIPE_ID
    assert monday_slot["is_modified"] is True

def test_locked_plan_rejection():
    """b) Test locked plan rejection (HTTP 400)."""
    ensure_test_household_schedule()
    token = get_auth_token()

    # Generate plan
    status, plan = make_request(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": TEST_HOUSEHOLD_ID},
        token=token
    )
    plan_id = plan["plan_id"]

    # Lock plan
    lock_status, _ = make_request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/lock",
        method="POST",
        payload={"lock": True},
        token=token
    )
    assert lock_status == 200

    # Attempt assignment on locked plan
    assign_payload = [{
        "day_of_week": "Wednesday",
        "recipe_id": QUICK_RECIPE_ID,
        "force": False
    }]
    try:
        make_request(
            f"{BASE_URL}/api/meal-plans/{plan_id}/assign-slots",
            method="POST",
            payload=assign_payload,
            token=token
        )
        assert False, "Expected HTTP 400 Bad Request on locked plan"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        body = json.loads(e.read().decode("utf-8"))
        assert "locked" in body["detail"].lower()

def test_busy_day_prep_ceiling_violation_and_force_override():
    """c) Test busy day prep ceiling violation (HTTP 422) and override with force=True."""
    ensure_test_household_schedule()
    token = get_auth_token()

    # Generate plan
    status, plan = make_request(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": TEST_HOUSEHOLD_ID},
        token=token
    )
    plan_id = plan["plan_id"]

    # 1. Attempt assigning long recipe (35m) to Tuesday (busy day, max 20m) without force
    busy_payload = [{
        "day_of_week": "Tuesday",
        "recipe_id": LONG_RECIPE_ID,
        "force": False
    }]
    try:
        make_request(
            f"{BASE_URL}/api/meal-plans/{plan_id}/assign-slots",
            method="POST",
            payload=busy_payload,
            token=token
        )
        assert False, "Expected HTTP 422 Unprocessable Entity for prep ceiling violation"
    except urllib.error.HTTPError as e:
        assert e.code == 422
        body = json.loads(e.read().decode("utf-8"))
        detail = body["detail"]
        assert detail.get("error") == "prep_ceiling_exceeded"
        assert detail.get("force_required") is True
        assert detail.get("prep_time_minutes") == 35
        assert detail.get("busy_max_prep_minutes") == 20

    # 2. Override with force=True -> must succeed with HTTP 200
    force_payload = [{
        "day_of_week": "Tuesday",
        "recipe_id": LONG_RECIPE_ID,
        "force": True
    }]
    status, updated = make_request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/assign-slots",
        method="POST",
        payload=force_payload,
        token=token
    )
    assert status == 200
    tuesday_slot = updated["meals"]["Tuesday"]
    assert tuesday_slot["recipe_id"] == LONG_RECIPE_ID
    assert tuesday_slot["is_modified"] is True

def test_shuffle_preserves_manually_assigned_slots():
    """d) Test shuffle preserves manually assigned slots."""
    ensure_test_household_schedule()
    token = get_auth_token()

    # Generate plan
    status, plan = make_request(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": TEST_HOUSEHOLD_ID},
        token=token
    )
    plan_id = plan["plan_id"]

    # Assign recipe to Monday and Thursday (with force)
    make_request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/assign-slots",
        method="POST",
        payload=[
            {"day_of_week": "Monday", "recipe_id": QUICK_RECIPE_ID, "force": False},
            {"day_of_week": "Thursday", "recipe_id": LONG_RECIPE_ID, "force": True}
        ],
        token=token
    )

    # Perform multiple shuffles to guarantee stability
    for _ in range(3):
        status, shuffled = make_request(
            f"{BASE_URL}/api/meal-plans/{plan_id}/shuffle",
            method="POST",
            payload={"preserve_modified": True},
            token=token
        )
        assert status == 200
        # Preserved slots must not change
        assert shuffled["meals"]["Monday"]["recipe_id"] == QUICK_RECIPE_ID
        assert shuffled["meals"]["Monday"]["is_modified"] is True
        assert shuffled["meals"]["Thursday"]["recipe_id"] == LONG_RECIPE_ID
        assert shuffled["meals"]["Thursday"]["is_modified"] is True

def test_frontend_ui_elements():
    """Verify frontend modal and buttons for slot assignment exist in index.html."""
    req = urllib.request.Request(f"{BASE_URL}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "Add to Active Plan" in html
        assert 'id="assignSlotModal"' in html
        assert 'id="assignModalDaySelect"' in html
        assert 'id="assignModalBusyWarning"' in html
        assert 'id="btnConfirmAssignSlot"' in html
        assert "openAssignRecipeModal" in html
        assert "confirmAssignSlot" in html
