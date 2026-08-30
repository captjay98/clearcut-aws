# Identity & Organization Entry UI Design

**Date:** 2026-08-29
**Status:** Approved
**Surfaces:** `#auth`, `#onboarding`, `#invite`, `#projects`
**Depends on reviewed surfaces:** `#trust`, `#records`, `#team`, `#settings`

## Purpose

This design establishes the identity, organization-resolution, invitation-acceptance, and authorized project-discovery behavior that ClearCut needs before preliminary tenancy and authorization architecture begins. The mock at `misc/clearcut-flow/` remains the visual and interaction source of truth, but its seeded identity and authorization shortcuts must not become production semantics.

This document does not authorize mock implementation changes or freeze the complete OpenAPI and database schema.

## Approved decisions

1. ClearCut uses a membership-driven organization resolver after authentication.
2. Local PostgreSQL authentication is the default OSS deployment mode. Firebase/Identity Platform remains an optional managed mode.
3. A deployment selects one authentication provider for the initial release; mixed-provider account linking is out of scope.
4. Organization context is explicit in production URLs and enforced from immutable organization and project identifiers by the API.
5. Any verified user may create additional organizations unless deployment policy disables organization creation.
6. Invitations are bound to the invited verified email, store hashed single-use tokens, and accept idempotently.
7. Invitation lifecycle states are pending, accepted, declined, expired, and revoked.
8. An active Owner may invite another Owner after recent reauthentication and explicit confirmation.
9. Organization bootstrap may include an optional first invitation in the same database transaction. External delivery occurs after commit through a transactional outbox.
10. Membership deactivation immediately removes access to that organization without terminating identity sessions needed for unrelated organizations.
11. Only Owners and Admins may create projects.
12. Project rows, search results, aggregates, and activity expose only projects the user may access.
13. Registration policy is deployment-configurable and defaults to bootstrap-plus-invitation-only.
14. Email delivery is optional. Secure one-time bootstrap, invitation, and recovery-link workflows remain available without an email provider.
15. The initial release uses one deployment-level email provider selected from none, SMTP, Resend, or ZeptoMail.
16. Editor, Reviewer, and Viewer invitations may include zero or more explicit project grants. Owner and Admin inherit all-project access.
17. Organization slugs are stable, generated, collision-safe, and unique within a deployment. Renaming an organization does not change existing URLs.

## Relationship to the Team & Settings design

This later approval extends `docs/plans/2026-08-29-team-settings-ui-design.md` in two places:

- invitation lifecycle now includes `declined` in addition to pending, accepted, expired, and revoked;
- membership deactivation revokes organization and project authorization immediately but preserves an identity session that may still authorize unrelated organizations.

Implementation and contract plans must use this document for those identity-entry details while preserving the earlier Team, role, protected-setting, retention, and deletion decisions.

## Authentication architecture boundary

ClearCut supports one configured provider per deployment:

```text
AUTH_PROVIDER=local
AUTH_PROVIDER=firebase
```

### Local authentication

Local authentication is the default OSS path. The initial implementation may use FastAPI Users behind a ClearCut-owned identity interface, subject to an implementation-time dependency and security review because FastAPI Users is in maintenance mode.

Required properties:

- PostgreSQL-backed users and opaque revocable sessions;
- Argon2id password hashing with versioned parameters;
- secure, HTTP-only, SameSite cookies;
- email verification and account-recovery workflows when delivery is configured;
- rate limiting, generic credential errors, and security-event logging;
- account-level suspension and global session revocation;
- no organization role, project grant, or governed capability embedded in authentication state.

### Optional Firebase authentication

Firebase Authentication/Google Cloud Identity Platform remains an optional managed adapter. Terraform may configure it for Google Cloud deployments with billing enabled. Firebase establishes identity only; PostgreSQL remains authoritative for ClearCut users, memberships, roles, invitations, and project access.

### Internal identity

Both provider modes resolve to an internal `User` and then issue the same ClearCut server-side opaque, revocable application session. Provider-specific credentials and subject identifiers remain behind the identity boundary. Firebase ID tokens are verified only during session establishment or refresh and are not the browser's long-lived API authorization state. Mixed local/Firebase account linking is excluded from the initial release because unsafe email-based linking could enable account takeover.

### Browser session and CSRF boundary

The authenticated workspace and API are exposed through one same-origin public boundary even when `clearcut-web` and `clearcut-api` remain separately deployable Cloud Run services. A load balancer or workspace server routes `/api/*` without exposing a cross-site browser credential flow.

