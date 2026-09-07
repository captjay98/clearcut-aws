# Deadline application adapters implementation plan

**Goal:** Select real object storage and secret adapters and bound paid provider calls without contacting providers during verification.

**Architecture:** Preserve the existing ObjectStoragePort contract, injecting SDK clients into GCS and S3 adapters and translating remote errors to redacted typed exceptions. Resolve named secrets from explicit environment, host-mounted files, or Secret Manager references without fallback. Require explicit paid-provider opt-in and enforce process-wide concurrency at the actual client call boundary.

**Tech stack:** Python, pytest, Google Cloud Storage and Secret Manager clients, boto3.

Approved by coordinator for the existing `feat/deadline-gcp-adapters` child. Firebase, PostgreSQL dispatch, cloud resources and Terraform are excluded.

1. Baseline: `uv run pytest services/api/tests -q`; record existing failures separately.
2. Storage RED: add `services/api/tests/adapters/test_remote_storage.py` proving binary round trips, missing versus unavailable objects, key validation, bounded SDK options, injected factories and redaction. Run before implementation.
3. Storage GREEN: implement `scripts/adapters/remote_storage.py` and `bootstrap/storage.py`, wire `create_app`, pin only imported SDK dependencies, rerun focused tests and commit.
4. Secrets RED: add `services/api/tests/bootstrap/test_secrets.py` for explicit source selection, missing/invalid sources, typed redacted values and provider exceptions. Run before implementing `bootstrap/secrets.py` and runtime integration; rerun and commit.
5. Paid providers RED: add `services/api/tests/bootstrap/test_paid_providers.py` proving default denial, validated limits, shared concurrency and release after exceptions/cancellation with fake clients. Implement settings, client-bound controls and runtime factory guards; rerun and commit.
6. Verify: focused tests, full API tests, Ruff and Pyright; scan dependencies if a scanner is available. Record exact commands, outcomes, remaining constraints and coherent commit IDs in the handoff report.

Examples of the intended boundaries:

```python
storage = build_object_storage(settings.storage, client=fake_client)
await storage.put_object('org/project/script', b'screenplay', 'text/plain')
secret = resolver.resolve('PARALLEL_API_KEY')  # SecretStr; explicit reveal at SDK boundary
with gate.acquire('parallel'):
    response = client.post(url, json=payload)
```
