---
description: 'Plan and safely execute database migrations'
---

@backend-engineer Plan or execute this optional migration scope: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If migration, environment, and authorization are not explicit, remain in plan mode and ask focused questions.

## Default mode: plan and dry-run

This command is **plan/dry-run by default**. It must not apply a migration, alter data, create a production backup, or claim rollback success without explicit human authorization for the named environment and action. The current repository is pre-implementation; if migration tooling, schema, or database configuration is absent, report `not applicable — prerequisite absent` and do not create guessed artifacts.

## Guardrails

- Display and confirm the exact environment (`local`, `staging`, or `production`), account/project, database instance, schema revision, actor, and intended effect before any database mutation.
- Never put credentials in commands or logs. Do not connect to an unapproved database.
- Prefer additive, backward-compatible changes. No single-deploy drops, renames, narrowing types, non-null constraints without a safe backfill, or unbounded updates.
- Use expand-contract: expand schema and dual-read/write, backfill in bounded resumable batches, verify parity, cut over, then contract in a later approved release.
- Use forward-fix for production issues unless an explicit rollback is safer and tested. A down migration is not automatically a safe rollback for data changes.
- Preserve ownership-aware scope in every query: organization-owned data uses authenticated `org_id`; project-owned data uses `org_id` + `project_id` with membership/ownership checks; explicitly global catalogs are allowlisted and contain no tenant content. Preserve immutable script versions and transactional decision/audit records.

## Protocol

1. Inventory actual migration files, ORM configuration, current revision, environment configuration, data volume, locks, and deployment compatibility.
2. Produce a dry-run SQL/DDL summary, affected tables/indexes, lock/latency risks, tenant impact, backfill plan, observability, and rollback/forward-fix decision.
3. Review destructive operations and classify expand, backfill, contract, or forward-fix steps. Require human owner sign-off for protected rules and production.
4. In an isolated environment only after authorization, apply the migration through the repository's declared tool, capture output, and run schema/constraint/tenant-scope checks.
5. For production, obtain fresh confirmation immediately before each mutation. Verify backups/restore point, deploy compatibility, bounded batch progress, and audit logs.
6. Verify application behavior and report the exact revision, timing, rows affected, errors, and remaining contract/cleanup work.

## Output

Return mode (`plan`, `dry-run`, or authorized execution), environment identity, migration risk, exact commands actually run, output, tenant/data safety, rollback or forward-fix plan, and explicit not-run items. Never claim a migration was applied from a plan.
