# Notifications UI Design

**Date:** 2026-08-29
**Status:** Approved
**Surface:** `#notifications`
**Depends on reviewed surfaces:** `#trust`, `#records`, `#team`, `#settings`, `#auth`, `#onboarding`, `#invite`, `#projects`, `#new`

## Purpose

This design establishes the notification inbox, event taxonomy, recipient model, delivery layers, destination integrity, privacy, authorization, and operational state behavior for ClearCut's `#notifications` surface. It defines what generates a notification, who receives it, how it reaches them, what it contains, and where it links — grounded in the domain actions approved by the previous surface designs.

The mock at `misc/clearcut-flow/` remains the visual and interaction source of truth. Its seed entries illustrate the inbox pattern but must not become production semantics. This document does not authorize mock implementation changes.

## Approved decisions

1. Notifications live in a single organization-level inbox. Entries from all authorized projects appear together, each labeled with its project name. Organization-level events (invitations, role changes, learning governance) appear without a project label.
2. Each event computes an explicit recipient list based on the event type, the item's ownership/assignment, and the recipient's project authorization. The actor who performed the action never receives their own notification. Recipients are scoped to the project the event occurred in.
3. Each notification carries a redacted human-facing projection with a title, summary, tier, and stable destination. Internal metadata (model names, rubric versions, prompt IDs, search methods, provider receipts) is never included. That detail remains in Records for authorized users.
4. Each notification stores a structured entity destination: `{org_id, project_id, entity_type, entity_id}`. The UI resolves this to a production URL. If the target entity has been deleted or the recipient has lost access, the destination resolves to an inline not-found or access-denied explanation rather than silently falling back to a different entity.
5. Users see two states: unread and read. A separate backend delivery-attempt log tracks push, SSE, and poll delivery status for operational debugging. The delivery log is not exposed in the notification UI; it lives in Records.
6. Notifications are classified into three tiers: urgent, action-required, and informational. The nav badge counts urgent plus action-required unreads.
7. The event taxonomy is defined below, grounded in approved domain actions from the baseline and surface designs.
8. The inbox has a filter bar with a project selector (dropdown of authorized projects plus "All" and "Organization") and a tier selector (urgent / action-required / informational / all). Filters are URL-addressable: `#notifications?project={id}&tier=urgent`.
9. Three delivery layers: browser push via service worker for urgent-tier events (requires user permission), SSE for real-time in-app updates across all tiers when a tab is open, and polling as the universal fallback when SSE drops or is unsupported.
10. The surface implements loading, empty, recoverable error, permanent error, success, filter-empty, and push-permission-prompt states with complete accessibility.

## Event taxonomy

### Urgent — something broke or a deadline passed

| Event | Recipients | Originating surface |
|---|---|---|
| Your assigned item is overdue | Assignee | Evidence workspace |
| A learning candidate was auto-rolled-back (canary breach) | All Owners | AI Trust |
| An analysis run failed with permanent errors | Actor who started it + project Owners | Project ingestion |
| A source change was detected on an item you already verified | The member who recorded the verification + item owner | Source watch |

### Action-required — someone needs you to act

| Event | Recipients | Originating surface |
|---|---|---|
| An item was assigned to you | Assignee | Evidence workspace |
| An item you own was reassigned to you | New assignee | Evidence workspace |
| A rewrite was proposed on your item — needs approval | Item owner + members with Reviewer+ on the project | Evidence workspace |
| A referral was created — specialist action needed | Referred specialist + item owner | Evidence workspace |
| A comment was added on an item you own or are assigned to | Item owner + assignee (excluding commenter) | Evidence workspace |
| Your assigned item's due date is approaching (3 days) | Assignee | Evidence workspace |
| Your assigned item's due date is approaching (1 day) | Assignee | Evidence workspace |
| A monitoring review needs your call | Item owner + assignee | Source watch |
| You were invited to an organization | Invitee | Team & roles |

### Informational — awareness, no action needed

