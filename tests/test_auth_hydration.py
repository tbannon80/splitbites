import urllib.request
import urllib.error
import json
from uuid import uuid4

BASE_URL = "http://127.0.0.1:8001"

def test_auth_me_unauthorized():
    # Request without token
    req = urllib.request.Request(f"{BASE_URL}/api/auth/me")
    try:
        urllib.request.urlopen(req)
        assert False, "Expected 401 Unauthorized"
    except urllib.error.HTTPError as e:
        assert e.code == 401

    # Request with invalid token
    req = urllib.request.Request(f"{BASE_URL}/api/auth/me", headers={"Authorization": "Bearer invalid_token"})
    try:
        urllib.request.urlopen(req)
        assert False, "Expected 401 Unauthorized"
    except urllib.error.HTTPError as e:
        assert e.code == 401

def test_serve_dashboard_and_root():
    for path in ["/", "/dashboard"]:
        req = urllib.request.Request(f"{BASE_URL}{path}")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            html = resp.read().decode("utf-8")
            # Verify authScreen is hidden by default to prevent login flashing on hard refresh
            assert 'id="authScreen" class="hidden' in html
            # Verify synchronous authentication script and CSS are present
            assert "html.is-authenticated #authScreen" in html
            assert "splitbites_token" in html
            assert "apiFetch" in html
            assert "loadActiveMealPlan" in html

def test_household_latest_plan_not_found():
    fake_hid = uuid4()
    req = urllib.request.Request(f"{BASE_URL}/api/meal-plans/household/{fake_hid}/latest")
    try:
        urllib.request.urlopen(req)
        assert False, "Expected 404 Not Found"
    except urllib.error.HTTPError as e:
        assert e.code == 404

def test_auth_me_authenticated():
    from app.services.auth import create_access_token
    # Use existing user ID
    token = create_access_token({"sub": "0d38cb28-71ef-4a71-9650-6943f49e6b48", "email": "timothy.bannon@gmail.com"})
    req = urllib.request.Request(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["user"]["email"] == "timothy.bannon@gmail.com"
        assert "household" in data
        assert data["household"]["household_name"] == "The Bannon Family"

def test_household_latest_plan_found():
    # Use household with known meal plan (80ece546-89b7-4ed7-a28e-5804e656b43d)
    req = urllib.request.Request(f"{BASE_URL}/api/meal-plans/household/80ece546-89b7-4ed7-a28e-5804e656b43d/latest")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert "plan_id" in data
        assert "meals" in data
