# ClearCut Decision Register

This register records accepted cross-document decisions and the few external questions that remain open. Implementation agents follow accepted decisions even when a historical design file still describes an earlier state.

## Accepted decisions

| ID | Decision | Consequence |
|---|---|---|
| DG-01 | Comments support one reply level, immutable parent identity, edit history, mentions, and no reply-to-reply nesting. | Plan 07c owns the schema/API. |
| DG-02 | Owner, Admin, Editor, and Reviewer may assign/reassign within authorized projects. Assignment is operational, version-checked, idempotent, and audited. | Plans 02c and 07b use one capability matrix. |
| DG-03 | Specialist referral is governed and available to Owner, Admin, and Reviewer only. Editor may draft a brief but cannot submit it. | Plan 07b and UI capability tests use this rule. |
| DG-04 | Mock check totals come from live command output. Living gates do not hard-code 366 or 418; dated historical evidence remains unchanged. | Plan 06a parses the audit summary. |
| DG-06 | The canonical prototype count is 20 product/review surfaces. Supporting renderers are tracked separately. | `docs/UI_SURFACE_CONTRACT.md` is authoritative. |
| DG-07 | Domain records are `ReportSnapshot`, `ReportRelease`, and `ExportArtifact`; UI copy says “clearance report.” | No `DossierExport` enters new contracts. |
| DG-08 | Production release copy is “Release this frozen snapshot?” and “Release report.” Release never regenerates. | Plans 06a and 11b test release-only semantics. |
| DG-09 | The mock chooser is a disclosed visual simulation. Production uses a real file input/drop target plus server byte validation. | Plan 03a owns behavior. |
| DG-10 | Generic state-gallery coverage is insufficient. `docs/UI_STATE_MATRIX.md` is the production route/state contract. | Every UI packet tests its assigned rows. |
| DG-11 | `packages/contracts/openapi.yaml` is the only OpenAPI source. Schemas live under `packages/contracts/schemas/`; generated clients live under `packages/contracts/generated/`. | Plan 01b creates the contract package. |
| DG-12 | Stored/API job success is `succeeded`; UI may display “Completed.” `manual_retry` is a declared state. | All schemas use `docs/API_CONTRACT.md`. |
| DG-13 | Provider failure kinds are `retryable`, `rate_limited`, `authentication`, `configuration`, `invalid_response`, `permanent`, and `ambiguous`. | Provider ports share one top-level taxonomy. |
| DG-14 | Feature coverage has one accountable plan packet and zero or more contributors. | `FEATURE_COVERAGE.md` distinguishes owner from contributors. |
| DG-15 | Evaluation is staged. Unavailable dimensions are `not_applicable` or `incomplete`; they never receive invented scores. | Plans 04b, 05c, 08b, and 11b complete eligible dimensions. |
| DG-16 | PostgreSQL and object storage use staged publication plus reconciliation; they are not one atomic transaction. | Plans 03a and 11a own the two artifact workflows. |
| DG-17 | Records owns cross-module read projections. Source modules own records/events and projection ports, not Records routes. | Plan 10a owns Records API/UI. |
| DG-18 | Core identifiers are UUIDv7. External provider IDs remain opaque bounded strings. | OpenAPI, migrations, constraints, and examples use UUIDv7. |
| DG-19 | Generation and initial release are governed. Downloading an authorized released artifact is a read, not another release decision. | Plan 11b separates release and download. |
| DG-20 | The open-source core uses typed ports and explicit registration. The contest profile implements only Gemini/ADK for AI and Parallel for research. | `docs/EXTENSIONS.md` governs all adapter work. |

## Open external decision

| ID | Question | Required action | Blocks |
|---|---|---|---|
| DG-05 | Does the organizer's development-assistant interpretation add a restriction beyond the official submitted-project/runtime wording? | Obtain written Devpost/organizer clarification, retain it, and disclose truthfully. | Final submission GO only. |

## Resolution record format

```text
decision ID
owner and date
selected behavior and rejected alternatives
authoritative documents changed
contract, migration, UI, test, and extension consequences
whether the mock must change first
```

Historical documents are not silently rewritten. A living document that conflicts with an accepted decision must be corrected before its implementation packet begins.
