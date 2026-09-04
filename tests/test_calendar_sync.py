import json
import urllib.request
import urllib.error
from uuid import uuid4
from app.services.auth import create_access_token

BASE_URL = "http://127.0.0.1:8001"
TEST_HOUSEHOLD_ID = "80ece546-89b7-4ed7-a28e-5804e656b43d"
TEST_USER_ID = "0d38cb28-71ef-4a71-9650-6943f49e6b48"
TEST_USER_EMAIL = "timothy.bannon@gmail.com"

def get_household_token(household_id: str) -> str:
    req = urllib.request.Request(f"{BASE_URL}/api/households/{household_id}")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["calendar_feed_token"]

def get_latest_plan_id(household_id: str) -> str:
    req = urllib.request.Request(f"{BASE_URL}/api/meal-plans/household/{household_id}/latest")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["plan_id"]

def test_calendar_feed_success():
    feed_token = get_household_token(TEST_HOUSEHOLD_ID)
    assert feed_token, "Household must have a valid calendar_feed_token"

    req = urllib.request.Request(f"{BASE_URL}/api/meal-plans/feed/{feed_token}/calendar.ics")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "text/calendar" in content_type
        assert "inline" in content_disp
        assert 'filename="meal-plan.ics"' in content_disp

        raw_bytes = resp.read()
        body = raw_bytes.decode("utf-8")

        # Verify RFC 5545 CRLF line endings
        assert b"\r\n" in raw_bytes

        # Verify RFC 5545 structure
        assert "BEGIN:VCALENDAR" in body
        assert "END:VCALENDAR" in body
        assert "VERSION:2.0" in body
        assert "PRODID:" in body
        assert "BEGIN:VEVENT" in body
        assert "SUMMARY:Dinner:" in body
        assert "DTSTART:" in body
        assert "DTEND:" in body
        assert "UID:" in body
        assert "DESCRIPTION:" in body
        assert "STATUS:CONFIRMED" in body
        assert "END:VEVENT" in body

def test_calendar_feed_invalid_token():
    req = urllib.request.Request(f"{BASE_URL}/api/meal-plans/feed/invalid_random_token_99999/calendar.ics")
    try:
        urllib.request.urlopen(req)
        assert False, "Expected 404 for invalid feed token"
    except urllib.error.HTTPError as e:
        assert e.code == 404

def test_calendar_token_regeneration_and_invalidation():
    # 1. Fetch initial token and verify feed works
    old_token = get_household_token(TEST_HOUSEHOLD_ID)
    req_old = urllib.request.Request(f"{BASE_URL}/api/meal-plans/feed/{old_token}/calendar.ics")
    with urllib.request.urlopen(req_old) as resp:
        assert resp.status == 200

    # 2. Trigger token regeneration
    regen_req = urllib.request.Request(
        f"{BASE_URL}/api/households/{TEST_HOUSEHOLD_ID}/regenerate-calendar-token",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(regen_req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        new_token = data["calendar_feed_token"]
        assert new_token != old_token
        assert len(new_token) > 20

    # 3. Old token MUST return 404
    try:
        urllib.request.urlopen(req_old)
        assert False, "Expected old token to be invalidated and return 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404

    # 4. New token MUST return 200
    req_new = urllib.request.Request(f"{BASE_URL}/api/meal-plans/feed/{new_token}/calendar.ics")
    with urllib.request.urlopen(req_new) as resp:
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert "BEGIN:VCALENDAR" in body

def test_direct_export_unauthorized():
    plan_id = get_latest_plan_id(TEST_HOUSEHOLD_ID)
    req = urllib.request.Request(f"{BASE_URL}/api/meal-plans/{plan_id}/export.ics")
    try:
        urllib.request.urlopen(req)
        assert False, "Expected 401 Unauthorized for direct export without token"
    except urllib.error.HTTPError as e:
        assert e.code == 401

def test_direct_export_authorized_bearer():
    plan_id = get_latest_plan_id(TEST_HOUSEHOLD_ID)
    token = create_access_token({"sub": TEST_USER_ID, "email": TEST_USER_EMAIL, "hid": TEST_HOUSEHOLD_ID})

    req = urllib.request.Request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/export.ics",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content_type = resp.headers.get("Content-Type", "")
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "text/calendar" in content_type
        assert "attachment" in content_disp
        assert f'filename="splitbites-meal-plan-{plan_id}.ics"' in content_disp

        body = resp.read().decode("utf-8")
        assert "BEGIN:VCALENDAR" in body
        assert "SUMMARY:Dinner:" in body
        assert "END:VCALENDAR" in body

def test_direct_export_authorized_query_param():
    plan_id = get_latest_plan_id(TEST_HOUSEHOLD_ID)
    token = create_access_token({"sub": TEST_USER_ID, "email": TEST_USER_EMAIL, "hid": TEST_HOUSEHOLD_ID})

    req = urllib.request.Request(
        f"{BASE_URL}/api/meal-plans/{plan_id}/export.ics?token={token}"
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        content_disp = resp.headers.get("Content-Disposition", "")
        assert f'filename="splitbites-meal-plan-{plan_id}.ics"' in content_disp

def test_frontend_calendar_integration():
    req = urllib.request.Request(f"{BASE_URL}/")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert 'id="btnSyncCalendar"' in html
        assert 'id="calendarModal"' in html
        assert 'id="calendarWebcalUrl"' in html
        assert 'id="calendarHttpsUrl"' in html
        assert 'id="btnRegenerateToken"' in html
        assert 'id="btnDownloadIcs"' in html
        assert "webcal://" in html
        assert "openCalendarModal" in html
        assert "closeCalendarModal" in html
        assert "regenerateCalendarToken" in html
        assert "downloadPlanIcs" in html
