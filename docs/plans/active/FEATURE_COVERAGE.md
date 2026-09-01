# ClearCut Feature Coverage

**Feature source:** `docs/feature-ledger.md` (47 mandatory rows)  
**Rule:** a feature is complete only when its acceptance evidence is produced at the owning layer.

| # | Feature | Accountable packet | Contributors | Required acceptance evidence |
|---:|---|---|---|---|
| 1 | Pasted text | 03b | 03c | deterministic parse fixture + authorized E2E import |
| 2 | Fountain import | 03b | 03c | parser corpus + malformed/size tests + E2E |
| 3 | PDF import | 03b | 03a, 03c | isolated parser/model contract + hostile PDF tests + E2E |
| 4 | Final Draft `.fdx` | 03b | 03c | safe XML corpus + entity/bomb tests + E2E |
| 5 | Scene/page references | 03b | 07d | normalized fixture + rendered anchor assertion |
| 6 | Character/dialogue parsing | 03b | — | golden parser corpus |
| 7 | Prop/location/music extraction | 03b | — | golden parser corpus |
| 8 | Draft/version comparison | 08b | 08c | stable-ID diff property tests |
| 9 | Changed-clearance-element detection | 08b | — | affected/unaffected re-scan tests |
| 10 | People & likeness | 04a | 04b | positive/negative/ambiguous corpus |
| 11 | Names & characters | 04a | 04b | positive/negative/ambiguous corpus |
| 12 | Brands & trademarks | 04a | 04b | positive/negative/ambiguous corpus |
| 13 | Products & trade dress | 04a | 04b | positive/negative/ambiguous corpus |
| 14 | Locations & property | 04a | 04b | positive/negative/ambiguous corpus |
| 15 | Music & lyrics | 04a | 04b | positive/negative/ambiguous corpus |
| 16 | Artwork & media | 04a | 04b | positive/negative/ambiguous corpus |
| 17 | Dialogue & quotations | 04a | 04b | positive/negative/ambiguous corpus |
| 18 | Organizations & insignia | 04a | 04b | positive/negative/ambiguous corpus |
| 19 | Privacy & sensitive facts | 04a | 04b | positive/negative/ambiguous corpus + legal-boundary gate |
| 20 | Parallel runtime calls | 05a | 05b, 09a, 12b | mandatory deployed Search trace; truthful Extract and conditional Monitor evidence/status |
| 21 | Item-specific query generation | 05a | 04a | saved query/tool-call trace and judge/gate evidence |
| 22 | Source URL/title/date/excerpt | 05a/05b | 05c | Search/Extract contract tests + live snapshots |
| 23 | Source-authority classification | 05c | 10b | versioned policy/gate tests |
| 24 | Conflicting-evidence detection | 05c | — | conflict fixtures + live demo example |
| 25 | Confidence/unresolved states | 05c | 07d | zero-evidence, partial-enrichment, and conflict UI/API tests |
| 26 | Evidence freshness | 05c | 09a | retrieval-time display + scheduled recheck test |
| 27 | Query/response provenance | 05a | 05b, 09a, 10a | redacted capability/ID/session trace + schema completeness gate |
| 28 | Source-change monitoring | 09a/09b | 09d | scheduled Search/Extract + optional Monitor signal + review E2E |
| 29 | Item status workflow | 07a | 07b, 07d | orthogonal-state transition/property tests |
| 30 | Evidence attachments | 05c | 07d | scoped source/claim/item relational tests |
| 31 | Suggested rewrites | 08a | 07b, 08c | proposal + separate approval E2E |
| 32 | Re-scan after revision | 08b | 08c | affected-only durable job proof |
| 33 | Progress dashboard | 07d | 07a | derived-count component/API/E2E tests |
| 34 | Exportable evidence packet | 11a | 11b, 11c | frozen version-bound report/PDF proof |
| 35 | Assignments/due dates | 07b | 07d | role/scope/idempotency/UI tests |
| 36 | Comments/notes | 07c | 07d | one-level thread/edit-history/mention tests |
| 37 | Related-item grouping | 07a | 07d | filter/group contract and UI tests |
| 38 | Audit trail | 10a | 07b, 08a, 09b, 11a | same-transaction audit + redacted Receipt consistency |
| 39 | Hosted web experience | 12a | 06b | deployed exact-SHA browser E2E |
| 40 | Project/script storage | 03a | 12a | PostgreSQL/GCS integration + restore test |
| 41 | Annotated script viewer | 07d | 06a, 06b | visual/accessibility/responsive parity |
| 42 | Item/evidence database | 05c | 04a | PostgreSQL integration + tenancy/constraint tests |
| 43 | Search/filter/sort/group | 07a | 07d | URL/query contract + list/board parity tests |
| 44 | Revision history | 08b | 08c | immutable lineage API/UI tests |
| 45 | Document export | 11b | 11c | deterministic renderer/semantic binding tests |
| 46 | Auth/orgs/fixed roles | 02a | 02b, 02c, 02d | session/CSRF/invitation/RBAC/cross-tenant E2E |
| 47 | Secure source/file handling | 03a | 05a, 05b, 09a, 12a | upload/SSRF/Extract-target/webhook/prompt-injection/redaction suite |

## Coverage gates

- Exactly 47 rows; no duplicates or ownerless features; exactly one accountable packet per row.
- Every row has a narrow acceptance artifact and a golden-path link where applicable.
- “Implemented” requires evidence; plan prose, fixtures, screenshots, and mock behavior alone do not count.
- A failed hard invariant blocks the owning feature even if its happy path works.
