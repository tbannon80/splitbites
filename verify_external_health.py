#!/usr/bin/env python3
import urllib.request
import ssl
import json
import sys

EXTERNAL_URL = "https://splitbites.tbannon80-hp-mini.stream"
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 SplitBitesVerifier/1.2"

def request_external(path, method="GET", data=None):
    url = f"{EXTERNAL_URL}{path}"
    headers = {"User-Agent": USER_AGENT}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
        return resp.status, resp.read()

def run_verification():
    print(f"================================================================")
    print(f"  SplitBites External HTTPS Health Check & Validation")
    print(f"  Domain: {EXTERNAL_URL}")
    print(f"================================================================")

    # 1. Healthz probe
    print("\n1. Probing /healthz (GET & HEAD)...")
    status_get, body_get = request_external("/healthz", method="GET")
    assert status_get == 200, f"Expected 200, got {status_get}"
    health_data = json.loads(body_get.decode("utf-8"))
    assert health_data.get("status") == "healthy", "Service status not healthy"
    print(f"   ✓ GET /healthz returned HTTP 200: {health_data}")

    status_head, _ = request_external("/healthz", method="HEAD")
    assert status_head == 200, f"Expected 200 on HEAD, got {status_head}"
    print(f"   ✓ HEAD /healthz returned HTTP 200")

    # 2. Web Dashboard & Static Assets
    print("\n2. Probing /dashboard and / (HTML & Checkable Grocery Template)...")
    status_dash, body_dash = request_external("/dashboard", method="GET")
    assert status_dash == 200
    html = body_dash.decode("utf-8")
    print(f"   ✓ GET /dashboard returned HTTP 200 ({len(body_dash)} bytes)")

    # Assertions for grocery list & clipboard & localStorage features
    print("   ✓ Validating Interactive UI Components in HTML template:")
    assert "Checkable Live Multi-Store Shopping List" in html
    print("     - Checkable live multi-store shopping list view: PRESENT")
    assert "splitbites_checks_" in html
    print("     - Persistent client-side storage (localStorage): PRESENT")
    assert "copyFullShoppingList" in html and "copyStoreShoppingList" in html
    print("     - Mobile notes one-click copy functions (Full trip & Per-store): PRESENT")
    assert "Hide Completed" in html
    print("     - In-store aisle filtering (Hide Completed): PRESENT")
    assert "splitbites.tbannon80-hp-mini.stream" in html
    print("     - External domain header badge: PRESENT")

    # 3. Live API Flow over HTTPS
    print("\n3. Testing End-to-End API Routing over HTTPS...")
    # Generate a draft plan
    gen_status, gen_body = request_external(
        "/api/meal-plans/generate",
        method="POST",
        data={"dietary_tags": ["gluten-free", "dairy-free"], "days_count": 5}
    )
    assert gen_status == 200
    plan_data = json.loads(gen_body.decode("utf-8"))
    plan_id = plan_data["plan_id"]
    print(f"   ✓ POST /api/meal-plans/generate -> Plan ID: {plan_id}")

    # Grocery aggregation query
    g_status, g_body = request_external(f"/api/meal-plans/{plan_id}/grocery-list", method="GET")
    assert g_status == 200
    g_data = json.loads(g_body.decode("utf-8"))
    print(f"   ✓ GET /api/meal-plans/{plan_id}/grocery-list -> {g_data['total_unique_ingredients']} ingredients")
    print(f"     * Optimal Split Basket: ${g_data['optimal_split_total_cost']:.2f}")
    print(f"     * Stores mapped: {list(g_data['store_baskets'].keys())}")

    print("\n================================================================")
    print("  ✅ All External HTTPS Probes & Feature Assertions PASSED!")
    print("  SplitBites backend is 100% reachable externally.")
    print("================================================================")

if __name__ == "__main__":
    run_verification()
