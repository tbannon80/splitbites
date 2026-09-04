import json
import urllib.request
import urllib.error
import pytest
from uuid import uuid4

from app.services.cook_mode import (
    TIMER_REGEX,
    extract_timer_durations,
    normalize_instruction_steps,
)

BASE_URL = "http://127.0.0.1:8001"

def make_request(url, method="GET", payload=None, token=None):
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def test_frontend_cook_mode_delivery():
    """a) Test endpoint delivering static frontend contains Cook Mode modal, wake lock bindings, and timer logic."""
    for path in ["/", "/dashboard"]:
        req = urllib.request.Request(f"{BASE_URL}{path}")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")

            # Check modal and key UI element IDs
            assert 'id="cookModeModal"' in html
            assert 'id="cookModeTitle"' in html
            assert 'id="cookModeWakeLockBadge"' in html
            assert 'id="cookTimersDock"' in html
            assert 'id="cookIngredientsDrawer"' in html
            assert 'id="cookStepProgressBar"' in html
            assert 'id="cookStepText"' in html
            assert 'id="cookStepTimersContainer"' in html
            assert 'id="btnCookPrevStep"' in html
            assert 'id="btnCookNextStep"' in html

            # Check Cook Mode JavaScript and Screen Wake Lock bindings
            assert "navigator.wakeLock.request" in html
            assert "requestCookWakeLock" in html
            assert "releaseCookWakeLock" in html
            assert "visibilitychange" in html

            # Check Timers & Audio chime engine
            assert "AudioContext" in html
            assert "playTimerChime" in html
            assert "startCookTimer" in html
            assert "pauseCookTimer" in html
            assert "resumeCookTimer" in html
            assert "resetCookTimer" in html
            assert "dismissCookTimer" in html
            assert "tickCookTimers" in html

            # Check step navigation and shortcuts
            assert "openCookMode" in html
            assert "closeCookMode" in html
            assert "setCookStep" in html
            assert "nextCookStep" in html
            assert "prevCookStep" in html
            assert "ArrowRight" in html
            assert "openCookModeForScheduledMeal" in html
            assert "openCookModeForRecipe" in html

def test_instruction_steps_normalization():
    """b) Test instruction parsing utility handles JSON step arrays, list of strings, and raw newline strings."""
    # 1. JSON step array of dicts
    dict_steps = [
        {"step": 1, "text": "Preheat oven to 400°F (200°C)."},
        {"step": 2, "text": "Season salmon fillets with salt and pepper."},
        {"step": 3, "text": "Bake for 12 to 15 minutes."}
    ]
    norm1 = normalize_instruction_steps(dict_steps)
    assert len(norm1) == 3
    assert norm1[0] == {"step": 1, "text": "Preheat oven to 400°F (200°C)."}
    assert norm1[2] == {"step": 3, "text": "Bake for 12 to 15 minutes."}

    # 2. List of raw strings
    str_steps = [
        "Chop onions and garlic finely.",
        "Sauté in olive oil until translucent.",
        "Simmer for 20 minutes."
    ]
    norm2 = normalize_instruction_steps(str_steps)
    assert len(norm2) == 3
    assert norm2[0]["step"] == 1
    assert norm2[0]["text"] == "Chop onions and garlic finely."
    assert norm2[2]["step"] == 3
    assert norm2[2]["text"] == "Simmer for 20 minutes."

    # 3. Raw newline-delimited string with numbers
    newline_str = "1. Bring water to a boil.\n2. Add pasta and cook for 10 minutes.\n3. Drain and serve."
    norm3 = normalize_instruction_steps(newline_str)
    assert len(norm3) == 3
    assert norm3[0]["step"] == 1
    assert norm3[0]["text"] == "Bring water to a boil."
    assert norm3[1]["step"] == 2
    assert norm3[1]["text"] == "Add pasta and cook for 10 minutes."
    assert norm3[2]["step"] == 3
    assert norm3[2]["text"] == "Drain and serve."

    # 4. Empty and null inputs
    assert normalize_instruction_steps([]) == []
    assert normalize_instruction_steps("") == []
    assert normalize_instruction_steps(None) == []

def test_timer_durations_extraction():
    """c) Verify time extraction regex reliably identifies minutes and hours across diverse phrasing."""
    # Minutes phrasing
    text_min = "Simmer the sauce for 15 minutes, stirring occasionally."
    timers_min = extract_timer_durations(text_min)
    assert len(timers_min) == 1
    assert timers_min[0]["minutes"] == 15
    assert timers_min[0]["seconds"] == 900
    assert timers_min[0]["label"] == "15m"

    # Abbreviated mins & ranges
    text_range = "Bake in preheated oven for 25-30 mins until golden."
    timers_range = extract_timer_durations(text_range)
    assert len(timers_range) == 1
    assert timers_range[0]["minutes"] == 25
    assert timers_range[0]["seconds"] == 1500
    assert timers_range[0]["label"] == "25m"

    # 'to' syntax
    text_to = "Sear steaks about 3 to 4 minutes per side."
    timers_to = extract_timer_durations(text_to)
    assert len(timers_to) == 1
    assert timers_to[0]["minutes"] == 3
    assert timers_to[0]["seconds"] == 180

    # Hours phrasing
    text_hr = "Roast in oven for 1 hour until tender."
    timers_hr = extract_timer_durations(text_hr)
    assert len(timers_hr) == 1
    assert timers_hr[0]["minutes"] == 60
    assert timers_hr[0]["seconds"] == 3600
    assert timers_hr[0]["label"] == "1h"

    # Fractional hours
    text_frac_hr = "Slow cook chili for 1.5 hours on low."
    timers_frac = extract_timer_durations(text_frac_hr)
    assert len(timers_frac) == 1
    assert timers_frac[0]["minutes"] == 90
    assert timers_frac[0]["seconds"] == 5400
    assert timers_frac[0]["label"] == "1.5h"

    # Multiple distinct durations in a single text
    text_multi = "Rest dough for 10 minutes. Then bake for 25 mins and cool for 1 hour."
    timers_multi = extract_timer_durations(text_multi)
    assert len(timers_multi) == 3
    minutes_found = [t["minutes"] for t in timers_multi]
    assert 10 in minutes_found
    assert 25 in minutes_found
    assert 60 in minutes_found

    # Non-timer text
    text_none = "Whisk eggs with a fork until smooth and fluffy."
    assert extract_timer_durations(text_none) == []
    assert extract_timer_durations("") == []

def test_meal_plan_payload_includes_instructions_and_ingredients():
    """Verify that active meal plan format response includes instructions and ingredients for instant Cook Mode."""
    # Use known household with active meal plan
    req = urllib.request.Request(f"{BASE_URL}/api/meal-plans/household/0cd6b528-48ac-4b49-b3aa-1c27ef410479/latest")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "meals" in data
        assert len(data["meals"]) > 0

        for day, meal in data["meals"].items():
            assert "instructions" in meal
            assert isinstance(meal["instructions"], list)
            assert "ingredients" in meal
            assert isinstance(meal["ingredients"], list)
            assert "servings" in meal
