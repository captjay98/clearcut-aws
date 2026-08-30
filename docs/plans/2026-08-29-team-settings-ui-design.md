# Team & Settings UI Design

**Date:** 2026-08-29
**Status:** Approved
**Surfaces:** `#team`, `#settings`
**Depends on reviewed surfaces:** `#trust`, `#records`

## Purpose

This design updates the semantic requirements for Team & roles and Settings before ClearCut locks its authorization architecture, API contracts, or database schema. The mock at `misc/clearcut-flow/` remains the visual and interaction source of truth, but the current Team and Settings content must be reconciled with the newer ownership, governance, tenant-scope, protected-policy, and evidence-retention decisions.

## Approved decisions

1. Owner, Admin, and Reviewer may perform governed evidence decisions and report generation/release, subject to server authorization and same-transaction audit.
2. Protected organization settings are Owner-only. Admin may manage operational settings and inspect protected configuration but cannot change or activate it.
3. Owner and Admin receive inherited access to every project. Editor, Reviewer, and Viewer require explicit project grants.
4. Active members are deactivated rather than hard-deleted. Historical attribution remains intact.
5. Invitations use the complete lifecycle: pending, accepted, declined, expired, and revoked, with edit and resend support.
6. Organizations may have multiple Owners and must always retain at least one active Owner.
7. Team remains one route with URL-addressable Members, Invitations, and Roles & access tabs.
8. Settings remains one route with URL-addressable General, Governance, Data & privacy, and Integrations tabs.
9. Protected configuration follows draft → validate/preview → activate. Active versions are immutable.
10. Core project data is retained indefinitely until an Owner deletes the project or organization. There is no automatic age-based deletion.
11. Individual claims, source snapshots, decisions, comments, policy bindings, and audit events cannot be selectively deleted.
12. Project and organization deletion use a 30-day reversible grace period before final purge.

## Role and authority model

ClearCut uses five fixed roles. They are global read-only definitions; organizations assign them through tenant-scoped memberships.

| Role | Authority |
|---|---|
| Owner | Organization lifecycle, ownership, protected settings, project access, operations, and all governed review actions |
| Admin | Membership, projects, providers, operational settings, and all governed review actions; protected settings are read-only |
| Editor | Script import, research, assignments, comments, and rewrite proposals |
| Reviewer | Evidence verification/rejection, referrals, dispositions, rewrite approval, and report generation/release |
| Viewer | Read-only access to authorized projects and reports |

Authorization is enforced by backend services and repositories. UI gating is explanatory, not a security boundary. Every governed decision requires an accountable human and commits its immutable audit event in the same transaction.

## Project-access model

- Owners and Admins have access to every organization project.
- Project authorization remains explicit and auditable. Creating a project creates role-inherited project memberships for all active Owners and Admins in the same transaction.
- Promoting a member to Owner or Admin grants every current project.
- Demoting an Owner or Admin removes role-inherited grants. The role-change flow must select any explicit projects the person should retain before committing.
- Editor, Reviewer, and Viewer access is always represented by explicit project memberships.
- Role-derived grants cannot be removed while the person remains Owner or Admin.
- The UI distinguishes `All projects · inherited from Owner/Admin` from explicit project names.

## Team & roles

### Route and tabs

- `#team?tab=members`
- `#team?tab=invitations`
- `#team?tab=roles`

The tab state is URL-addressable so notifications and records can deep-link to the relevant view. Tabs use the existing `TabsBar` pattern and scroll horizontally on narrow screens.

### Members tab

The primary tab shows active and deactivated organization memberships.

Desktop columns:

- Member
- Organization role
- Project access
- Status
- Last active
- Actions

On mobile, rows become cards and actions collapse into a compact menu.

Member actions:

- Change role
- Edit project access
- Deactivate
- Reactivate
- View audit history

Role changes must preselect the current role, show before/after capability differences, explain access effects, require explicit retained-project selection when demoting Owner/Admin, and prevent removal of the final Owner. Role and project-access changes commit atomically with their receipt.

Deactivation:

- sets membership status to `deactivated`;
- immediately revokes that organization's membership and project authorization, invalidates organization-scoped authorization caches, and returns active organization pages to the resolver;
- preserves the identity session when it still authorizes unrelated organizations; account suspension, not membership deactivation, performs global session revocation;
- blocks new assignments and governed actions in the deactivated organization;
- preserves identity on previous decisions, comments, assignments, reports, and receipts;
- permits later reactivation only after explicit role and project-access review; invitation acceptance never silently reactivates a deactivated membership;
- cannot remove the final active Owner.

### Invitations tab

Columns or card fields:

- Invitee email
- Proposed role
- Project access
- Invited by
- Sent at
- Expires at
- Status
- Actions

Actions by state:

| State | Actions |
|---|---|
| Pending | Edit, resend, revoke |
| Expired | Resend |
| Revoked | View receipt |
| Declined | View receipt, create a new invitation |
| Accepted | View resulting member |

