# Memberships, Invitations, Roles, and Grants Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement five-state invitations, fixed roles, project grants, and safe membership lifecycle.  
**Architecture:** PostgreSQL state is authoritative; role/capability input is never accepted from clients/adapters.  
**Tech Stack:** FastAPI, PostgreSQL, outbox email port.

---

**Files:** Create `organizations/domain/capabilities.py`, `domain/invitations.py`, `application/membership_service.py`, `application/invitation_service.py`, `ports/email_delivery.py`, `services/api/alembic/versions/0003_memberships_invitations.py`; test `services/api/tests/organizations/test_capabilities.py`, `test_invitations.py`, `test_membership_lifecycle.py`.

1. Add failing table-driven tests for every role/action in `docs/APPROVAL_POLICY.md`, DG-02/DG-03, final-Owner protection, token hashing/versioning, wrong email, resend invalidation, and idempotent acceptance.
2. Add migration 0003 and uniqueness/index constraints; prove downgrade and no plaintext token storage.
3. Implement semantic membership/invitation operations and outbox intent; use a typed disabled-email result when configured.
4. Run role matrix, invitation replay, deactivation/cache invalidation, contract, and migration suites; expect exit 0.
5. Record evidence; commit `feat: add governed membership and invitation lifecycle` after authorization.

**Exit:** Every capability comes from current server state and at least one active Owner remains.