The application session uses a server-set `__Host-` cookie with `Secure`, `HttpOnly`, `Path=/`, no `Domain`, and `SameSite=Lax` (or stricter where compatible). The browser never stores an API bearer or refresh token in local storage. Every state-changing request requires a session-bound CSRF token and validated `Origin`; absent, cross-origin, expired, or mismatched values fail closed. Safe methods remain side-effect free. CORS does not permit arbitrary credentialed origins.

Session rotation occurs after sign-in, reauthentication, recovery, and privilege-sensitive account changes. Account suspension and global recovery revoke every ClearCut application session in both local and Firebase modes; Firebase disablement is checked during establishment/refresh and forces matching local-session revocation.

## Organization resolver

After authentication, ClearCut resolves the next surface in this order:

1. A valid invitation continuation resumes the invitation after identity matching.
2. One active organization membership enters that organization automatically.
3. Multiple active memberships show an organization chooser.
4. Zero memberships show Create organization when deployment policy permits it.
5. Deactivated-only memberships show a blocked/recovery state while still allowing creation when policy permits.

Projects never render until the server has authorized an active organization context.

Production route shape:

```text
/orgs/{stable-org-slug}/projects
/orgs/{stable-org-slug}/projects/{project-id}
```

The slug is a routing locator, not an authorization credential. API services resolve immutable identifiers and enforce authenticated `org_id`, plus `project_id` and project authorization for project-owned resources.

## Sign in

### Primary content

The surface adapts to deployment configuration:

- email and password fields for local authentication;
- Create account only when verified public registration is enabled;
- Forgot password with email or deployment-administrator recovery;
- Google sign-in only when the configured provider supports it;
- no seeded role or organization claim before membership resolution;
- preserved invitation continuation through authentication.

Registration defaults:

```text
ALLOW_PUBLIC_REGISTRATION=false
```

The first Owner uses a one-time bootstrap link. Subsequent users normally enter through invitations. Public deployments may enable verified self-registration. Public registration cannot be enabled without working email verification.

### States

- initial;
- authenticating;
- invalid credentials without account enumeration;
- unverified account;
- suspended account;
- provider unavailable;
- expired session;
- recovery requested;
- success and organization resolution.

## Create organization

Authentication is required. The surface contains:

- organization name;
- stable generated slug preview;
- creator identified as the first Owner;
- optional first teammate email, role, and project-access explanation;
- explanation of organization ownership and Owner authority.

Any verified user may create another organization unless:

```text
ALLOW_ORGANIZATION_CREATION=false
```

### Atomic bootstrap

One database transaction creates:

- Organization and immutable `org_id`;
- collision-safe stable slug;
- creator's active Owner membership;
- initial organization preference and policy bindings;
- optional invitation record;
- email-delivery outbox record when applicable;
- immutable audit events.

External email delivery never occurs inside the database transaction. A worker sends after commit. Provider failure remains visible and retryable without rolling back the organization or inventing delivery success.

The operation is idempotent so retries cannot create duplicate organizations, memberships, or invitations.

## Accept invitation

The route resolves an actual invitation token rather than seeded role or project data.

### Presented information

- organization;
- authorized inviter;
- invited normalized email;
- proposed fixed role;
- inherited or explicit project access;
- sent and expiration timestamps;
- capabilities and restrictions;
- current invitation status.

### Identity binding

Acceptance requires an authenticated account with a verified normalized email matching the invitation. Email normalization trims surrounding whitespace and lowercases the address only; ClearCut does not apply provider-specific dot removal, plus-address folding, or alias guessing. A mismatched account sees a safe explanation and a Sign out and use another account action. Possession of a forwarded token alone never grants access.

Only a current active Owner may issue an Owner invitation. Creation, edit, and resend each require current authority, recent reauthentication, and explicit confirmation. A pending Owner invitation never satisfies the requirement to retain at least one active Owner.

### Lifecycle

```text
pending → accepted
pending → declined
pending → expired
pending → revoked
```

Editing or resending a pending invitation invalidates its previous token and creates a new token version. Only token hashes are stored.

Acceptance atomically:

- locks and validates the invitation;
- marks it accepted;
- creates the organization membership only when no active or deactivated membership conflicts;
- creates applicable explicit project grants;
- records inherited Owner/Admin access semantics;
- writes the immutable audit event.

An already-active membership returns a conflict or the existing accepted result according to the invitation's history. A deactivated membership is never silently reactivated; the authorized Team reactivation flow must review role and project access explicitly. Repeated valid requests for an already-accepted invitation return the existing accepted result without duplicate memberships or grants.

Declining requires the matching authenticated identity, invalidates the token, creates no membership or project access, and writes a domain audit event. A later invitation is a new historical record with a new token.