Editing or resending invalidates the previous token and issues a new token version. Owner invitations require a current active Owner, recent reauthentication, and explicit confirmation on create, edit, and resend. Invitations retain historical state after acceptance, decline, expiry, or revocation. Pending invitees use `Edit invitation`, never `Change role`.

Acceptance transactionally creates a new organization membership or returns the existing active membership, creates applicable project memberships, writes the audit event, and marks the invitation accepted. It must not silently reactivate a deactivated membership; that requires the separate explicit reactivation flow. Owner/Admin invitations force inherited all-project access. Editor/Reviewer/Viewer invitations allow multiple explicit project selections.

Decline requires the matching verified identity, creates no membership or project grant, invalidates the token, and writes a domain audit event. A later invitation is a distinct record with a new token.

Handle duplicate member, wrong-account, expired-token, revoked-token, and already-accepted outcomes explicitly.

### Roles & access tab

This tab shows the canonical role matrix, grouped into:

- organization capabilities;
- project capabilities;
- governed review actions;
- protected Owner-only controls;
- inherited and explicit access behavior.

The mock-only `Preview as a role` control remains useful for prototype and automated role testing but does not ship as an organization-management control.

## Settings

### Route and tabs

- `#settings?tab=general`
- `#settings?tab=governance`
- `#settings?tab=data`
- `#settings?tab=integrations`

The route remains one of the approved 20 surfaces. Tabs are URL-addressable and use the existing responsive `TabsBar` pattern.

### General tab

Owner and Admin may edit:

- organization name;
- primary jurisdiction;
- default monitoring cadence;
- other non-protected organization preferences.

The plan is read-only. The cadence control states that changes apply to projects created after activation; existing projects retain their project-specific cadence. Appearance remains a personal browser preference and is not an organization setting.

### Governance tab

Global read-only catalogs:

- role and capability definitions;
- ten-category schema;
- platform source-authority defaults.

Organization-owned, versioned configuration:

- sign-off and approval policy;
- organization source-authority policy or approved overrides;
- prompt versions;
- rubric configuration;
- permitted evidence-schema extensions;
- deterministic blocking rules;
- legal-boundary language.

Category definitions and source-authority ranking remain separate protected policies. Neither establishes a legal conclusion.

Only Owners may create, edit, validate, or activate protected drafts. Admins may inspect active configuration, validation results, and history. Activation requires recent reauthentication, typed confirmation, and a recorded rationale. Permitted evidence-schema extensions may add optional organization fields only; they cannot remove or weaken required source, excerpt, stance, authority, conflict, uncertainty, query/run identity, or provenance fields.

Lifecycle:

```text
draft → validated → active → superseded
          ↘ validation_failed
```

Each area shows active version, status, author, activation time, rationale, validation outcome, linked AI Trust evaluation, linked Records receipt, and version history. Active versions are immutable. Restoring old content creates a new draft copied from the historical version.

Activation transactionally supersedes the prior version, activates the new one, and writes the audit event. Research runs, evidence decisions, reports, and judge evaluations bind to the exact configuration versions used.

### Data & privacy tab

Automatic age-based deletion is off.

Primary product statement:

> Project evidence is retained until an Owner deletes the project or organization.

The UI inventories stored data classes without assigning separate expiration timers:

- original scripts and normalized screenplay data;
- source snapshots and evidence;
- reports and export artifacts;
- operational logs and provider payloads;
- minimized audit metadata.

Private scripts are never used for shared-model training. Signed download URLs are short-lived and regenerated on demand; link expiry does not delete the artifact.

Deletion rules:

- only an Owner may delete a project or organization;
- individual claims, snapshots, decisions, comments, policy bindings, and audit events cannot be selectively deleted;
- deletion requires typed confirmation and a complete impact preview;
- the Owner may export the retained record before scheduling deletion;
- scheduling makes the resource read-only, blocks new jobs and governed actions, revokes signed links, and safely terminates active work;
- a 30-day grace period permits Owner restoration;
- final purge removes sensitive content, provider payloads, and stored blobs;
- minimized tombstone and audit metadata retain only the identifiers, hashes, timestamps, action type, scope, and deletion linkage needed to preserve historical references; personal data is removed or irreversibly pseudonymized unless an approved legal obligation requires otherwise;
- any report whose required source material was purged becomes explicitly unavailable and no longer claims reproducibility;
- the impact preview names which reproducibility guarantees will be lost;
- scheduling, restoration, and final purge each create immutable audit events and Receipt projections.

The tab lists pending deletions with deletion dates and Restore actions.

### Integrations tab

Providers include Gemini; mandatory Parallel Search; bounded Parallel Extract; conditional Parallel Monitor when its reviewed go/no-go is GO; Cloud Storage; the configured identity adapter; the configured email adapter; and Cloud Tasks/Scheduler when implemented. Search, Extract, and Monitor appear as separate capability rows under one Parallel partner grouping so health never implies that one successful capability proves the others.

