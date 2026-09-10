---
feature: local-image-live-journey
status: delivered
updated: 2026-09-10
branch: feat/local-image-journey
commits: c12c9f5..c12c9f5
---

# Local Image Live Journey

## Report

**What was built** — A provider-free GET smoke plus a full authenticated live-provider journey against the running one-image Docker runtime at `http://localhost:18080` (`clearcut:local`). The journey used the real browser workspace (not the e2e fixture API): registration, org/project creation, paste import, live Gemini detection, live Parallel Search+Extract research, a governed evidence decision, a frozen report snapshot, container restart, persistence verification, and deep-link/reserved-route checks.

**Verification** — `scripts/deployment_smoke.py --url http://127.0.0.1:18080` → 4/4 PASS. Browser journey: detect job succeeded (5 items, judgePassed, headlineScore 93.75); research job succeeded (6 claims, 25 snapshots, 2 search + 2 extract attempts, judgePassed, headlineScore 82.5); `recordEvidenceDecision` 200 with attributable history; report snapshot 201 with contentHash `fcbb1f13827eb730c75789af986feb9daaaf0ee5a4bb39b0819cbac589a34d86`. `docker restart clearcut-app` then healthz 200; same session still authenticated; 5 items + 6 claims + report history still present. Deep links for `/app` project/items/item/report all 200 HTML; `/healthz`, `/api/v1/healthz`, `/api/openapi.json` still JSON.

**Journey log** —
1. GET-only smoke is necessary but far from sufficient; live detect+research proved the paid adapters and provenance path on this image.
2. Org-scoped API paths accept slug (`journey-studio-live`) in the browser client; UUID org-id in hand-rolled fetches 404s.
3. Item evidence UI does not auto-poll after research 202; a hard reload is required to show new claims.
4. Header avatar shows "Jamie Park" while session-context email is the registered address — display-name bug, not a session leak.
5. `/evaluations` on this project 500s with `operator does not exist: uuid = text` (`sql_evaluation_repository.list_persisted_evaluations`); unauthenticated curl correctly 401s.

## [S1] Problem

The one-image Docker runtime at `http://localhost:18080` (`clearcut:local`) passes GET-only deployment smoke, but that does not prove the product journey. Existing Playwright E2E boots uvicorn + vite, not this image. Submission handoff T11 requires a meaningful persistence journey and live provider paths when authorized. We need evidence that this exact container can run signup → import → Gemini detection → Parallel research → governed readbacks → restart survival.

## [S2] Design

### Target

- Base URL: `http://localhost:18080` (compose override; host 18080 → container 8080)
- Image: `clearcut:local` (`8fbbc1a36936` at plan time)
- Profile: `local` filesystem storage, local non-durable dispatch, builtin sessions
- Paid providers: `gemini,parallel` enabled, cost acknowledged, concurrency 1 each
- Credentials: ADC mounted at `/var/run/secrets/gcp/adc.json`, `PARALLEL_API_KEY` present in container
- Demo seed: off — all accounts created through public registration

### Execution surface

Drive the journey in a real browser against the built image (Playwright browser automation). Use HTTP only for healthz/openapi probes and container restart. Do not use the e2e fixture API (`e2e_api:app`); it is not in this image.

### Journey stages

1. **Baseline** — `/`, `/app/`, `/api/v1/healthz`, `/api/openapi.json` already smoke-passed; reconfirm healthz attestation.
2. **Register** — unique email via `/app/auth/sign-up`; opaque session cookie set; land in onboarding.
3. **Org + project** — create organization and project through UI forms.
4. **Import** — paste a short screenplay containing trademark/location triggers; parse diagnostics; commit version.
5. **Detect (live Gemini)** — start detection on committed version; poll job until terminal; clearance items appear (or typed provider failure is recorded honestly).
6. **Research (live Parallel)** — research one item; require a cited SourceSnapshot with URL/retrieval/excerpt/provenance, or a typed unavailable/empty state. Never invent evidence.
7. **Governed readback** — open item workspace, confirm unresolved/cited state language; record an evidence decision if the UI exposes one for the available claims.
8. **Report surface** — open report preview/history if reachable without fabricating clearance.
9. **Restart persistence** — `docker restart clearcut-app` only (no `down -v`); wait healthy; re-login; confirm org/project/version/items still present.
10. **Deep links** — reload `/app` project/item/report URLs; reserved `/healthz` and `/api/openapi.json` still win over static catch-all.

