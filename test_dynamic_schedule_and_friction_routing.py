import urllib.request
import urllib.error
import json
import pytest

BASE_URL = "http://127.0.0.1:8001"

def http_req(url, method="GET", payload=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def test_default_7_day_generation():
    """Verify that default meal plan generation creates a standard 7-day week (Monday - Sunday)."""
    status, plan = http_req(f"{BASE_URL}/api/meal-plans/generate", method="POST", payload={})
    assert status == 200
    assert plan["status"] == "success"
    assert plan["plan_type"] == "Standard 7-Day Week"
    expected_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert len(plan["meals"]) == 7
    for day in expected_days:
        assert day in plan["meals"], f"Missing day {day} in generated plan"
        assert plan["meals"][day]["recipe_id"] is not None
        assert plan["meals"][day]["title"] != ""
        assert "fallback_applied" in plan["meals"][day]

def test_day_subtraction_and_custom_subsets():
    """Verify generating custom subsets of days, adding days, and subtracting days."""
    # 1. Custom 3-day weekend plan
    custom_days = ["Friday", "Saturday", "Sunday"]
    status, plan = http_req(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"target_days": custom_days}
    )
    assert status == 200
    assert len(plan["meals"]) == 3
    assert set(plan["meals"].keys()) == set(custom_days)
    assert plan["plan_type"] == "3-Day Schedule"
    plan_id = plan["plan_id"]

    # 2. Subtract day (Sunday)
    sub_status, sub_plan = http_req(
        f"{BASE_URL}/api/meal-plans/{plan_id}/subtract-day",
        method="POST",
        payload={"day_of_week": "Sunday"}
    )
    assert sub_status == 200
    assert len(sub_plan["meals"]) == 2
    assert "Sunday" not in sub_plan["meals"]
    assert "Friday" in sub_plan["meals"]
    assert "Saturday" in sub_plan["meals"]

    # 3. Add day (Thursday)
    add_status, add_plan = http_req(
        f"{BASE_URL}/api/meal-plans/{plan_id}/add-day",
        method="POST",
        payload={"day_of_week": "Thursday"}
    )
    assert add_status == 200
    assert len(add_plan["meals"]) == 3
    assert "Thursday" in add_plan["meals"]

    # 4. Batch adjust days (5-day workweek)
    batch_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    batch_status, batch_plan = http_req(
        f"{BASE_URL}/api/meal-plans/{plan_id}/days",
        method="POST",
        payload={"target_days": batch_days}
    )
    assert batch_status == 200
    assert len(batch_plan["meals"]) == 5
    assert set(batch_plan["meals"].keys()) == set(batch_days)

def test_schedule_aware_busy_routing_and_fallback():
    """Verify schedule-aware prep-time routing on busy days and fallback degradation."""
    # 1. Create household with busy days (Tuesday, Thursday) with prep ceiling <= 20 min
    h_payload = {
        "household_name": "Fast Weeknights Family",
        "busy_days": ["Tuesday", "Thursday"],
        "busy_max_prep_minutes": 20
    }
    h_status, household = http_req(f"{BASE_URL}/api/households/", method="POST", payload=h_payload)
    assert h_status == 200
    hid = household["household_id"]
    assert household["busy_days"] == ["Tuesday", "Thursday"]
    assert household["busy_max_prep_minutes"] == 20

    # 2. Generate plan for this household
    p_status, plan = http_req(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"household_id": hid}
    )
    assert p_status == 200
    plan_id = plan["plan_id"]

    # Tuesday and Thursday must respect prep_time_minutes <= 20
    tue_prep = plan["meals"]["Tuesday"]["prep_time_minutes"]
    thu_prep = plan["meals"]["Thursday"]["prep_time_minutes"]
    assert tue_prep <= 20, f"Tuesday prep time {tue_prep}m exceeds 20m ceiling"
    assert thu_prep <= 20, f"Thursday prep time {thu_prep}m exceeds 20m ceiling"
    assert plan["meals"]["Tuesday"]["fallback_applied"] is False
    assert plan["meals"]["Thursday"]["fallback_applied"] is False

    # 3. Swap Tuesday meal automatically -> must continue respecting prep <= 20m
    swap_status, swap_plan = http_req(
        f"{BASE_URL}/api/meal-plans/{plan_id}/swap",
        method="POST",
        payload={"day_of_week": "Tuesday", "use_vector_similarity": True}
    )
    assert swap_status == 200
    assert swap_plan["meals"]["Tuesday"]["prep_time_minutes"] <= 20
    assert swap_plan["meals"]["Tuesday"]["fallback_applied"] is False

    # 4. Explicit swap to a 35-min recipe on Tuesday must fail with HTTP 400
    # Fetch a high-prep recipe ID
    _, recipes = http_req(f"{BASE_URL}/api/recipes/")
    high_prep_recipe = next((r for r in recipes if r.get("prep_time_minutes", 0) > 20), None)
    assert high_prep_recipe is not None

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        http_req(
            f"{BASE_URL}/api/meal-plans/{plan_id}/swap",
            method="POST",
            payload={"day_of_week": "Tuesday", "new_recipe_id": high_prep_recipe["recipe_id"]}
        )
    assert exc_info.value.code == 400

    # 5. Fallback degradation: impossible ceiling (e.g. 5 min where no recipe <= 5m exists)
    fb_status, fb_plan = http_req(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={
            "household_id": hid,
            "busy_days": ["Wednesday"],
            "busy_max_prep_minutes": 5,
            "target_days": ["Monday", "Wednesday", "Friday"]
        }
    )
    assert fb_status == 200
    wed_meal = fb_plan["meals"]["Wednesday"]
    # Graceful fallback selects lowest available prep recipe (15 min) and marks fallback_applied=True
    assert wed_meal["fallback_applied"] is True
    assert wed_meal["prep_time_minutes"] == 15

