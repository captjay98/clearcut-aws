# Chronological Commit Reconstruction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the completed dirty worktree on `feat/rebuild-a` into a reviewable, dependency-ordered Git history dated to the evidence-backed implementation timeline.

**Architecture:** Preserve the working tree as the source of truth while staging explicit, non-overlapping path groups. Shared composition and contract files are committed at dependency checkpoints rather than split into invented intermediate states. Both Git author and committer dates use approved reconstructed WAT timestamps.

**Tech Stack:** Git, zsh, Python/pytest, pnpm/Bun, FastAPI, Alembic, OpenAPI-generated clients, Vite/Vitest, Playwright.

---

## Global safety rules

- Work only in `/Users/captjay98/projects/clearcut-rebuild-a` on `feat/rebuild-a`.
- Never inspect, stage, or commit `.clearcut/` or `services/api/.clearcut/`.
- Never use `git add .`, `git add -A`, stash, reset, clean, revert, amend, force push, or `--no-verify`.
- Before every commit run `git diff --cached --name-only`, `git diff --cached --stat`, and `git diff --cached --check`.
- If an unexpected file is staged, unstage that explicit path with `git restore --staged -- <path>`; do not alter its working-tree content.
- Preserve all hooks. If a hook fails, fix the issue, restage explicit files, and create a new commit attempt without amending.
- `semantic-review/` remains untracked unless a local content/secret review proves it suitable as repository evidence.
- Dates below are normalized ordering timestamps; both `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` must be set.

## Preflight

1. Confirm branch: `git branch --show-current` must print `feat/rebuild-a`.
2. Record status excluding protected paths.
3. Run `git diff --check`.
4. Confirm the two plan files exist:
   - `docs/plans/2026-09-06-chronological-commit-reconstruction-design.md`
   - `docs/plans/2026-09-06-chronological-commit-reconstruction.md`
5. Do not stage either plan until Task 16.

### Task 1: Record the rebuild remediation status

**Date:** `2026-09-01T12:20:00+01:00`
**Commit:** `docs: update rebuild remediation status`

**Stage:**
- `docs/reviews/2026-08-31-remediation-status.md`

**Verify:** inspect cached diff and run `git diff --cached --check`.

**Commit:**
```bash
GIT_AUTHOR_DATE="2026-09-01T12:20:00+01:00" GIT_COMMITTER_DATE="2026-09-01T12:20:00+01:00" git commit -m "docs: update rebuild remediation status"
```

### Task 2: Make Alembic the runtime schema authority

**Date:** `2026-09-02T10:00:00+01:00`
**Commit:** `fix(api): make Alembic the runtime schema authority`

**Stage:**
- `services/api/alembic/versions/0022_runtime_alignment.py`
- `services/api/src/clearcut/database.py`
- `services/api/src/clearcut/init_db.py`
- `services/api/tests/conftest.py`
- `services/api/tests/architecture/test_migrated_runtime_schema.py`

**Verify:** `uv run pytest services/api/tests/architecture/test_migrated_runtime_schema.py -q`.

**Commit with the task date.**

### Task 3: Persist signup and scoped sessions

**Date:** `2026-09-02T11:00:00+01:00`
**Commit:** `feat(identity): persist signup and scoped sessions`

**Stage:**
- `services/api/src/clearcut/csrf.py`
- `services/api/src/clearcut/delivery_errors.py`
- `services/api/src/clearcut/identity/`
- `services/api/src/clearcut/organizations/adapters/sql_repository.py`
- `services/api/src/clearcut/organizations/application/invitation_service.py`
- `services/api/src/clearcut/organizations/application/membership_service.py`
- `services/api/src/clearcut/organizations/domain/`
- `services/api/scripts/seed_db.py`
- `services/api/tests/identity/`

**Verify:** `uv run pytest services/api/tests/identity -q`.

**Commit with the task date.**

### Task 4: Persist screenplay import and immutable versions