### Success criteria

- Live Gemini detect produces either persisted clearance items or an explicit typed provider error — never a silent empty success.
- Live Parallel research produces either provenance-complete claims or an explicit empty/unavailable item state.
- After restart, previously created account can sign in and see the same project version and items.
- No volume wipe, no cloud mutation beyond authorized provider calls, no fabricated evidence.

### Observed IDs

- Account: `journey-owner-20260910@example.com` (`01a08d19-c836-7b5d-aed0-2895a649fbd2`)
- Org: Journey Studio Live / `journey-studio-live` (`01a08d19-f3ed-708e-aa54-8726c60a6449`)
- Project: Signal Check Live (`01a08d1a-5a9f-7d89-b906-7eb9c7344232`)
- Version 1: `01a08d1b-388c-70d6-b2e7-740db1c1adba`
- Detect job: `01a08d1b-5a9f-79f8-9126-c1f81cb6af3b` — succeeded, 5 items
- Research job: `01a08d1c-7c1c-7b40-a012-a7d60a45dc3d` — succeeded, 6 claims / 25 snapshots
- Coca-Cola item: `01a08d1b-bddc-7aa5-af90-293a1ef44801`
- Report snapshot contentHash: `fcbb1f13827eb730c75789af986feb9daaaf0ee5a4bb39b0819cbac589a34d86`

### Defects observed (not fixed in this pass)

1. **Critical path bug** — `GET .../evaluations` returns 500: `asyncpg.UndefinedFunctionError: operator does not exist: uuid = text` in `clearcut/evaluation/adapters/sql_evaluation_repository.py` `list_persisted_evaluations` when org scope is the slug used by the browser client.
2. **UI display** — workspace header shows "Jamie Park" while authenticated session email is the registered address.
3. **UX** — research returns 202; item page does not auto-refresh claims until a hard reload.
4. **Monitoring** — report page requests `/monitoring-policy` and `/monitoring-runs` which 404 on this image.

### Safety

- Disposable test identity only (`journey-owner-20260910@example.com`).
- Do not print secrets or full Parallel keys.
- Do not call `docker compose down -v`.
- If a provider fails, record the typed failure; do not disable gates to force a pass.

## [S3] Out of Scope

- Hosted GCP profile validation (`--expected-profile gcp`)
- Terraform, SBOM, registry digest promotion
- Multi-user invitation/role matrix beyond the single owner account
- Rewriting product code for the defects above (follow-up feature)
- Turning this one-off journey into a permanent CI Playwright suite (separate feature)
- Report release (snapshot created; release left for accountable human)

## Tasks

- [x] T1: Confirm baseline attestation on running container — acceptance: healthz shows local profile, paid providers listed, databaseConfigured true (covers: S2)
- [x] T2: Register owner and create org+project in browser — acceptance: session authenticated, projectId present in UI (covers: S2; depends: T1)
- [x] T3: Paste-import and commit script version — acceptance: committed version id visible in versions/UI (covers: S2; depends: T2)
- [x] T4: Run live Gemini detection and observe items or typed failure — acceptance: job terminal + item list or typed error recorded (covers: S2; depends: T3)
- [x] T5: Run live Parallel research on one item — acceptance: claim with source snapshot provenance or typed empty/unavailable (covers: S2; depends: T4)
- [x] T6: Capture governed readbacks and report surface reachability — acceptance: workspace language matches persisted state; report route reachable or unavailable reason noted (covers: S2; depends: T5)
- [x] T7: Restart app container and verify persistence — acceptance: re-login shows same project/version/items (covers: S2; depends: T6)
- [x] T8: Deep-link reload and reserved-route checks — acceptance: workspace deep links render; healthz/openapi still JSON (covers: S2; depends: T7)