| Event | Recipients | Originating surface |
|---|---|---|
| An evidence decision was recorded on an item you own | Item owner (excluding the decision actor) | Evidence workspace |
| A rewrite was approved on an item you proposed | Proposer | Evidence workspace |
| A rewrite was rejected on an item you proposed | Proposer | Evidence workspace |
| A referral was acknowledged by the specialist | Referrer | Evidence workspace |
| A selective re-scan completed on items you own | Item owners of affected items | Versions |
| A report was generated | Project members with Reviewer+ | Report |
| A report was released | All project members | Report |
| An analysis run completed | Project members with Editor+ | Project ingestion |
| A script version was committed | Project members with Editor+ | Project ingestion |
| Your role was changed | Affected member | Team & roles |
| Your project access was changed | Affected member | Team & roles |
| A membership was deactivated (yours) | Affected member | Team & roles |
| A membership was reactivated (yours) | Affected member | Team & roles |
| A protected setting was activated | Owners + Admins | Settings |
| A learning candidate was promoted | All Owners | AI Trust |

### Excluded from notifications — stays in Records only

- Source-watch cadence setting changes.
- AI trust configuration reads.
- Internal model, rubric, prompt, and policy metadata.
- Provider operational events (delivery attempts, retries, health).
- The actor's own actions (no self-notification).
- Security events (authentication failures, token replay, escalation attempts) — these use a restricted operational channel, not the user inbox.

## Notification record structure

Each notification is a first-class domain entity, not a Receipt projection. A notification references but does not duplicate the underlying AuditEvent.

Required fields:

- `notification_id` — immutable unique identifier.
- `org_id` — organization scope.
- `project_id` — project scope; null for organization-level events.
- `recipient_user_id` — the specific user this notification is for.
- `event_type` — typed enum from the taxonomy above.
- `tier` — `urgent`, `action_required`, or `informational`.
- `title` — human-readable summary generated from the event display template.
- `body` — one or two sentence expansion with entity names and context.
- `destination` — structured reference: `{org_id, project_id, entity_type, entity_id}`.
- `actor_user_id` — who performed the action (for display, never the recipient).
- `audit_event_id` — link to the authoritative AuditEvent in Records.
- `read_state` — `unread` or `read`.
- `created_at` — timestamp of notification creation.

Absent fields:

- No raw Receipt text.
- No model names, rubric versions, prompt IDs, search methods, or provider metadata.
- No screenplay text or source excerpts.
- No tokens, signed URLs, or credentials.

## Display templates

Each event type has a fixed display template that produces the title and body. Templates reference entity display names, not internal identifiers. Examples:

| Event type | Title template | Body template |
|---|---|---|
| `item_assigned` | `{item_term} assigned to you` | `{item_id} · {category} · due {due_date}` |
| `source_change_detected` | `A source changed for {item_term}` | `{source_title} · your verified evidence may need review` |
| `rewrite_proposed` | `Rewrite proposed on {item_term}` | `{proposer_name} proposed a change · needs approval` |
| `report_released` | `Clearance report released` | `{project_name} · {script_version} · {flag_count} flags documented` |
| `overdue_item` | `{item_term} is overdue` | `{item_id} · was due {due_date} · {days_overdue} days ago` |
| `learning_auto_rollback` | `Learning candidate rolled back` | `Canary breached {gate_name} · reverted to {previous_version}` |

Templates are defined in code, not stored per notification. The notification record stores the rendered title and body at creation time so historical notifications remain readable even if templates change.

## Destination resolution

Each notification stores a structured destination rather than a URL string:

```text
{
  org_id: "org_abc",
  project_id: "proj_123",       // null for org-level events
  entity_type: "clearance_item", // or "report", "source_watch", "invitation", etc.
  entity_id: "item_456"
}
```

The frontend resolves this to a route:

```text
/orgs/{org_slug}/projects/{proj_slug}/items/{item_id}
```

Resolution checks:

1. Does the recipient still have organization membership? If not → "You no longer have access to this organization."
2. Does the recipient still have project authorization? If not → "You no longer have access to this project."
3. Does the entity still exist? If not → "This {entity_type} was deleted."
4. Success → navigate to the resolved route.