**Date:** `2026-09-02T12:00:00+01:00`
**Commit:** `feat(scripts): persist screenplay import and versions`

**Stage:**
- `services/api/alembic/versions/0023_persistent_script_import.py`
- `services/api/src/clearcut/scripts/`
- `services/api/tests/scripts/`
- `demo/original-screenplay/clearcut_test.fountain`

**Verify:** `uv run pytest services/api/tests/scripts -q`.

**Commit with the task date.**

### Task 5: Persist detection and evaluation provenance

**Date:** `2026-09-02T14:00:00+01:00`
**Commit:** `feat(ai): persist detection and evaluation provenance`

**Stage:**
- `services/api/alembic/versions/0024_ai_evaluation_provenance.py`
- `services/api/alembic/versions/0025_detection_execution.py`
- `services/api/alembic/versions/0026_full_provenance.py`
- `services/api/src/clearcut/ai/`
- `services/api/src/clearcut/detection/`
- `services/api/src/clearcut/evaluation/`
- `services/api/tests/ai/`
- `services/api/tests/detection/`
- `services/api/tests/evaluation/`
- `services/api/tests/conformance/test_model_runtime.py`
- `services/api/tests/conformance/test_provider_selection.py`

**Verify:** run detection, evaluation, AI, and model-runtime tests.

**Commit with the task date.**

### Task 6: Execute scoped Parallel research jobs

**Date:** `2026-09-02T16:00:00+01:00`
**Commit:** `feat(research): execute scoped Parallel research jobs`

**Stage:**
- `services/api/alembic/versions/0027_research_execution.py`
- `services/api/src/clearcut/research/`
- `services/api/tests/research/`
- `services/api/tests/conformance/test_url_extract_port.py`

**Verify:** `uv run pytest services/api/tests/research services/api/tests/conformance/test_url_extract_port.py -q`.

**Commit with the task date.**

### Task 7: Add durable jobs and production details

**Date:** `2026-09-03T10:00:00+01:00`
**Commit:** `feat(operations): add durable jobs and production details`

**Stage:**
- `services/api/alembic/versions/0028_project_production_details.py`
- `services/api/alembic/versions/0029_job_list_pagination.py`
- `services/api/src/clearcut/operations/`
- `services/api/src/clearcut/projects/`
- `services/api/src/clearcut/organizations/delivery/http.py`
- `services/api/src/clearcut/records/delivery/http.py`
- `services/api/src/clearcut/monitoring/delivery/http.py`
- `services/api/tests/operations/`
- `services/api/tests/organizations/test_tenant_isolation.py`

**Verify:** run operations, organization isolation, and project-related tests.

**Commit with the task date.**

### Task 8: Align the canonical API and generated clients

**Date:** `2026-09-03T14:00:00+01:00`
**Commit:** `feat(contracts): align canonical API and generated clients`

**Stage:**
- `packages/contracts/openapi.yaml`
- `packages/contracts/generated/typescript/index.ts`
- `packages/contracts/generated/python/__init__.py`
- `scripts/check-contract-drift.mjs`
- `scripts/generate-clients.mjs`
- `services/api/src/clearcut/main.py`
- `tests/contracts/`

**Verify:** `pnpm contract:check` and `uv run pytest tests/contracts -q`.

**Commit with the task date.**

### Task 9: Add the authenticated import and clearance browser flow

**Date:** `2026-09-03T18:00:00+01:00`
**Commit:** `feat(web): add authenticated import and clearance flow`

