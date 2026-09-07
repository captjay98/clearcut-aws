# Product Map

## Current Phase: Integrated implementation, release evidence pending

The repository contains the product runtime, frontends, contracts, design system, deployment controls, and demo assets. Local and provider-free verification evidence exists. Hosted cloud, live-provider, recovery, video, and final compliance evidence remains absent, so release readiness is NO-GO.

## Mock UI Prototype

- **Status:** complete — 20 surfaces with structural, responsive, and accessibility baselines.
- **Location:** `misc/clearcut-flow/`.
- **Role:** visual identity and interaction-design source of truth.

## Product capabilities

| Plan area                            | Repository state                              | External evidence boundary                  |
| ------------------------------------ | --------------------------------------------- | ------------------------------------------- |
| Foundation and contracts             | Implemented                                   | Clean-clone/release evidence still required |
| Identity and tenancy                 | Implemented with built-in sessions            | Firebase runtime composition deferred       |
| Ingestion and versioning             | Implemented                                   | Hosted object-storage proof absent          |
| Detection and evaluation             | Implemented behind typed provider ports       | Authorized live Gemini proof absent         |
| Parallel evidence                    | Implemented behind typed provider ports       | Authorized live Search/Extract proof absent |
| Design system and application shell  | Implemented from the mock                     | Hosted/browser release proof incomplete     |
| Evidence workspace and collaboration | Implemented                                   | Hosted role/tenant proof absent             |
| Revisions and selective re-scan      | Implemented                                   | Hosted golden-path proof absent             |
| Monitoring and notifications         | Implemented with conditional Monitor boundary | Signed hosted Monitor proof absent          |
| Trust and governance                 | Implemented                                   | Hosted recovery/compliance proof absent     |
| Report and export                    | Implemented with separate governed release    | Hosted artifact proof absent                |
| Infrastructure and submission        | Provider-free controls implemented            | Terraform unapplied; manifest remains NO-GO |

## Deployment shape

One immutable `clearcut` image contains Astro, TanStack Start, FastAPI, migrations, and scripts. FastAPI serves public pages, `/app/*`, `/api/*`, and protected `/api/internal/*`. Local, Portable Server, and GCP Starter use that image. GCP Starter uses one public Cloud Run service and a same-digest migration job. Portable PostgreSQL dispatch and optional Firebase runtime composition remain deferred.

## Feature ledger

The protected product vocabulary covers script ingestion, ten detection categories, Parallel-backed evidence, workflow, and non-AI product capabilities. See `docs/feature-ledger.md`. Category and source-authority policies remain distinct.

## Submission

- Deadline: September 9, 2026, 2:00 PM PT.
- Track: Parallel.
- Required external artifacts include a hosted URL, public repository and license, three-minute video, and verified Devpost fields.
- `docs/submission/manifest.yaml` is the authoritative GO/NO-GO ledger.

## Next milestone

Finish complete provider-free branch verification and independent review. Any later cloud mutation, live paid-provider call, or release evidence collection requires explicit authorization and must bind one repository SHA to one image digest.
