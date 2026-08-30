# Identity and Tenancy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement revocable application sessions, organization resolution, five-state invitations, fixed roles, and ownership-aware project authorization.

**Architecture:** Identity adapters establish a user only; PostgreSQL owns sessions, organizations, memberships, roles, and project grants. Every request loads current scope; UI gating explains but never enforces security.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, PostgreSQL, Argon2id, optional Firebase adapter, generated clients, TanStack Start.

---

**Depends on:** Plan 01  
**Checkpoint:** R2 with Plan 03

### Task 1: Model sessions, organizations, memberships, and invitations

**Files:** Create `services/api/src/clearcut/identity/`, `organizations/`, Alembic migration, and domain tests.

Write failing tests for opaque-session revocation, final-Owner protection, explicit Editor/Reviewer/Viewer grants, and invitation transitions.

```python
assert invitation.transition("accepted", actor=matching_user).status == "accepted"
with pytest.raises(WrongInvitationIdentity):
    invitation.transition("accepted", actor=other_user)
```

Run narrow tests red; implement framework-free aggregates; run green; commit.

### Task 2: Implement local identity and application sessions

**Files:** Create `identity/ports.py`, `identity/adapters/local.py`, session repository/service/routes, CSRF middleware, security tests.

Test Argon2id parameters, generic login errors, verified-email policy, recovery, cookie attributes, CSRF/Origin rejection, fixation rotation, global revocation, and safe-method purity. Add Firebase only as a contract-tested optional adapter; do not mix providers.

### Task 3: Implement atomic organization bootstrap and resolver

**Files:** Create organization application service/routes and `apps/web/src/routes/auth/`, `onboarding/`, `organizations/`.

Bootstrap transaction includes organization, stable slug, Owner membership, default bindings, optional invitation/outbox, and audit. Test idempotent retry and rollback. Resolver covers invitation continuation, one/many/zero/deactivated memberships.

### Task 4: Implement invitation lifecycle and Team foundation

**Files:** Create invitation service/routes, token/email outbox adapter boundary, generated-client consumers, invitation UI tests.

Test pending/accepted/declined/expired/revoked, token hashing/versioning, edit/resend invalidation, wrong account, Owner invitation reauthentication, deactivated-membership conflict, and idempotent repeated acceptance.

### Task 5: Enforce project scope everywhere

**Files:** Create authorization policy/repository helpers and cross-tenant tests.

```python
async def get_project(
    *, org_id: UUID, project_id: UUID, actor_id: UUID
) -> AuthorizedProject: ...
```

No repository overload omits `org_id`. Test list, count, search, direct link, cache invalidation, deactivation, role change, and unknown/unauthorized parity.

### Verification

Run narrow domain tests, PostgreSQL integration tests, contract drift, generated-client tests, and browser flows for sign-in/resolver/invite/onboarding/projects/team at 320 and 1440 in both themes.

```bash
uv run pytest services/api/tests/identity services/api/tests/organizations -q
pnpm --filter @clearcut/web test -- identity tenancy
pnpm contract:check
```

Expected: all commands exit 0; cross-tenant negative tests are included in the passing count.

### Exit criteria

- Local auth and optional identity adapter satisfy one shared contract.
- Opaque session/CSRF/revocation behavior passes security tests.
- Organization bootstrap and invitation acceptance are atomic/idempotent.
- Cross-tenant/project access is denied without leakage.
- Owner/Admin versus explicit project grants match policy.
- No production UI trusts seeded role/scope state.