Resolution never silently falls back to a different entity. The check happens at click time so it reflects current authorization, not stale creation-time state.

## Recipient computation

When a domain action commits, the notification system computes recipients in the same transaction by evaluating:

1. **Event type** → which relationship roles are relevant (item owner, assignee, project members at a role threshold, etc.).
2. **Entity ownership** → the specific users in those roles for the affected entity.
3. **Project authorization** → only members currently authorized for the event's project.
4. **Self-exclusion** → the actor who performed the action is always excluded.
5. **Deactivation exclusion** → deactivated members do not receive notifications.

Notification records are written transactionally with the domain action and its AuditEvent. Delivery (push, SSE, poll) is asynchronous after commit through the same transactional outbox pattern established by the identity-entry design.

## Delivery layers

### Layer 1: Browser push (urgent tier only)

- Uses the Push API with a service worker.
- Only urgent-tier events trigger a push notification.
- Requires explicit user permission; the inbox shows a contextual permission prompt on first visit.
- Push payload contains notification ID, title, tier, and destination reference — no sensitive content in the push payload itself.
- Clicking the push notification opens ClearCut and navigates to the resolved destination.
- Push registration is per-browser, per-user, stored server-side.
- If the user denies permission or the browser doesn't support push, the system falls back to SSE and polling without degradation of the inbox experience.
- Push delivery attempts are recorded in the backend delivery log with status (delivered, failed, expired, permission_revoked).

### Layer 2: SSE (all tiers, in-app)

- When a ClearCut tab is open and authenticated, the client opens an SSE connection to a notification stream endpoint.
- New notifications arrive in real time and are prepended to the inbox list.
- The nav badge updates immediately.
- SSE events contain the notification ID and enough metadata to render the row without a full refetch.
- Connection drops are detected; the client reconnects with exponential backoff.
- If SSE is unavailable (proxy issues, Cloud Run timeout), the client falls back to polling automatically.
- SSE connections are authenticated and scoped to the user's organization.

### Layer 3: Polling (universal fallback)

- The client polls a lightweight `/notifications/unread-count` endpoint.
- Poll interval: 30 seconds when the tab is focused, paused when backgrounded.
- Returns `{urgent: n, action_required: n, informational: n}` counts.
- The nav badge is computed from `urgent + action_required`.
- Full notification list is fetched on inbox open and on filter change.
- Polling ensures consistent badge behavior across desktop sidebar and mobile bottom nav regardless of SSE or push availability.

## Organization inbox layout

### Desktop (1440px)

```text
┌─────────────────────────────────────────────────────┐
│ Northlight Pictures / Notifications                 │
│ ORGANIZATION                                        │
│ Notifications                                       │
│ [description]                          Mark all read│
├─────────────────────────────────────────────────────┤
│ Project: [All ▾]   Tier: [All] [Urgent] [Action] [Info] │
├─────────────────────────────────────────────────────┤
│ URGENT (2)                                          │
│ 🔴 CC-110 is overdue · Borrowed Light   2h ago  New│
│ 🔴 Learning candidate rolled back · Org  1h ago  New│
├─────────────────────────────────────────────────────┤
│ NEEDS YOUR ACTION (3)                               │
│ 🔵 CC-110 assigned to you · BL     Aug 19    New   │
│ 🔵 Rewrite proposed on CC-103 · BL Aug 20    New   │
│ 🔵 You were invited to Northlight  Aug 18          │
├─────────────────────────────────────────────────────┤
│ INFORMATIONAL (4)                                   │
│    Report released · Borrowed Light Aug 26          │
│    Re-scan completed · BL           Aug 26          │
│    Referral acknowledged · BL       Aug 19          │
│    Script v2 committed · BL         Aug 25          │
└─────────────────────────────────────────────────────┘
```

### Mobile (375px)

