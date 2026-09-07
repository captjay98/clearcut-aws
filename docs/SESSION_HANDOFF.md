# ClearCut Session Handoff

**Current phase:** portable single-service implementation and provider-free release verification

**Current verdict:** NO-GO for hosted or contest release

**Next allowed action:** complete provider-free verification and review; perform cloud mutation or paid-provider calls only after explicit owner authorization

## Start here

1. Read `README.md`, `docs/ARCHITECTURE.md`, ADR 0004, and `docs/plans/2026-08-31-portable-single-service-deployment.md`.
2. Read `docs/submission/manifest.yaml` before making any hosted, provider, production, or contest claim.
3. Read `docs/PARALLEL_INTEGRATION.md` before changing detection, research, or provider contracts. Search is mandatory when research runs; Extract is bounded; Monitor is conditional.
4. Run the provider-free verification appropriate to the changed scope. Do not substitute local source-contract checks for hosted evidence.
5. Preserve unrelated work and protected local artifacts. Do not reset, clean, or overwrite user-owned files.

## Accepted deployment contract

- One immutable `clearcut` image contains Astro, TanStack Start, FastAPI, migrations, and operational scripts.
- FastAPI is the sole public entry point for public pages, `/app/*`, `/api/*`, and protected `/api/internal/*` delivery.
- Local, Portable Server, and GCP Starter use the same image and select adapters through validated configuration.
- GCP Starter uses one public Cloud Run service and a separate migration job pinned to the same digest.
- Built-in opaque sessions are the default; Firebase runtime composition is not yet wired.
- Paid providers are disabled by default and require explicit cost acknowledgement plus bounded concurrency.

## Explicit deferrals

- Portable PostgreSQL dispatch is designed but not composed into the runtime.
- Firebase/Identity Platform settings validation does not constitute runtime integration.
- Terraform does not provision the complete workload and has not been planned or applied against GCP.
- No hosted image, URL, candidate revision, backup/restore drill, provider trace, video, or cost evidence exists.
- Docker and actionlint checks may be unavailable on a given workstation; report them rather than claiming them.

## Current provider-free evidence

- The one-image, Cloud Tasks, storage/secret, paid-provider governance, Artifact Registry, submission, and release-workflow source contracts have focused passing tests.
- Frontend production builds have passed in the integration worktree.
- Terraform formatting, backend-disabled initialization, validation, and mock-provider tests have passed without cloud mutation.
- The container startup contract enables bundled static delivery, but no local Docker engine was available for an image build or smoke test.

## Release boundary

A future release must bind one repository SHA and one image digest through build, migration, candidate deployment, smoke, and promotion. It must retain exact workflow-run evidence, hosted authorization checks, runtime Gemini/Parallel traces when enabled, recovery evidence, and an accountable GO decision. Until those artifacts are recorded, `docs/submission/manifest.yaml` remains NO-GO.
