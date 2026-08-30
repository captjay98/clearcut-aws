# Upload Capability and Import Artifact Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Safely stage screenplay bytes and finalize immutable import artifacts.  
**Architecture:** One-time capabilities bind scope and expected bytes; object storage and PostgreSQL use staged publication/reconciliation.  
**Tech Stack:** FastAPI, PostgreSQL, GCS, Alembic.

---

**Files:** Create `scripts/domain/artifacts.py`, `scripts/ports/object_storage.py`, `scripts/adapters/gcs.py`, `scripts/adapters/local_storage.py`, `scripts/application/upload_service.py`, `scripts/delivery/http.py`, `services/api/alembic/versions/0004_import_artifacts.py`; test `services/api/tests/scripts/test_upload_capabilities.py`, `tests/security/test_uploads.py`, `tests/conformance/test_object_storage.py`.

1. Write failing tests for scope/key/size/type/hash/nonce/expiry/generation, replay, object swap, MIME/magic/extension, orphan reconciliation, and adapter conformance.
2. Add migration 0004 and staged artifact lifecycle constraints; test upgrade/downgrade.
3. Implement capability/finalization operations, GCS generation preconditions, and local test adapter blocked in production.
4. Run security, integration, migration, and contract suites; expect exit 0 with no partial accepted artifact.
5. Record evidence; commit `feat: add scoped import artifact staging` after authorization.

**Exit:** Server-verified bytes, not browser metadata, determine accepted artifact identity.