Distinct states identify wrong account, malformed or missing token, already accepted, declined, expired, and revoked outcomes.

## Project access in invitations

- Owner and Admin invitations communicate inherited all-project access.
- Editor, Reviewer, and Viewer invitations permit zero or more explicit project selections.
- A member with zero grants may enter the organization but sees a no-project-access state.
- Organization membership is never treated as an implicit project grant for Editor, Reviewer, or Viewer.

## Projects

### Authorization and visibility

- Owner and Admin see every active project in the selected organization.
- Editor, Reviewer, and Viewer see only explicitly granted projects.
- Search, filters, counts, open-review totals, blocked-item totals, report totals, and activity use the same authorized project set.
- Unauthorized projects do not leak through names, counts, search suggestions, activity, or direct-link error details.
- Direct unauthorized or cross-tenant project locators produce an access-safe not-found response.

Only Owner and Admin may create projects. Editors receive script-import and content capabilities only within explicitly authorized projects.

### Empty and exceptional states

The surface distinguishes:

1. organization has no projects and the user can create one;
2. organization has no projects and the user lacks creation authority;
3. organization has projects but the user has no grants;
4. filters return no authorized results;
5. loading with project-card skeletons;
6. recoverable request failure with Retry;
7. organization access removed, returning to the resolver;
8. access-safe organization not found that echoes the typed slug but uses the same status, timing class, and explanation for unknown and unauthorized organizations;
9. successful project creation or import.

Capability-gated creation remains focusable and explains the restriction. Authorization-restricted project data is not rendered.

## Deactivation and session behavior

Organization membership deactivation:

- immediately denies organization and project requests;
- invalidates organization-scoped authorization caches and grants;
- preserves historical attribution;
- preserves the identity session for other organizations;
- returns an affected active page to the organization resolver.

Account-level suspension revokes all active sessions. Local opaque sessions make global revocation enforceable. Every request still resolves current membership and project authorization rather than trusting stale session claims.

## Email provider boundary

The initial deployment selects one provider:

```text
EMAIL_PROVIDER=none
EMAIL_PROVIDER=smtp
EMAIL_PROVIDER=resend
EMAIL_PROVIDER=zeptomail
```

Adapters implement a typed `EmailProvider` port and return typed success or error results. ClearCut owns templates, legal-boundary text, URLs, token generation, and message intent.

A durable outbox provides:

- same-transaction enqueueing for domain actions;
- idempotency keys;
- bounded retries with jitter;
- permanent-failure visibility;
- delivery status and provider receipt identifiers;
- verified webhook processing where supported;
- duplicate-delivery defenses.

Invitation, bootstrap, verification, and recovery secrets use cryptographically random high-entropy single-use tokens with bounded expiry. Only token hashes are stored in domain records. An email outbox never persists a live token or complete one-time URL in plaintext: any delivery-only token material is envelope-encrypted for the worker, excluded from logs/traces/provider metadata, and erased after terminal delivery or expiry. Token use, expiry, replacement, recovery, and administrative issuance are auditable. Account recovery invalidates prior recovery tokens and, on completion, revokes all application sessions.

Credentials remain deployment-managed in Secret Manager or equivalent environment configuration. Organization-specific sending providers, provider failover, and automatic cross-provider rerouting are out of initial scope.

### No-email operation

Without a configured provider:

- the initial Owner receives a one-time bootstrap link from the deployment workflow;
- Owners may copy one-time invitation links;
- the deployment CLI may generate one-time recovery links after explicit administrator confirmation;
- secrets are not re-displayed after initial issuance;
- public registration remains disabled;
- account-recovery UI explains that the deployment administrator must assist.

## State, accessibility, and responsive requirements

All four surfaces implement loading, empty, recoverable error, permanent error, success, and not-found states appropriate to their resource.

Forms use visible labels, `aria-invalid`, and linked `aria-describedby` messages. Async controls expose busy state, prevent accidental duplicate submission, and announce outcomes through live regions. Focus moves to the first invalid field or resolved page heading. Authentication and invitation errors avoid identity or tenant enumeration.

Organization choosers, invitation controls, and project rows are keyboard operable. Coarse-pointer targets are at least 44px. Dialogs trap focus, make the background inert, and restore focus. Reduced-motion settings are honored.

At narrow breakpoints, prerequisite and error banners stack actions below copy instead of compressing text. Script and Night shoot themes retain equivalent contrast, states, and hierarchy from 320 through 1440 pixels.

## Required mock corrections

