# Team & Settings Mock Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update the authoritative ClearCut mock so Team & roles and Settings faithfully implement the approved membership, invitation, authorization, protected-configuration, retention, and deletion designs.

**Architecture:** Keep the dependency-free 20-surface prototype and its existing `page()`, `tabsBar()`, `dataTable()`, `card()`, `banner()`, dialog, receipt, and hash-query patterns. Expand the local prototype state into distinct membership, invitation, governance-version, and deletion-request projections; preserve one route per approved surface and use hash-query tabs. Every consequential simulated mutation updates state and writes a receipt together in one action handler.

**Tech Stack:** Dependency-free HTML/CSS/JavaScript prototype, localStorage state, hash router, Node structural audit, `agent-browser` browser inspection.

---

## Constraints

- Implement from `docs/plans/2026-08-29-team-settings-ui-design.md`.
- Preserve `misc/clearcut-flow/` as the visual source of truth and keep exactly 20 routes.
- Do not add shadcn, Tailwind, Radix, an icon package, or another component system.
- Do not add inline geometry; only runtime-computed inline values remain permitted.
- Do not test implementation details outside the mock audit. Extend the structural audit for durable invariants and use browser walkthroughs for behavior.
- Preserve Script and Night shoot themes, the `page()` wrapper, advisory prerequisites, focus handling, capability explanations, responsive table cards, and print isolation.
- Do not modify production directories; they remain planned.
- Do not create commits unless the user explicitly asks. The commit steps below are optional handoff checkpoints and must be skipped otherwise.

### Task 1: Add failing structural checks for the approved invariants

**Files:**
- Modify: `misc/clearcut-flow/mockup-audit.mjs`

**Step 1: Add Team structure checks**

Add checks requiring:

- URL-query Team tabs for `members`, `invitations`, and `roles` rendered through `tabsBar()`;
- separate `state.members` and `state.invitations` collections;
- all five invitation states: pending, accepted, declined, expired, revoked;
- invitation edit, resend, revoke, decline, and acceptance actions;
- no `Change role` action for pending invitations;
- role dialogs carrying the current role and explicit selected state;
- member deactivate/reactivate actions;
- final-Owner protection;
- inherited versus explicit project-access provenance;
- governed decision and release capabilities for Owner, Admin, and Reviewer;
- protected-settings capability limited to Owner.

Use semantic regular-expression checks against named constants/functions rather than exact rendered copy where possible.

**Step 2: Add Settings structure checks**

Add checks requiring:

- URL-query Settings tabs for `general`, `governance`, `data`, and `integrations`;
- protected configuration lifecycle states `draft`, `validated`, `validation_failed`, `active`, and `superseded`;
- active version/history/receipt links in Governance;
- no duration-based `retention` selector or `DEFAULT_ORG.retention` field;
- explicit `automatic deletion` off copy;
- project/organization deletion requests only, with no item/evidence deletion action;
- a 30-day reversible deletion grace period;
- schedule, restore, and purge receipt paths;
- integration history linking to Records rather than embedding detailed tool-call history.

**Step 3: Add responsive banner checks**

Require the mobile media query to stack `.banner` and its action container so the prerequisite copy cannot collapse into a narrow column.

**Step 4: Run the audit and verify RED**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: the new Team, Settings, and responsive checks fail while the existing baseline checks continue to pass.

**Step 5: Optional checkpoint commit**

Only if explicitly authorized:

```bash
git add misc/clearcut-flow/mockup-audit.mjs
git commit -m "test(mock): define team and settings invariants"
```

### Task 2: Expand prototype state and capability definitions

**Files:**
- Modify: `misc/clearcut-flow/assets/app.js:169-211`
- Modify: `misc/clearcut-flow/assets/app.js:590-632`
- Modify: `misc/clearcut-flow/assets/app.js:679-715`

**Step 1: Update roles and capabilities**

Update `ROLE_MATRIX`, `CAPABILITIES`, and `CAPABILITY_LABELS` so:

