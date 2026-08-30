---
description: 'Diagnose incidents read-only and recover only with fresh authorization'
---

@devops-engineer Investigate this optional incident context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If absent, request incident ID, account, project, environment, symptoms, start time, and impact before touching a system.

## Safety contract

- **Read-only by default.** Diagnosis may inspect status, logs, metrics, revisions, queue state, and audit records only.
- Before every cloud, database, or provider mutation, display the target account/project/environment, resource, intended effect, and rollback. Obtain a fresh, explicit human confirmation for that one mutation. A prior confirmation does not carry forward; batch approval is not sufficient.
- Never run an ad hoc live Parallel search or an HTTP request with credentials. Do not probe providers using fabricated queries, keys, shell placeholders, or invalid quoting. Inspect provider receipts, recorded responses, approved health telemetry, or the typed provider port in a controlled environment.
- Do not print secrets, tokens, screenplay text, source contents, or personal data. Do not use destructive commands, broad retries, or emergency schema edits during diagnosis.
- If the deployment/platform paths are absent, report `not applicable — prerequisite absent`; do not invent resource names or environments.

## Read-only protocol

1. Record incident scope, account/project/environment, actor, timestamp, correlation ID, and severity.
2. Inspect repository status and deployed version metadata without mutation.
3. Read service health, recent revisions, error rates, traces, queue/lease/checkpoint state, database health, and provider receipts using existing approved tooling and exact configured resource names.
4. Check ClearCut invariants:
   - no fabricated evidence during provider failure;
   - failed jobs are visible as retryable/permanent review items;
   - no decisions without a matching same-transaction authoritative `AuditEvent` and consistent Receipt projection;
   - no cross-tenant access or missing `org_id`/`project_id` scope;
   - immutable script versions and exact report bindings remain intact;
   - prompt/source content did not alter policy or tool permissions.
5. Form ranked hypotheses and identify evidence that would falsify each. Keep diagnosis read-only.
6. Propose mitigations with blast radius, rollback, owner, and verification. Stop before mutation and request fresh confirmation.

## Authorized recovery protocol

Only after confirmation for a named action: restate the exact target and environment, execute one reversible mutation, capture output/receipt, verify health and invariants, and request a new confirmation before the next mutation. Examples include traffic rollback, bounded queue recovery, or scaling; never run guessed scripts or direct provider calls. Database changes go through the migration workflow, not incident shell commands.

## Post-incident report

Include timeline, detection, impact by tenant/project, root cause confidence, read-only evidence, authorized actions and confirmations, recovery verification, authoritative audit events and Receipt references, unresolved risk, and prevention work. Do not claim recovery until evidence supports it.
