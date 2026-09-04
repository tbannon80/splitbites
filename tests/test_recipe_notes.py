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
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"detail": body}

def register_test_user(prefix="recipe_note"):
    unique_email = f"{prefix}_{uuid4().hex[:8]}@example.com"
    status, data = make_request(
        f"{BASE_URL}/api/auth/register",
        method="POST",
        payload={
            "email": unique_email,
            "password": "password123",
            "confirm_password": "password123",
            "full_name": "Recipe Note User",
            "household_name": "Recipe Note Household"
        }
    )
    assert status == 200
    return data["access_token"], data["user"], data["household"]

def get_any_recipe_id(token):
    status, recipes = make_request(f"{BASE_URL}/api/recipes/", token=token)
    assert status == 200
    assert len(recipes) > 0
    return recipes[0]["recipe_id"]

def test_recipe_notes_crud():
    """Verify CRUD lifecycle for personal kitchen notes and 5-star ratings."""
    token, user, household = register_test_user("crud_note")
    recipe_id = get_any_recipe_id(token)

    # 1. Initial note state is empty
    status, initial_note = make_request(f"{BASE_URL}/api/recipes/{recipe_id}/note", token=token)
    assert status == 200
    assert initial_note["note_text"] == ""
    assert initial_note["rating"] is None

    # 2. Upsert note and 5-star rating
    note_payload = {
        "note_text": "Family loves extra parmesan on top!",
        "rating": 5
    }
    status, upserted = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload=note_payload,
        token=token
    )
    assert status == 200
    assert upserted["note_text"] == "Family loves extra parmesan on top!"
    assert upserted["rating"] == 5
    assert upserted["recipe_id"] == recipe_id
    assert upserted["household_id"] == household["household_id"]

    # 3. GET /api/recipes/{recipe_id}/note confirms updated note
    status, fetched_note = make_request(f"{BASE_URL}/api/recipes/{recipe_id}/note", token=token)
    assert status == 200
    assert fetched_note["note_text"] == "Family loves extra parmesan on top!"
    assert fetched_note["rating"] == 5

    # 4. GET /api/recipes/{recipe_id} includes personal_note and user_rating
    status, recipe_detail = make_request(f"{BASE_URL}/api/recipes/{recipe_id}", token=token)
    assert status == 200
    assert recipe_detail["personal_note"] == "Family loves extra parmesan on top!"
    assert recipe_detail["user_rating"] == 5

    # 5. GET /api/recipes/ (catalog) includes personal_note and user_rating
    status, catalog = make_request(f"{BASE_URL}/api/recipes/", token=token)
    assert status == 200
    matched = [r for r in catalog if r["recipe_id"] == recipe_id]
    assert len(matched) == 1
    assert matched[0]["personal_note"] == "Family loves extra parmesan on top!"
    assert matched[0]["user_rating"] == 5

    # 6. Clear rating while updating text
    update_payload = {
        "note_text": "Updated: bake 5 mins less",
        "rating": None
    }
    status, updated = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload=update_payload,
        token=token
    )
    assert status == 200
    assert updated["note_text"] == "Updated: bake 5 mins less"
    assert updated["rating"] is None

def test_recipe_notes_rating_boundaries():
    """Verify validation boundaries: ratings must be between 1 and 5, or None."""
    token, user, household = register_test_user("boundary_note")
    recipe_id = get_any_recipe_id(token)

    # Rating 0 -> reject with 422
    status, err_0 = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload={"note_text": "Invalid rating 0", "rating": 0},
        token=token
    )
    assert status == 422

    # Rating 6 -> reject with 422
    status, err_6 = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload={"note_text": "Invalid rating 6", "rating": 6},
        token=token
    )
    assert status == 422

    # Rating -1 -> reject with 422
    status, err_neg = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload={"note_text": "Invalid negative rating", "rating": -1},
        token=token
    )
    assert status == 422

    # Boundary valid 1 -> accept with 200
    status, ok_1 = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload={"note_text": "Minimum valid rating", "rating": 1},
        token=token
    )
    assert status == 200
    assert ok_1["rating"] == 1

    # Boundary valid 5 -> accept with 200
    status, ok_5 = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload={"note_text": "Maximum valid rating", "rating": 5},
        token=token
    )
    assert status == 200
    assert ok_5["rating"] == 5

def test_recipe_notes_multi_tenant_isolation():
    """Verify strict multi-tenant isolation: notes and ratings are private per household."""
    token_a, user_a, household_a = register_test_user("tenant_a")
    token_b, user_b, household_b = register_test_user("tenant_b")
    recipe_id = get_any_recipe_id(token_a)

    # Household A adds private note and rating
    status, _ = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload={"note_text": "Household A secret spice blend", "rating": 4},
        token=token_a
    )
    assert status == 200

    # Household B checks note for same recipe -> should be empty
    status, note_b = make_request(f"{BASE_URL}/api/recipes/{recipe_id}/note", token=token_b)
    assert status == 200
    assert note_b["note_text"] == ""
    assert note_b["rating"] is None

    # Household B views recipe detail -> personal_note and user_rating are None
    status, detail_b = make_request(f"{BASE_URL}/api/recipes/{recipe_id}", token=token_b)
    assert status == 200
    assert detail_b["personal_note"] is None
    assert detail_b["user_rating"] is None

    # Household B adds their own note and rating
    status, _ = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload={"note_text": "Household B adds extra garlic", "rating": 2},
        token=token_b
    )
    assert status == 200

    # Household A still sees their own note and rating intact
    status, note_a_check = make_request(f"{BASE_URL}/api/recipes/{recipe_id}/note", token=token_a)
    assert status == 200
    assert note_a_check["note_text"] == "Household A secret spice blend"
    assert note_a_check["rating"] == 4

    # Household B sees their own note and rating intact
    status, note_b_check = make_request(f"{BASE_URL}/api/recipes/{recipe_id}/note", token=token_b)
    assert status == 200
    assert note_b_check["note_text"] == "Household B adds extra garlic"
    assert note_b_check["rating"] == 2

def test_recipe_notes_in_meal_plan_and_cook_mode():
    """Verify that active meal plan items include household personal notes and ratings."""
    token, user, household = register_test_user("plan_note")
    hid = household["household_id"]

    # 1. Generate weekly meal plan
    status, plan = make_request(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": hid},
        token=token
    )
    assert status == 200
    meals = plan["meals"]
    assert len(meals) > 0

    first_day = list(meals.keys())[0]
    recipe_id = meals[first_day]["recipe_id"]

    # 2. Attach personal note & rating to the recipe in first day
    status, _ = make_request(
        f"{BASE_URL}/api/recipes/{recipe_id}/note",
        method="PUT",
        payload={"note_text": "Prep ingredients the night before!", "rating": 5},
        token=token
    )
    assert status == 200

    # 3. Fetch latest active meal plan
    status, latest_plan = make_request(
        f"{BASE_URL}/api/meal-plans/household/{hid}/latest",
        token=token
    )
    assert status == 200
    assert latest_plan["meals"][first_day]["personal_note"] == "Prep ingredients the night before!"
    assert latest_plan["meals"][first_day]["user_rating"] == 5
