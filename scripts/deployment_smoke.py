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


def validate_deployment_health(health: dict[str, Any], *, expected_profile: str | None) -> None:
    """Fail closed when a hosted candidate reports local or non-durable adapters."""
    assert health.get("status") == "ok", "Invalid healthz response"
    if expected_profile is None:
        return

    deployment = health.get("deployment")
    assert isinstance(deployment, dict), "Missing redacted deployment attestation"
    assert deployment.get("profile") == expected_profile, "Expected GCP deployment profile"
    if expected_profile == "gcp":
        assert deployment.get("databaseConfigured") is True, "GCP database is not configured"
        assert deployment.get("storageAdapter") in {"gcs", "s3"}, (
            "GCP storage must be hosted and non-ephemeral"
        )
        assert deployment.get("dispatchAdapter") == "cloud_tasks", (
            "GCP dispatch must use Cloud Tasks"
        )
        assert deployment.get("dispatchEnabled") is True, "GCP dispatch must remain enabled"
        assert deployment.get("secretBackend") == "secret_manager", (
            "GCP secrets must use Secret Manager"
        )
        dispatch = health.get("jobDispatch")
        assert dispatch == {"mode": "cloud_tasks", "durable": True}, (
            "GCP job dispatch must be durable"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="ClearCut Deployment Smoke Gate")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Base URL of candidate service",
    )
    parser.add_argument(
        "--expected-profile",
        choices=("gcp",),
        default=None,
        help="Require a redacted hosted runtime attestation before promotion",
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
    validate_deployment_health(health, expected_profile=args.expected_profile)

    openapi = test_endpoint(f"{base_url}/api/openapi.json")
    assert "paths" in openapi, "Invalid OpenAPI schema"

    print("\n🎉 ALL 4 DEPLOYMENT SMOKE GATES PASSED! Revision is healthy and verified.\n")


if __name__ == "__main__":
    main()