- Sidebar collapses to bottom nav; notification badge appears on the Inbox/bell icon.
- Filter bar stacks: project dropdown full-width, tier buttons scroll horizontally.
- Notification rows become full-width cards with tier indicator, title, project label, and timestamp.
- Mark all read moves into a compact action menu or remains as a top-level button above filters.
- Tier section headings remain as sticky `<h2>` elements.

## Nav badge behavior

- Desktop sidebar: `Notifications {count}` where count = urgent + action-required unreads.
- Mobile bottom nav: numeric badge on the inbox/bell icon with the same count.
- Both desktop and mobile compute the count from the same server endpoint.
- Count of zero hides the badge entirely.
- Urgent-only indicator: if any urgent unreads exist, the badge uses the danger/red color. Otherwise it uses the accent/blue color.

## Unread management

- Opening a notification (clicking to navigate to its destination) marks it as read.
- Mark all read transitions all unread notifications to read, across all tiers and projects.
- Mark all read is idempotent; repeated requests return success without side effects.
- There is no "mark as unread" action in the initial release.
- The server returns the updated counts after any read-state change.

## Retention and cleanup

- Notifications older than 90 days are archived and no longer appear in the inbox.
- Archived notifications remain in the database for operational queries and Records correlation.
- Notifications for deleted entities retain their rendered title and body but resolve their destination to an explicit "deleted" state.
- Project or organization deletion during the 30-day grace period marks associated notifications as destination-unavailable. Final purge removes notification bodies and retains only tombstone metadata consistent with the data-privacy design.
- Notification delivery-attempt logs follow the same operational telemetry retention as other provider events in Records.

## Authorization and privacy

- The notification list endpoint requires active authenticated organization membership.
- Notifications with a `project_id` are returned only when the recipient has current project authorization. If project access is revoked, those notifications disappear from the inbox without error — they are filtered, not deleted.
- Notification content never includes screenplay text, source excerpts, provider payloads, signed URLs, tokens, or credentials.
- Push notification payloads contain only the notification ID, tier, and a generic title. Sensitive details require opening ClearCut to view.
- Cross-tenant notification access is impossible by construction: `recipient_user_id` + `org_id` are required fields, and every query enforces the authenticated user's current organization scope.
- Unknown or unauthorized notification IDs return access-safe not-found responses indistinguishable from nonexistent ones.

## Role-specific behavior

| Role | Receives | Can mark read | Can manage push preferences |
|---|---|---|---|
| Owner | All event types for all projects + org-level + learning events | Yes | Yes |
| Admin | All event types for all projects + org-level (excluding learning governance) | Yes | Yes |
| Editor | Project-scoped events for authorized projects (assignments, comments, run outcomes, versions) | Yes | Yes |
| Reviewer | Project-scoped events for authorized projects (decisions, referrals, rewrites, reports, assignments) | Yes | Yes |
| Viewer | Limited project-scoped events for authorized projects (report released, own role/access changes) | Yes | Yes |

A Viewer never receives notifications about evidence decisions, rewrite proposals, referrals, run failures, or internal workflow actions they cannot act on.

## Push permission prompt

On first visit to `#notifications` when push is not yet enabled and the browser supports it:

```text
┌─────────────────────────────────────────────────────┐
│ 🔔 Get notified about urgent changes               │
│                                                     │
│ ClearCut can send you a browser notification when   │
│ something urgent happens — like an overdue item or  │
│ a rolled-back learning candidate. You'll only get   │
│ these for urgent events, not routine updates.       │
│                                                     │
│ [Enable push notifications]  [Not now]              │
└─────────────────────────────────────────────────────┘
```

- The prompt is an inline banner within the notification page, not a system dialog.
- Clicking "Enable" triggers the browser permission request.
- "Not now" dismisses the banner for the session; it reappears on the next session.
- If the user has previously denied browser permission, the banner explains how to re-enable it in browser settings.
- Push preference (enabled/disabled) is stored per user and manageable from Settings → Integrations or from the notification surface itself.

## State completeness

