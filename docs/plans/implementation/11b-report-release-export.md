# Report Release, Rendering, and Download Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Release a frozen snapshot separately and provide reproducible authorized HTML/PDF downloads.  
**Architecture:** Release is a governed attestation; subsequent download is a read; rendering uses pinned deterministic inputs.  
**Tech Stack:** HTML/CSS print renderer, PDF tooling, PostgreSQL, GCS.

---

**Files:** Create `export/domain/releases.py`, `export/application/release_report.py`, `export/adapters/html_pdf_renderer.py`, `export/delivery/http.py`, `services/api/alembic/versions/0021_report_releases.py`, `services/api/tests/fixtures/reports/`; test `services/api/tests/reports/test_release.py`, `test_renderer_determinism.py`, `test_download_authorization.py`.

1. Add failing release-only copy/intent, attestation, stale version, snapshot immutability, supersession, canonical manifest, pinned font/metadata/timezone, and download authorization/expiry tests.
2. Add migration 0021; implement release transaction, exhibits/open items/legal boundary, deterministic renderer, and read-only download.
3. Run golden HTML/PDF/semantic hash/migration/contract tests; expect no live-state read after snapshot and no regeneration on release.
4. Record evidence; commit `feat: add governed report release and export` after authorization.

**Exit:** Release never regenerates and authorized downloads never read mutable live report state.