- Owner: lifecycle, protected settings, all governed actions;
- Admin: team, projects, providers, operational settings, all governed actions;
- Editor: import, research, assignment/comment, rewrite proposals;
- Reviewer: evidence decisions, referrals, dispositions, rewrite approval, report generation/release;
- Viewer: read only.

Set `release` to Owner/Admin/Reviewer. Split the current broad `settings` capability into:

```js
settings: ['Owner', 'Admin'],
protectedSettings: ['Owner'],
deleteOrganization: ['Owner'],
deleteProject: ['Owner'],
```

Keep capability-gated controls focusable and descriptive through the existing `gated()` helper.

**Step 2: Replace compressed member access strings with explicit prototype fields**

Change seeded members to carry:

```js
{
  id,
  name,
  initials,
  email,
  role,
  status: 'active' | 'deactivated',
  accessMode: 'inherited' | 'explicit',
  projectIds: [],
  lastActive,
}
```

Owners/Admins use `accessMode: 'inherited'`. Other roles use explicit project IDs.

**Step 3: Move invited people into a dedicated invitation collection**

Seed `state.invitations` with fields:

```js
{
  id,
  email,
  proposedRole,
  projectIds,
  invitedBy,
  sentAt,
  expiresAt,
  status: 'pending' | 'accepted' | 'declined' | 'expired' | 'revoked',
  tokenVersion,
  acceptedMemberId,
}
```

Do not keep invited rows in `state.members`.

**Step 4: Add Settings projections**

Remove `DEFAULT_ORG.retention`. Add prototype projections for:

- organization governance versions and active version IDs;
- validation results;
- provider health summaries;
- pending deletion requests.

Use immutable arrays/objects in action handlers rather than mutating protected active versions in place.

**Step 5: Bump the local schema version**

Increment `SCHEMA_VERSION` so stale localStorage state is discarded. Keep `loadState()` guard clauses and defaults valid for all new collections.

**Step 6: Run the audit**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: state/capability checks pass; renderer/action checks remain RED.

### Task 3: Implement Team tabs and member lifecycle

**Files:**
- Modify: `misc/clearcut-flow/assets/app.js:1115-1117`
- Modify: `misc/clearcut-flow/assets/app.js:1248-1250`
- Modify: `misc/clearcut-flow/assets/app.js:1295-1303`
- Modify: `misc/clearcut-flow/assets/app.js:1724-1763`
- Modify: `misc/clearcut-flow/assets/app.js:3276-3923`

**Step 1: Add a guarded Team tab resolver**

Use `routeQuery()` and a fixed allow-list:

```js
const TEAM_TABS = ['members', 'invitations', 'roles'];
function teamTab() {
  const tab = routeQuery().tab;
  return TEAM_TABS.includes(tab) ? tab : 'members';
}
```

Tab actions navigate with `go('team?tab=...')`; do not add another route or persist tab state globally.

**Step 2: Split `renderTeam()` into tab renderers**

Create:

- `renderTeamMembers()`;
- `renderTeamInvitations()`;
- `renderTeamRoles()`.

`renderTeam()` remains the only route renderer and composes the page head, Invite member action, prerequisite notice, `tabsBar()`, and active tab body.

**Step 3: Implement Members content**

Render active and deactivated memberships with Member, Role, Project access, Status, Last active, and Actions. Display inherited access as `All projects · inherited from Owner/Admin`; resolve explicit project IDs through `PROJECT_DEFS`.

Actions:

- Change role;
- Edit project access;
- Deactivate;
- Reactivate;
- View audit history.

Use compact action markup that remains usable in responsive table cards.

**Step 4: Correct role-change behavior**

Pass both member ID and current role to the dialog. Mark the current option `selected`. Show:

- current and proposed role;
- capability changes;
- inherited/explicit access effect;
- explicit retained-project controls when demoting Owner/Admin.

Guard against deactivating or demoting the last active Owner. Commit member, project-access, and receipt changes in one handler branch.

**Step 5: Implement deactivation/reactivation**

