#!/usr/bin/env python3
import urllib.request
import ssl
import json
import time
import sys

TARGET_URL = "https://splitbites.tbannon80-hp-mini.stream"
ORIGIN_DOMAIN = "https://splitbites.tbannon80-hp-mini.stream"
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) SplitBitesTunnelTester/1.0"

class TestReport:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def record(self, test_name, success, detail=""):
        if success:
            self.passed += 1
            status_str = "\033[92m[PASS]\033[0m"
        else:
            self.failed += 1
            status_str = "\033[91m[FAIL]\033[0m"
        print(f"  {status_str} {test_name}: {detail}")
        self.results.append((test_name, success, detail))

def execute_http(path, method="GET", headers=None, body=None):
    url = f"{TARGET_URL}{path}"
    req_headers = {
        "User-Agent": USER_AGENT,
        "Origin": ORIGIN_DOMAIN
    }
    if headers:
        req_headers.update(headers)

    data_bytes = None
    if body is not None:
        if isinstance(body, (dict, list)):
            data_bytes = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif isinstance(body, str):
            data_bytes = body.encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
    ctx = ssl.create_default_context()
    start_time = time.time()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            duration_ms = round((time.time() - start_time) * 1000, 1)
            lower_headers = {k.lower(): v for k, v in resp.headers.items()}
            return {
                "status": resp.status,
                "headers": lower_headers,
                "body": resp.read(),
                "duration_ms": duration_ms,
                "error": None
            }
    except urllib.error.HTTPError as e:
        duration_ms = round((time.time() - start_time) * 1000, 1)
        lower_headers = {k.lower(): v for k, v in e.headers.items()}
        return {
            "status": e.code,
            "headers": lower_headers,
            "body": e.read(),
            "duration_ms": duration_ms,
            "error": str(e)
        }
    except Exception as e:
        duration_ms = round((time.time() - start_time) * 1000, 1)
        return {
            "status": 0,
            "headers": {},
            "body": b"",
            "duration_ms": duration_ms,
            "error": str(e)
        }

