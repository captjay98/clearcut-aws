#!/usr/bin/env python3
"""ClearCut Deployment Smoke Gate Test.

Verifies health, OpenAPI schema, live PostgreSQL queries, screenplay delivery,
and decision recording against a deployed Cloud Run candidate or local service.
"""
import argparse
import sys
import urllib.request
import json
import time

def test_endpoint(url: str, expected_status: int = 200, method: str = "GET", data: bytes = None, retries: int = 2) -> dict:
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("User-Agent", "ClearCut-Deployment-Smoke/1.0")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                status = response.getcode()
                body = response.read().decode("utf-8")
                if status != expected_status:
                    print(f"❌ FAIL: {method} {url} returned HTTP {status}, expected {expected_status}", file=sys.stderr, flush=True)
                    sys.exit(1)
                print(f"✅ PASS: {method} {url} -> HTTP {status}", flush=True)
                try:
                    return json.loads(body)
                except Exception:
                    return {"raw": body}
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            print(f"❌ ERROR: {method} {url} failed after {retries + 1} attempts: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="ClearCut Deployment Smoke Gate")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base URL of candidate service")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    print(f"==================================================")
    print(f"Running ClearCut Smoke Gate on: {base_url}")
    print(f"==================================================")

    # 1. Healthcheck
    health = test_endpoint(f"{base_url}/api/v1/healthz")
    assert health.get("status") == "ok", "Invalid healthz response"

    # 2. OpenAPI JSON specification
    openapi = test_endpoint(f"{base_url}/openapi.json")
    assert "paths" in openapi, "Invalid OpenAPI schema"

    # 3. Organizations list (from PostgreSQL)
    orgs = test_endpoint(f"{base_url}/api/v1/organizations")
    assert len(orgs.get("data", [])) > 0, "No organizations returned from DB"

    # 4. Clearance items list (from PostgreSQL)
    items = test_endpoint(f"{base_url}/api/v1/organizations/northlight/projects/borrowed-light/items")
    assert len(items.get("data", [])) >= 10, "Expected at least 10 items from PostgreSQL"

    # 5. Screenplay AST delivery (from PostgreSQL)
    script = test_endpoint(f"{base_url}/api/v1/organizations/northlight/projects/borrowed-light/script")
    assert len(script.get("data", {}).get("scenes", [])) >= 7, "Expected 7 scenes from PostgreSQL"

    # 6. Decision mutation (persists to PostgreSQL)
    decision_payload = json.dumps({
        "item_id": "CC-101",
        "decision": "accepted",
        "rationale": "Automated deployment smoke test verification",
        "actor": "Smoke Bot"
    }).encode("utf-8")
    decision = test_endpoint(
        f"{base_url}/api/v1/organizations/northlight/projects/borrowed-light/items/CC-101/decisions",
        expected_status=201,
        method="POST",
        data=decision_payload
    )
    assert decision.get("data", {}).get("db_persisted") is True, "Decision was not persisted to DB"

    # 7. Audit records ledger (from PostgreSQL)
    records = test_endpoint(f"{base_url}/api/v1/organizations/northlight/records")
    assert len(records.get("data", [])) > 0, "No audit events returned from DB"

    print("\n🎉 ALL 7 DEPLOYMENT SMOKE GATES PASSED! Revision is healthy and verified.\n")

if __name__ == "__main__":
    main()