Each row shows:

- purpose;
- configuration state;
- current health;
- last successful operation;
- active incident or retry state;
- link to filtered Records history.

Credentials remain environment-managed. Settings presents configuration and health; detailed attempts, retries, failures, and recovery history live in Records. Owner and Admin may perform permitted operational recovery actions, and every consequential action writes a receipt.

## State and accessibility requirements

Both routes handle loading, empty, recoverable error, permanent error, success, and not-found states. Stale member, invitation, configuration-version, project, or deletion-request links identify the missing identifier.

Capability-restricted controls remain focusable and explain the restriction. Forms use visible labels and linked validation messages. Dialogs trap focus, make the background inert, and restore focus to the triggering control. Draft validation and activation report progress through status text and live regions. Coarse-pointer targets are at least 44px.

## Visual and responsive findings

Desktop Script and 375px Night shoot layouts were inspected. The existing visual vocabulary, table-to-card conversion, typography, themes, navigation, and semantic states remain appropriate.

Required mock corrections:

1. The narrow-screen prerequisite banner currently keeps its CTA beside the message and compresses the copy into an unreadably narrow column. Stack the CTA below the copy at the mobile breakpoint on both Team and Settings.
2. The current Change role dialog does not preselect the member’s existing role and therefore defaults to Owner. It must preselect the current role and show the access/capability effects before saving.
3. Pending invitations currently expose Change role. Replace it with Edit invitation and separate invitation actions.
4. Replace the Settings evidence-retention duration selector with the approved indefinite-retention and Owner-controlled deletion model.
5. Move operational retry history out of Settings and link to the filtered Records ledger.

No mock implementation changes are authorized by this document alone.

## Domain implications for later architecture

This design establishes the need for, without fixing the final column schema:

- User/identity records;
- Organization;
- Membership with status and fixed role;
- Invitation with token lifecycle and proposed access;
- ProjectMembership with inherited or explicit grant provenance;
- global RoleDefinition and CapabilityDefinition catalogs;
- organization preference versions;
- protected configuration drafts, validations, and active versions;
- provider configuration and health projections;
- deletion requests and durable purge jobs;
- immutable audit events and receipts.

The database and API design must preserve organization versus project ownership, transactional audit for consequential actions, immutable version binding, and full historical attribution.

## Verification expectations

When production targets exist, verify:

- role and project-access transitions;
- final-Owner protection;
- invitation decline, expiry, resend, edit, revoke, acceptance, and wrong-account handling;
- deactivation/reactivation, organization-scoped cache invalidation, preserved unrelated-organization sessions, and account-level global revocation;
- protected Settings authorization;
- draft validation and atomic activation;
- exact version bindings in Trust, Records, runs, decisions, and reports;
- project/organization deletion scheduling, restoration, and purge;
- desktop and 320–1440px responsive behavior in both themes;
- keyboard operation, dialog focus, live regions, and capability explanations;
- same-transaction audit completeness.


## Semantic UI review status and remaining order

Approved in the current requirements review:

1. `#trust` — AI trust
2. `#records` — Records
3. `#team` — Team & roles
4. `#settings` — Settings

Recommended remaining sequence:

1. **Identity and organization entry:** `#auth`, `#onboarding`, `#invite`, `#projects`. This locks configured identity-provider transitions, organization creation, invitation acceptance, membership bootstrap, project discovery, and tenant boundaries.
2. **Project creation and ingestion:** `#new`. This locks project creation, four import paths, immutable first version, upload state, and initial durable detection/research execution.
3. **Analysis and evidence workspace:** `#project`, `#workspace`, `#items`, `#item`. This locks the primary project projections, stable script spans, clearance-item states, evidence/provenance presentation, assignment, filtering, and governed evidence actions.
4. **Revision, monitoring, and delivery:** `#versions`, `#watch`, `#report`. This locks immutable revision lineage, selective re-scan, monitoring changes, final dispositions, report bindings, generation, release, and export.
5. **Cross-workflow notifications:** `#notifications`. Review after its producing workflows so every notification type and destination is grounded in an approved event.
6. **Public and prototype-only surfaces:** `#marketing`, `#sitemap`, `#states`. These can be finalized after domain workflows because they do not define the relational model.

Architecture gate:

- Preliminary tenancy and authorization architecture may begin after the Identity and organization-entry batch because Team and Settings authority is now approved.
- Do not freeze the full database schema or OpenAPI domain contracts until Project creation, Analysis/evidence, and Revision/monitoring/delivery reviews are approved. Those surfaces determine version lineage, evidence provenance, durable job states, governed decisions, monitoring, and report reproducibility.
- Marketing and prototype-tool review does not block backend schema design.