def run_suite():
    report = TestReport()
    print("=" * 70)
    print(f"  Cloudflare Zero Trust Tunnel & FastAPI CORS Verification Suite")
    print(f"  Endpoint: {TARGET_URL}")
    print("=" * 70)

    # 1. Cloudflare Edge & TLS Verification
    print("\n[Phase 1: Cloudflare Edge Routing & Health Handshake]")
    res = execute_http("/healthz", method="GET")
    report.record(
        "GET /healthz Status",
        res["status"] == 200,
        f"HTTP {res['status']} in {res['duration_ms']}ms"
    )
    is_cf = "cloudflare" in res["headers"].get("server", "").lower()
    cf_ray = res["headers"].get("cf-ray", "N/A")
    report.record(
        "Cloudflare Edge Tunnel Active",
        is_cf,
        f"Server: {res['headers'].get('server')} (CF-Ray: {cf_ray})"
    )
    try:
        payload = json.loads(res["body"].decode("utf-8"))
        healthy = payload.get("status") == "healthy" and payload.get("service") == "splitbites-backend"
        report.record("Service Health Payload", healthy, f"{payload}")
    except Exception as e:
        report.record("Service Health Payload", False, str(e))

    # 2. HEAD Requests for Probe Compatibility
    res_head = execute_http("/healthz", method="HEAD")
    report.record(
        "HEAD /healthz (Uptime Probes)",
        res_head["status"] == 200,
        f"HTTP {res_head['status']} in {res_head['duration_ms']}ms"
    )

    # 3. Web Dashboard Template & Static Routing
    print("\n[Phase 2: Web Dashboard & Interactive Frontend Delivery]")
    dash_res = execute_http("/dashboard", method="GET")
    report.record(
        "GET /dashboard Status",
        dash_res["status"] == 200,
        f"HTTP {dash_res['status']} ({len(dash_res['body'])} bytes) in {dash_res['duration_ms']}ms"
    )
    html_text = dash_res["body"].decode("utf-8", errors="ignore")
    
    report.record(
        "Dashboard HTML: Checkable Shopping List",
        "Checkable Live Multi-Store Shopping List" in html_text,
        "Interactive itemized retail list rendered"
    )
    report.record(
        "Dashboard HTML: LocalStorage State Sync",
        "splitbites_checks_" in html_text,
        "Client-side persistence logic embedded"
    )
    report.record(
        "Dashboard HTML: Mobile Notes Clipboard Handlers",
        "copyFullShoppingList" in html_text and "copyStoreShoppingList" in html_text,
        "Trip and per-store markdown export functions present"
    )
    report.record(
        "Dashboard HTML: In-Store Aisle Filter",
        "Hide Completed" in html_text,
        "Active aisle completion toggle present"
    )

    root_res = execute_http("/", method="HEAD")
    report.record(
        "HEAD / (Root Route Aliasing)",
        root_res["status"] == 200,
        f"HTTP {root_res['status']} in {root_res['duration_ms']}ms"
    )

    # 4. CORS Preflight & Reflection Analysis
    print("\n[Phase 3: CORS Preflight & Cross-Origin Security]")
    preflight_headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type"
    }
    options_res = execute_http("/api/meal-plans/generate", method="OPTIONS", headers=preflight_headers)
    report.record(
        "OPTIONS /api/meal-plans/generate (Preflight)",
        options_res["status"] == 200,
        f"HTTP {options_res['status']} in {options_res['duration_ms']}ms"
    )

    allow_origin = options_res["headers"].get("access-control-allow-origin", "")
    report.record(
        "CORS: Access-Control-Allow-Origin",
        allow_origin in [ORIGIN_DOMAIN, "*"],
        f"Header value: '{allow_origin}'"
    )
    allow_methods = options_res["headers"].get("access-control-allow-methods", "")
    report.record(
        "CORS: Access-Control-Allow-Methods",
        "POST" in allow_methods and "GET" in allow_methods,
        f"Allowed: {allow_methods}"
    )
    allow_creds = options_res["headers"].get("access-control-allow-credentials", "").lower()
    report.record(
        "CORS: Access-Control-Allow-Credentials",
        allow_creds == "true",
        f"Credentials enabled: {allow_creds}"
    )

    # 5. Live Full-Stack End-to-End Flow over Tunnel
    print("\n[Phase 4: Full-Stack API Operations over Cloudflare Tunnel]")
    # Generate Plan
    gen_res = execute_http("/api/meal-plans/generate", method="POST", body={"days_count": 5})
    report.record(
        "POST /api/meal-plans/generate",
        gen_res["status"] == 200,
        f"HTTP {gen_res['status']} in {gen_res['duration_ms']}ms"
    )
    gen_data = json.loads(gen_res["body"].decode("utf-8"))
    plan_id = gen_data["plan_id"]

    # Swap Meal with pgvector similarity
    swap_res = execute_http(f"/api/meal-plans/{plan_id}/swap", method="POST", body={"day_of_week": "Thursday", "use_vector_similarity": True})
    report.record(
        "POST /api/meal-plans/{id}/swap (pgvector)",
        swap_res["status"] == 200,
        f"HTTP {swap_res['status']} in {swap_res['duration_ms']}ms"
    )

    # Lock Plan
    lock_res = execute_http(f"/api/meal-plans/{plan_id}/lock", method="POST", body={"lock": True})
    report.record(
        "POST /api/meal-plans/{id}/lock (Freeze)",
        lock_res["status"] == 200,
        f"HTTP {lock_res['status']} in {lock_res['duration_ms']}ms"
    )

    # Multi-Store Grocery Arbitrage
    groc_res = execute_http(f"/api/meal-plans/{plan_id}/grocery-list", method="GET")
    report.record(
        "GET /api/meal-plans/{id}/grocery-list",
        groc_res["status"] == 200,
        f"HTTP {groc_res['status']} in {groc_res['duration_ms']}ms"
    )
    groc_data = json.loads(groc_res["body"].decode("utf-8"))
    report.record(
        "Grocery Aggregation Metrics Valid",
        groc_data.get("optimal_split_total_cost", 0) > 0 and len(groc_data.get("store_baskets", {})) == 4,
        f"Optimal: ${groc_data.get('optimal_split_total_cost'):.2f}, Stores: {list(groc_data.get('store_baskets', {}).keys())}"
    )

    print("\n" + "=" * 70)
    print(f"  Execution Summary: {report.passed} Passed | {report.failed} Failed")
    print("=" * 70)
    if report.failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_suite()