Deactivation sets status, disables the membership's inherited or explicit grants without deleting their historical provenance, invalidates organization-scoped authorization caches, and writes a receipt without removing the historical member. It preserves identity sessions that still authorize unrelated organizations. Reactivation requires role/access confirmation and restores only explicitly approved grants. Invitation acceptance cannot reactivate a deactivated membership. Do not offer deactivation for the final active Owner.

**Step 6: Implement Roles & access content**

Render the fixed matrix from the canonical role/capability constants and explain inherited versus explicit access. Move the prototype-only role preview below a clearly marked prototype instrumentation subsection or link it to `#states`; do not present it as a production team-management action.

**Step 7: Run the audit**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: Team tabs, role selection, access provenance, capability, and membership lifecycle checks pass.

### Task 4: Implement the invitation lifecycle

**Files:**
- Modify: `misc/clearcut-flow/assets/app.js:1587-1624`
- Modify: `misc/clearcut-flow/assets/app.js:1724-1763`
- Modify: `misc/clearcut-flow/assets/app.js:3276-3923`

**Step 1: Replace invite-row role actions**

Pending invitations render Edit, Resend, and Revoke. Expired invitations render Resend. Revoked and declined invitations render View receipt; a new invitation is always a new record. Accepted invitations link to the resulting member. Never render Change role for an invitation.

**Step 2: Expand the invitation dialog**

Support create and edit modes. Fields:

- email;
- fixed proposed role;
- multi-project access for Editor/Reviewer/Viewer;
- forced inherited-all-project explanation for Owner/Admin;
- expiration date;
- inviter identity.

Link errors to their fields and keep entered values after recoverable validation errors.

**Step 3: Implement edit, resend, decline, expiry, and revoke**

- Edit updates the proposed role/access and increments `tokenVersion`; Owner invitation edits require current Owner authority, recent reauthentication, and explicit confirmation.
- Resend increments `tokenVersion`, resets sent/expiry timestamps, and sets status pending; Owner invitation resend uses the same authority and reauthentication checks as creation.
- Revoke sets status revoked without deleting history.
- Decline requires the matching verified identity, sets status declined, invalidates the token, creates no membership, and writes a domain receipt.
- Expiry derives from `expiresAt` or is applied by a deterministic prototype action; do not use an unreliable long-running timer.

Every transition writes a membership receipt.

**Step 4: Implement acceptance transaction semantics in the prototype**

Update the existing `#invite` acceptance path so accepted invitations create a member only when no active or deactivated membership conflicts, create project memberships, mark the invitation accepted, record `acceptedMemberId`, and add one receipt before saving state. A deactivated membership requires the separate explicit reactivation flow. Handle wrong account, duplicate active member, deactivated member, declined, expired, revoked, and already-accepted cases explicitly.

**Step 5: Run the audit**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: all invitation lifecycle checks pass.

### Task 5: Implement Settings tabs and General/Integrations behavior

**Files:**
- Modify: `misc/clearcut-flow/assets/app.js:1115-1117`
- Modify: `misc/clearcut-flow/assets/app.js:1765-1804`
- Modify: `misc/clearcut-flow/assets/app.js:3276-3923`

**Step 1: Add a guarded Settings tab resolver**

Use a fixed allow-list:

```js
const SETTINGS_TABS = ['general', 'governance', 'data', 'integrations'];
function settingsTab() {
  const tab = routeQuery().tab;
  return SETTINGS_TABS.includes(tab) ? tab : 'general';
}
```

Render tabs through `tabsBar()` and navigate with query-bearing hashes.

**Step 2: Split `renderSettings()` into tab renderers**

Create:

- `renderSettingsGeneral()`;
- `renderSettingsGovernance()`;
- `renderSettingsData()`;
- `renderSettingsIntegrations()`.

Keep one `renderSettings()` page wrapper.

**Step 3: Implement General**

Retain organization name, read-only plan, jurisdiction, and default cadence. Remove evidence retention. Add explicit cadence copy: changes seed only future projects; existing project cadence remains unchanged. Keep save authorization under `settings` (Owner/Admin).

Update `save-settings` receipts to include only changed operational fields using existing display vocabulary helpers.

**Step 4: Implement Integrations**

