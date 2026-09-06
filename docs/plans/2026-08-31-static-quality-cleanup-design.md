# Repository-Wide Static Quality Cleanup Design

**Date:** 2026-08-31
**Branch:** feat/rebuild-a
**Goal:** Drive `uv run ruff check services/api/src services/api/tests services/api/alembic/versions tests` and `uv run pyright services/api/src services/api/tests` to zero diagnostics without suppressing checks, without changing runtime behavior, and without weakening tenant scope or governance. No commits.

## Constraints (approach A)

- Fix all 67 diagnostics (35 Ruff, 32 Pyright); no `# noqa`, no `# type: ignore`, no per-file check disables.
- Preserve public API JSON field names (wire contract) via Pydantic aliases.
- Retain every authentication / organization-membership / project-ownership check.
- Add no new dependencies.
- Keep all changes uncommitted.

## Ruff (35 → 0)

1. **Mechanical (23):** targeted `ruff check --fix` (safe fixes only) for I001 import ordering, F401 unused imports, and W293 whitespace-only lines in `decisions/delivery/http.py`, `items/delivery/http.py`, `monitoring/delivery/http.py`, `identity/adapters/sql_repository.py`, `organizations/adapters/sql_repository.py`, `projects/adapters/sql_repository.py`, `tests/decisions/test_decision_audit_pipeline.py`, `tests/identity/test_sql_sessions.py`, and `tests/foundation/test_web_runtime_boundary.py`. Removals are genuinely unused.
2. **B904 exception chaining (5):** add `raise ... from None` to the UUID `ValueError` → 404 handlers in `decisions/delivery/http.py` (1) and `items/delivery/http.py` (4), matching existing research delivery style. Status/body unchanged.
3. **F841 unused authorization binding (2):** in `monitoring/delivery/http.py`, keep the mandatory `await get_request_scope(...)` side effect (session auth + org membership + project ownership); drop only the unused local binding. Never delete the call.
4. **N815 public camelCase (5):** convert `items/delivery/http.py` request models (`assignedToUserId`, `targetRole`, `parentCommentId`, `originalText`, `proposedText`) to snake_case attributes with `Field(alias=...)`, preserving wire JSON. Pattern already used in `scripts/delivery/http.py`.

## Pyright (32 → 0)

1. **Cookie-policy tests (9):** the scheme-aware `_session_cookie_policy` emits `clearcut_session` on HTTP and `__Host-clearcut_session` only on HTTPS. Single-user tests (decisions, export, research, scripts) rely on `AsyncClient` cookie retention — remove redundant manual get/set. `organizations/test_tenant_isolation.py` genuinely switches identities — keep captured cookie values, add non-None assertions, then `set()`.
2. **`main.py` SPA closure (4):** narrow `web_dist_env: str | None` to a non-null `Path` once before defining `serve_spa`; close over the `Path`.
3. **`research/delivery/http.py` scope (2):** add a fail-closed guard (or typed project-scope helper) yielding non-optional `org_id`/`project_id` before constructing `EnqueueJob`. Keep membership/ownership checks and item filter by item+org+project. `EnqueueJob` stays strict.
4. **`identity/delivery/http.py` return type (1):** type the register conflict path as `dict[...] | JSONResponse` with `response_model=None`.
5. **SQLAlchemy typing (8):** `cast(CursorResult[Any], ...)` around the two DML results before `.rowcount` in `sql_import_repository.py`; import `IntegrityError` from `sqlalchemy.exc` and `event` from `sqlalchemy` directly in the import repo and `tests/architecture/test_migrated_runtime_schema.py`; add a `TypedDict` for the mutable scene accumulator so `scene["page"]` is `int | None`.
6. **`test_sql_sessions.py` (1):** tighten `SessionService.get_session_context` return to non-optional `SessionContextDto` (matches implementation), or assert locally. Prefer tightening the contract.
7. **`test_provider_selection.py` (7):** assert against concrete `VertexDetectionRuntime` / `VertexJudgeAdapter` (isinstance + concrete config) rather than adding `project`/`location`/`model` to `ModelRuntimePort` / `JudgePort`.

## Validation

Re-run the two exact static commands after each logical group; then focused Task 7 suite, full API suite (excluding separately-run architecture), architecture suite (DATABASE_URL unset), `pnpm verify`, web build, and contract drift. Independent semantic review of the cleanup diff.

## Rejected alternatives

- Global `ruff --fix --unsafe-fixes`: risks semantic edits (e.g. renaming contract fields).
- Optional UUID casts / broad `Any` / expanding provider protocols: hide real type gaps or contaminate ports.
- Per-file lint/type disables: violates approach A.