1. Replace the seeded Owner identity and unconditional Google-only flow with configuration-aware authentication content.
2. Stop routing every successful sign-in directly to onboarding; represent the organization resolver outcomes.
3. Require authentication for organization creation and invitation mutation.
4. Replace seeded organization mutation with atomic organization bootstrap semantics.
5. Replace embedded invited pseudo-members with durable Invitation records and all five lifecycle states.
6. Resolve invitation token, inviter authority, email match, role, projects, and timestamps from invitation state.
7. Replace unconditional invitation acceptance with matched, idempotent, atomic acceptance.
8. Scope Projects, aggregates, search, and activity to the selected authorized organization and project set.
9. Gate project creation to Owner/Admin and stop selecting a seeded project as a substitute for creation.
10. Add complete state, form-error, async-progress, narrow-banner, and resource-not-found behavior.

No mock implementation changes are authorized by this document alone.

## Domain implications for later architecture

This design establishes the need for, without fixing final table or column names:

- User;
- provider identity or local credential record;
- opaque Session with revocation;
- Organization with stable slug;
- Membership with fixed role and status;
- Invitation with hashed versioned token and lifecycle;
- ProjectMembership with inherited or explicit grant provenance;
- EmailOutbox and EmailDeliveryAttempt;
- provider configuration and health projection;
- immutable AuditEvent and security-event records.

The implementation must keep identity verification separate from authorization, preserve ownership-aware tenant scope, enforce current membership on every request, and commit consequential domain actions with their audit events.

## Deployment and agent-setup implications

The future Google Cloud Terraform and agent-friendly setup system should:

- support local auth without Firebase configuration;
- optionally provision Firebase/Identity Platform;
- choose one authentication mode explicitly;
- configure one email provider or no-email mode;
- store secrets in Secret Manager;
- use Application Default Credentials or workload identity rather than exported service-account keys;
- use plan/apply approval gates;
- consume Terraform outputs to configure services;
- verify authentication, organization bootstrap, email delivery or fallback, and authorization after deployment.

Relevant external skill references discovered during review include:

- `firebase/agent-skills@firebase-auth-basics`;
- `google/agents-cli@google-agents-cli-deploy`;
- `google/skills@google-cloud-solution-build-deploy-agents`;
- `gemini-cli-extensions/cicd@google-cicd-terraform`.

ClearCut should use those as reviewed references and produce its own canonical deployment skill under `.agents/skills/` rather than importing overlapping instructions without review.

## Architecture gate and remaining review order

This approval permits preliminary design of:

- identity-provider and session boundaries;
- User, Organization, Membership, Invitation, and ProjectMembership relationships;
- membership-driven organization resolution;
- authorization middleware and repository scopes;
- email-provider and transactional-outbox ports;
- organization bootstrap and invitation-acceptance transactions.

Do not freeze the complete OpenAPI or database schema yet. Continue semantic UI review in this order:

1. `#new` — project creation, four ingestion paths, immutable initial version, and durable initial processing;
2. `#project`, `#workspace`, `#items`, `#item` — analysis, evidence, provenance, filtering, assignments, and governed evidence actions;
3. `#versions`, `#watch`, `#report` — revision lineage, selective re-scan, monitoring, version-bound dossier generation, release, and export;
4. `#notifications` — event types and destinations after producing workflows are approved;
5. `#marketing`, `#sitemap`, `#states` — public and prototype-only surfaces.

Project ingestion, evidence, revisions, monitoring, and report review remain prerequisites for freezing the full schema and OpenAPI domain contracts.

## Verification expectations

When implementation targets exist, verify:

- same-origin routing, `__Host-` session-cookie attributes, session rotation/revocation, CSRF token and Origin enforcement, safe-method side-effect freedom, and restrictive credentialed CORS;
- local registration, login, logout, verification, recovery, and session revocation;
- trim-and-lowercase email normalization without dot/plus folding;
- optional Firebase identity verification and suspension parity without Firebase-held authorization or browser-held long-lived API bearer tokens;
- provider-mode isolation and disabled mixed-account linking;
- membership-driven resolver outcomes;
- multiple-organization switching and explicit URL context;
- organization bootstrap idempotency and optional invitation outbox behavior;
- all invitation lifecycle, token, wrong-account, and repeat-acceptance cases;
- Owner-invitation reauthentication and final-active-Owner protection;
- membership deactivation across one versus multiple organizations;
- Owner/Admin inherited and explicit project grants;
- authorized-only Projects lists, search, counts, and direct links;
- no-email bootstrap, invitation, and recovery operations;
- SMTP, Resend, and ZeptoMail shared provider-contract tests;
- keyboard, focus, form-error, live-region, responsive, and both-theme behavior.