| State | Behavior |
|---|---|
| **Loading** | Skeleton notification cards matching row height; filter controls visible but disabled; nav badge shows last-known count |
| **Empty — no notifications** | Icon + "Nothing here yet" + "Notifications appear when teammates take actions on your items or when sources change" |
| **Empty — filters match nothing** | "No {tier} notifications for {project}" + clear-filters action |
| **Empty — no organization** | Redirects to organization resolver per identity-entry design; notification route never renders without org context |
| **Recoverable error** | "Couldn't load notifications · Retry" preserves current filters |
| **Permanent error** | Names the failure class without exposing internals |
| **Success** | Tier-grouped chronological list with project labels, filter bar, mark-all-read |
| **Push permission prompt** | Inline banner on first visit when browser supports push and permission is not yet granted |
| **Destination unavailable** | Clicking a notification whose entity was deleted or access was revoked shows an inline explanation instead of navigating |

## Accessibility

- Notification rows are list items within a `<ul>`, each containing a `<button>` for navigation.
- Tier sections use `<h2>` headings: "Urgent," "Needs your action," "Informational."
- New notifications arriving via SSE are announced through an `aria-live="polite"` region: "New notification: {title}."
- Urgent push arrivals, when the tab is focused, are announced through `aria-live="assertive"`.
- Mark all read confirms via live region: "All notifications marked as read."
- Filter changes are announced: "Showing urgent notifications for Borrowed Light."
- Relative timestamps use `<time datetime="{ISO}">` for machine-readable dates.
- Coarse-pointer targets are at least 44px.
- Keyboard: Tab navigates between filter controls and notification rows; Enter/Space activates a notification or filter; filter buttons use `aria-pressed` for the active state.
- Focus management: after mark-all-read, focus remains on the Mark all read button (now hidden) or moves to the first notification or empty-state heading. After navigating to a destination and pressing Back, focus returns to the notification row.
- The push permission banner is keyboard-operable and does not trap focus.
- Reduced-motion settings are honored for SSE prepend animations.
- Script and Night shoot themes maintain equivalent contrast, states, and hierarchy from 320 through 1440px.

## Responsive behavior

- **1440px:** Full sidebar with badge, page wrapper, filter bar inline, tier sections with notification rows.
- **900px:** Sidebar becomes drawer; filter bar remains inline; notification rows may wrap project label below title.
- **700px:** Bottom nav with badge icon; filter bar stacks (project dropdown full-width, tier buttons scroll horizontally); notification rows become full-width cards.
- **375px/320px:** Same as 700px with tighter spacing; push permission banner stacks action below copy; tier section headings become sticky for scroll context.

## Required mock corrections

1. Replace receipt-derived notification entries with domain-event notifications carrying redacted display templates.
2. Add project labels to every project-scoped notification row.
3. Add the filter bar with project and tier selectors.
4. Fix the nav badge to count urgent + action-required unreads consistently across desktop sidebar and mobile bottom nav.
5. Remove internal metadata (model names, rubric versions, prompt IDs) from notification content.
6. Replace generic hash-route destinations (`#item`, `#watch`, `#items`) with structured entity references that resolve to item-specific, version-specific, or report-specific deep links.
7. Make destination resolution access-aware: show inline not-found or access-denied instead of falling back to a different entity.
8. Add three-tier visual treatment: danger/red for urgent, accent/blue for action-required, no emphasis for informational.
9. Add the push permission prompt banner.
10. Add complete loading, empty, filter-empty, recoverable error, permanent error, and destination-unavailable states.
11. Replace plain-text relative timestamps with `<time datetime>` elements.
12. Add `aria-live` regions for new-notification arrival, mark-all-read confirmation, and filter changes.
13. Ensure notification rows and filter controls reach 44px minimum height at mobile breakpoints.
14. Stop showing seed/sample rows when no organization context exists; redirect to the organization resolver.

No mock implementation changes are authorized by this document alone.

## Domain entities established

This design establishes the need for, without fixing final table or column names:

