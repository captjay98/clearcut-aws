# ClearCut Approval Policy

## Fixed roles

| Role | Authority |
|---|---|
| Owner | Organization lifecycle, ownership, protected configuration, all authorized review/report actions |
| Admin | Members, projects, providers, operational settings, all authorized review/report actions; protected config read-only |
| Editor | Import, research, assignments/reassignments, comments, rewrite proposals, operational monitoring triggers |
| Reviewer | Assignments/reassignments, evidence decisions, referrals, dispositions, rewrite approval, monitoring review, report generation/release |
| Viewer | Read-only authorized projects and released reports |

Owner/Admin inherit all project access. Editor/Reviewer/Viewer require explicit project grants. At least one active Owner must remain.

## Action classes

- **Read:** authorized retrieval; no domain mutation.
- **Operational write:** assignment, due date, comment, notification read state, cadence, manual run trigger. Requires capability and ordinary audit/operation record.
- **Draft:** item candidate, query, rewrite proposal, proposed decision. Does not make an authoritative call.
- **Governed write:** evidence decision, rewrite approval, specialist referral, disposition, monitoring review, protected policy activation, report generation, initial release, deletion scheduling/restoration. Downloading an already released artifact is an authorized read.

## Governed command contract

```python
class GovernedCommand(BaseModel):
    actor_id: UUID
    org_id: UUID
    project_id: UUID
    intent_hash: str
    rationale: str
    expected_version: int
    idempotency_key: str
```

The server ignores client-supplied roles/capabilities, loads current membership/project/policy state, checks any recent-reauthentication and maker/checker rule, validates the intent hash and optimistic version, then commits domain state and `AuditEvent` together.

## Maker/checker

- A rewrite proposer cannot approve the same proposal.
- A protected-policy drafter cannot use an Admin role to activate it; activation is Owner-only with recent reauthentication, typed confirmation, and rationale.
- Automated learning cannot bypass regression, gate, shadow/canary, or rollback requirements.

## Failure behavior

Authorization, stale-version, sign-off, and maker/checker failures are typed conflicts/forbidden errors. The UI keeps the attempted control focusable and explains the current restriction; it never hides a policy failure behind a generic error.
