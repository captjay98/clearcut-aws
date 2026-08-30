---
name: migration-strategy
description: Use when planning or reviewing SQLAlchemy and Alembic schema changes for Cloud SQL PostgreSQL, including zero-downtime rollouts, backfills, and rollback.
---

# Migration Strategy

Evolve ClearCut's Cloud SQL PostgreSQL schema without breaking running application versions or weakening evidence and audit integrity.

## Expand-Contract

Prefer additive changes and staged rollouts:

- Add nullable columns, tables, indexes, or enum values first.
- Deploy code that can read old and new shapes, then backfill in bounded batches.
- Switch reads and writes only after the new shape is populated and verified.
- Remove old columns or constraints in a later migration after no deployed code depends on them.

Never drop, rename, or change a large column type in one deploy.

## Alembic and PostgreSQL Rules

- Write migrations with Alembic and explicit SQLAlchemy types; do not use framework-specific migration systems from another stack.
- Provide a tested `upgrade()` and `downgrade()` for reversible changes. If data loss makes rollback impossible, document the irreversible boundary and recovery plan.
- Use PostgreSQL-safe deployment patterns. Create large indexes concurrently when appropriate, and account for Alembic transaction behavior before using `CONCURRENTLY`.
- Avoid table rewrites and long locks. Backfill by stable primary-key ranges or bounded batches, with progress and restartability.
- Never deploy code that requires a new column, index, or constraint before the migration is applied.
- Preserve tenant keys, foreign keys, unique constraints, version binding, provenance, and transactional audit invariants.

## Verification

Test migrations against representative production-sized data, exercise both upgrade and rollback paths, inspect query plans for new indexes, and verify old and new application versions can coexist during the rollout. Record the migration, backfill status, lock assumptions, and recovery steps in the release notes.
