# ClearCut Database Contract

**Database:** Cloud SQL PostgreSQL  
**Migration tool:** Alembic  
**Identifier:** UUIDv7 for ClearCut-owned primary keys

`docs/DATA_MODEL.md` defines the logical aggregates. This document freezes physical ownership, cross-cutting constraints, indexes, and migration rules for implementation agents.

## Module ownership

| Module | Initial tables |
|---|---|
| identity | `users`, `local_credentials`, `provider_identities`, `sessions`, `security_events` |
| organizations | `organizations`, `memberships`, `invitations`, `project_grants` |
| projects | `projects`, `project_preferences` |
| scripts | `import_artifacts`, `parse_runs`, `scripts`, `script_versions`, `script_elements`, `element_spans`, `version_lineage`, `version_diffs` |
| detection | `analysis_runs`, `detection_runs`, `clearance_items`, `item_version_states` |
| research | `research_runs`, `research_queries`, `source_snapshots`, `evidence_claims`, `evidence_conflicts`, `confidence_assessments` |
| decisions | `evidence_decisions`, `specialist_referrals`, `rewrite_proposals`, `disposition_decisions`, `follow_up_tasks` |
| collaboration | `assignments`, `comments`, `comment_revisions`, `mentions`, `notifications`, `notification_delivery_attempts`, `push_subscriptions` |
| monitoring | `monitoring_policies`, `monitoring_runs`, `source_changes`, `monitoring_reviews` |
| evaluation | `deterministic_gate_results`, `judge_verdicts`, `agent_evaluations`, `learning_proposals`, `learning_candidates`, `canary_runs`, `prompt_versions`, `policy_versions`, `rubric_versions` |
| operations | `jobs`, `job_attempts`, `outbox_messages`, `inbox_receipts`, `provider_attempts`, `agent_runs`, `agent_tool_calls` |
| export | `report_snapshots`, `report_releases`, `export_artifacts` |
| audit | `audit_events`, `receipt_projections`, `deletion_requests`, `deletion_tombstones` |

The Records module owns read models/views only. It reads source-module projections through application ports; it does not own or query another module's tables directly.

## Tenant and relationship constraints

- Every organization-owned row has non-null `org_id` with an organization foreign key.
- Every project-owned row has non-null `(org_id, project_id)` and a composite foreign key to the project ownership tuple.
- Child relationships include the same ownership tuple so a foreign key cannot cross projects accidentally.
- `EvidenceClaim` has composite foreign keys to its item/version/source/query/run ownership tuple.
- `ReportRelease.snapshot_id` references an immutable snapshot in the same project.
- `AuditEvent` references actor, action, aggregate type/ID/version, scope, intent hash, correlation, and timestamp without storing secret/raw provider content.
- Mutable aggregates use non-null integer `version >= 1` for optimistic concurrency.
- Immutable records reject update/delete through repository behavior and database privileges/triggers only where the operational cost is justified.
- Core timestamps are `timestamptz`, stored in UTC.
- External IDs are length-bounded strings and never reused as primary keys.

## Required uniqueness

| Table | Constraint |
|---|---|
| `organizations` | unique stable `slug` |
| `memberships` | unique `(org_id, user_id)` |
| `project_grants` | unique `(org_id, project_id, membership_id)` |
| `invitations` | unique active token hash/version; email normalized and indexed within organization |
| `sessions` | unique token hash; no plaintext token column |
| `script_versions` | unique `(org_id, project_id, script_id, ordinal)` and source hash binding |
| `clearance_items` | unique stable logical identity within a script |
| `research_queries` | unique run-local normalized query identity |
| `evidence_claims` | unique cited claim identity without collapsing distinct excerpts/stances |
| `jobs` | unique scoped idempotency intent |
| `outbox_messages` | unique event ID |
| `inbox_receipts` | unique `(consumer, event_id)` |
| `report_releases` | unique release identity; multiple releases may supersede, never overwrite |
| `notifications` | unique recipient/event/dedupe key |

## Initial indexes

Every migration packet must name and explain its indexes. The minimum index families are:

```sql
-- Ownership-first lookup
CREATE INDEX ... ON clearance_items (org_id, project_id, created_at DESC, id DESC);

-- Mutable chronology cursor
CREATE INDEX ... ON audit_events (org_id, project_id, occurred_at DESC, id DESC);

-- Durable job leasing
CREATE INDEX ... ON jobs (status, available_at, lease_expires_at, id)
WHERE status IN ('queued', 'retry_wait', 'claimed', 'running');

-- Outbox dispatch
CREATE INDEX ... ON outbox_messages (published_at, available_at, id)
WHERE published_at IS NULL;
```

Search/filter indexes are added only with a named query and `EXPLAIN (ANALYZE, BUFFERS)` evidence. Large indexes use PostgreSQL-safe concurrent creation where required.

## Migration packet requirements

Every schema-owning implementation packet includes:

1. exact Alembic revision path and predecessor;
2. tables, columns, types, defaults, foreign keys, check constraints, unique constraints, and indexes;
3. expected lock and table-rewrite behavior;
4. compatibility with the currently deployed application version;
5. bounded, restartable backfill where required;
6. tested `upgrade()` and `downgrade()`, or an explicit irreversible boundary and restore procedure;
7. representative-volume timing and query-plan evidence;
8. tenant/provenance/audit invariant tests;
9. release-note entry and rollback decision point.

## Expand-contract sequence

```text
expand schema
-> deploy dual-read/dual-write compatible code
-> bounded backfill with progress checkpoint
-> verify constraints and query plans
-> switch reads
-> observe
-> contract old shape in a later release
```

Renaming/dropping a populated column, changing a large column type, or adding a validated non-null constraint in one deployment is prohibited.

## Object pointers

Database rows store bucket/key, immutable object generation/version, content hash, byte size, media type, encryption/retention classification, and lifecycle state. They do not assume an upload and database commit are atomic. Import and report workflows follow the staged protocol in `docs/ARCHITECTURE.md`.

## Migration verification commands

Plan 01 freezes the exact test database command. Subsequent migration packets expose commands equivalent to:

```bash
uv run alembic upgrade head
uv run pytest services/api/tests/migrations -q
uv run alembic downgrade -1
uv run alembic upgrade head
```

Expected: all commands exit 0 against an empty database, the previous release schema, and a representative-volume fixture. Irreversible migrations replace the downgrade step with a tested restore/recovery rehearsal and explicit approval.