def test_locked_plan_immutability():
    """Verify that a locked meal plan rejects any modifications (swap, shuffle, add/subtract day) with HTTP 400."""
    # 1. Generate and lock plan
    _, plan = http_req(f"{BASE_URL}/api/meal-plans/generate", method="POST", payload={})
    plan_id = plan["plan_id"]

    lock_status, locked_plan = http_req(
        f"{BASE_URL}/api/meal-plans/{plan_id}/lock",
        method="POST",
        payload={"lock": True}
    )
    assert lock_status == 200
    assert locked_plan["is_locked"] is True

    # 2. Attempt swap on locked plan
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        http_req(f"{BASE_URL}/api/meal-plans/{plan_id}/swap", method="POST", payload={"day_of_week": "Monday"})
    assert exc_info.value.code == 400

    # 3. Attempt shuffle on locked plan
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        http_req(f"{BASE_URL}/api/meal-plans/{plan_id}/shuffle", method="POST", payload={})
    assert exc_info.value.code == 400

    # 4. Attempt add day on locked plan
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        http_req(f"{BASE_URL}/api/meal-plans/{plan_id}/add-day", method="POST", payload={"day_of_week": "Saturday"})
    assert exc_info.value.code == 400

    # 5. Attempt subtract day on locked plan
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        http_req(f"{BASE_URL}/api/meal-plans/{plan_id}/subtract-day", method="POST", payload={"day_of_week": "Monday"})
    assert exc_info.value.code == 400

    # 6. Attempt update days on locked plan
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        http_req(f"{BASE_URL}/api/meal-plans/{plan_id}/days", method="POST", payload={"target_days": ["Monday", "Tuesday"]})
    assert exc_info.value.code == 400

def test_grocery_aggregation_dynamic_schedules():
    """Verify multi-store grocery aggregation computes accurate basket totals across dynamic schedules."""
    # Generate 7-day plan
    _, plan7 = http_req(f"{BASE_URL}/api/meal-plans/generate", method="POST", payload={})
    status7, g7 = http_req(f"{BASE_URL}/api/meal-plans/{plan7['plan_id']}/grocery-list")
    assert status7 == 200
    assert g7["total_unique_ingredients"] > 0
    assert "store_baskets" in g7
    assert "optimal_split_basket" in g7
    assert set(g7["store_baskets"].keys()) == {"Aldi", "Walmart", "Meijer", "Amazon"}

    # Generate 3-day plan
    _, plan3 = http_req(
        f"{BASE_URL}/api/meal-plans/generate",
        method="POST",
        payload={"target_days": ["Friday", "Saturday", "Sunday"]}
    )
    status3, g3 = http_req(f"{BASE_URL}/api/meal-plans/{plan3['plan_id']}/grocery-list")
    assert status3 == 200
    assert g3["total_unique_ingredients"] > 0
    assert "store_baskets" in g3
    assert "optimal_split_basket" in g3