- `Notification` — first-class domain entity with org scope, project scope, recipient, event type, tier, rendered title/body, structured destination, read state, audit-event link, and creation timestamp.
- `NotificationDeliveryAttempt` — backend log of push, SSE, and poll delivery attempts with status, provider receipt, and timestamps.
- `PushSubscription` — per-user, per-browser registration for web push with endpoint, keys, and enablement state.
- Event-type enum covering the complete taxonomy.
- Display-template registry keyed by event type.
- Recipient-computation rules keyed by event type.

Notifications reference but do not duplicate AuditEvents, Receipts, ClearanceItems, Reports, Invitations, or other domain entities. The notification is the delivery record; the AuditEvent remains the source of truth.

## Relationship to other approved designs

- **Identity & Entry:** Organization resolver must complete before the notification route renders. Deactivation removes notification access for that organization. Push subscriptions are per-user identity, not per-organization.
- **Team & Settings:** Role changes, project-access changes, invitation events, and deactivation/reactivation generate notifications per the taxonomy. Protected setting activation notifies Owners and Admins. Push preferences may be managed from Settings → Integrations.
- **Trust & Records:** Learning candidate promotion and auto-rollback generate notifications to Owners. Notification delivery attempts are operational records visible in Records → Operations. The notification's `audit_event_id` link enables deep navigation from inbox to the authoritative record.
- **Project Ingestion:** Script version commits, analysis run completion, and analysis run failure generate notifications to project members at the appropriate role threshold.
- **Evidence Workspace (pending design):** Assignment, evidence decision, referral, rewrite, comment, and due-date events will generate notifications per the taxonomy. The evidence workspace design must confirm the item ownership and assignment model that the recipient computation depends on.
- **Revision & Monitoring (pending design):** Selective re-scan completion and source-change detection generate notifications. The monitoring design must confirm the relationship between verified-source ownership and notification recipients.
- **Report (pending design):** Report generation and release generate notifications. The report design must confirm which roles receive generation vs. release notifications.

## Architecture gate

This approval permits preliminary design of:

- Notification domain entity, delivery-attempt log, and push-subscription storage.
- Recipient-computation service with event-type dispatch.
- Transactional notification creation alongside domain actions.
- SSE streaming endpoint with authentication.
- Push provider port (Web Push protocol).
- Unread-count polling endpoint.
- Notification list and read-state mutation endpoints.
- Display-template registry.

This does not freeze notification endpoint schemas until the evidence workspace, revision/monitoring, and report surface designs confirm the item-ownership, assignment, monitoring-verification, and report-release models that recipient computation depends on.

## Verification expectations

When implementation targets exist, verify:

- Notifications are created transactionally with their originating domain action.
- Self-exclusion: actors never receive their own action's notification.
- Recipient computation matches the taxonomy for every event type.
- Project authorization filtering: revoking project access removes those notifications from the inbox.
- Deactivated members do not receive new notifications.
- Structured destinations resolve correctly to entity-specific routes.
- Destination resolution shows not-found/access-denied for deleted entities and revoked access.
- Destinations never silently fall back to a different entity.
- Notification content contains no internal metadata, screenplay text, source excerpts, or credentials.
- Push payloads contain only notification ID, tier, and generic title.
- Three-tier classification matches the approved taxonomy.
- Nav badge counts urgent + action-required unreads consistently across desktop and mobile.
- Urgent badge uses danger color; mixed urgent + action-required uses danger color.
- SSE delivers real-time updates; connection drops fall back to polling.
- Push notifications arrive for urgent-tier events when permission is granted.
- Push permission prompt appears contextually and does not block inbox usage.
- Mark all read is idempotent and announces via live region.
- Filter controls are URL-addressable and announced via live region.
- 90-day archival removes old notifications from the inbox.
- Project/organization deletion marks notifications as destination-unavailable.
- Keyboard navigation, focus management, and live-region announcements work correctly.
- Coarse-pointer targets are at least 44px.
- Both themes across 320–1440px.
- Loading, empty, filter-empty, error, push-prompt, and destination-unavailable states render correctly.
- Cross-tenant notification access is impossible.
- Unknown notification IDs return access-safe not-found.