**Stage:**
- `apps/web/src/routes/auth/`
- `apps/web/src/features/scripts/`
- `apps/web/src/features/operations/`
- `apps/web/src/routes/o/$orgSlug/projects/new.tsx`
- `apps/web/src/routes/o/$orgSlug/projects/$projectId/items/index.tsx`
- `apps/web/src/routes/o/$orgSlug/projects/$projectId/versions.tsx`
- `apps/web/src/routes/o/$orgSlug/projects/$projectId/watch.tsx`
- `apps/web/src/routes/o/$orgSlug/records.tsx`
- `apps/web/src/routes/o/$orgSlug/trust.tsx`
- `apps/web/src/routes/o/$orgSlug/team.tsx`
- `apps/web/src/features/monitoring/CadenceSelector.tsx`
- `apps/web/src/features/clearance/ClearanceItemCard.tsx`
- `apps/web/src/routeTree.gen.ts`
- `apps/web/vite.config.ts`
- `apps/web/tests/config/`
- `apps/web/tests/e2e/auth-flow.spec.ts`
- `apps/web/tests/e2e/new-clearance-flow.spec.ts`
- `apps/web/tests/e2e/script-import.spec.ts`
- `apps/web/tests/e2e/signup-onboarding.spec.ts`
- `apps/web/tests/e2e/trust-center-learning.spec.ts`
- `apps/web/tests/e2e/version-diff-lineage.spec.ts`

**Verify:** web units/build plus the listed focused Playwright specs.

**Commit with the task date.**

### Task 10: Add the governed collaboration schema and command kernel

**Date:** `2026-09-04T23:25:00+01:00`
**Commit:** `feat(collaboration): add governed schema and command kernel`

**Stage:**
- `services/api/alembic/versions/0030_governed_collaboration.py`
- `services/api/alembic/versions/0031_comment_revision_author.py`
- `services/api/alembic/versions/0032_comment_mention_revision.py`
- `services/api/alembic/versions/0033_comment_mention_revision_scope.py`
- `services/api/src/clearcut/commanding/`
- `services/api/tests/commanding/`
- `services/api/tests/architecture/test_governed_collaboration_schema.py`

**Verify:** commanding and governed-collaboration schema tests.

**Commit with the task date.**

### Task 11: Persist governed decisions, assignments, and dispositions

**Date:** `2026-09-05T00:15:00+01:00`
**Commit:** `feat(collaboration): persist decisions assignments and dispositions`

**Stage:**
- `services/api/src/clearcut/decisions/`
- `services/api/src/clearcut/items/`
- `services/api/tests/decisions/`
- `services/api/tests/items/`

**Verify:** decisions and items test suites.

**Commit with the task date.**

### Task 12: Add referrals, comments, mentions, and outbox

**Date:** `2026-09-05T02:00:00+01:00`
**Commit:** `feat(collaboration): add referrals comments mentions and outbox`

**Stage:**
- `services/api/src/clearcut/collaboration/`
- `services/api/tests/collaboration/`

**Verify:** collaboration tests plus neighboring decisions/items tests.

**Commit with the task date.**

### Task 13: Connect the governed evidence workspace

**Date:** `2026-09-05T14:00:00+01:00`
**Commit:** `feat(web): connect governed evidence collaboration`

**Stage:**
- `apps/web/src/features/clearance/EvidenceDrawer.tsx`
- `apps/web/src/features/clearance/ItemGovernanceControls.tsx`
- `apps/web/src/features/collaboration/`
- `apps/web/src/mutations/`
- `apps/web/src/queries/`
- `apps/web/src/routes/o/$orgSlug/projects/$projectId/items/$itemId.tsx`
- `apps/web/src/routes/o/$orgSlug/projects/$projectId/workspace.tsx`
- `apps/web/src/routes/o/$orgSlug/projects/$projectId/route.tsx`
- `apps/web/src/routes/o/$orgSlug/projects/route.tsx` if present
- `apps/web/src/routes/o/$orgSlug/route.tsx`
- `apps/web/src/routes/o/$orgSlug/projects/index.tsx`
- `apps/web/tests/unit/`

**Verify:** web units and build.

**Commit with the task date.**

### Task 14: Add deterministic multi-user browser evidence

**Date:** `2026-09-05T20:00:00+01:00`
**Commit:** `test(e2e): add deterministic multi-user evidence matrix`

