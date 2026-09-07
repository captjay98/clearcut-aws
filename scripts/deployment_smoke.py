#!/usr/bin/env python3
"""Provider-free smoke checks for the unified ClearCut runtime."""

import argparse
import json
import sys
import time
import urllib.request
from typing import Any


def test_endpoint(url: str, expected_status: int = 200, retries: int = 2) -> dict[str, Any]:
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, method="GET")
        request.add_header("User-Agent", "ClearCut-Deployment-Smoke/1.0")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = response.getcode()
                body = response.read().decode("utf-8")
                if status != expected_status:
                    print(
                        f"❌ FAIL: GET {url} returned HTTP {status}, expected {expected_status}",
                        file=sys.stderr,
                        flush=True,
                    )
                    raise SystemExit(1)
                print(f"✅ PASS: GET {url} -> HTTP {status}", flush=True)
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return {"raw": body}
        except Exception as error:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            print(
                f"❌ ERROR: GET {url} failed after {retries + 1} attempts: {error}",
                file=sys.stderr,
                flush=True,
            )
            raise SystemExit(1) from error
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description="ClearCut Deployment Smoke Gate")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Base URL of candidate service",
    )
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    print("==================================================")
    print(f"Running ClearCut Smoke Gate on: {base_url}")
    print("==================================================")

    public_site = test_endpoint(f"{base_url}/")
    assert "<html" in public_site.get("raw", "").lower(), "Invalid public site response"

    workspace = test_endpoint(f"{base_url}/app/")
    assert "<html" in workspace.get("raw", "").lower(), "Invalid workspace response"

    health = test_endpoint(f"{base_url}/api/v1/healthz")
    assert health.get("status") == "ok", "Invalid healthz response"

    openapi = test_endpoint(f"{base_url}/api/openapi.json")
    assert "paths" in openapi, "Invalid OpenAPI schema"

    print("\n🎉 ALL 4 DEPLOYMENT SMOKE GATES PASSED! Revision is healthy and verified.\n")


if __name__ == "__main__":
    main()