Show purpose, configuration state, current health, last successful operation, and incident/retry state. Replace the embedded recovery-history behavior with a deep link to `#records` carrying provider/run filters. Permitted Owner/Admin recovery actions remain capability-gated and write receipts.

**Step 5: Run the audit**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: Settings tab and General/Integrations checks pass; governance/deletion checks remain RED.

### Task 6: Implement Governance version workflow

**Files:**
- Modify: `misc/clearcut-flow/assets/app.js:1765-1804`
- Modify: `misc/clearcut-flow/assets/app.js:2570-2641`
- Modify: `misc/clearcut-flow/assets/app.js:3276-3923`

**Step 1: Render global and organization-owned policy groups separately**

Global read-only catalogs:

- role/capability definitions;
- category schema;
- platform source-authority defaults.

Organization-owned versioned configuration:

- sign-off/approval policy;
- organization source-authority policy;
- prompt versions;
- rubric;
- permitted evidence-schema extensions;
- deterministic blocking rules;
- legal-boundary language.

Keep category schema and source-authority policy visibly distinct.

**Step 2: Render active version and history**

For each organization-owned policy show version, state, author, activation time, rationale, validation result, Trust link, Records link, and history. Admin sees Owner-only controls through `gated('protectedSettings', ...)` with the restriction explained.

**Step 3: Implement draft/validation/activation actions**

Add actions for:

- create draft from active version;
- edit draft rationale/content summary;
- validate draft;
- record validation failure;
- activate a validated draft;
- create a new draft from a superseded version.

Activation requires recent reauthentication, typed confirmation, and a rationale. It marks the prior active version superseded, marks the selected version active, updates the active ID, and adds an authoritative audit event plus Receipt projection before one `saveState()` call. Never edit active/superseded versions in place. Evidence-schema extensions may add optional fields only and must not weaken required provenance, source, stance, authority, conflict, or uncertainty fields.

**Step 4: Bind Trust display to active versions**

Update `renderTrust()` to show the active rubric/prompt/policy version IDs from state rather than unrelated literals. Keep the ten-dimension rubric and bounded-learning behavior intact.

**Step 5: Run the audit**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: Governance lifecycle and Trust-binding checks pass.

### Task 7: Implement Data & privacy and deletion scheduling

**Files:**
- Modify: `misc/clearcut-flow/assets/app.js:1765-1804`
- Modify: `misc/clearcut-flow/assets/app.js:1870-1882`
- Modify: `misc/clearcut-flow/assets/app.js:3276-3923`

**Step 1: Render indefinite retention clearly**

Display:

- Automatic deletion: Off;
- project evidence retained until an Owner deletes the project or organization;
- stored data classes;
- private scripts never used for shared-model training;
- signed-link expiry separate from artifact retention.

Do not render age-based retention choices.

**Step 2: Add Owner-only deletion dialogs**

Allow project or organization deletion only. Dialogs must:

- identify the project/organization;
- summarize affected scripts, evidence, reports, members, and integrations;
- offer export first;
- require typing the resource name;
- state the 30-day deletion date;
- explain read-only state and restoration.

Do not add evidence/source/item deletion actions.

**Step 3: Implement schedule and restore actions**

Scheduling creates a deletion request with scope, target ID, requester, requested time, purge time, state `scheduled`, and receipt. It marks the target read-only in the prototype, revokes simulated signed links, and blocks new governed actions through a central guard.

Restoration changes the request to `restored`, re-enables the resource, and writes a receipt. Represent final purge as a deterministic prototype action or recorded terminal example; do not run destructive browser timers.

**Step 4: Update Records**

Show scheduled deletion, restoration, and purge receipts in the existing ledger. Preserve minimal tombstone wording for purged examples without inventing selectively deleted evidence.

**Step 5: Run the audit**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: indefinite-retention, deletion-boundary, grace-period, receipt, and Records checks pass.

### Task 8: Fix responsive banners and complete accessibility behavior

**Files:**
- Modify: `misc/clearcut-flow/assets/app.css:373-386`
- Modify: `misc/clearcut-flow/assets/app.css` mobile media query near the existing `max-width: 700px` rules
- Modify: `misc/clearcut-flow/assets/app.js:1244-1282`