**Stage:**
- `apps/web/playwright.config.ts`
- `apps/web/tests/support/`
- `apps/web/tests/e2e/support/`
- `apps/web/tests/e2e/evidence-access.spec.ts`
- `apps/web/tests/e2e/evidence-workspace.spec.ts`
- `apps/web/tests/e2e/review-collaboration-actions.spec.ts`
- `apps/web/tests/e2e/TESTING.md`
- deletion of `apps/web/tests/e2e/clearance-evidence-drawer.spec.ts`
- deletion of `apps/web/tests/e2e/e2e-clearance-lifecycle.spec.ts`
- deletion of `apps/web/tests/e2e/script-import-viewer.spec.ts`
- `services/api/tests/e2e/`
- `tests/foundation/test_web_runtime_boundary.py`

**Verify:** focused evidence Chromium tests, then the four-project serial matrix.

**Commit with the task date.**

### Task 15: Add immutable report release and download

**Date:** `2026-09-06T07:30:00+01:00`
**Commit:** `feat(reports): add immutable report release and download`

**Stage:**
- `services/api/alembic/versions/0034_report_artifacts.py`
- `services/api/src/clearcut/export/`
- `services/api/tests/export/`
- `apps/web/src/features/reports/`
- `apps/web/src/routes/o/$orgSlug/projects/$projectId/report.tsx`
- `apps/web/tests/e2e/report-release-flow.spec.ts`

**Verify:** report API/renderer tests, web build, and focused report Playwright matrix.

**Commit with the task date.**

### Task 16: Add fail-closed infrastructure and submission readiness

**Date:** `2026-09-06T09:00:00+01:00`
**Commit:** `chore(release): add fail-closed submission readiness gates`

**Stage:**
- `.github/workflows/deploy.yml`
- `.github/workflows/migrate.yml`
- `Dockerfile`
- `docker-compose.yml`
- `cloudbuild.yaml`
- `clearcut`
- `scripts/deploy_gcp.sh`
- `scripts/start_local.sh`
- `scripts/verify-submission.mjs`
- `services/api/src/clearcut/bootstrap/production_manifest.py`
- `services/api/tests/bootstrap/test_contest_profile.py`
- `infra/gcp/`
- `README.md`
- `demo/runbook.md`
- `docs/submission/`
- `docs/plans/2026-08-31-static-quality-cleanup-design.md`
- `docs/plans/2026-08-31-task-10-governed-collaboration-design.md`
- `docs/plans/2026-08-31-task-10-governed-collaboration.md`
- `docs/plans/2026-08-31-testable-ai-records-flow-design.md`
- `docs/plans/2026-08-31-testable-ai-records-flow.md`
- `docs/plans/2026-09-02-task-9-spec-review-remediation.md`
- `docs/plans/2026-09-06-chronological-commit-reconstruction-design.md`
- `docs/plans/2026-09-06-chronological-commit-reconstruction.md`
- `tests/foundation/test_deployment_boundaries.py`
- `tests/submission/`
- `package.json`

**Verify before commit:** submission tests, deployment-boundary tests, production-profile tests, formatting, shell/YAML parsing, and `git diff --cached --check`.

**Commit with the task date.**

## Final completeness and verification

1. Run status excluding `.clearcut` and inspect every remaining tracked/untracked path.
2. Any omitted implementation file must be assigned to its owning commit through a new follow-up commit dated no earlier than its dependency; do not silently leave source changes behind.
3. Keep `semantic-review/` untracked unless explicitly accepted after inspection.
4. Run:
   - `pnpm verify`
   - `uv run pytest services/api/tests -q`
   - `pnpm --filter clearcut-web test`
   - `pnpm lint`
   - `pnpm build`
   - `pnpm --filter clearcut-web test:e2e -- --workers=1`
   - `git diff --check`
5. Confirm commit order and dates with `git log --date=iso-strict --reverse` for the reconstructed range.
6. Do not push or create a pull request without a separate request.