**Step 1: Give banner actions a stable class**

Update `banner()` so the optional action wrapper uses a named class such as `banner-actions`, preserving the shared component and avoiding surface-specific overrides.

**Step 2: Stack banner content on narrow screens**

Inside the existing mobile breakpoint:

```css
.banner { flex-wrap: wrap; }
.banner-body { min-width: min(100%, 16rem); }
.banner-actions { width: 100%; }
.banner-actions .button { width: 100%; }
```

Adapt the exact values to existing tokens and verify no horizontal overflow at 320px. Do not add inline geometry or `!important`.

**Step 3: Verify dialogs and forms**

For invite, role/access, protected-version, and deletion dialogs confirm:

- accessible title and description;
- visible labels;
- linked errors;
- focus trap and background inertness;
- focus restoration;
- Escape behavior;
- 44px coarse-pointer targets;
- polite/assertive live feedback for validation and activation.

**Step 4: Run the audit**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: every structural check passes, including the responsive-banner invariant.

### Task 9: Run browser walkthroughs in both themes and responsive widths

**Files:**
- Modify only if walkthroughs expose a concrete defect: `misc/clearcut-flow/assets/app.js`, `misc/clearcut-flow/assets/app.css`

**Step 1: Start the static server**

Run from `misc/clearcut-flow/`:

```bash
python3 -m http.server 4173 --bind 127.0.0.1
```

**Step 2: Verify Team flows**

Using `agent-browser`, inspect `#team?tab=members`, `#team?tab=invitations`, and `#team?tab=roles` at 320, 375, 768, 1024, and 1440px in Script and Night shoot.

Exercise:

- invite creation/edit/resend/revoke;
- role current-value selection;
- Owner/Admin inheritance;
- demotion retained-project selection;
- final-Owner refusal;
- deactivate/reactivate;
- Viewer capability explanations;
- keyboard and dialog focus behavior.

**Step 3: Verify Settings flows**

Inspect all four Settings tabs at the same widths and themes.

Exercise:

- General save and future-project cadence wording;
- Admin read-only protected configuration;
- Owner draft, validation failure/success, activation, and historical copy;
- indefinite-retention copy;
- deletion scheduling/restoration;
- Records and Trust deep links;
- provider history link.

**Step 4: Check console and page errors**

Run:

```bash
agent-browser --session clearcut-team-settings console
agent-browser --session clearcut-team-settings errors
```

Expected: no uncaught errors and no accessibility-breaking warnings.

### Task 10: Update the current mock baseline and documentation

**Files:**
- Modify: `misc/clearcut-flow/README.md`
- Modify: `.agents/steering/ui-standards.md` only if the audit count changes
- Modify: `.agents/skills/mock-to-tanstack/SKILL.md` only if the audit count changes
- Generated when canonical agent docs change: `.kiro/steering/ui-standards.md`, `.kiro/skills/mock-to-tanstack/SKILL.md`, `.agents/render-manifest.json`, `AGENTS.md`

**Step 1: Run the final audit and capture its actual count**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: all checks pass. Record the exact new total rather than assuming 366.

**Step 2: Update current baseline references**

Update `misc/clearcut-flow/README.md` and current canonical `.agents` references from 366 to the actual total if checks were added. Do not rewrite `docs/2026-08-28-mock-ui-verification.md`; it is a historical record of the earlier 366-check run.

If canonical `.agents` files change, regenerate:

```bash
AGENTS_STRICT=1 bun .agents/scripts/build.mjs
node .agents/scripts/signoff.mjs
```

Expected: strict generation and sign-off pass with no generated drift.

**Step 3: Run patch and mock verification**

Run:

```bash
git diff --check
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: clean diff and full audit pass.

**Step 4: Report evidence**

Report:

- exact mock-audit total;
- reviewed routes, widths, and themes;
- Team and Settings interaction results;
- accessibility/focus results;
- agent sign-off output if canonical baseline references changed;
- files changed;
- any limitation not verified on real mobile hardware or a screen reader.
