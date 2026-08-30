/* ClearCut — full-surface clearance workspace prototype
   Dependency-free. 20 surfaces, two appearances, advisory navigation. */
(() => {
  'use strict';

  /* ═══════════════════════════════ CONSTANTS ═══════════════════════════════ */

  const STORAGE_KEY = 'clearcut-flow-state-v2';
  /* Bumped when persisted demo state stops matching what the surfaces expect.
     Discarding stale demo state is the right trade: a returning visitor gets a
     coherent workspace rather than a half-migrated one.
       4 — cadence became canonical ('weekly'), not the display string
           ('Weekly'); stale values matched no watch radio and read "Paused".
       5 — Borrowed Light ships with a script and a completed check, and the
           wizard's step-1 flag moved from one global boolean to each project's
           own `details`. v4 state would keep an empty Borrowed Light, and so
           keep the contradiction the seed exists to remove. */
  const SCHEMA_VERSION = 5;
  const THEME_KEY = 'clearcut-theme';

  const THEMES = [
    { id: 'script', label: 'Script', tagline: 'Typewriter ink on cream stock — the daily draft', swatch: '#f3e5b5' },
    { id: 'night', label: 'Night shoot', tagline: 'Amber flags on charcoal pages for late sessions', swatch: '#e8a33d' },
  ];

  const ROUTES = [
    // Public
    { id: 'marketing', label: 'Screenplay clearance', layer: 'public', group: 'Public', icon: '◆' },
    { id: 'marketing-a', label: 'Landing A · Polished OSS', layer: 'public', group: 'Public', icon: '◆' },
    { id: 'marketing-b', label: 'Landing B · Dev-first', layer: 'public', group: 'Public', icon: '◆' },
    { id: 'marketing-c', label: 'Landing C · Hybrid', layer: 'public', group: 'Public', icon: '◆' },
    { id: 'features', label: 'Features', layer: 'public', group: 'Public', icon: '⬡' },
    { id: 'docs', label: 'Docs', layer: 'public', group: 'Public', icon: '⊞' },
    { id: 'auth', label: 'Sign in', layer: 'public', group: 'Public', icon: '⊙' },
    { id: 'resolver', label: 'Choose an organization', layer: 'public', group: 'Public', icon: '◈' },
    { id: 'invite', label: 'Accept invitation', layer: 'public', group: 'Public', icon: '✉' },
    // Onboarding
    { id: 'onboarding', label: 'Create organization', layer: 'public', group: 'Onboarding', icon: '⊕' },
    // Organization
    { id: 'projects', label: 'Projects', layer: 'org', group: 'Organization', icon: '▤', needs: 'onboarding' },
    { id: 'notifications', label: 'Notifications', layer: 'org', group: 'Organization', icon: '◔', needs: 'onboarding' },
    { id: 'team', label: 'Team & roles', layer: 'org', group: 'Organization', icon: '◉', needs: 'onboarding' },
    { id: 'settings', label: 'Settings', layer: 'org', group: 'Organization', icon: '⚙', needs: 'onboarding' },
    { id: 'trust', label: 'AI trust', layer: 'org', group: 'Trust & records', icon: '◐', needs: 'onboarding' },
    { id: 'records', label: 'Records', layer: 'org', group: 'Trust & records', icon: '≡', needs: 'onboarding' },
    // New clearance wizard (details → import → check)
    { id: 'new', label: 'New clearance', layer: 'org', group: 'Project setup', icon: '✚', needs: 'onboarding' },
    // Project analysis
    { id: 'project', label: 'Overview', layer: 'project', group: 'Analysis', icon: '◈', needs: 'new' },
    { id: 'workspace', label: 'Screenplay', layer: 'project', group: 'Analysis', icon: '⌑', needs: 'new' },
    { id: 'items', label: 'Flags', layer: 'project', group: 'Analysis', icon: '☰', needs: 'new' },
    { id: 'item', label: 'Flag detail', layer: 'project', group: 'Analysis', icon: '◦', needs: 'new' },
    // Project review & delivery
    { id: 'versions', label: 'Versions', layer: 'project', group: 'Review', icon: '⑂', needs: 'new' },
    { id: 'watch', label: 'Source watch', layer: 'project', group: 'Review', icon: '◉', needs: 'new' },
    { id: 'report', label: 'Clearance report', layer: 'project', group: 'Delivery', icon: '◎', needs: 'new' },
    // Meta
    // Instrumentation, not product. Labelled as such in the sidebar and the
    // sitemap so neither reads as a feature a producer would ship with.
    { id: 'sitemap', label: 'All surfaces', layer: 'meta', group: 'Prototype tools', icon: '⊞' },
    { id: 'states', label: 'UI states', layer: 'meta', group: 'Prototype tools', icon: '◫' },
  ];

  const NAV = {
    org: [
      { label: 'Organization', links: ['projects', 'notifications', 'team', 'settings'] },
      { label: 'Trust & records', links: ['trust', 'records'] },
    ],
    project: [
      { label: 'Project', links: ['project', 'workspace', 'items'] },
      { label: 'History & delivery', links: ['versions', 'watch', 'report'] },
    ],
    meta: [
      { label: 'Prototype tools', links: ['sitemap', 'states'] },
    ],
  };

  /** Production scripts are printed on coloured stock as revisions accumulate. */
  const REVISION_STOCK = ['white', 'blue', 'pink', 'yellow', 'green', 'goldenrod'];

  /* The workspace renders an excerpt of the script. Every flag in ITEMS has a
     line here, and each flag sits in the scene its record names — the scene
     number, the page, and the surrounding line are the single source the
     worklist, the drawer, and the report all read from. Adding a flag to ITEMS
     without a line here is caught by the audit (every flag must be placed). */
  const SCENES = [
    {
      number: 3, slug: 'INT. VELEZ CAMERA SHOP — DUSK', page: 2,
      lines: [
        { type: 'action', text: 'Dust hangs in the last bar of window light.' },
        { type: 'action', text: 'MINA VELEZ, 31, turns the lock and studies the room as if it belongs to someone else.', flag: 'CC-102' },
        { type: 'action', text: 'She lifts the Vega Camera from a glass case.', flag: 'CC-101' },
        { type: 'character', text: 'MINA' },
        { type: 'dialogue', text: 'We only borrow the light.' },
      ],
    },
    {
      number: 7, slug: 'EXT. SUNSET TOWER — NIGHT', page: 5, pageBreakBefore: true,
      lines: [
        { type: 'action', text: 'The crew unloads beneath the Sunset Tower marquee.', flag: 'CC-103' },
        { type: 'action', text: 'A radio host announces "Blue Monday" over the PA. Mina reaches for the dial.', flag: 'CC-104' },
      ],
    },
    {
      number: 9, slug: 'INT. CORNER DINER — NIGHT', page: 7, pageBreakBefore: true,
      lines: [
        { type: 'action', text: 'A trucker counts coins onto the counter.' },
        { type: 'character', text: 'TRUCKER' },
        { type: 'dialogue', text: 'Keep the change.', flag: 'CC-105' },
      ],
    },
    {
      number: 12, slug: 'EXT. HARBOR CHECKPOINT — DAY', page: 9, pageBreakBefore: true,
      lines: [
        { type: 'action', text: 'A polished Northstar badge catches the light as the officer waves the truck through.', flag: 'CC-106' },
      ],
    },
    {
      number: 14, slug: 'EXT. BOARDWALK — DUSK', page: 11, pageBreakBefore: true,
      lines: [
        { type: 'action', text: 'A red bicycle silhouette leans against the rail.', flag: 'CC-107' },
      ],
    },
    {
      number: 16, slug: 'INT. PROJECTION BOOTH — NIGHT', page: 13, pageBreakBefore: true,
      lines: [
        { type: 'action', text: 'A faded Glass House poster watches from the wall.', flag: 'CC-108' },
      ],
    },
    {
      number: 18, slug: 'INT. CLINIC CORRIDOR — DAY', page: 15, pageBreakBefore: true,
      lines: [
        { type: 'action', text: 'DR. LENORA SHAW reviews a chart.', flag: 'CC-109' },
        { type: 'character', text: 'DR. SHAW' },
        { type: 'dialogue', text: 'Her relapse began after she left the East Mercer clinic, room 214.', flag: 'CC-110', rewritten: 'She struggled again after she left treatment.' },
      ],
    },
  ];

  const ACTOR = { name: 'Jamie Park', role: 'Owner', initials: 'JP' };

  /** Two projects at different stages, so org-level behaviour is demonstrated
      rather than asserted. Each keeps its own clearance state. */
  const PROJECT_DEFS = [
    { id: 'borrowed-light', title: 'Borrowed Light', type: 'Independent feature', stage: 'Pre-production', jurisdiction: 'United States · California', lock: 'Sep 18, 2026', brief: 'A quiet drama about memory and image-making. Prioritize depicted marks, music, artwork, and privacy.' },
    { id: 'quiet-coast', title: 'The Quiet Coast', type: 'Limited series', stage: 'Development', jurisdiction: 'United States · New York', lock: 'Nov 4, 2026', brief: 'Coastal ensemble drama. Early pass: locations, real organisations, and archival media.' },
  ];

  const PROJECT_STATE = {
    versions: [], runStep: 0, runComplete: false,
    evidenceDecisions: {}, comments: [], assignments: {}, assignmentDue: {},
    /* What each decision was actually bound to at the moment it was made:
       { version, actor, at }. The verdict alone could not say which draft it
       answered, so a call made on v1 started claiming v2 as soon as a rewrite
       created one. */
    decisionBinding: {},
    /* Which version the reader is looking at. null means the latest. An earlier
       version is readable but not decidable — a call against a superseded draft
       would bind evidence to text that is no longer current. */
    viewingVersion: null,
    referralCreated: false, referralBrief: '', rewriteApproved: false, rewriteText: '', rewriteProposals: {}, rescanComplete: false,
    /* A re-scan in flight: which affected flag is being re-read. A single
       complete/not-complete flag could not show that this work takes time and
       happens per item. */
    rescanning: false, rescanDone: [], rescanFailed: null, rescanFailAt: null,
    // The reason behind the final call, and the screenplay text a Paste import
    // actually received — both were collected and discarded before.
    dispositionRationale: '', pastedSource: '',
    // Production details as entered in the New-clearance wizard. Null until the
    // reviewer saves step 1; then it overlays the static PROJECT_DEFS entry.
    details: null, runStartedAt: null, running: false,
    monitoring: { cadence: 'weekly', checkRun: false, reviewed: false, reviewEffect: '', checking: false, checked: 0 },
    // Seeded from the script itself: a hardcoded number goes stale the moment a
    // scene is renumbered, and the header readout then contradicts the rail.
    disposition: '', dossier: null, activeItem: 'CC-101', activeScene: SCENES[0].number,
  };

  /* Invitations are their own records with their own lifecycle, kept after they
     end. Folding them into the member list as status 'Invited' lost the states
     entirely: an expired invitation and a declined one need different actions, and
     an accepted one has to remain as history. */
  const INVITE_STATES = {
    Pending: { tone: 'is-warning', actions: ['edit', 'resend', 'revoke'] },
    Expired: { tone: '', actions: ['resend'] },
    Revoked: { tone: '', actions: ['receipt'] },
    Declined: { tone: '', actions: ['receipt', 'new'] },
    Accepted: { tone: 'is-success', actions: ['member'] },
  };

  const DEFAULT_INVITATIONS = [
    { id: 'inv_05', email: 'nora@northlight.example', role: 'Viewer', access: 'The Quiet Coast', invitedBy: 'Jamie Park', sentAt: 'Aug 18 · 09:12', expiresAt: 'Sep 1', status: 'Pending', tokenVersion: 1 },
    { id: 'inv_04', email: 'sam@northlight.example', role: 'Editor', access: 'Borrowed Light', invitedBy: 'Jamie Park', sentAt: 'Aug 2 · 14:40', expiresAt: 'Aug 16', status: 'Expired', tokenVersion: 1 },
    { id: 'inv_03', email: 'kit@northlight.example', role: 'Reviewer', access: 'Borrowed Light', invitedBy: 'Jamie Park', sentAt: 'Aug 9 · 11:05', expiresAt: 'Aug 23', status: 'Revoked', tokenVersion: 2 },
    { id: 'inv_02', email: 'rae@northlight.example', role: 'Viewer', access: 'Borrowed Light', invitedBy: 'Mara Voss', sentAt: 'Aug 7 · 16:20', expiresAt: 'Aug 21', status: 'Declined', tokenVersion: 1 },
    { id: 'inv_01', email: 'eli@northlight.example', role: 'Reviewer', access: 'Borrowed Light', invitedBy: 'Jamie Park', sentAt: 'Aug 1 · 10:00', expiresAt: 'Aug 15', status: 'Accepted', tokenVersion: 1 },
  ];

  /* Protected configuration. The design separates two kinds: global catalogs nobody
     in an organization can edit, and organization-owned versioned policy that only
     an Owner may change. The Governance tab previously showed neither — it held two
     data-handling toggles, which is not the same thing as the contracts in force. */
  const GLOBAL_CATALOGS = [
    { name: 'Role and capability definitions', detail: 'Five fixed roles and what each may do.', version: 'platform 4.1' },
    { name: 'The ten clearance categories', detail: 'The category schema detection works against.', version: 'platform 4.1' },
    { name: 'Platform source-authority defaults', detail: 'Baseline authority tiers for publisher classes.', version: 'platform 4.1' },
  ];

  /* draft → validated → active → superseded, with validation_failed off validated. */
  const CONFIG_STATUS = {
    active: { label: 'Active', tone: 'is-success' },
    validated: { label: 'Validated', tone: 'is-accent' },
    draft: { label: 'Draft', tone: 'is-warning' },
    validation_failed: { label: 'Validation failed', tone: 'is-danger' },
    superseded: { label: 'Superseded', tone: '' },
  };

  const ORG_POLICIES = [
    { id: 'signoff', name: 'Sign-off and approval policy', version: '3.2', status: 'active', author: 'Jamie Park', at: 'Aug 12 · 09:40', rationale: 'Added a second reviewer for music and privacy categories.', validation: 'Passed · 41 checks', history: 4 },
    { id: 'authority', name: 'Source-authority overrides', version: '2.0', status: 'active', author: 'Jamie Park', at: 'Aug 5 · 15:10', rationale: 'Promoted two national registries to primary for this organization.', validation: 'Passed · 12 checks', history: 2 },
    { id: 'prompts', name: 'Prompt versions', version: 'cc-research-17', status: 'active', author: 'Jamie Park', at: 'Aug 3 · 11:22', rationale: 'Tightened the quotation category instructions.', validation: 'Passed · 9 checks', history: 6 },
    { id: 'rubric', name: 'Judge rubric configuration', version: '2.4', status: 'active', author: 'Jamie Park', at: 'Jul 30 · 16:05', rationale: 'Raised the weight on evidence provenance.', validation: 'Passed · 10 checks', history: 3 },
    { id: 'schema', name: 'Evidence-schema extensions', version: '1.1', status: 'validated', author: 'Jamie Park', at: '—', rationale: 'Adds an optional internal reference field. Awaiting activation.', validation: 'Passed · required fields untouched', history: 1 },
    { id: 'blocking', name: 'Deterministic blocking rules', version: '3.0', status: 'active', author: 'Jamie Park', at: 'Jul 28 · 10:00', rationale: 'Privacy policy P-12 blocks release while unresolved.', validation: 'Passed · 7 checks', history: 5 },
    { id: 'boundary', name: 'Legal-boundary language', version: '1.4', status: 'draft', author: 'Jamie Park', at: '—', rationale: 'Wording review with counsel in progress.', validation: 'Not yet validated', history: 2 },
  ];

  const DEFAULT_MEMBERS = [
    { name: 'Jamie Park', initials: 'JP', email: 'jamie@northlight.example', role: 'Owner', access: 'All projects', status: 'Active', lastActive: 'Just now' },
    { name: 'Mara Voss', initials: 'MV', email: 'mara@northlight.example', role: 'Reviewer', access: 'Borrowed Light', status: 'Active', lastActive: 'Aug 19' },
    { name: 'Theo Grant', initials: 'TG', email: 'theo@northlight.example', role: 'Editor', access: 'Borrowed Light', status: 'Active', lastActive: 'Aug 18' },
    { name: 'Eli Chen', initials: 'EC', email: 'eli@northlight.example', role: 'Reviewer', access: 'Borrowed Light', status: 'Active', lastActive: 'Aug 12' },
    { name: 'Sam Okafor', initials: 'SO', email: 'sam.o@northlight.example', role: 'Editor', access: 'Borrowed Light', status: 'Deactivated', lastActive: 'Jun 3' },
  ];

  // Cadence is stored canonically ('off'|'manual'|'daily'|'weekly') everywhere —
  // org default and per-project watch alike — and only ever displayed through
  // cadenceLabel(), so the two can no longer read as different words.
  /* No retention duration: evidence is kept until the project is deleted, so a
     '90 days' value here only invited a surface to print a promise the product
     does not make. */
  const DEFAULT_ORG = { name: 'Northlight Pictures', plan: 'Studio', jurisdiction: 'United States · California', cadence: 'weekly' };


  const ROLE_MATRIX = [
    { role: 'Owner', can: 'Billing, policy, release, all decisions' },
    { role: 'Admin', can: 'Team, providers, projects, all decisions' },
    { role: 'Editor', can: 'Import scripts, run research, propose rewrites' },
    { role: 'Reviewer', can: 'Verify sources, refer, record final decisions' },
    { role: 'Viewer', can: 'Read records and exports' },
  ];

  const ROLE_ORDER = ['Owner', 'Admin', 'Editor', 'Reviewer', 'Viewer'];

  /** Which roles hold each capability. Derived from ROLE_MATRIX above so the
      demo role switcher gates controls the same way the matrix reads. A control
      the current role lacks is disabled with a reason — the authority is real,
      not decorative. */
  const CAPABILITIES = {
    decide: ['Owner', 'Admin', 'Reviewer'],       // verify / rule out evidence, record final calls
    refer: ['Owner', 'Admin', 'Reviewer'],        // refer to a specialist
    rewrite: ['Owner', 'Admin', 'Editor'],        // propose a rewrite
    'approve-rewrite': ['Owner', 'Admin', 'Reviewer'], // approve somebody else's proposal into a version
    reassign: ['Owner', 'Admin', 'Reviewer'],     // reassign a flag
    import: ['Owner', 'Admin', 'Editor'],         // import a script / run the check
    research: ['Owner', 'Admin', 'Editor'],       // run a research batch
    release: ['Owner', 'Admin', 'Reviewer'],      // generate and release the clearance report
    team: ['Owner', 'Admin'],                     // invite / change roles
    settings: ['Owner', 'Admin'],                 // org settings
    reset: ['Owner', 'Admin'],                    // demo reset
    /* Promoting or reverting a learning candidate changes how research behaves, so
       it is Owner-only rather than folded into the broad settings capability that
       also covers operational preferences. Admin inspects; Admin does not activate. */
    'learning-governance': ['Owner'],
    'project-create': ['Owner', 'Admin'],        // create a project in this organization
    /* Protected configuration is Owner-only. Admin manages operational settings and
       inspects protected policy but cannot validate or activate it. */
    'settings-protected': ['Owner'],
    comment: ['Owner', 'Admin', 'Editor', 'Reviewer'], // add a review comment
  };

  const CAPABILITY_LABELS = {
    'learning-governance': 'promote or revert a learning candidate',
    'project-create': 'create a project',
    'settings-protected': 'change protected configuration',
    decide: 'record clearance decisions', refer: 'refer flags to a specialist',
    rewrite: 'propose rewrites', reassign: 'reassign flags', import: 'import scripts',
    research: 'run research', release: 'release the clearance report',
    team: 'manage the team', settings: 'change org settings', reset: 'reset the demo',
    comment: 'comment on the review record',
  };

  const CATEGORIES = [
    'People & likeness', 'Names & characters', 'Brands & trademarks', 'Products & trade dress',
    'Locations & property', 'Music & lyrics', 'Artwork & media', 'Dialogue & quotations',
    'Organizations & insignia', 'Privacy & sensitive facts',
  ];

  const SHORT = {
    'People & likeness': 'PEOPLE', 'Names & characters': 'NAMES', 'Brands & trademarks': 'MARK',
    'Products & trade dress': 'PRODUCT', 'Locations & property': 'LOCATION', 'Music & lyrics': 'MUSIC',
    'Artwork & media': 'ART', 'Dialogue & quotations': 'QUOTE', 'Organizations & insignia': 'INSIGNIA',
    'Privacy & sensitive facts': 'PRIVACY',
  };

  const ITEMS = [
    /* scene, page, and context are filled from SCENES below — do not set them here. */
    { id: 'CC-101', term: 'Vega Camera', category: CATEGORIES[2], severity: 'High', confidence: 92, status: 'Needs your call', authority: 'Primary registry', source: 'USPTO TSDR record 8850142', excerpt: 'VEGA is registered for professional motion-picture camera equipment in class 009.', conflict: 'A trade article describes the mark as abandoned; the primary registry record is current.', owner: 'Mara Voss', due: 'Aug 22' },
    { id: 'CC-102', term: 'Mina Velez', category: CATEGORIES[0], severity: 'Medium', confidence: 84, status: 'Needs your call', authority: 'Secondary', source: 'Licensed talent directory', excerpt: 'No exact public-figure match. Two partial matches require contextual review.', conflict: '', owner: 'Theo Grant', due: 'Aug 23' },
    { id: 'CC-103', term: 'Sunset Tower', category: CATEGORIES[4], severity: 'High', confidence: 79, status: 'Sources disagree', authority: 'Mixed', source: 'Property release archive', excerpt: 'Exterior photography terms permit editorial use but do not address commercial set dressing.', conflict: 'Venue policy and municipal filming guidance differ on commercial dressing.', owner: 'Mara Voss', due: 'Aug 21' },
    { id: 'CC-104', term: 'Blue Monday', category: CATEGORIES[5], severity: 'High', confidence: 73, status: 'With specialist', authority: 'Primary', source: 'PRO repertory search', excerpt: 'Multiple compositions share the title. The lyric fragment match is inconclusive.', conflict: 'No definitive publisher match from the supplied fragment.', owner: 'Eli Chen', due: 'Aug 20' },
    { id: 'CC-105', term: 'Keep the change', category: CATEGORIES[7], severity: 'Low', confidence: 61, status: 'Could not verify', authority: 'Unavailable', source: 'Quotation corpus search', excerpt: 'No unique attributable source found after a bounded search.', conflict: 'Search budget exhausted without an authoritative result.', owner: 'Theo Grant', due: 'Aug 26' },
    { id: 'CC-106', term: 'Northstar badge', category: CATEGORIES[8], severity: 'Medium', confidence: 89, status: 'Verified', authority: 'Primary', source: 'State insignia code §14.2', excerpt: 'The depicted seven-point badge differs materially from the protected state seal.', conflict: '', owner: 'Mara Voss', due: 'Aug 24' },
    { id: 'CC-107', term: 'Red bicycle silhouette', category: CATEGORIES[3], severity: 'Medium', confidence: 86, status: 'Needs your call', authority: 'Secondary', source: 'Visual similarity index', excerpt: 'The shape is common; a distinctive frame decal raises a separate mark question.', conflict: '', owner: 'Theo Grant', due: 'Aug 25' },
    { id: 'CC-108', term: 'Glass House poster', category: CATEGORIES[6], severity: 'High', confidence: 95, status: 'Verified', authority: 'Primary registry', source: 'Copyright Office record PA000224189', excerpt: 'Poster artwork is registered to Halcyon Archive LLC.', conflict: '', owner: 'Mara Voss', due: 'Aug 21' },
    { id: 'CC-109', term: 'Dr. Lenora Shaw', category: CATEGORIES[1], severity: 'Medium', confidence: 81, status: 'Needs your call', authority: 'Mixed', source: 'Character and name corpus', excerpt: 'No exact fictional-character match; a similar real professional was identified.', conflict: 'Fictional context reduces but does not remove the name concern.', owner: 'Eli Chen', due: 'Aug 26' },
    { id: 'CC-110', term: 'patient relapse history', category: CATEGORIES[9], severity: 'High', confidence: 97, status: 'Must fix', authority: 'Policy', source: 'ClearCut privacy policy P-12', excerpt: 'Specific health history combined with location detail may identify a real person.', conflict: '', owner: 'Mara Voss', due: 'Aug 19' },
  ];

  const ITEM_STATUSES = ['Needs your call', 'Sources disagree', 'With specialist', 'Verified', 'Must fix', 'Could not verify'];

  /** Retrieved sources, two to five per flag. Previously the interface asserted
      "38 sources" with nothing behind it; now the count is derived from this
      dataset and Exhibit C lists the actual records. `stance` says how a source
      bears on the flag: it supports the concern, contradicts another source, or
      simply provides context. */
  const SOURCES = [
    // CC-101 · Vega Camera — registry current, trade press says otherwise
    { id: 'SRC-001', item: 'CC-101', title: 'USPTO TSDR record 8850142', authority: 'Primary registry', retrieved: 'Aug 19 · 15:42', stance: 'supports', claim: 'VEGA registered in class 009 for professional motion-picture camera equipment; status live.' },
    { id: 'SRC-002', item: 'CC-101', title: 'USPTO assignment history, reel 7741', authority: 'Primary registry', retrieved: 'Aug 19 · 15:42', stance: 'context', claim: 'Ownership assigned to Vega Optics LLC in 2019; no later transfer recorded.' },
    { id: 'SRC-003', item: 'CC-101', title: 'Trade article, Camera Quarterly', authority: 'Secondary', retrieved: 'Aug 19 · 15:43', stance: 'conflicts', claim: 'Describes the VEGA mark as abandoned after the 2021 product line was retired.' },
    { id: 'SRC-004', item: 'CC-101', title: 'Vega Optics product catalogue', authority: 'Secondary', retrieved: 'Aug 19 · 15:43', stance: 'context', claim: 'Mark still used in commerce on current service parts.' },
    // CC-102 · Mina Velez — no public-figure match
    { id: 'SRC-005', item: 'CC-102', title: 'Licensed talent directory', authority: 'Secondary', retrieved: 'Aug 19 · 15:44', stance: 'supports', claim: 'No exact public-figure match for the character name.' },
    { id: 'SRC-006', item: 'CC-102', title: 'Public records index, two partial matches', authority: 'Secondary', retrieved: 'Aug 19 · 15:44', stance: 'context', claim: 'Two individuals share the surname in the depicted region; neither is a public figure.' },
    { id: 'SRC-007', item: 'CC-102', title: 'Screen credits database', authority: 'Secondary', retrieved: 'Aug 19 · 15:44', stance: 'context', claim: 'No prior screen character of this name in the last twenty years.' },
    // CC-103 · Sunset Tower — the venue and the city disagree
    { id: 'SRC-008', item: 'CC-103', title: 'Property release archive, exterior terms', authority: 'Mixed', retrieved: 'Aug 19 · 15:45', stance: 'supports', claim: 'Editorial exterior photography permitted; commercial set dressing not addressed.' },
    { id: 'SRC-009', item: 'CC-103', title: 'Venue filming policy, revision 4', authority: 'Primary', retrieved: 'Aug 19 · 15:45', stance: 'conflicts', claim: 'Requires written consent for any commercial dressing of the marquee.' },
    { id: 'SRC-010', item: 'CC-103', title: 'Municipal filming guidance, §6', authority: 'Primary', retrieved: 'Aug 19 · 15:45', stance: 'conflicts', claim: 'Treats public-right-of-way exteriors as permitted with a location permit alone.' },
    { id: 'SRC-011', item: 'CC-103', title: 'Prior production location log', authority: 'Secondary', retrieved: 'Aug 19 · 15:46', stance: 'context', claim: 'Two features shot the same exterior under permit in the past five years.' },
    // CC-104 · Blue Monday — ownership unresolved
    { id: 'SRC-012', item: 'CC-104', title: 'PRO repertory search, title query', authority: 'Primary', retrieved: 'Aug 19 · 15:47', stance: 'supports', claim: 'Multiple registered compositions share the title; none matched conclusively.' },
    { id: 'SRC-013', item: 'CC-104', title: 'Second PRO repertory, writer query', authority: 'Primary', retrieved: 'Aug 19 · 15:47', stance: 'conflicts', claim: 'Returns a different candidate work than the title query.' },
    { id: 'SRC-014', item: 'CC-104', title: 'Sound-recording rights index', authority: 'Secondary', retrieved: 'Aug 19 · 15:47', stance: 'context', claim: 'Recording and composition rights sit with different owners for two candidates.' },
    { id: 'SRC-015', item: 'CC-104', title: 'Lyric fragment concordance', authority: 'Unavailable', retrieved: 'Aug 19 · 15:48', stance: 'context', claim: 'Fragment too short to attribute; search bounded without a result.' },
    // CC-105 · Keep the change — nothing attributable
    { id: 'SRC-016', item: 'CC-105', title: 'Quotation corpus search', authority: 'Unavailable', retrieved: 'Aug 19 · 15:49', stance: 'supports', claim: 'No unique attributable source after a bounded search.' },
    { id: 'SRC-017', item: 'CC-105', title: 'Idiom usage index', authority: 'Secondary', retrieved: 'Aug 19 · 15:49', stance: 'context', claim: 'Phrase recorded in common usage well before any candidate source.' },
    // CC-106 · Northstar badge — clearly distinguishable
    { id: 'SRC-018', item: 'CC-106', title: 'State insignia code §14.2', authority: 'Primary', retrieved: 'Aug 19 · 15:50', stance: 'supports', claim: 'Protected seal specifies five points and a distinct motto ring.' },
    { id: 'SRC-019', item: 'CC-106', title: 'State seal reference image', authority: 'Primary', retrieved: 'Aug 19 · 15:50', stance: 'supports', claim: 'Depicted seven-point badge differs materially from the protected seal.' },
    { id: 'SRC-020', item: 'CC-106', title: 'Prop house design provenance', authority: 'Secondary', retrieved: 'Aug 19 · 15:50', stance: 'context', claim: 'Badge is an original prop design commissioned for the production.' },
    // CC-107 · Red bicycle silhouette — the decal is the question
    { id: 'SRC-021', item: 'CC-107', title: 'Visual similarity index', authority: 'Secondary', retrieved: 'Aug 19 · 15:51', stance: 'supports', claim: 'Silhouette is a common shape with no distinctive protected form.' },
    { id: 'SRC-022', item: 'CC-107', title: 'Design registry, frame decal', authority: 'Primary registry', retrieved: 'Aug 19 · 15:51', stance: 'context', claim: 'A registered decal design resembles the one visible on the frame.' },
    { id: 'SRC-023', item: 'CC-107', title: 'Manufacturer catalogue, 2024 range', authority: 'Secondary', retrieved: 'Aug 19 · 15:51', stance: 'context', claim: 'Decal appears on a current production model.' },
    // CC-108 · Glass House poster — cleanly owned
    { id: 'SRC-024', item: 'CC-108', title: 'Copyright Office record PA000224189', authority: 'Primary registry', retrieved: 'Aug 19 · 15:52', stance: 'supports', claim: 'Poster artwork registered to Halcyon Archive LLC.' },
    { id: 'SRC-025', item: 'CC-108', title: 'Copyright Office renewal record', authority: 'Primary registry', retrieved: 'Aug 19 · 15:52', stance: 'supports', claim: 'Registration renewed; term runs well past the production window.' },
    { id: 'SRC-026', item: 'CC-108', title: 'Halcyon Archive licensing terms', authority: 'Primary', retrieved: 'Aug 19 · 15:52', stance: 'context', claim: 'Publishes a standard set-dressing licence for archival poster art.' },
    { id: 'SRC-027', item: 'CC-108', title: 'Auction catalogue provenance note', authority: 'Secondary', retrieved: 'Aug 19 · 15:53', stance: 'context', claim: 'Confirms the artist attribution recorded in the registration.' },
    // CC-109 · Dr. Lenora Shaw — a real professional shares the name
    { id: 'SRC-028', item: 'CC-109', title: 'Character and name corpus', authority: 'Mixed', retrieved: 'Aug 19 · 15:54', stance: 'supports', claim: 'No exact fictional-character match in the corpus.' },
    { id: 'SRC-029', item: 'CC-109', title: 'Professional licensing register', authority: 'Primary', retrieved: 'Aug 19 · 15:54', stance: 'conflicts', claim: 'A licensed clinician of the same name practises in the depicted specialty.' },
    { id: 'SRC-030', item: 'CC-109', title: 'Regional name frequency study', authority: 'Secondary', retrieved: 'Aug 19 · 15:54', stance: 'context', claim: 'Surname is uncommon in the region, raising identifiability.' },
    { id: 'SRC-031', item: 'CC-109', title: 'Published news archive', authority: 'Secondary', retrieved: 'Aug 19 · 15:55', stance: 'context', claim: 'No reporting links that clinician to the depicted events.' },
    // CC-110 · patient relapse history — policy, not a registry
    { id: 'SRC-032', item: 'CC-110', title: 'ClearCut privacy policy P-12', authority: 'Policy', retrieved: 'Aug 19 · 15:56', stance: 'supports', claim: 'Health history combined with a named location may identify a real person.' },
    { id: 'SRC-033', item: 'CC-110', title: 'Named facility register', authority: 'Primary', retrieved: 'Aug 19 · 15:56', stance: 'supports', claim: 'The clinic named in the passage exists at the stated location.' },
    { id: 'SRC-034', item: 'CC-110', title: 'Health-information handling guidance', authority: 'Primary', retrieved: 'Aug 19 · 15:56', stance: 'context', claim: 'Room-level detail is treated as directly identifying in guidance.' },
    { id: 'SRC-035', item: 'CC-110', title: 'Broadcast standards note, depiction', authority: 'Secondary', retrieved: 'Aug 19 · 15:57', stance: 'context', claim: 'Recommends removing facility identifiers from dramatised treatment.' },
    { id: 'SRC-036', item: 'CC-110', title: 'Prior rewrite precedent log', authority: 'Secondary', retrieved: 'Aug 19 · 15:57', stance: 'context', claim: 'Comparable passages cleared after removing the location detail.' },
    { id: 'SRC-037', item: 'CC-110', title: 'Facility press office statement', authority: 'Primary', retrieved: 'Aug 19 · 15:57', stance: 'context', claim: 'Declines to consent to identification in dramatic contexts.' },
    { id: 'SRC-038', item: 'CC-110', title: 'Insurer clearance checklist, item 9', authority: 'Secondary', retrieved: 'Aug 19 · 15:58', stance: 'context', claim: 'Lists identifiable health detail among standard pre-delivery removals.' },
  ];

  /** Sources retrieved for one flag. */
  function sourcesFor(itemId) {
    return SOURCES.filter((s) => s.item === itemId);
  }

  /** True when this flag's sources actually disagree with each other. */
  function hasSourceConflict(itemId) {
    return SOURCES.some((s) => s.item === itemId && s.stance === 'conflicts');
  }

  /** Names the kind of uncertainty retained, so a bounded search that found
      nothing is not presented as sources contradicting one another. */
  function uncertaintyTitle(item) {
    return hasSourceConflict(item.id) ? 'Conflict retained' : 'Uncertainty retained';
  }

  /* ── Single source of truth: the script placement ──
     Each flag's scene, page, and on-screen context come from the line it sits
     on in SCENES, not from a second copy on the ITEMS record. This removes the
     class of defect where a flag's drawer said "Scene 3" while it rendered in
     scene 1. Any ITEMS.scene/page/context written by hand is overwritten here,
     and a flag with no line in SCENES is a hard error surfaced at load. */
  const FLAG_PLACEMENT = (() => {
    const map = new Map();
    for (const scene of SCENES) {
      for (const line of scene.lines) {
        if (line.flag) map.set(line.flag, { scene: scene.number, page: scene.page, text: line.text, slug: scene.slug });
      }
    }
    return map;
  })();

  ITEMS.forEach((item) => {
    const place = FLAG_PLACEMENT.get(item.id);
    if (!place) {
      // Fail loudly in the console; the audit also asserts full placement.
      console.error(`ClearCut: flag ${item.id} has no line in SCENES — scene/context will be blank.`);
      return;
    }
    item.scene = place.scene;
    item.page = place.page;
    item.sceneSlug = place.slug;
    item.context = place.text;
  });

  /** Scale of the fictional sample screenplay, Borrowed Light. These describe
      the whole script; SCENES holds only the excerpt the workspace renders, so
      they are declared as sample metadata rather than derived from it, and
      every surface that shows them says "sample script". Page count follows
      from the word count at roughly 190 words to a screenplay page. */
  const SCRIPT_META = { scenes: 43, pages: 62, words: '11,842', passages: '1,204' };

  /** Per-format import identity. The mock previously named one FDX file whatever
      mode was chosen, so a Fountain import wrote an .fdx receipt and a PDF failure
      reported truncated XML. Every format-specific string resolves through here. */
  const IMPORT_FORMATS = {
    FDX: {
      file: 'Borrowed-Light-v1.fdx', size: '2.4 MB', detail: 'Final Draft 13 metadata',
      deterministic: true,
      errorTitle: 'The Final Draft XML is truncated',
      errorBody: 'The file ends after scene 31 with an unclosed element. Re-export from Final Draft.',
      errorCode: 'FDX_XML_UNCLOSED',
      warnings: [{ level: 'Info', text: 'Two scene headings used non-standard capitalisation and were normalised.' }],
    },
    Fountain: {
      file: 'borrowed-light.fountain', size: '184 KB', detail: 'plain-text Fountain syntax',
      deterministic: true,
      errorTitle: 'The Fountain source has an unterminated block',
      errorBody: 'A boneyard comment opened at line 412 and never closed, so everything after it parsed as one note.',
      errorCode: 'FOUNTAIN_UNTERMINATED_BONEYARD',
      warnings: [{ level: 'Warning', text: 'Three transitions were ambiguous and were read as action lines.' }],
    },
    PDF: {
      file: 'Borrowed-Light-locked.pdf', size: '8.1 MB', detail: '62 pages, mixed text and scanned',
      deterministic: false,
      errorTitle: 'This PDF is encrypted',
      errorBody: 'The file carries an owner password that blocks text extraction. Supply the password or export an unprotected copy.',
      errorCode: 'PDF_ENCRYPTED_NO_PASSWORD',
      warnings: [
        { level: 'Warning', text: 'Pages 48–51 are scanned images. Gemini extracted them at 82% average confidence.' },
        { level: 'Info', text: 'Page numbering restarted at page 52 and was renormalised.' },
      ],
    },
    Paste: {
      file: 'pasted text', size: null, detail: 'Fountain-style inference',
      deterministic: true,
      errorTitle: 'The pasted text has no recognisable structure',
      errorBody: 'No scene headings were found, so the text cannot be split into addressable passages.',
      errorCode: 'PASTE_NO_STRUCTURE',
      warnings: [{ level: 'Info', text: 'Scene boundaries were inferred from capitalisation.' }],
    },
  };
  function importFormat() { return IMPORT_FORMATS[state.importMode] || IMPORT_FORMATS.FDX; }

  /** The flags a selective re-check touches after the CC-110 rewrite: the
      rewritten passage and its scene neighbour. Single source for the re-check
      card, its prose, and the receipt, which previously disagreed. */
  /** Which scene a flag sits in, read from the script itself. */
  function sceneOfItem(itemId) {
    const scene = SCENES.find((s) => s.lines.some((l) => l.flag === itemId));
    return scene ? scene.number : null;
  }

  /** What a re-scan has to cover after the given passages were rewritten.

      Derived from the script's own structure rather than a fixture: the rewritten
      flag is directly affected, and other flags in the same scene are affected by
      context because the surrounding text they were read against has moved. A
      hard-coded pair could not answer this for a rewrite of any other passage, and
      would have gone stale the moment a scene was renumbered. */
  function rescanScopeFor(rewrittenIds) {
    const direct = rewrittenIds.filter((id) => ITEMS.some((i) => i.id === id));
    const scenes = new Set(direct.map(sceneOfItem).filter((n) => n !== null));
    const nearby = ITEMS
      .filter((i) => !direct.includes(i.id) && scenes.has(sceneOfItem(i.id)))
      .map((i) => i.id);
    return {
      direct: direct.map((id) => ({ id, why: 'Passage rewritten in this version' })),
      nearby: nearby.map((id) => ({ id, why: `Same scene as a rewritten passage (scene ${sceneOfItem(id)})` })),
      get all() { return [...this.direct, ...this.nearby]; },
      untouched: ITEMS.length - direct.length - nearby.length,
    };
  }

  /** The scope for this project's approved rewrites. Empty until one is approved. */
  function rescanScope() {
    const approved = Object.keys(proj().rewriteProposals || {})
      .filter((id) => proposalFor(id)?.approvedAt);
    // The designed demo approves CC-110 through createVersionTwo, which predates
    // per-item approval records, so honour that flag too.
    if (proj().rewriteApproved && !approved.includes('CC-110')) approved.push('CC-110');
    return rescanScopeFor(approved);
  }

  /** The designed demo scenario, computed the same way so the landing page and the
      versions surface cannot report different numbers for the same rewrite. */
  const DEMO_RESCAN = rescanScopeFor(['CC-110']);

  /** Counts derived from the seed data so every surface — including the landing
      page — reports numbers a reviewer can verify in the flags worklist. */
  const DEMO_FACTS = {
    categories: CATEGORIES.length,
    flags: ITEMS.length,
    high: ITEMS.filter((i) => i.severity === 'High').length,
    mustFix: ITEMS.filter((i) => i.status === 'Must fix').length,
    /* Flags where retrieved sources genuinely disagree, read from the source
       records. Counting ITEMS with any `conflict` note gave 5, but CC-105's note
       describes a bounded search that found nothing — an unavailable result, not
       a disagreement — so the two readings differed by one. */
    conflicts: ITEMS.filter((i) => SOURCES.some((s) => s.item === i.id && s.stance === 'conflicts')).length,
    rescanUntouched: DEMO_RESCAN.untouched,
    // Sources are a real dataset now, so this count is derived like the rest.
    sources: SOURCES.length,
  };

  /** What the workspace actually renders, derived from SCENES. Shown alongside
      the sample script's scale so the excerpt is never mistaken for the whole. */
  const EXCERPT = {
    scenes: SCENES.length,
    lines: SCENES.reduce((n, s) => n + s.lines.length, 0),
    firstPage: SCENES[0].page,
    lastPage: SCENES[SCENES.length - 1].page,
  };

  /** Decision wording per seed status, so the landing page never overstates
      where a flag actually stands. */
  const LP_DECISION = {
    'Needs your call': { label: 'Waiting on a human call', tone: 'is-open' },
    'Verified': { label: 'Verified by', tone: 'is-cleared', withOwner: true },
    'With specialist': { label: 'Referred to a music specialist', tone: 'is-referred' },
  };

  /** The flagged passages the landing page demonstrates, drawn from the same
      seed records the flags worklist shows. The before/after fragments are
      split from each flag's real script line (item.context, itself sourced
      from SCENES), so the landing page and the workspace can never show the
      same passage two different ways. Curly quotes in the copy are normalised
      to match the straight quotes used in the script source. */
  const LP_EVIDENCE = ['CC-101', 'CC-108', 'CC-104'].map((id) => {
    const item = ITEMS.find((i) => i.id === id);
    const decision = LP_DECISION[item.status] || { label: 'On the record', tone: '' };
    const idx = item.context.indexOf(item.term);
    const before = idx >= 0 ? item.context.slice(0, idx) : '';
    const after = idx >= 0 ? item.context.slice(idx + item.term.length) : item.context;
    return {
      id,
      before,
      after,
      term: item.term,
      mark: SHORT[item.category],
      authority: item.authority.toLowerCase(),
      source: item.source,
      claim: item.excerpt,
      conflict: item.conflict,
      decision: decision.withOwner ? `${decision.label} ${item.owner}` : decision.label,
      tone: decision.tone,
    };
  });

  const RUN_STEPS = [
    { label: 'Reading the script', detail: 'Scenes, dialogue, and structure are recognized', result: `${SCRIPT_META.scenes} scenes · ${SCRIPT_META.words} words · nothing needed repair`, ms: 1600, working: 'Parsing scene headings and dialogue…' },
    { label: 'Flagging sensitive material', detail: 'Ten clearance categories checked in scene context', result: `${DEMO_FACTS.flags} flags · ${DEMO_FACTS.high} high priority · ${DEMO_FACTS.mustFix} must fix`, ms: 2200, working: 'Running ten category detectors across every scene…' },
    { label: 'Checking sources', detail: 'Registries, copyright, property, music, quotation, and policy sources', result: `${DEMO_FACTS.sources} sources · ${DEMO_FACTS.conflicts} where sources disagree`, ms: 2600, working: 'Retrieving and cross-checking primary sources…' },
  ];

  /* ── The judge's rubric ──
     All ten dimensions the planning baseline scores (§12), each with the plain
     label the surface shows and the formal name the design document uses. The
     trust surface graded four of them and asserted an aggregate of 88; the
     headline now derives from these scores, so it cannot drift from the rows
     printed beneath it. */
  const JUDGE_RUBRIC = [
    { label: 'Finds what matters', formal: 'Detection recall and category correctness', score: 91 },
    { label: 'Every claim points to its source', formal: 'Claim-to-source grounding', score: 94 },
    { label: 'Provenance is complete', formal: 'Citation and provenance completeness', score: 89 },
    { label: 'Prefers official, current sources', formal: 'Source authority and freshness', score: 86 },
    { label: 'Spots disagreements', formal: 'Conflict identification', score: 81 },
    { label: 'Says what it is unsure of', formal: 'Appropriate uncertainty', score: 93 },
    { label: 'Rewrites are usable', formal: 'Rewrite usefulness', score: 84 },
    { label: 'Re-checks only what changed', formal: 'Affected-item re-scan correctness', score: 92 },
    { label: 'Draws no legal conclusions', formal: 'Legal-boundary compliance', score: 100 },
    { label: 'Stays inside its budget', formal: 'Tool efficiency, latency and cost', score: 88 },
  ];

  /** Deterministic gates that run before any output is accepted — block, warn,
      info — as distinct from the judge's scored rubric above. */
  const JUDGE_GATES = [
    { label: 'Every claim points to its source', result: 'Pass', tone: 'is-success' },
    { label: 'Script versions recorded', result: 'Pass', tone: 'is-success' },
    { label: 'Open disagreement flagged', result: 'Warn', tone: 'is-warning' },
    { label: 'No legal conclusions', result: 'Pass', tone: 'is-success' },
  ];

  /** The exact versions a graded run was evaluated against. One source, so the
      trust surface and a released report cannot cite different ones. */
  const EVAL_PROVENANCE = {
    rubric: '2.4', prompt: 'cc-research-17', policy: '3.2',
    judge: 'gemini-2.5-pro', latency: '4.2s', cost: '$0.031',
  };

  const judgeScore = () => Math.round(JUDGE_RUBRIC.reduce((n, d) => n + d.score, 0) / JUDGE_RUBRIC.length);
  const weakestDimension = () => JUDGE_RUBRIC.reduce((a, b) => (b.score < a.score ? b : a));

  /* ── Tool calls ──
     The baseline makes AgentToolCall first class alongside AgentRun (§6.5, §17),
     but the ledger carried only run-level totals: a reader could see that a run
     recovered from something without being able to see what. Each call records
     the tool, the argument it was given, how long it took, what came back, and
     its terminal status.

     The searches are generated from the dataset, one per flag, carrying that
     flag's real source and conflict counts — a hand-written list could disagree
     with SOURCES, and this cannot. Run totals then derive from the calls, so a
     run cannot report a source count its own calls do not add up to. */
  const TIMED_OUT_FLAG = 'CC-104';

  function searchCall(item) {
    const own = SOURCES.filter((s) => s.item === item.id);
    const conflicts = own.filter((s) => s.stance === 'conflicts').length;
    return {
      tool: 'parallel.search',
      target: `${SHORT[item.category].toLowerCase()} · ${item.term}`,
      // Longer retrievals for the flags that returned more to cross-check.
      ms: 2400 + own.length * 420,
      sources: own.length,
      result: `${own.length} source${own.length === 1 ? '' : 's'}${conflicts ? ` · ${conflicts} conflicting` : ''}`,
      status: item.status === 'Could not verify' ? 'partial' : 'ok',
    };
  }

  function buildInitialRun() {
    const searchedFlags = ITEMS.filter((i) => i.id !== TIMED_OUT_FLAG).map(searchCall);
    const timedOut = ITEMS.find((i) => i.id === TIMED_OUT_FLAG);
    const retrieved = searchedFlags.reduce((n, c) => n + c.sources, 0);
    return [
      { tool: 'script.parse', target: 'Borrowed-Light-v1.fdx', ms: 2140, result: `${SCRIPT_META.scenes} scenes · ${SCRIPT_META.passages} passages`, status: 'ok' },
      { tool: 'detect.categories', target: `all ${CATEGORIES.length} categories`, ms: 18400, result: `${ITEMS.length} flags proposed`, status: 'ok' },
      ...searchedFlags,
      {
        tool: 'parallel.search',
        target: `${SHORT[timedOut.category].toLowerCase()} · ${timedOut.term}`,
        ms: 30000, sources: 0, result: 'Provider timeout after 30s — retried as run_02', status: 'timeout',
      },
      { tool: 'evidence.normalise', target: `${retrieved} retrieved sources`, ms: 1870, claims: 55, result: `55 claims · ${DEMO_FACTS.conflicts} conflicts retained`, status: 'ok' },
      { tool: 'judge.evaluate', target: `rubric ${EVAL_PROVENANCE.rubric}`, ms: 4200, result: `Score ${judgeScore()} · ${JUDGE_GATES.filter((g) => g.result === 'Warn').length} warning`, status: 'ok' },
    ];
  }

  const TOOL_CALLS = {
    run_01: buildInitialRun(),
    run_02: [
      { tool: 'parallel.search', target: 'music · recording owner', ms: 5100, sources: 2, result: '2 sources', status: 'ok' },
      { tool: 'parallel.search', target: 'music · composition publisher', ms: 4700, sources: 2, result: '2 sources · 1 conflicting', status: 'ok' },
      { tool: 'evidence.normalise', target: '4 retrieved sources', ms: 900, claims: 5, result: '5 claims · owners differ', status: 'ok' },
      { tool: 'source.fetch', target: 'quotation anthology · robots.txt denies', ms: 1200, sources: 0, result: 'Access forbidden — flagged for a person', status: 'failed' },
    ],
    run_03: [
      { tool: 'script.diff', target: 'v1 → v2', ms: 640, result: '1 passage changed · stable ids preserved', status: 'ok' },
      { tool: 'detect.categories', target: 'affected passages only', ms: 3300, result: `${DEMO_RESCAN.all.length} flags re-evaluated`, status: 'ok' },
      { tool: 'parallel.search', target: 'privacy · revised line', ms: 4100, sources: 6, result: '6 sources', status: 'ok' },
      { tool: 'evidence.normalise', target: '6 retrieved sources', ms: 780, claims: 9, result: '9 claims · none conflicting', status: 'ok' },
    ],
  };

  const TOOL_STATUS = {
    ok: { label: 'Accepted', tone: 'is-success' },
    timeout: { label: 'Timed out', tone: 'is-warning' },
    partial: { label: 'Bounded', tone: 'is-warning' },
    failed: { label: 'Needs a person', tone: 'is-danger' },
  };

  /** Calls for a run: seeded runs carry them here, runs the visitor starts carry
      their own on the saved record. */
  function toolCallsFor(runId) {
    if (TOOL_CALLS[runId]) return TOOL_CALLS[runId];
    const saved = state.researchRuns.find((r) => r.id === runId);
    return (saved && saved.calls) || [];
  }

  /** A run's totals, derived from its calls. `sources`, `claims` and `latency`
      were literals on the run record that nothing recomputed, so they could not
      be checked against the calls that produced them. */
  function runTotals(runId) {
    const calls = toolCallsFor(runId);
    return {
      calls: calls.length,
      sources: calls.reduce((n, c) => n + (c.sources || 0), 0),
      claims: calls.reduce((n, c) => n + (c.claims || 0), 0),
      ms: calls.reduce((n, c) => n + c.ms, 0),
      exceptions: calls.filter((c) => c.status !== 'ok').length,
    };
  }

  /** Milliseconds as the ledger shows them: sub-second in ms, then seconds,
      then minutes once a run passes one. */
  function fmtDuration(ms) {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
    const m = Math.floor(ms / 60_000);
    return `${m}m ${String(Math.round((ms % 60_000) / 1000)).padStart(2, '0')}s`;
  }

  /* Each seeded run declares the project state it belongs to, so the ledger
     cannot list work the project has not done. The re-scan run appeared as soon
     as the check completed, which put a "Selective re-scan" in the ledger of a
     project whose Versions surface still offered to run one. */
  const RESEARCH_RUNS = [
    { id: 'run_03', needs: 'rescanComplete', started: 'Aug 19 · 15:42', scope: 'Selective re-scan (2 items)', cost: '$0.014', model: 'gemini-2.5-flash', prompt: 'cc-research-17', status: 'Complete' },
    { id: 'run_02', needs: 'runComplete', started: 'Aug 19 · 15:20', scope: 'Music ownership retry', cost: '$0.009', model: 'gemini-2.5-flash', prompt: 'cc-research-17', status: 'Recovered' },
    { id: 'run_01', needs: 'runComplete', started: 'Aug 19 · 14:58', scope: 'Full detection & research', cost: '$0.212', model: 'gemini-2.5-pro', prompt: 'cc-research-17', status: 'Complete with exceptions' },
  ];

  /* ── Notification templates ──
     One place decides how each domain event reads, so the same event cannot be
     phrased two ways by two writers. A notification is an event plus a
     destination, never a hand-written sentence with a route guessed beside it. */
  const NOTIFICATION_EVENTS = {
    'item.assigned': {
      tier: 'action',
      title: (d) => `${d.entityId} assigned to you`,
      detail: (d) => [d.severity, d.due ? `due ${d.due}` : ''].filter(Boolean).join(' · '),
    },
    'source.changed': {
      tier: 'urgent',
      title: (d) => `A source behind ${d.entityId} changed`,
      detail: (d) => d.summary || 'Needs your review',
    },
    'referral.acknowledged': {
      tier: 'informational',
      title: () => 'Specialist referral acknowledged',
      detail: (d) => `${d.entityId} · ${d.specialist || 'specialist'}`,
    },
  };

  /** Renders an event record into the inbox shape. The destination is structured
      — project plus entity type and id — rather than a bare route string, which
      could not say *which* item it meant. The seeded assignment notification used
      route 'item' with no id, so it opened whichever flag happened to be active. */
  function notificationFrom(event) {
    const template = NOTIFICATION_EVENTS[event.event];
    if (!template) return null;
    return {
      id: event.id,
      kind: event.kind,
      tier: template.tier,
      event: event.event,
      destination: event.destination,
      project: PROJECT_DEFS.find((d) => d.id === event.destination.project)?.title || event.destination.project,
      title: template.title(event.data),
      detail: template.detail(event.data),
      at: event.at,
      atISO: event.atISO,
      atRaw: event.atRaw || 0,
      unread: event.unread,
    };
  }

  /** Where a structured destination points. One resolver, so every entity type
      lands on the surface that actually shows it. */
  function destinationRoute(dest) {
    if (!dest) return 'records';
    switch (dest.entityType) {
      case 'clearance_item': return `item?id=${encodeURIComponent(dest.entityId)}`;
      case 'monitoring_review': return 'watch?review=open';
      case 'version': return 'versions';
      case 'report': return 'report';
      default: return 'records';
    }
  }

  /** Whether the signed-in person can reach a destination's project. A
      notification is not permission: if the project is not theirs, or no longer
      exists, it says so instead of navigating somewhere misleading. */
  function destinationBlock(dest) {
    if (!dest || !dest.project) return null;
    if (!PROJECT_DEFS.some((d) => d.id === dest.project)) {
      return 'That project is no longer on this organization.';
    }
    const me = state.members.find((m) => m.name === ACTOR.name);
    const title = PROJECT_DEFS.find((d) => d.id === dest.project)?.title;
    if (me && me.access !== 'All projects' && me.access !== title) {
      return `${me.access} is the only project your access covers, so ${title} cannot be opened.`;
    }
    return null;
  }

  const NOTIFICATION_EVENTS_SEED = [
    { id: 'n1', kind: 'assignment', event: 'item.assigned', at: 'Aug 19 · 15:05', atISO: '2026-08-19T15:05', unread: true,
      destination: { org: 'northlight', project: 'borrowed-light', entityType: 'clearance_item', entityId: 'CC-110' },
      data: { entityId: 'CC-110', severity: 'Must fix', due: 'Aug 19' } },
    { id: 'n2', kind: 'monitoring', event: 'source.changed', at: 'Aug 19 · 14:40', atISO: '2026-08-19T14:40', unread: true,
      destination: { org: 'northlight', project: 'borrowed-light', entityType: 'monitoring_review', entityId: 'CC-101' },
      data: { entityId: 'CC-101', summary: 'Registration now contested — cancellation petition filed' } },
    { id: 'n3', kind: 'referral', event: 'referral.acknowledged', at: 'Aug 19 · 13:22', atISO: '2026-08-19T13:22', unread: false,
      destination: { org: 'northlight', project: 'borrowed-light', entityType: 'clearance_item', entityId: 'CC-104' },
      data: { entityId: 'CC-104', specialist: 'Eli Chen' } },
    /* No seeded "Script check finished" entry: a real run writes its own receipt
       and the inbox renders that, so a seed copy sat beside it under the same
       title with different figures. */
  ];

  const NOTIFICATIONS = NOTIFICATION_EVENTS_SEED.map(notificationFrom).filter(Boolean);

  /* ── Seeded project state ──
     ITEMS is a constant, so every project surface rendered ten researched flags
     while PROJECT_STATE started with no script and no completed run. A visitor
     arriving at the worklist saw a finished analysis; the overview beside it said
     "Finish checking the script"; the versions surface said "No versions yet".
     Three surfaces disagreed about whether the work had happened.

     Borrowed Light now ships with the machine half done — script imported,
     detection and research complete — because that is precisely what the seed
     data represents. Everything a person must decide is left undone, so the
     human half of the workflow is still the visitor's to perform. The Quiet
     Coast ships empty, which keeps the import wizard, the live check and every
     empty state demonstrable on a project where they belong. */
  const SEEDED_PROJECTS = {
    'borrowed-light': {
      // Mirrors the wizard's own step-1 payload, so the guided flow reads as
      // complete rather than asking for details the project already has.
      details: {
        title: PROJECT_DEFS[0].title, type: PROJECT_DEFS[0].type, stage: PROJECT_DEFS[0].stage,
        jurisdiction: PROJECT_DEFS[0].jurisdiction, lock: PROJECT_DEFS[0].lock, brief: PROJECT_DEFS[0].brief,
      },
      versions: [{ label: 'v1', source: 'FDX import', hash: '9c7a23d08e41', createdAt: '2026-08-19T14:52:00', parent: null }],
      runStep: RUN_STEPS.length,
      runComplete: true,
    },
  };

  const DEFAULT_STATE = {
    schema: SCHEMA_VERSION,
    /* Tabbed surfaces keep their view here; the URL is the source of truth on
       arrival and this is what persists between visits. */
    settingsTab: 'general', teamTab: 'members', recordsView: 'activity',
    invitations: DEFAULT_INVITATIONS.map((i) => ({ ...i })),
    visited: [],
    completed: [],
    auth: false,
    orgReady: false,
    actorRole: 'Owner',
    org: { ...DEFAULT_ORG },
    members: DEFAULT_MEMBERS.map((m) => ({ ...m })),
    projects: PROJECT_DEFS.reduce((acc, p) => {
      acc[p.id] = { ...JSON.parse(JSON.stringify(PROJECT_STATE)), ...JSON.parse(JSON.stringify(SEEDED_PROJECTS[p.id] || {})) };
      return acc;
    }, {}),
    activeProjectId: PROJECT_DEFS[0].id,
    importMode: 'FDX',
    /* Ingestion #4/#5/#7: the mock described one FDX file whatever mode was
       selected, so a Fountain import produced an .fdx receipt and a PDF failure
       reported truncated XML. Per-format identity, validation, and failure. */
    fileChosen: false,
    parseWarnings: null,
    itemsView: 'list',
    itemFilter: 'all',
    itemsSort: { key: 'severity', dir: 'desc' },
    itemsGroup: 'none',
    itemsSearch: '',
    paneTab: 'script',
    drawerOpen: true,
    sidebarCollapsed: false,
    selectedItems: [],
    learning: { stage: 'candidate' },
    researchRuns: [],
    receipts: [],
    readNotifications: [],
  };

  /* ═══════════════════════════════ DOM REFS ═══════════════════════════════ */

  const el = {
    publicHeader: document.querySelector('#public-header'),
    appHeader: document.querySelector('#app-header'),
    sidebar: document.querySelector('#app-sidebar'),
    contextChip: document.querySelector('#context-chip'),
    main: document.querySelector('#app-main'),
    root: document.querySelector('#route-root'),
    mobileNav: document.querySelector('#mobile-nav'),
    drawer: document.querySelector('#mobile-drawer'),
    dialogHost: document.querySelector('#dialog-host'),
    toasts: document.querySelector('#toast-region'),
    polite: document.querySelector('#live-polite'),
    assertive: document.querySelector('#live-assertive'),
  };

  let state = loadState();
  let currentRoute = routeFromHash();
  let lastFocus = null;
  let drawerTrigger = null;
  /** Pending timeouts for the staged script check, so a cancel can clear them.
      Held outside persisted state because timer ids do not survive a reload. */
  let runTimers = [];
  let runTicker = null;
  /** Project the in-flight check belongs to, so its timers cannot land on another. */
  let runProjectId = null;
  /** Set while re-rendering in place (live search), so the route render does not
      steal focus, scroll to top, or re-announce the surface on every keystroke. */
  let suppressRouteFocus = false;
  /** Unique ids for gated-control reasons referenced by aria-describedby. */
  let gateSeq = 0;
  /** Hash whose deep-link query has already been applied to worklist state. */
  let appliedQueryHash = null;
  let rescanTimers = [];
  let rescanProjectId = null;
  let monitorTimers = [];
  let monitorProjectId = null;

  /* ═══════════════════════════════ STATE ═══════════════════════════════ */

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function esc(value = '') {
    return String(value).replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
  }

  function loadState() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (!saved || saved.schema !== SCHEMA_VERSION) return clone(DEFAULT_STATE);
      const merged = {
        ...clone(DEFAULT_STATE),
        ...saved,
        org: { ...DEFAULT_ORG, ...(saved.org || {}) },
        members: Array.isArray(saved.members) && saved.members.length ? saved.members : DEFAULT_MEMBERS.map((m) => ({ ...m })),
        invitations: Array.isArray(saved.invitations) && saved.invitations.length ? saved.invitations : DEFAULT_INVITATIONS.map((i) => ({ ...i })),
        learning: { ...DEFAULT_STATE.learning, ...(saved.learning || {}) },
        projects: { ...clone(DEFAULT_STATE.projects) },
      };
      // Merge each project slice so new fields appear without wiping saved work.
      // The base is the seeded default, not bare PROJECT_STATE: a saved slice
      // missing a key would otherwise fall back past its project's own seed.
      PROJECT_DEFS.forEach((def) => {
        const savedProject = saved.projects && saved.projects[def.id];
        merged.projects[def.id] = {
          ...clone(DEFAULT_STATE.projects[def.id]),
          ...(savedProject || {}),
          monitoring: { ...PROJECT_STATE.monitoring, ...((savedProject || {}).monitoring || {}) },
        };
        // A run in progress cannot survive a reload — its timers are gone — so
        // an interrupted check resets to its pre-run state rather than hanging
        // on a "Working…" step forever.
        if (merged.projects[def.id].running && !merged.projects[def.id].runComplete) {
          merged.projects[def.id].running = false;
          merged.projects[def.id].runStep = 0;
          merged.projects[def.id].runStartedAt = null;
        }
        // Same for an interrupted re-scan: its timers died with the page, so it
        // resets to not-started rather than leaving rows stuck mid-flight.
        if (merged.projects[def.id].rescanning && !merged.projects[def.id].rescanComplete) {
          merged.projects[def.id].rescanning = false;
          merged.projects[def.id].rescanDone = [];
        }
        if (merged.projects[def.id].monitoring.checking) {
          merged.projects[def.id].monitoring.checking = false;
          merged.projects[def.id].monitoring.checked = 0;
        }
      });
      if (!merged.projects[merged.activeProjectId]) merged.activeProjectId = PROJECT_DEFS[0].id;
      return merged;
    } catch (_) {
      return clone(DEFAULT_STATE);
    }
  }

  /** Active project's mutable clearance state. */
  function proj() {
    return state.projects[state.activeProjectId] || state.projects[PROJECT_DEFS[0].id];
  }

  /** Static definition of the active project. */
  function projDef(id = state.activeProjectId) {
    return PROJECT_DEFS.find((p) => p.id === id) || PROJECT_DEFS[0];
  }

  /** The role the demo is currently acting as (switchable, defaults to Owner). */
  function actorRole() {
    return state.actorRole || 'Owner';
  }

  /** True when the current role holds the capability. */
  function can(capability) {
    const roles = CAPABILITIES[capability];
    return !roles || roles.includes(actorRole());
  }

  /** A control that requires a capability: the button when allowed, or a
      disabled version with a reason when the current role cannot perform it.
      Keeps gating consistent — every gated control reads the same way. */
  function gated(capability, buttonHtml) {
    if (can(capability)) return buttonHtml;
    const why = `${actorRole()} cannot ${CAPABILITY_LABELS[capability] || 'do this'}`;
    /* aria-disabled rather than disabled: a `disabled` button leaves the tab
       order, so a keyboard or screen-reader user met a control they could
       neither reach nor have explained. This stays focusable, is described by
       visible text, and its action is neutralised so activating it does
       nothing but repeat the reason. */
    const id = `gate-${capability}-${gateSeq += 1}`;
    const control = buttonHtml
      .replace(/<button /, `<button aria-disabled="true" data-gated="1" aria-describedby="${id}" `)
      .replace(/data-action="[^"]*"/, 'data-action="gated-blocked"');
    return `${control}<span class="gate-reason" id="${id}"><span aria-hidden="true">🔒</span>${esc(why)}</span>`;
  }

  /** Production details as they should display: the reviewer's saved edits from
      the wizard, falling back to the static definition for anything untouched.
      Every surface that shows title/type/stage/jurisdiction/lock/brief reads
      this, so the New-clearance form is the single source for those facts. */
  function projInfo(id = state.activeProjectId) {
    const def = projDef(id);
    const saved = (state.projects[id] || {}).details;
    return saved ? { ...def, ...saved } : def;
  }

  function saveState() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (_) { /* keep working */ }
  }

  function resetDemo() {
    // Kill any in-flight run first, or its pending steps write a completed
    // check and a receipt into the state we just reset.
    clearRunTimers();
    try { localStorage.removeItem(STORAGE_KEY); } catch (_) {}
    state = clone(DEFAULT_STATE);
    saveState();
  }

  /** Receipt kinds that belong to the organization, not to one project. */
  const ORG_RECEIPT_KINDS = ['auth', 'membership', 'organization', 'settings', 'learning', 'provider'];

  /** Receipts for one project: its own actions, newest first. */
  function projectReceipts(id = state.activeProjectId) {
    return state.receipts.filter((r) => r.project === id);
  }

  /** A rewrite proposal, normalized. Older saved state stored a bare string, so
      the author and time were unknown — those read as null rather than being
      invented. */
  function proposalFor(itemId) {
    const raw = (proj().rewriteProposals || {})[itemId];
    if (!raw) return null;
    if (typeof raw === 'string') return { text: raw, by: null, byRole: null, at: null, approvedBy: null, approvedRole: null, approvedAt: null };
    return { approvedBy: null, approvedRole: null, approvedAt: null, ...raw };
  }

  /** Whether the current actor may approve this proposal. Proposing and approving
      are deliberately different hands: a change to the script that one person can
      both author and wave through is not reviewed, it is just typed. */
  function rewriteApprovalBlock(itemId) {
    const proposal = proposalFor(itemId);
    if (!proposal) return 'A rewrite has to be proposed before it can be approved.';
    if (proposal.approvedAt) return null;
    if (!can('approve-rewrite')) return `Approving a rewrite needs ${CAPABILITIES['approve-rewrite'].join(', ')}. You are viewing as ${actorRole()}.`;
    if (proposal.byRole && proposal.byRole === actorRole()) {
      return `${esc(proposal.byRole)} proposed this rewrite, so the same hand cannot approve it. Switch the prototype role to another approver to continue.`;
    }
    return null;
  }

  /** Stable comment ids so replies and edits can name their target. */
  function nextCommentId() {
    const used = new Set(proj().comments.map((c) => c.id).filter(Boolean));
    let i = 1;
    while (used.has(`c-${i}`)) i += 1;
    return `c-${i}`;
  }

  function addReceipt(kind, title, detail, item = null) {
    const receipt = {
      id: `R-${String(state.receipts.length + 1).padStart(3, '0')}`,
      /* Which clearance item the action concerned, when it concerned one. The
         item timeline reads these rather than keeping a second log, so what it
         shows is the recorded trail and not a parallel story. */
      item,
      /* Which project the action belonged to, so a clearance report can carry
         its own decisions instead of the whole organization's. Org-level
         actions (sign-in, settings, membership) record no project. */
      project: ORG_RECEIPT_KINDS.includes(kind) ? null : state.activeProjectId,
      kind, title, detail,
      at: new Date().toISOString(),
      actor: ACTOR.name,
    };
    state.receipts.unshift(receipt);
    saveState();
    return receipt;
  }

  function completeStage(id) {
    if (!state.completed.includes(id)) state.completed.push(id);
    saveState();
  }

  /** The one timestamp format: relative inside 24 h, then "Aug 19 · 15:05".
      Values that are not parseable dates (older saved comments) pass through. */
  function fmtStamp(value) {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    const diff = Date.now() - d.getTime();
    if (diff >= 0 && diff < 60_000) return 'Just now';
    if (diff >= 0 && diff < 3_600_000) return `${Math.round(diff / 60_000)}m ago`;
    if (diff >= 0 && diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h ago`;
    const day = new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(d);
    const time = new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit', hour12: false }).format(d);
    return `${day} · ${time}`;
  }

  /* ── Verification progress ──
     A literal 6 used to stand in for "flags that can carry a verify call" in
     four places, so the denominator could not be checked against the worklist.
     It now derives: the flags awaiting a call, plus the two the seed run already
     verified. Without the verified pair in the population, the overview read
     "0 verified" while two rows in the worklist read "Verified". */
  const AWAITING_CALL_STATUSES = ['Needs your call', 'Sources disagree', 'Could not verify'];
  const VERIFIABLE_ITEMS = ITEMS.filter((i) => AWAITING_CALL_STATUSES.includes(i.status) || i.status === 'Verified');

  /* ── Flags belong to a project ──
     ITEMS is the demo screenplay's result set. Reading it globally meant a
     project with no script still reported ten researched flags, so the worklist
     showed a finished analysis while the overview beside it asked the visitor to
     start one. A project owns flags once its check has completed — which also
     makes the empty states real and gives the live check a visible consequence. */
  function flagsFor(p) { return p.runComplete ? ITEMS : []; }
  function flags() { return flagsFor(proj()); }

  /** Verified flags in a given project slice: the reviewer's own calls plus the
      seed run's, minus any the reviewer has since ruled out. */
  function verifiedCountFor(p) {
    if (!p.runComplete) return 0;
    return VERIFIABLE_ITEMS.filter((i) => {
      const decision = p.evidenceDecisions[i.id];
      if (decision === 'accepted') return true;
      if (decision === 'rejected') return false;
      return i.status === 'Verified';
    }).length;
  }
  function verifiedCount() { return verifiedCountFor(proj()); }

  function itemStatus(item) {
    const decision = proj().evidenceDecisions[item.id];
    if (decision === 'accepted') return 'Verified';
    if (decision === 'rejected') return 'Needs your call';
    if (decision === 'resolved-on-v2') return 'Fixed in v2';
    if (item.id === 'CC-104' && proj().referralCreated) return 'With specialist';
    return item.status;
  }

  /** Which evidence phase an item is in. The drawer previously rendered one
      layout for every case, so an item whose search returned nothing showed the
      same confident source card as a fully-verified one, and an item still being
      researched offered a Verify button with no evidence behind it.

      Returns one of: 'running' | 'failed' | 'empty' | 'referred' | 'decided' | 'ready'. */
  function evidencePhase(item) {
    // Nothing has been researched until the project's check has completed.
    if (!proj().runComplete) return 'running';
    const decision = proj().evidenceDecisions[item.id];
    if (decision === 'accepted' || decision === 'resolved-on-v2') return 'decided';
    if (item.id === 'CC-104' && proj().referralCreated) return 'referred';
    // A bounded search that ended without an attributable source is not a
    // failure of the provider, and it is not clearance either.
    if (item.authority === 'Unavailable' || !sourcesFor(item.id).length) return 'empty';
    return 'ready';
  }

  function statusTone(status) {
    if (status === 'Verified' || status === 'Fixed in v2') return 'is-success';
    if (status === 'Must fix') return 'is-danger';
    if (status === 'Sources disagree' || status === 'With specialist') return 'is-warning';
    if (status === 'Could not verify') return '';
    return 'is-accent';
  }

  /* ── Sorting & grouping (items worklist) ── */

  /* Highest severity ranks highest so 'desc' reads worst-first. */
  const SEVERITY_ORDER = { High: 2, Medium: 1, Low: 0 };
  const SORT_LABELS = { term: 'Term', severity: 'Severity', confidence: 'Confidence', scene: 'Scene', due: 'Due', status: 'Status' };
  const SORT_DEFAULT_DIR = { term: 'asc', severity: 'desc', confidence: 'desc', scene: 'asc', due: 'asc', status: 'asc' };

  function dueTime(item) {
    return new Date(`${effectiveDue(item)}, 2026`).getTime() || 0;
  }

  function effectiveOwner(item) {
    return proj().assignments[item.id] || item.owner;
  }

  /** A flag's due date, honouring any reassignment. Falls back to the seed due. */
  function effectiveDue(item) {
    return proj().assignmentDue[item.id] || item.due;
  }

  /** "2026-08-22" (date-input value) → "Aug 22". Passes through values that are
      already short-form so the seed dates and picker values render identically. */
  function fmtDueDate(value) {
    if (!value) return '';
    const iso = /^\d{4}-\d{2}-\d{2}$/.test(value);
    const d = iso ? new Date(`${value}T00:00:00`) : new Date(`${value}, 2026`);
    if (Number.isNaN(d.getTime())) return String(value);
    return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(d);
  }

  /** The script line a flag sits on, plus any pre-drafted lower-risk rewrite. */
  function scriptLineFor(itemId) {
    for (const scene of SCENES) {
      for (const line of scene.lines) {
        if (line.flag === itemId) return { text: line.text, rewritten: line.rewritten || '' };
      }
    }
    return { text: '', rewritten: '' };
  }

  /** Local calendar date as yyyy-mm-dd. Never use toISOString() for this: it
      converts to UTC first, which lands on the previous day everywhere east of
      Greenwich and silently moves a date every time a picker round-trips. */
  function isoDateLocal(d) {
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  /** "Sep 18, 2026" or "2026-09-18" → yyyy-mm-dd for a date input. */
  function lockInputValue(value) {
    if (!value) return '2026-09-18';
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '2026-09-18' : isoDateLocal(d);
  }

  /** yyyy-mm-dd → "Sep 18, 2026" for display/storage of the lock date. */
  function lockDisplay(value) {
    if (!value) return '';
    const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
    return Number.isNaN(d.getTime()) ? String(value) : new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(d);
  }

  /** yyyy-mm-dd value for the date input, seeded from the flag's current due. */
  function dueInputValue(itemId) {
    const item = ITEMS.find((i) => i.id === itemId);
    const current = item ? effectiveDue(item) : '';
    const d = /^\d{4}-\d{2}-\d{2}$/.test(current) ? new Date(`${current}T00:00:00`) : new Date(`${current}, 2026`);
    if (Number.isNaN(d.getTime())) return '2026-08-22';
    return isoDateLocal(d);
  }

  /** Items a human must act on — blocked, conflicted, or referred. */
  function isAttention(item) {
    return ['Must fix', 'Sources disagree', 'With specialist'].includes(itemStatus(item));
  }

  function sortItems(list) {
    const { key, dir } = state.itemsSort;
    const mul = dir === 'asc' ? 1 : -1;
    const rank = (i) => {
      switch (key) {
        case 'term': return i.term.toLowerCase();
        case 'severity': return SEVERITY_ORDER[i.severity];
        case 'confidence': return i.confidence;
        case 'scene': return i.scene;
        case 'due': return dueTime(i);
        case 'status': return ITEM_STATUSES.indexOf(itemStatus(i));
        default: return i.term.toLowerCase();
      }
    };
    return [...list].sort((a, b) => {
      const av = rank(a);
      const bv = rank(b);
      if (av < bv) return -mul;
      if (av > bv) return mul;
      return a.id.localeCompare(b.id);
    });
  }

  const GROUPERS = {
    none: null,
    scene: { label: (k) => `Scene ${k}`, sortKeys: (a, b) => a - b, key: (i) => i.scene },
    category: { label: (k) => k, sortKeys: (a, b) => CATEGORIES.indexOf(a) - CATEGORIES.indexOf(b), key: (i) => i.category },
    owner: { label: (k) => k, sortKeys: (a, b) => a.localeCompare(b), key: effectiveOwner },
    due: { label: (k) => `Due ${k}`, sortKeys: (a, b) => new Date(`${a}, 2026`) - new Date(`${b}, 2026`), key: effectiveDue },
  };

  /** Buckets the (already sorted) list for the active grouping. */
  function groupItems(list) {
    const grouper = GROUPERS[state.itemsGroup];
    if (!grouper) return [{ label: '', items: list }];
    const buckets = new Map();
    for (const item of list) {
      const k = grouper.key(item);
      if (!buckets.has(k)) buckets.set(k, []);
      buckets.get(k).push(item);
    }
    return [...buckets.keys()].sort(grouper.sortKeys).map((k) => ({ label: grouper.label(k), items: buckets.get(k) }));
  }

  const PUSH_PREF_LABELS = { 'in-app': 'in the app only', email: 'in the app and by email', push: 'in the app and by browser push' };

  /** The delivery preference control. Lives in Settings because it is a standing
      choice, and is rendered from one place so the inbox summary quotes the same
      vocabulary. */
  function deliveryPreferenceCard() {
    const pref = state.pushPref || 'in-app';
    return card({
      body: `<div class="choice-row">${[
          ['in-app', 'In the app only'],
          ['email', 'In the app and by email'],
          ['push', 'In the app and browser push'],
        ].map(([v, label]) => `<label class="choice"><input type="radio" name="push-pref" value="${v}" ${pref === v ? 'checked' : ''} data-action="set-push-pref"><span>${esc(label)}</span></label>`).join('')}</div>
        <p class="small muted gap-t-3" role="status">${pref === 'push'
          ? 'Browser push asks your permission the first time. This prototype records the preference and registers no push subscription, so nothing is delivered outside this tab.'
          : pref === 'email'
            ? `Email would go to ${esc((state.members.find((m) => m.name === ACTOR.name) || {}).email || 'your address')}. This prototype records the preference and sends nothing.`
            : 'Only the inbox inside ClearCut. Nothing leaves the app.'}</p>`,
    });
  }

  /** Members named in a comment. Matching real member names means a mention
      either resolves to somebody who can act on it or is left as plain text —
      never a link to nobody. */
  function mentionsIn(text) {
    const lower = String(text).toLowerCase();
    return state.members.filter((m) => lower.includes(`@${m.name.toLowerCase()}`)
      || lower.includes(`@${m.name.split(' ')[0].toLowerCase()}`));
  }

  /** Renders comment text with resolved mentions marked. Escapes first, so the
      markup cannot be injected through a comment body. */
  function commentBody(text) {
    let html = esc(text);
    mentionsIn(text).forEach((m) => {
      const first = m.name.split(' ')[0];
      html = html.replace(new RegExp(`@(${esc(m.name)}|${esc(first)})\\b`, 'gi'),
        `<span class="mention" title="${esc(m.name)} · ${esc(m.role)}">@$1</span>`);
    });
    return html;
  }

  /** The review record for one item: what people said and what was done, in the
      order it happened. Comments alone read as a conversation with no consequences
      — the governed actions are the half that matters, so they share the timeline.

      System entries come from recorded receipts, so nothing appears here that was
      not actually done. Seeded state carries no receipt and therefore no entry,
      rather than an invented timestamp. */
  function itemTimeline(itemId) {
    const said = proj().comments
      .filter((c) => c.item === itemId)
      .map((c) => ({ type: 'comment', at: c.at, comment: c }));
    const done = state.receipts
      .filter((r) => r.item === itemId && r.project === state.activeProjectId)
      .map((r) => ({ type: 'action', at: r.at, seq: Number(String(r.id).replace(/\D/g, '')) || 0, receipt: r }));
    /* Same-second actions are common (a comment and the mention it contains), so
       ties fall back to the recorded sequence. Without it a mention sorted above
       the comment that produced it. */
    return [...said, ...done].sort((a, b) => (new Date(a.at) - new Date(b.at)) || ((a.seq || 0) - (b.seq || 0)));
  }

  /** Where each receipt kind routes when opened from the notifications inbox. */
  const RECEIPT_ROUTE = {
    assignment: 'items', evidence: 'items', comment: 'items', referral: 'items',
    rewrite: 'versions', rescan: 'versions', version: 'versions',
    // A monitoring notification is about a specific change, so it opens the review
    // record rather than the surface and leaves the reader to find it.
    monitoring: 'watch?review=open', run: 'records', research: 'records',
    export: 'report', learning: 'trust', provider: 'records',
    project: 'project', organization: 'projects', auth: 'projects', role: 'team',
  };

  /** The notifications inbox is generated from real recorded actions (receipts)
      plus the seed inbox — so a decision or assignment the reviewer just made
      shows up here, rather than a static list that never reflects their work. */
  function notifications() {
    const TIER_MAP = { rewrite: 'informational', rescan: 'informational', cadence: 'informational', monitor: 'informational', 'monitor-review': 'informational', dossier: 'informational' };
    const fromReceipts = state.receipts.map((r) => ({
      id: r.id,
      kind: r.kind,
      tier: TIER_MAP[r.kind] || 'informational',
      /* Name the project the action actually belonged to. Reading the active
         project's title labelled every past receipt with whatever project the
         reader happened to be in, so a Borrowed Light decision appeared under
         The Quiet Coast. */
      project: r.project ? (PROJECT_DEFS.find((d) => d.id === r.project)?.title || r.project) : state.org.name,
      title: r.title,
      detail: r.detail,
      at: fmtStamp(r.at),
      atISO: r.at,
      atRaw: r.at,
      /* An item-scoped action opens that item, now that items are addressable.
         Routing to the generic list left the reader to find it again by hand. */
      route: r.item ? `item?id=${encodeURIComponent(r.item)}` : (RECEIPT_ROUTE[r.kind] || 'records'),
      /* Same structured destination as a templated event, so one resolver and one
         access check cover both sources. */
      destination: r.project
        ? { org: 'northlight', project: r.project, entityType: r.item ? 'clearance_item' : 'record', entityId: r.item || r.id }
        : null,
      generated: true,
    }));
    // Seed entries carry an absolute-ish ordering after freshly generated ones.
    const seed = NOTIFICATIONS.map((n) => ({ ...n, atRaw: n.atRaw || 0 }));
    return [...fromReceipts, ...seed];
  }

  /** Unread means "something happened that you have not seen". An action you
      just took yourself is not news, so receipt-derived entries are not unread —
      otherwise the badge counts your own clicks. */
  function unreadCount() {
    /* Counts urgent and action-required only. Informational entries are awareness,
       not a task, so including them made the badge a number nobody could act on. */
    return notifications().filter((n) => !n.generated && n.unread
      && !state.readNotifications.includes(n.id)
      && (n.tier === 'urgent' || n.tier === 'action')).length;
  }

  /** True when any unread actionable entry is urgent, so the badge can carry the
      danger tone rather than presenting a deadline breach as routine. */
  function unreadHasUrgent() {
    return notifications().some((n) => !n.generated && n.unread
      && !state.readNotifications.includes(n.id) && n.tier === 'urgent');
  }

  /** Human label for a source-watch cadence value. Single source for the words
      so the watch surface, the project rail, and the report never disagree. */
  const CADENCE_LABELS = { off: 'Off', manual: 'Manual only', daily: 'Daily', weekly: 'Weekly' };
  function cadenceLabel(value) {
    return CADENCE_LABELS[value] || (value ? String(value) : 'Weekly');
  }
  /** When the next automatic look happens, in the same vocabulary. Kept beside
      cadenceLabel so the two readings of one value cannot drift apart. */
  const NEXT_LOOK_LABELS = { off: 'Paused', manual: 'When you ask', daily: 'Tomorrow', weekly: 'Aug 26' };
  function nextLookLabel(value) {
    return NEXT_LOOK_LABELS[value] || NEXT_LOOK_LABELS.weekly;
  }

  /** Why each cadence exists. A cadence picker with no stated consequence asks the
      reviewer to choose between four words that all sound reasonable. */
  const CADENCE_RATIONALE = {
    off: 'Nothing is watched. A source can change without anyone hearing about it, so a released report can go stale silently.',
    manual: 'Nothing is checked until you ask. Suits a locked script that is not moving.',
    daily: 'Catches a change within a day. Worth the extra provider calls close to a delivery date.',
    weekly: 'Catches a change within a week. The usual balance while a script is still in development.',
  };
  function cadenceRationale(value) {
    return CADENCE_RATIONALE[value] || CADENCE_RATIONALE.weekly;
  }

  /** How much a source change matters. This is the judgement the reviewer needs
      first: a cancellation petition against a live registration is not the same
      event as a typo in a publisher's address, and showing both as 'changed' made
      the reviewer read the diff to find out which one they had.

      Materiality describes the change, not the clearance outcome — it never says
      the item is clear or unclear. */
  const MATERIALITY = {
    material: { label: 'Material', tone: 'is-warning', meaning: 'Touches the fact the decision relied on. Needs a person before the report is trusted again.' },
    contextual: { label: 'Worth knowing', tone: 'is-accent', meaning: 'Around the fact rather than on it. Read it, but the decision probably stands.' },
    immaterial: { label: 'Not material', tone: '', meaning: 'No bearing on the fact the decision relied on. Recorded so the trail is complete.' },
  };

  /** The monitored change the demo presents, with its classification and the
      reason for it stated rather than implied. */
  const WATCHED_CHANGE = {
    item: 'CC-101',
    source: 'USPTO registration record',
    verifiedOn: 'Aug 19',
    changedOn: 'Aug 26',
    before: 'VEGA — active registration, owner Vega Optics LLC.',
    after: 'VEGA — cancellation petition filed; registration remains active.',
    materiality: 'material',
    why: 'The decision relied on the registration being unchallenged. A petition does not cancel it, but it is the fact that was checked.',
  };

  /** One version chip, used wherever a version is shown as a coloured-stock
      pill (header context chip, versions table). Single source so the chip
      cannot drift between surfaces. */
  function versionChip(v, { srStock = false } = {}) {
    if (!v) return '<span class="mono muted">no version</span>';
    const stock = stockFor(v.label);
    return `<span class="version-chip" style="--stock:var(--rev-${stock})"><span class="stock-dot" aria-hidden="true"></span>${esc(v.label)}${srStock ? `<span class="sr-only"> — ${stock} pages</span>` : ''}</span>`;
  }

  /** Caption for the script stage. Reads the same version as the header chip:
      it used to fall back to a literal 'v1', so an unimported project captioned
      its pages "v1" while the chip beside it read "no version". */
  function stageVersionLabel(v, stock) {
    return v ? `${esc(v.label)} (${stock} pages)` : 'no saved version';
  }

  /** The version label a record binds to. Three call sites fell back to a
      literal 'v1' when a project had no saved version, so an unimported project
      printed a report headed "Script snapshot v1" and receipts citing a version
      that was never created. */
  function boundVersionLabel() {
    const v = currentVersion();
    return v ? v.label : 'no version';
  }

  /** Revision stock colour for a version label (v1 → white, v2 → blue, …). */
  function stockFor(label) {
    const index = Math.max(0, parseInt(String(label).replace(/\D/g, ''), 10) - 1);
    return REVISION_STOCK[Math.min(index, REVISION_STOCK.length - 1)];
  }

  function latestVersion() {
    return proj().versions.length ? proj().versions.at(-1) : null;
  }

  /** The version being read. Defaults to the latest; a reader may pin an earlier
      one to see the draft an older decision was made against. */
  function currentVersion() {
    const want = proj().viewingVersion;
    if (!want) return latestVersion();
    return proj().versions.find((v) => v.label === want) || latestVersion();
  }

  /** True when the reader has pinned a version that is no longer the newest. */
  function viewingSuperseded() {
    const latest = latestVersion();
    const viewed = currentVersion();
    return Boolean(latest && viewed && latest.label !== viewed.label);
  }

  /** The version a decision was bound to, or null when nothing was recorded. */
  function decisionVersion(itemId) {
    return proj().decisionBinding[itemId]?.version || null;
  }

  function currentStock() {
    const v = currentVersion();
    return v ? stockFor(v.label) : 'white';
  }

  /** Severity class + gutter glyph for a clearance flag. */
  function severityOf(item) {
    const status = itemStatus(item);
    if (status === 'Must fix') return { cls: 'is-blocked', glyph: '■' };
    if (item.severity === 'High') return { cls: 'is-high', glyph: '▲' };
    if (item.severity === 'Medium') return { cls: 'is-medium', glyph: '●' };
    return { cls: 'is-low', glyph: '○' };
  }

  /** Scenes that carry at least one clearance flag, with their items resolved.
      Reads the project's flags, so an unchecked project shows its script pages
      without annotations rather than another project's findings. */
  function scenesWithItems() {
    const own = flags();
    return SCENES.map((scene) => ({
      ...scene,
      items: scene.lines
        .filter((l) => l.flag)
        .map((l) => own.find((i) => i.id === l.flag))
        .filter(Boolean),
    }));
  }

  /* ═══════════════════════════════ ROUTER ═══════════════════════════════ */

  function routeFromHash() {
    // Empty hash is the landing page; anything else is returned verbatim so an
    // unknown surface can render a real not-found state instead of silently
    // redirecting to marketing (which hid typos and dead links).
    return location.hash.replace(/^#/, '').split('?')[0] || 'marketing';
  }

  function isKnownRoute(id) {
    return ROUTES.some((r) => r.id === id);
  }

  /** Query portion of the hash (#items?status=Must%20fix) for filter deep-links. */
  function routeQuery() {
    return Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || ''));
  }

  function routeMeta(id) { return ROUTES.find((r) => r.id === id); }

  /** Project stages derive completion from real data rather than a tracked list,
      so each project reports its own true position. */
  function stageComplete(id) {
    const p = proj();
    switch (id) {
      case 'new': return p.runComplete;
      case 'versions': return p.versions.length > 0;
      case 'watch': return p.monitoring.reviewed;
      case 'trust': return state.learning.stage !== 'candidate';
      case 'report': return Boolean(p.dossier);
      // Read the real flags rather than a visit list, so entering the demo
      // directly is as complete as walking the sign-in and setup surfaces.
      // `orgReady` was written by onboarding and never read until now.
      case 'auth': return state.auth;
      case 'onboarding': return state.orgReady;
      case 'workspace': case 'items': case 'item': case 'project': case 'records':
        return state.completed.includes(id);
      default: return state.completed.includes(id);
    }
  }

  /** Advisory only — returns the unmet prerequisite, never blocks navigation. */
  function prerequisiteFor(id) {
    const meta = routeMeta(id);
    if (!meta || !meta.needs) return null;
    if (stageComplete(meta.needs)) return null;
    return routeMeta(meta.needs);
  }

  /** Navigate to a hash target, which may carry a deep-link query
      (`items?status=attention`). The route id is validated on its own: checking
      the whole string meant every query-bearing CTA failed the lookup and
      silently did nothing — including the project overview's primary next-step
      button, whose target is always a filtered worklist. */
  function go(target) {
    const id = String(target).split('?')[0];
    if (!routeMeta(id)) return;
    if (location.hash === `#${target}`) { renderRoute(); return; }
    location.hash = target;
  }

  function toast(message, assertive = false) {
    const node = document.createElement('div');
    node.className = 'toast';
    node.textContent = message;
    el.toasts.append(node);
    (assertive ? el.assertive : el.polite).textContent = message;
    setTimeout(() => node.remove(), 4000);
    while (el.toasts.children.length > 3) el.toasts.firstElementChild.remove();
  }


  /* ═══════════════════════════ LAYOUT PRIMITIVES ═══════════════════════════ */

  function breadcrumb(trail) {
    const parts = trail.map((entry, index) => {
      const last = index === trail.length - 1;
      if (last) return `<span aria-current="page">${esc(entry.label)}</span>`;
      return `<a href="#${entry.route}">${esc(entry.label)}</a><span class="breadcrumb-sep" aria-hidden="true">/</span>`;
    });
    return `<nav class="breadcrumb" aria-label="Breadcrumb">${parts.join('')}</nav>`;
  }

  /** Standard page wrapper. Every surface renders through this — including the
      screenplay, which sets `srTitle` because its heading is already carried by
      the header context chip and the position readout beside it. Routing it
      through here rather than hand-writing the wrapper is what gives it the
      breadcrumb and, more importantly, the sample-data notice that every other
      project surface shows. */
  function page({ trail = null, eyebrow = '', title, srTitle = false, lede = '', actions = '', body = '', width = '', notice = '' }) {
    const heading = srTitle
      ? `<h1 id="route-heading" class="sr-only" tabindex="-1">${esc(title)}</h1>`
      : `<div class="page-head-row">
          <div>
            ${eyebrow ? `<span class="eyebrow">${esc(eyebrow)}</span>` : ''}
            <h1 id="route-heading" tabindex="-1">${esc(title)}</h1>
            ${lede ? `<p class="page-lede">${lede}</p>` : ''}
          </div>
          ${actions ? `<div class="page-head-actions">${actions}</div>` : ''}
        </div>`;
    return `<div class="page ${width}">
      <header class="page-head">
        ${trail ? breadcrumb(trail) : ''}
        ${heading}
      </header>
      ${notice}
      ${body}
    </div>`;
  }

  function section({ title = '', description = '', actions = '', body, id = '' }) {
    const head = title || actions ? `<div class="section-head"><div>${title ? `<h2>${esc(title)}</h2>` : ''}${description ? `<p>${description}</p>` : ''}</div>${actions ? `<div class="cluster">${actions}</div>` : ''}</div>` : '';
    // An optional anchor, so a section rail can address a group directly.
    return `<section class="section"${id ? ` id="sec-${esc(id)}" tabindex="-1"` : ''}>${head}${body}</section>`;
  }

  function card({ title = '', eyebrow = '', badge = '', body, accent = false, quiet = false, actions = '' }) {
    const head = title || badge || eyebrow
      ? `<div class="card-head"><div>${eyebrow ? `<span class="eyebrow">${esc(eyebrow)}</span>` : ''}${title ? `<h2>${esc(title)}</h2>` : ''}</div>${badge}</div>`
      : '';
    return `<article class="card ${accent ? 'card-accent' : ''} ${quiet ? 'card-quiet' : ''}">${head}${body}${actions ? `<div class="cluster gap-t-4 card-actions">${actions}</div>` : ''}</article>`;
  }

  function statGrid(stats, columns = 4) {
    return `<div class="grid grid-${columns}">${stats.map((s) => {
      const inner = `<span class="stat-label">${esc(s.label)}</span><span class="stat-value">${esc(String(s.value))}</span>${s.hint ? `<span class="stat-hint">${esc(s.hint)}</span>` : ''}`;
      if (s.route) {
        return `<a class="stat stat-link ${s.tone || ''}" href="#${s.route}" aria-label="${esc(s.label)}: ${esc(String(s.value))} — open the underlying records">${inner}<span class="stat-go" aria-hidden="true">→</span></a>`;
      }
      return `<div class="stat ${s.tone || ''}">${inner}</div>`;
    }).join('')}</div>`;
  }

  function dataTable({ columns, rows, caption = '' }) {
    return `<div class="table-wrap"><table class="data-table">${caption ? `<caption class="sr-only">${esc(caption)}</caption>` : ''}
      <thead><tr>${columns.map((c) => `<th scope="col" ${c.align === 'right' ? 'class="cell-actions"' : ''}>${esc(c.label)}</th>`).join('')}</tr></thead>
      <tbody>${rows.map((row) => `<tr>${row.map((cell, i) => `<td data-label="${esc(columns[i].label)}" ${columns[i].align === 'right' ? 'class="cell-actions"' : ''}>${cell}</td>`).join('')}</tr>`).join('')}</tbody>
    </table></div>`;
  }

  function emptyState({ icon = '◦', title, description = '', action = '' }) {
    return `<div class="empty-state"><span class="empty-icon" aria-hidden="true">${icon}</span><h3>${esc(title)}</h3>${description ? `<p>${description}</p>` : ''}${action}</div>`;
  }

  function banner({ tone = '', icon = 'ℹ', title = '', message = '', action = '' }) {
    return `<div class="banner ${tone}"><span class="banner-icon" aria-hidden="true">${icon}</span><div class="banner-body">${title ? `<strong>${esc(title)}</strong>` : ''}${message ? `<p>${message}</p>` : ''}</div>${action ? `<div class="cluster">${action}</div>` : ''}</div>`;
  }

  function tabsBar({ items, active, action, label }) {
    return `<div class="tabs" role="group" aria-label="${esc(label)}">${items.map((t) => `<button class="tab" type="button" data-action="${action}" data-value="${t.value}" aria-pressed="${t.value === active}">${esc(t.label)}${t.count !== undefined ? ` (${t.count})` : ''}</button>`).join('')}</div>`;
  }

  function badge(text, tone = '') {
    return `<span class="badge ${tone}">${esc(text)}</span>`;
  }

  function progress(percent) {
    return `<div class="progress" role="img" aria-label="${percent}% complete"><span style="width:${percent}%"></span></div>`;
  }

  function avatar(initials, label) {
    return `<span class="avatar" title="${esc(label)}" aria-label="${esc(label)}">${esc(initials)}</span>`;
  }

  /** Advisory notice shown when a surface's prerequisite is unmet. */
  function prerequisiteNotice(routeId) {
    const need = prerequisiteFor(routeId);
    if (!need) return '';
    /* Two different truths. Before onboarding, the organization surfaces show a
       seeded organization — that is sample data. Before a check, the project
       surfaces show nothing at all, so calling those "sample data" described a
       state that no longer exists now that flags belong to their project. */
    const message = need.id === 'new'
      ? `No check has run on this project, so there is nothing here yet. Complete <strong>${esc(need.label)}</strong> to populate it.`
      : `This surface shows sample data. Complete <strong>${esc(need.label)}</strong> to populate it with your own organization record.`;
    return `<div class="page-notice">${banner({
      tone: 'is-warning',
      icon: '◔',
      title: `${need.label} comes first`,
      message,
      action: `<button class="button button-secondary button-sm" type="button" data-action="go" data-route="${need.id}">Go to ${esc(need.label)}</button>`,
    })}</div>`;
  }

  function projectTrail(label) {
    return [{ label: state.org.name, route: 'projects' }, { label: projInfo().title, route: 'project' }, { label }];
  }

  function orgTrail(label) {
    return [{ label: state.org.name, route: 'projects' }, { label }];
  }

  /** The fixed-roles capability table, rendered from one place so onboarding,
      the team page, and the invite surface can never describe roles three
      different ways. Marks the role the demo is currently acting as. */
  function rolesTable({ markCurrent = false } = {}) {
    return dataTable({
      columns: [{ label: 'Role' }, { label: 'Permissions' }],
      rows: ROLE_MATRIX.map((r) => [
        `<strong>${esc(r.role)}</strong>${markCurrent && r.role === actorRole() ? ` ${badge('You', 'is-accent')}` : ''}`,
        `<span class="small muted">${esc(r.can)}</span>`,
      ]),
    });
  }

  /* ═══════════════════════════════ SHELL ═══════════════════════════════ */

  function renderShell() {
    const meta = routeMeta(currentRoute);
    // Unknown routes (not-found) render in the public shell.
    const isPublic = !meta || meta.layer === 'public';
    el.publicHeader.hidden = !isPublic;
    el.appHeader.hidden = isPublic;
    el.sidebar.hidden = isPublic;
    el.mobileNav.hidden = isPublic;
    document.body.classList.toggle('app-shell', !isPublic);

    if (isPublic) {
      el.sidebar.innerHTML = '';
      el.mobileNav.innerHTML = '';
      return;
    }
    renderContextChip(meta);
    renderSidebar(meta);
    renderMobileNav();
  }

  function renderContextChip(meta) {
    const v = currentVersion();
    const stock = currentStock();
    if (meta.layer === 'project') {
      el.contextChip.innerHTML = `<button class="project-switch" type="button" data-action="switch-project-dialog" aria-haspopup="dialog">
          <strong>${esc(projInfo().title)}</strong><span aria-hidden="true" class="muted">▾</span>
        </button>
        ${proj().versions.length > 1
          ? `<button class="version-switch" type="button" data-action="switch-version-dialog" aria-haspopup="dialog" aria-label="Version ${esc(boundVersionLabel())}. Choose a version to read.">
              ${versionChip(v, { srStock: true })}<span aria-hidden="true" class="muted">▾</span>
            </button>`
          : versionChip(v, { srStock: true })}`;
    } else {
      el.contextChip.innerHTML = `<strong>${esc(state.org.name)}</strong><span class="divider-dot" aria-hidden="true">·</span><span class="muted small">${state.members.length} members</span>`;
    }

    const bar = document.querySelector('#revision-bar');
    if (bar) bar.style.setProperty('--stock', `var(--rev-${stock})`);

    const pos = document.querySelector('#script-position');
    if (pos) {
      // Fall back to the script's first scene, never to a literal 1: a number
      // no scene owns makes SCENES.find miss and prints a page that disagrees
      // with the rail rendered beside it.
      const activeScene = SCENES.some((s) => s.number === proj().activeScene)
        ? proj().activeScene
        : SCENES[0].number;
      const activePage = SCENES.find((s) => s.number === activeScene)?.page ?? SCENES[0].page;
      pos.innerHTML = currentRoute === 'workspace' && proj().runComplete
        // "of" is a page total, so it reads the page count — it previously read
        // the scene count, which made "Page 2 of 43" a category error.
        ? `<span>Scene <strong>${activeScene}</strong></span><span>·</span><span>Page <strong>${activePage}</strong> of ${SCRIPT_META.pages}</span>`
        : '';
    }
  }

  function navLink(id) {
    const meta = routeMeta(id);
    const isCurrent = id === currentRoute;
    const done = state.completed.includes(id);
    const pending = Boolean(prerequisiteFor(id));
    let badgeHtml = '';
    if (id === 'notifications' && unreadCount()) badgeHtml = `<span class="nav-badge ${unreadHasUrgent() ? 'is-urgent' : ''}">${unreadCount()}</span>`;
    else if (id === 'items') {
      const open = flags().filter(isAttention).length;
      if (open > 0) badgeHtml = `<span class="nav-badge">${open}</span>`;
    } else if (done) badgeHtml = '<span class="nav-dot" aria-hidden="true"></span>';
    return `<a class="nav-link ${pending ? 'is-pending' : ''}" href="#${id}" data-label="${esc(meta.label)}" ${isCurrent ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${meta.icon}</span><span class="truncate">${esc(meta.label)}</span>${badgeHtml}</a>`;
  }

  function navMarkup(meta) {
    const groups = meta.layer === 'project'
      ? [...NAV.project, ...NAV.meta]
      : [...NAV.org, ...NAV.meta];
    const backLink = meta.layer === 'project'
      ? `<div class="nav-group"><a class="nav-link" href="#projects" data-label="All projects"><span class="nav-icon" aria-hidden="true">←</span><span class="truncate">All projects</span></a></div>`
      : '';
    return backLink + groups.map((group) => `<div class="nav-group"><p class="nav-label">${esc(group.label)}</p>${group.links.map(navLink).join('')}</div>`).join('');
  }

  function renderSidebar(meta) {
    const collapsed = state.sidebarCollapsed === true;
    el.sidebar.innerHTML = navMarkup(meta);
    el.sidebar.classList.toggle('is-collapsed', collapsed);
    document.body.classList.toggle('sidebar-collapsed', collapsed);
    const toggle = document.querySelector('.rail-toggle');
    if (toggle) {
      toggle.setAttribute('aria-expanded', String(!collapsed));
      toggle.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
      toggle.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    }
  }

  function renderMobileNav() {
    const meta = routeMeta(currentRoute);
    const primary = meta.layer === 'project'
      ? ['project', 'workspace', 'items', 'versions']
      : ['projects', 'notifications', 'team', 'settings'];
    el.mobileNav.innerHTML = primary.map((id) => {
      const m = routeMeta(id);
      /* The mobile bar carried no unread count at all, so a phone user could not
         see an overdue item without opening the inbox. Same source as the rail. */
      const badge = id === 'notifications' && unreadCount()
        ? `<span class="nav-badge ${unreadHasUrgent() ? 'is-urgent' : ''}">${unreadCount()}</span>`
        : '';
      return `<a href="#${id}" ${id === currentRoute ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${m.icon}</span><span class="truncate">${esc(m.label.split(' ')[0])}</span>${badge}</a>`;
    }).join('') + `<button type="button" data-action="open-drawer"><span class="nav-icon" aria-hidden="true">☰</span><span>More</span></button>`;
  }

  function openDrawer() {
    const meta = routeMeta(currentRoute);
    drawerTrigger = document.activeElement;
    el.drawer.dataset.open = 'true';
    document.querySelectorAll('.nav-toggle').forEach((b) => b.setAttribute('aria-expanded', 'true'));
    el.drawer.innerHTML = `<div class="drawer-panel" role="dialog" aria-modal="true" aria-label="Navigation menu">
      <div class="cluster-between gap-b-5">
        <strong>${esc(meta.layer === 'project' ? projInfo().title : state.org.name)}</strong>
        <button class="icon-button is-bare" type="button" data-action="close-drawer" aria-label="Close menu"><span aria-hidden="true">✕</span></button>
      </div>
      ${(() => {
        /* The header context chip is hidden below 901px, so on mobile this drawer
           is the only place that can say which draft is being read — and which
           version a decision would bind to. */
        if (meta.layer !== 'project' || !proj().versions.length) return '';
        const v = currentVersion();
        const many = proj().versions.length > 1;
        return `<div class="drawer-version gap-b-5">
          <span class="field-label">Reading</span>
          <div class="cluster-between gap-t-2">
            <span class="cluster">${versionChip(v)}${viewingSuperseded() ? badge('Superseded', 'is-warning') : badge('Current', 'is-success')}</span>
            ${many ? `<button class="button button-quiet button-sm" type="button" data-action="switch-version-dialog">Change</button>` : ''}
          </div>
        </div>`;
      })()}
      ${navMarkup(meta)}
    </div>`;
    document.body.classList.add('dialog-open');
    el.drawer.querySelector('button')?.focus();
  }

  function closeDrawer() {
    if (el.drawer.dataset.open !== 'true') return;
    el.drawer.dataset.open = 'false';
    el.drawer.innerHTML = '';
    document.querySelectorAll('.nav-toggle').forEach((b) => b.setAttribute('aria-expanded', 'false'));
    if (!el.dialogHost.firstElementChild) document.body.classList.remove('dialog-open');
    if (drawerTrigger && document.contains(drawerTrigger)) drawerTrigger.focus();
    drawerTrigger = null;
  }


  /* ═══════════════════════════ PUBLIC SURFACES ═══════════════════════════ */

  function renderMarketing() {
    return `<div class="lp">

      <section class="lp-hero" aria-labelledby="route-heading">
        <div class="lp-hero-copy">
          <p class="lp-eyebrow"><span class="lp-kicker-mark" aria-hidden="true"></span>Screenplay clearance · Open source · Self-hosted</p>
          <h1 id="route-heading" tabindex="-1" class="lp-h1">Clear the script before it becomes a production problem.</h1>
          <p class="lp-sub">ClearCut finds brands, people, places, music, and other clearance concerns; brings flagged passages together with retained source evidence; and keeps the team’s final call attached to the exact line. Open source and self-hosted — your scripts and evidence never leave your servers.</p>
          <div class="lp-ctas">
            <button class="button button-primary" type="button" data-action="start-demo">Explore the live demo</button>
            <a class="button button-secondary" href="https://github.com/clearcut" target="_blank" rel="noopener">View on GitHub</a>
          </div>
          <dl class="lp-hero-proof" aria-label="What the sample project contains">
            <div><dt>${DEMO_FACTS.categories}</dt><dd>clearance categories checked</dd></div>
            <div><dt>${DEMO_FACTS.flags}</dt><dd>flagged passages, each with a source</dd></div>
            <div><dt>${DEMO_FACTS.conflicts}</dt><dd>where the sources disagree</dd></div>
            <div><dt>${DEMO_FACTS.mustFix}</dt><dd>blocked until it is fixed</dd></div>
          </dl>
          <p class="lp-micro">Pre-loaded with the fictional feature <strong>Borrowed Light</strong>. No account required; nothing leaves your browser.</p>
        </div>

        <figure class="lp-artifact" aria-label="A flagged screenplay page connected to its source evidence">
          <div class="lp-sheet">
            <span class="lp-holes" aria-hidden="true"><i></i><i></i><i></i></span>
            <span class="lp-sheet-stock" aria-hidden="true"></span>
            <p class="lp-fade">FADE IN:</p>
            <p class="lp-slug">INT. VELEZ CAMERA SHOP — DUSK</p>
            <p class="lp-action">Dust hangs in the last bar of window light.</p>
            ${LP_EVIDENCE.map((f) => `<p class="lp-action lp-demo-line">
              <span class="lp-margin-mark" aria-hidden="true">${esc(f.mark)}</span>
              <span class="lp-demo-copy">${f.before}<button class="lp-flag lp-flag-live" type="button" data-action="lp-show-evidence" data-flag="${f.id}" aria-pressed="${f.id === LP_EVIDENCE[0].id}" aria-controls="lp-ev-${f.id}">${esc(f.term)}</button>${f.after}</span>
            </p>`).join('')}
            <p class="lp-pageno" aria-hidden="true">1.</p>
          </div>
          ${LP_EVIDENCE.map((f) => `<aside class="lp-note" id="lp-ev-${f.id}" data-flag="${f.id}" data-shown="${f.id === LP_EVIDENCE[0].id}" aria-label="Source evidence for ${esc(f.term)}">
            <div class="lp-note-top"><span class="lp-note-stamp">Sample · ${esc(f.authority)}</span><time datetime="2026-08-19">Retrieved Aug 19, 2026</time></div>
            <strong class="lp-note-title">${esc(f.source)}</strong>
            <p>${esc(f.claim)}</p>
            ${f.conflict ? `<p class="lp-note-conflict"><span aria-hidden="true">≠</span>${esc(f.conflict)}</p>` : ''}
            <div class="lp-note-foot"><span class="lp-note-verdict ${f.tone}">${esc(f.decision)}</span><span>${esc(f.id)} · snapshot retained</span></div>
          </aside>`).join('')}
          <figcaption class="lp-artifact-caption">Choose any highlighted term to see the source behind it. The gutter mark names the category; the blue edge is its version.</figcaption>
        </figure>
      </section>

      <section class="lp-assurance" aria-labelledby="assurance-heading">
        <div class="lp-assurance-heading">
          <p class="lp-section-eyebrow">One connected record</p>
          <h2 id="assurance-heading">Nothing important gets separated from the line that raised it.</h2>
        </div>
        <dl class="lp-assurance-list">
          <div><dt>01 · Passage</dt><dd>The exact words and scene context.</dd></div>
          <div><dt>02 · Evidence</dt><dd>Authority, retrieval date, and conflicts.</dd></div>
          <div><dt>03 · Decision</dt><dd>Who made the call, when, and why.</dd></div>
        </dl>
      </section>

      <section class="lp-section" id="the-problem" aria-labelledby="problem-heading">
        <header class="lp-section-head">
          <p class="lp-section-eyebrow">The problem</p>
          <h2 id="problem-heading" class="lp-h2">Small things sink films.</h2>
          <p class="lp-lede">Not the volcano stunt. A can on a desk. A song on a radio. A name in one scene. They surface after the shoot, when fixing them costs the most.</p>
        </header>
        <div class="lp-notes">
          ${[
            ['A familiar can on a desk', 'TRADEMARK', 'A recognizable package can become a clearance question long after the set is struck.', 'Flagged in scene context; registry source attached.'],
            ['A song playing on a radio', 'MUSIC', 'One cue can involve both the recording and the composition, with different owners and terms.', 'Publisher and recording-owner checks kept together.'],
            ['A character with a real person’s name', 'PRIVACY', 'A close real-world match needs a documented review before the portrayal travels any further.', 'Public-record checks and the team’s decision recorded.'],
          ].map(([what, tag, why, fix], i) => `
          <article class="lp-note-card">
            <span class="lp-card-index" aria-hidden="true">0${i + 1}</span>
            <header><strong>${esc(what)}</strong><span class="lp-note-tag">${esc(tag)}</span></header>
            <p>${esc(why)}</p>
            <p class="lp-note-fix"><span aria-hidden="true">✓</span>${esc(fix)}</p>
          </article>`).join('')}
        </div>
      </section>

      <section class="lp-section" id="how-it-works" aria-labelledby="workflow-heading">
        <header class="lp-section-head">
          <p class="lp-section-eyebrow">How it works</p>
          <h2 id="workflow-heading" class="lp-h2">Six steps from script to clearance report.</h2>
          <p class="lp-lede">The workflow stays simple for the team while preserving the details a later review needs.</p>
        </header>
        <ol class="lp-steps">
          ${[
            ['Import', 'Paste or upload Fountain, FDX, or PDF. ClearCut creates a versioned snapshot the workflow never overwrites.'],
            ['Detect', 'ClearCut reads scene by scene across ten clearance categories: brands, people, places, music, quotes, names, privacy, products, insignia, and artwork.'],
            ['Research', 'Parallel retrieves current sources with authority tiers, retrieval timestamps, and provenance. Conflicts are shown, not hidden.'],
            ['Decide', 'Your team verifies, rewrites, or refers. Every call is recorded with a name, the script version, and a reason.'],
            ['Monitor', 'Sources change. ClearCut watches them and asks you to review — it never changes a decision on its own.'],
            ['Report', 'A version-bound clearance report packages everything for lawyers, insurers, and distributors.'],
          ].map(([t, d], i) => `
          <li class="lp-step">
            <span class="lp-step-no" aria-hidden="true">0${i + 1}</span>
            <h3>${esc(t)}</h3>
            <p>${esc(d)}</p>
          </li>`).join('')}
        </ol>
      </section>

      <section class="lp-section lp-section-compact" id="how-its-built" aria-labelledby="built-heading">
        <header class="lp-section-head">
          <p class="lp-section-eyebrow">How it’s built</p>
          <h2 id="built-heading" class="lp-h2">Gemini reads the script. Parallel finds the sources. The record stays yours.</h2>
        </header>
        <p class="lp-build-note"><span aria-hidden="true">ℹ</span>This is the interface prototype, so the model and search calls shown here are simulated in the browser. Nothing you click leaves the page.</p>
        <aside class="lp-boundary" aria-label="ClearCut product boundary">
          <span class="lp-boundary-label">Product boundary</span>
          <div><strong>Humans remain accountable.</strong><p>ClearCut organizes evidence and records decisions. It does not give legal advice, clear a work on its own, or replace counsel or an insurer’s review.</p></div>
        </aside>
      </section>

      <section class="lp-end" aria-labelledby="closing-heading">
        <div class="lp-end-inner">
          <p class="lp-fadeout">FADE OUT.</p>
          <h2 id="closing-heading">Tape the pages before the shoot, not after.</h2>
          <p>Walk through a complete fictional production — or deploy your own instance.</p>
          <div class="lp-ctas lp-end-ctas">
            <button class="button button-primary" type="button" data-action="start-demo">Explore the live demo</button>
            <a class="button button-secondary" href="https://github.com/clearcut" target="_blank" rel="noopener">View on GitHub</a>
          </div>
          <span class="lp-end-note">MIT License · No account required for the demo · Sample data only</span>
        </div>
      </section>

      <footer class="lp-footer">
        <div class="lp-footer-brand"><strong>ClearCut</strong><span>Open-source screenplay clearance evidence workspace.</span></div>
        <nav class="lp-footer-nav" aria-label="Footer navigation"><a href="#features">Features</a><a href="#docs">Docs</a><a href="https://github.com/clearcut" target="_blank" rel="noopener">GitHub</a><a href="#sitemap">Product tour</a></nav>
        <p class="lp-footer-legal">© 2026 ClearCut · MIT License · Nothing here is legal advice; clearance decisions belong to qualified humans.</p>
      </footer>
    </div>`;
  }

  /* === MARKETING VARIANTS === */

  function renderMarketingA() {
    return `<div class="lp"><section class="lp-hero" aria-labelledby="route-heading"><div class="lp-hero-copy">
      <p class="lp-eyebrow"><span class="lp-kicker-mark" aria-hidden="true"></span>Open source \u00b7 Self-hosted \u00b7 MIT License</p>
      <h1 id="route-heading" tabindex="-1" class="lp-h1">Screenplay clearance evidence, organized.</h1>
      <p class="lp-sub">ClearCut finds clearance concerns in scripts, retrieves source evidence with full provenance, and keeps the team\u2019s decisions attached to the exact line. Self-host it on your own infrastructure \u2014 your data never leaves your servers.</p>
      <div class="lp-ctas"><button class="button button-primary" type="button" data-action="start-demo">Explore the live demo</button><a class="button button-secondary" href="https://github.com/clearcut" target="_blank" rel="noopener">View on GitHub</a></div>
      <dl class="lp-hero-proof" aria-label="What ClearCut checks"><div><dt>${DEMO_FACTS.categories}</dt><dd>clearance categories</dd></div><div><dt>${DEMO_FACTS.flags}</dt><dd>flagged passages with sources</dd></div><div><dt>5</dt><dd>fixed roles for team governance</dd></div><div><dt>\u221e</dt><dd>your data, your servers</dd></div></dl>
    </div>
    <figure class="lp-artifact" aria-label="A flagged screenplay page">${renderLpArtifact('a')}</figure>
    </section>
    <section class="lp-end" aria-labelledby="closing-heading-a"><div class="lp-end-inner"><p class="lp-fadeout">FADE OUT.</p><h2 id="closing-heading-a">Clear the script before it becomes a production problem.</h2><div class="lp-ctas lp-end-ctas"><button class="button button-primary" type="button" data-action="start-demo">Explore the live demo</button><a class="button button-secondary" href="https://github.com/clearcut" target="_blank" rel="noopener">View on GitHub</a></div><span class="lp-end-note">MIT License \u00b7 No account required for the demo</span></div></section>
    <footer class="lp-footer"><div class="lp-footer-brand"><strong>ClearCut</strong><span>Open-source screenplay clearance evidence workspace.</span></div><nav class="lp-footer-nav" aria-label="Footer navigation"><a href="#sitemap">Product tour</a><a href="https://github.com/clearcut" target="_blank" rel="noopener">GitHub</a></nav><p class="lp-footer-legal">\u00a9 2026 ClearCut \u00b7 MIT License \u00b7 Nothing here is legal advice; clearance decisions belong to qualified humans.</p></footer></div>`;
  }

  function renderLpArtifact(prefix) {
    return `<div class="lp-sheet"><span class="lp-holes" aria-hidden="true"><i></i><i></i><i></i></span><span class="lp-sheet-stock" aria-hidden="true"></span><p class="lp-fade">FADE IN:</p><p class="lp-slug">INT. VELEZ CAMERA SHOP \u2014 DUSK</p><p class="lp-action">Dust hangs in the last bar of window light.</p>${LP_EVIDENCE.map((f) => `<p class="lp-action lp-demo-line"><span class="lp-margin-mark" aria-hidden="true">${esc(f.mark)}</span><span class="lp-demo-copy">${f.before}<button class="lp-flag lp-flag-live" type="button" data-action="lp-show-evidence" data-flag="${f.id}" aria-pressed="${f.id === LP_EVIDENCE[0].id}" aria-controls="lp-ev-${prefix}-${f.id}">${esc(f.term)}</button>${f.after}</span></p>`).join('')}<p class="lp-pageno" aria-hidden="true">1.</p></div>${LP_EVIDENCE.map((f) => `<aside class="lp-note" id="lp-ev-${prefix}-${f.id}" data-flag="${f.id}" data-shown="${f.id === LP_EVIDENCE[0].id}" aria-label="Source evidence for ${esc(f.term)}"><div class="lp-note-top"><span class="lp-note-stamp">Sample \u00b7 ${esc(f.authority)}</span><time datetime="2026-08-19">Retrieved Aug 19, 2026</time></div><strong class="lp-note-title">${esc(f.source)}</strong><p>${esc(f.claim)}</p>${f.conflict ? `<p class="lp-note-conflict"><span aria-hidden="true">\u2260</span>${esc(f.conflict)}</p>` : ''}<div class="lp-note-foot"><span class="lp-note-verdict ${f.tone}">${esc(f.decision)}</span><span>${esc(f.id)} \u00b7 snapshot retained</span></div></aside>`).join('')}<figcaption class="lp-artifact-caption">Choose any highlighted term to see the source behind it.</figcaption>`;
  }

  function renderMarketingB() {
    return `<div class="lp"><section class="lp-hero" aria-labelledby="route-heading"><div class="lp-hero-copy">
      <p class="lp-eyebrow"><span class="lp-kicker-mark" aria-hidden="true"></span>MIT License \u00b7 Self-hosted</p>
      <h1 id="route-heading" tabindex="-1" class="lp-h1">ClearCut</h1>
      <p class="lp-sub">Open-source screenplay pre-clearance workspace. Parse scripts, detect clearance concerns across ten categories, retrieve source-backed evidence via Parallel, coordinate human review with fixed roles, and export a reproducible evidence dossier.</p>
      <div class="lp-ctas"><a class="button button-primary" href="https://github.com/clearcut" target="_blank" rel="noopener">View on GitHub</a><button class="button button-secondary" type="button" data-action="start-demo">Live demo</button></div>
    </div></section>
    <section class="lp-section" aria-labelledby="quickstart-heading-b"><header class="lp-section-head"><p class="lp-section-eyebrow">Quick start</p><h2 id="quickstart-heading-b" class="lp-h2">Running in three commands.</h2></header><div class="lp-code-block"><pre class="mono"><code>git clone https://github.com/clearcut/clearcut.git
cd clearcut
docker compose up</code></pre></div><p class="lp-lede gap-t-4">Then open <span class="mono">http://localhost:3000</span>. The first user creates the organization and becomes Owner.</p></section>
    <section class="lp-section lp-section-compact" aria-labelledby="boundary-heading-b"><header class="lp-section-head"><h2 id="boundary-heading-b" class="lp-h2">Not legal advice.</h2><p class="lp-lede">ClearCut organizes evidence and records decisions. It does not clear a work, replace counsel, or certify legal safety. Clearance decisions belong to qualified humans.</p></header></section>
    <section class="lp-end" aria-labelledby="closing-heading-b"><div class="lp-end-inner"><h2 id="closing-heading-b">Get started.</h2><div class="lp-ctas lp-end-ctas"><a class="button button-primary" href="https://github.com/clearcut" target="_blank" rel="noopener">View on GitHub</a><button class="button button-secondary" type="button" data-action="start-demo">Live demo</button></div><span class="lp-end-note">MIT License \u00b7 Contributions welcome</span></div></section>
    <footer class="lp-footer"><div class="lp-footer-brand"><strong>ClearCut</strong><span>Open-source screenplay clearance evidence workspace.</span></div><nav class="lp-footer-nav" aria-label="Footer navigation"><a href="https://github.com/clearcut" target="_blank" rel="noopener">GitHub</a><a href="#sitemap">Product tour</a></nav><p class="lp-footer-legal">\u00a9 2026 ClearCut \u00b7 MIT License \u00b7 Not legal advice.</p></footer></div>`;
  }

  function renderMarketingC() {
    return `<div class="lp"><section class="lp-hero" aria-labelledby="route-heading"><div class="lp-hero-copy">
      <p class="lp-eyebrow"><span class="lp-kicker-mark" aria-hidden="true"></span>Screenplay clearance \u00b7 Open source \u00b7 Self-hosted</p>
      <h1 id="route-heading" tabindex="-1" class="lp-h1">Clear the script before it becomes a production problem.</h1>
      <p class="lp-sub">ClearCut finds brands, people, places, music, and other clearance concerns; brings flagged passages together with retained source evidence; and keeps the team\u2019s final call attached to the exact line. Open source and self-hosted \u2014 your scripts and evidence never leave your servers.</p>
      <div class="lp-ctas"><button class="button button-primary" type="button" data-action="start-demo">Explore the live demo</button><a class="button button-secondary" href="https://github.com/clearcut" target="_blank" rel="noopener">View on GitHub</a></div>
      <dl class="lp-hero-proof" aria-label="What ClearCut checks"><div><dt>${DEMO_FACTS.categories}</dt><dd>clearance categories checked</dd></div><div><dt>${DEMO_FACTS.flags}</dt><dd>flagged passages, each with a source</dd></div><div><dt>${DEMO_FACTS.conflicts}</dt><dd>where the sources disagree</dd></div><div><dt>${DEMO_FACTS.mustFix}</dt><dd>blocked until it is fixed</dd></div></dl>
      <p class="lp-micro">Pre-loaded with the fictional feature <strong>Borrowed Light</strong>. No account required; nothing leaves your browser.</p>
    </div>
    <figure class="lp-artifact" aria-label="A flagged screenplay page">${renderLpArtifact('c')}</figure>
    </section>
    <section class="lp-end" aria-labelledby="closing-heading-c"><div class="lp-end-inner"><p class="lp-fadeout">FADE OUT.</p><h2 id="closing-heading-c">Tape the pages before the shoot, not after.</h2><p>Walk through a complete fictional production \u2014 or deploy your own instance.</p><div class="lp-ctas lp-end-ctas"><button class="button button-primary" type="button" data-action="start-demo">Explore the live demo</button><a class="button button-secondary" href="https://github.com/clearcut" target="_blank" rel="noopener">View on GitHub</a></div><span class="lp-end-note">MIT License \u00b7 No account required for the demo \u00b7 Sample data only</span></div></section>
    <footer class="lp-footer"><div class="lp-footer-brand"><strong>ClearCut</strong><span>Open-source screenplay clearance evidence workspace.</span></div><nav class="lp-footer-nav" aria-label="Footer navigation"><a href="#sitemap">Product tour</a><a href="https://github.com/clearcut" target="_blank" rel="noopener">GitHub</a></nav><p class="lp-footer-legal">\u00a9 2026 ClearCut \u00b7 MIT License \u00b7 Nothing here is legal advice; clearance decisions belong to qualified humans.</p></footer></div>`;
  }

  /* === FEATURES PAGE === */

  function renderFeatures() {
    const bands = [
      {
        id: 'import', tag: 'Script ingestion', reversed: false,
        title: 'Every draft becomes a permanent record.',
        lead: 'Import Fountain, Final Draft, PDF, or pasted text. ClearCut parses the screenplay into stable elements and saves an immutable version the workflow never overwrites.',
        points: [
          ['Four parsers', 'Fountain, FDX, PDF, and paste. Scanned pages use Gemini with per-page confidence.'],
          ['Stable spans', 'Scenes, characters, and dialogue get identities that survive rewrites.'],
          ['Coloured stock', 'White pages, then blue, pink, yellow — the film convention for revisions.'],
        ],
        visual: `<div class="fv-sheet">
          <span class="fv-stock" aria-hidden="true"></span>
          <span class="fv-holes" aria-hidden="true"><i></i><i></i><i></i></span>
          <p class="fv-page-no">2.</p>
          <p class="fv-slug">INT. VELEZ CAMERA SHOP — DUSK</p>
          <p class="fv-action">Dust hangs in the last bar of window light.</p>
          <p class="fv-action"><span class="fv-mark">▲ MARK</span>She lifts the <span class="fv-flag is-high">Vega Camera</span> from a glass case.</p>
          <p class="fv-char">MINA</p>
          <p class="fv-dial">We only borrow the light.</p>
          <div class="fv-caption"><span class="fv-chip">v1 · white pages</span><span class="fv-chip mono">9c7a23d08e41</span></div>
        </div>`,
      },
      {
        id: 'research', tag: 'Detection & evidence', reversed: true,
        title: 'Live sources, full provenance, conflicts intact.',
        lead: 'Gemini detects items across ten clearance categories. Parallel retrieves current sources with authority tiers and retrieval timestamps. Disagreement is shown, never smoothed over.',
        points: [
          ['Ten categories', 'Brands, people, places, music, quotes, names, privacy, products, insignia, artwork.'],
          ['Complete provenance', 'URL, retrieval time, excerpt, publisher class, stance, query identity, snapshot ID.'],
          ['Zero evidence is unresolved', 'A failed search creates a review item — never a clear result.'],
        ],
        visual: `<div class="fv-stack">
          <div class="fv-evidence">
            <div class="fv-ev-top"><span class="fv-badge is-primary">Primary registry</span><span class="fv-time mono">Aug 19 · 15:42</span></div>
            <strong class="fv-ev-title">USPTO TSDR record 8850142</strong>
            <p class="fv-ev-body">VEGA registered in class 009 for professional motion-picture camera equipment; status live.</p>
            <div class="fv-ev-foot"><span class="fv-stance supports">Supports</span><span class="mono">SRC-001</span></div>
          </div>
          <div class="fv-evidence is-conflict">
            <div class="fv-ev-top"><span class="fv-badge">Secondary</span><span class="fv-time mono">Aug 19 · 15:43</span></div>
            <strong class="fv-ev-title">Trade article, Camera Quarterly</strong>
            <p class="fv-ev-body">Describes the VEGA mark as abandoned after the 2021 product line was retired.</p>
            <div class="fv-ev-foot"><span class="fv-stance disagrees">Disagrees</span><span class="mono">SRC-003</span></div>
          </div>
          <div class="fv-conflict-note"><span aria-hidden="true">⚠</span>Conflict retained, not resolved automatically</div>
        </div>`,
      },
      {
        id: 'team', tag: 'Workflow & collaboration', reversed: false,
        title: 'Every call has a name, a version, and a reason.',
        lead: 'Five fixed roles with backend-enforced authorization. Assignments, due dates, threaded comments, and governed decisions that commit with their audit event in one transaction.',
        points: [
          ['Fixed roles', 'Owner, Admin, Editor, Reviewer, Viewer. Not UI-only gating.'],
          ['Governed decisions', 'Verify, rule out, refer, rewrite — each with rationale and audit.'],
          ['Threaded discussion', 'Replies, edit history, @mentions, and system action entries in one timeline.'],
        ],
        visual: `<div class="fv-stack">
          <div class="fv-row">
            <span class="fv-dot is-warning" aria-hidden="true"></span>
            <div class="fv-row-main"><strong>Vega Camera</strong><span class="fv-row-meta"><span class="mono">CC-101</span><span>Scene 3</span><span class="fv-chip">4 sources · conflict</span></span></div>
            <div class="fv-row-aside"><span class="fv-avatar">MV</span><span class="fv-badge is-warning">Needs your call</span></div>
          </div>
          <div class="fv-comment">
            <div class="fv-comment-head"><span class="fv-avatar sm">MV</span><strong>Mara Voss</strong><span class="fv-time">Aug 19</span></div>
            <p>Primary registry says active, but the trade article says abandoned. Verifying on the registry.</p>
          </div>
          <div class="fv-comment is-reply">
            <div class="fv-comment-head"><span class="fv-avatar sm">EC</span><strong>Eli Chen</strong><span class="fv-time">Aug 19</span></div>
            <p>Check for a later filing first — that article is from 2021.</p>
          </div>
          <div class="fv-action-entry"><span aria-hidden="true">⟳</span>Mara Voss verified this source · Aug 20</div>
        </div>`,
      },
      {
        id: 'watch', tag: 'Revisions & monitoring', reversed: true,
        title: 'A rewrite never edits the old copy.',
        lead: 'An Editor proposes replacement text. A Reviewer approves. Approval creates an immutable new version and re-checks only the affected items — everything you settled stays settled.',
        points: [
          ['Maker/checker split', 'The proposer cannot approve their own rewrite.'],
          ['Selective re-scan', 'Only affected flags re-run. Untouched evidence carries forward.'],
          ['Source monitoring', 'ClearCut shows what changed and asks — it never decides for you.'],
        ],
        visual: `<div class="fv-diff">
          <div class="fv-diff-side">
            <span class="fv-diff-label">v1 · original <span class="fv-badge sm">Locked</span></span>
            <p class="fv-diff-text"><del>Her relapse began after she left the East Mercer clinic, room 214.</del></p>
            <span class="fv-diff-note">Blocked by the privacy rule.</span>
          </div>
          <div class="fv-diff-side is-new">
            <span class="fv-diff-label">v2 · approved <span class="fv-badge sm is-success">Current</span></span>
            <p class="fv-diff-text"><ins>She struggled again after she left treatment.</ins></p>
            <span class="fv-diff-note">Approved by Jamie Park with a recorded rationale.</span>
          </div>
          <div class="fv-diff-stats"><span><strong>1</strong> passage changed</span><span><strong>2</strong> flags re-checked</span><span><strong>8</strong> sources reused</span></div>
        </div>`,
      },
      {
        id: 'report', tag: 'Reports & export', reversed: false,
        title: 'A package your lawyer can actually use.',
        lead: 'Generation freezes evidence, decisions, and bindings into an immutable snapshot with a content hash. Release is a separate human attestation. The released document never silently changes.',
        points: [
          ['Frozen snapshots', 'Post-release changes cannot alter a released report.'],
          ['Five exhibits plus appendix', 'Versions, flags, sources, decisions, trust — open items disclosed, not hidden.'],
          ['Reproducible binding', 'Exact script, policy, prompt, rubric, and judge versions recorded.'],
        ],
        visual: `<div class="fv-report">
          <div class="fv-report-head"><span class="fv-report-eyebrow">Screenplay Clearance Report</span><strong>Borrowed Light</strong><span class="fv-badge is-success sm">Released</span></div>
          <div class="fv-exhibit-tabs"><span class="is-active">A · Versions</span><span>B · Flags</span><span>C · Sources</span><span>D · Decisions</span><span>E · Trust</span></div>
          <table class="fv-table"><thead><tr><th>Version</th><th>Source</th><th>Snapshot</th></tr></thead><tbody>
            <tr><td>v2</td><td>Approved rewrite</td><td class="mono">b2fd7a61c918</td></tr>
            <tr><td>v1</td><td>FDX import</td><td class="mono">9c7a23d08e41</td></tr>
          </tbody></table>
          <div class="fv-binding"><span class="fv-binding-label">Binding</span><span class="mono">script v2 · policy 3.2 · rubric 2.4 · graded 90/100</span></div>
        </div>`,
      },
      {
        id: 'security', tag: 'Security & governance', reversed: true,
        title: 'Protected rules only a person can change.',
        lead: 'Permissions, approval policy, category definitions, source-authority tiers, and legal-boundary language are human-only and Owner-governed. No automated process touches them.',
        points: [
          ['Same-transaction audit', 'Every governed action commits with its immutable AuditEvent.'],
          ['Tenant isolation', 'Organization and project scope enforced in repositories, not just routes.'],
          ['Hardened uploads', 'Magic-byte validation, FDX entity blocking, isolated PDF workers.'],
        ],
        visual: `<div class="fv-stack">
          <table class="fv-table"><thead><tr><th>Role</th><th>Governed actions</th><th>Protected</th></tr></thead><tbody>
            <tr><td><strong>Owner</strong></td><td><span class="fv-tick">✓</span></td><td><span class="fv-tick">✓</span></td></tr>
            <tr><td><strong>Admin</strong></td><td><span class="fv-tick">✓</span></td><td><span class="fv-lock">🔒</span></td></tr>
            <tr><td><strong>Reviewer</strong></td><td><span class="fv-tick">✓</span></td><td><span class="fv-lock">🔒</span></td></tr>
            <tr><td><strong>Editor</strong></td><td><span class="fv-lock">🔒</span></td><td><span class="fv-lock">🔒</span></td></tr>
            <tr><td><strong>Viewer</strong></td><td><span class="fv-lock">🔒</span></td><td><span class="fv-lock">🔒</span></td></tr>
          </tbody></table>
          <div class="fv-gate-note"><span aria-hidden="true">⚖</span>A suggestion to loosen the privacy rule was blocked automatically.</div>
        </div>`,
      },
      {
        id: 'trust', tag: 'AI trust & evaluation', reversed: false,
        title: 'The system grades its own work — and shows you.',
        lead: 'A separate judge model scores ten dimensions. Deterministic gates run first and a high score never overrides a blocker. Improvements go through regression, shadow, and canary with automatic rollback.',
        points: [
          ['Ten judged dimensions', 'Recall, grounding, authority, conflict, uncertainty, rewrites, re-scan, legal boundary, efficiency.'],
          ['Deterministic gates first', 'Blockers cannot be overridden by a good score.'],
          ['Bounded learning', 'Only query phrasing, examples, prompts, and preferences. Never permissions or policy.'],
        ],
        visual: `<div class="fv-stack">
          <div class="fv-score-row">
            <div class="fv-ring" style="--pct:90"><span>90</span></div>
            <div><strong>Strong, no warnings</strong><p class="fv-score-note">Mean of 10 graded dimensions. Weakest: source freshness at 84.</p></div>
          </div>
          <div class="fv-gates">
            <div class="fv-gate"><span>Claim grounding</span><span class="fv-badge is-success sm">Pass</span></div>
            <div class="fv-gate"><span>Citation completeness</span><span class="fv-badge is-success sm">Pass</span></div>
            <div class="fv-gate"><span>Legal boundary</span><span class="fv-badge is-success sm">Pass</span></div>
            <div class="fv-gate"><span>Source freshness</span><span class="fv-badge is-warning sm">Warn</span></div>
          </div>
          <div class="fv-learn"><span class="fv-badge is-accent sm">Candidate</span>Better music searches · 148/148 past cases pass · +6.1% retrieval</div>
        </div>`,
      },
    ];

    return `<div class="lp">
      <section class="feat-hero">
        <div class="feat-hero-inner">
          <p class="lp-eyebrow"><span class="lp-kicker-mark" aria-hidden="true"></span>Everything ClearCut does</p>
          <h1 id="route-heading" tabindex="-1" class="lp-h1">Built for evidence, not opinions.</h1>
          <p class="lp-sub">Seven capability areas, from script import through a reproducible clearance report. Every one designed so a human stays accountable and the record survives scrutiny.</p>
          <nav class="feat-jump" aria-label="Jump to a capability area">
            ${bands.map((b) => `<a href="#feat-${b.id}">${esc(b.tag)}</a>`).join('')}
          </nav>
        </div>
      </section>

      ${bands.map((b) => `<section class="feat-band ${b.reversed ? 'is-reversed' : ''}" id="feat-${b.id}" aria-labelledby="feat-h-${b.id}">
        <div class="feat-band-copy">
          <span class="lp-section-eyebrow">${esc(b.tag)}</span>
          <h2 id="feat-h-${b.id}" class="lp-h2">${esc(b.title)}</h2>
          <p class="lp-lede">${esc(b.lead)}</p>
          <ul class="feat-points">
            ${b.points.map(([t, d]) => `<li><strong>${esc(t)}</strong><span>${esc(d)}</span></li>`).join('')}
          </ul>
        </div>
        <figure class="feat-band-visual" aria-hidden="true">${b.visual}</figure>
      </section>`).join('')}

      <section class="lp-section lp-section-compact">
        <aside class="lp-boundary" aria-label="ClearCut product boundary">
          <span class="lp-boundary-label">Not legal advice</span>
          <div><p>ClearCut organizes evidence and records decisions. It does not give legal advice, clear a work on its own, or replace counsel or an insurer’s review.</p></div>
        </aside>
      </section>

      <section class="lp-end" aria-labelledby="feat-close">
        <div class="lp-end-inner">
          <p class="lp-fadeout">FADE OUT.</p>
          <h2 id="feat-close">See it working on a real screenplay.</h2>
          <p>Walk through a complete fictional production — or deploy your own instance.</p>
          <div class="lp-ctas lp-end-ctas">
            <button class="button button-primary" type="button" data-action="start-demo">Explore the live demo</button>
            <a class="button button-secondary" href="#docs">Read the docs</a>
          </div>
          <span class="lp-end-note">MIT License · No account required for the demo</span>
        </div>
      </section>

      <footer class="lp-footer">
        <div class="lp-footer-brand"><strong>ClearCut</strong><span>Open-source screenplay clearance evidence workspace.</span></div>
        <nav class="lp-footer-nav" aria-label="Footer navigation"><a href="#marketing">Home</a><a href="#docs">Docs</a><a href="https://github.com/clearcut" target="_blank" rel="noopener">GitHub</a></nav>
        <p class="lp-footer-legal">© 2026 ClearCut · MIT License · Nothing here is legal advice; clearance decisions belong to qualified humans.</p>
      </footer>
    </div>`;
  }

  /* === DOCS PAGE === */

  function renderDocs() {
    const sections = [
      { id: 'quickstart', title: 'Quick start', body: `<div class="lp-code-block"><pre class="mono"><code>git clone https://github.com/clearcut/clearcut.git\ncd clearcut\ndocker compose up</code></pre></div><p class="gap-t-4">Then open <span class="mono">http://localhost:3000</span>. The first user creates the organization and becomes Owner.</p><p class="small muted gap-t-2">This starts <span class="mono">clearcut-api</span> (FastAPI) and <span class="mono">clearcut-web</span> (TanStack Start) with a local PostgreSQL database. The marketing site is hosted separately by the ClearCut maintainers.</p>` },
      { id: 'requirements', title: 'Requirements', body: `<div class="lp-notes">${[['Docker', 'REQUIRED', 'Docker Compose v2+ for local development and single-server deployments.'],['PostgreSQL 15+', 'REQUIRED', 'Stores users, organizations, scripts, evidence, decisions, and audit records. Included in docker compose.'],['Gemini API key', 'REQUIRED', 'For detection, search planning, evidence synthesis, and evaluation. Get one at ai.google.dev.'],['Parallel API key', 'REQUIRED', 'For live source retrieval with provenance. Get one at parallel.com.'],['Cloud Storage', 'OPTIONAL', 'For script uploads and report exports. Local filesystem works for development.'],['Firebase', 'OPTIONAL', 'For managed authentication. Local PostgreSQL auth is the default.'],['Email provider', 'OPTIONAL', 'SMTP, Resend, or ZeptoMail for invitations and notifications. In-app delivery works without email.']].map(([what, tag, why]) => '<article class="lp-note-card"><header><strong>' + esc(what) + '</strong><span class="lp-note-tag">' + esc(tag) + '</span></header><p>' + esc(why) + '</p></article>').join('')}</div>` },
      { id: 'configuration', title: 'Configuration', body: `<p>Set environment variables for <span class="mono">clearcut-api</span>. Use a local <span class="mono">.env</span> file for development; never commit API keys to source control.</p><div class="lp-code-block gap-t-4"><pre class="mono"><code># Required\nDATABASE_URL=postgresql+asyncpg://clearcut:change-me@postgres:5432/clearcut\nGEMINI_API_KEY=your-gemini-key\nPARALLEL_API_KEY=your-parallel-key\n\n# Provider selections (defaults shown)\nAUTH_PROVIDER=local\nEMAIL_PROVIDER=none\nOBJECT_STORAGE_PROVIDER=local</code></pre></div>${dataTable({ caption: 'Provider configuration', columns: [{ label: 'Variable' }, { label: 'Values' }, { label: 'Default' }], rows: [['<span class="mono small">AUTH_PROVIDER</span>', '<span class="mono small">local</span> or <span class="mono small">firebase</span>', 'local \u2014 PostgreSQL credentials'],['<span class="mono small">EMAIL_PROVIDER</span>', '<span class="mono small">none</span>, <span class="mono small">smtp</span>, <span class="mono small">resend</span>, <span class="mono small">zeptomail</span>', 'none \u2014 in-app only'],['<span class="mono small">OBJECT_STORAGE_PROVIDER</span>', '<span class="mono small">local</span> or <span class="mono small">gcs</span>', 'local \u2014 filesystem']]})}` },
      { id: 'architecture', title: 'Architecture', body: `<p>Two self-hosted services and their dependencies:</p><div class="lp-code-block gap-t-4"><pre class="mono"><code>clearcut-api   \u2192 FastAPI modular monolith + Google ADK\nclearcut-web   \u2192 TanStack Start authenticated workspace\n\nPostgreSQL     \u2192 evidence, decisions, audit trail\nObject storage \u2192 scripts, snapshots, exports\nGemini + ADK   \u2192 detection, evaluation, judge\nParallel       \u2192 live source retrieval with provenance</code></pre></div><p class="small muted gap-t-4">The API is one modular monolith with bounded modules \u2014 not backend microservices.</p>` },
      { id: 'roles', title: 'Roles', body: `<p>Five fixed roles, backend-enforced.</p>${dataTable({ caption: 'Role capabilities', columns: [{ label: 'Role' }, { label: 'Capabilities' }], rows: [['<strong>Owner</strong>', 'Organization lifecycle, protected settings, all governed review and report actions'],['<strong>Admin</strong>', 'Members, projects, providers, operational settings, governed review and report actions'],['<strong>Editor</strong>', 'Script import, research, assignments, comments, rewrite proposals'],['<strong>Reviewer</strong>', 'Evidence decisions, referrals, dispositions, rewrite approval, report generation and release'],['<strong>Viewer</strong>', 'Read-only access to authorized projects and released reports']]})}` },
      { id: 'formats', title: 'Script formats', body: `${dataTable({ caption: 'Accepted import formats', columns: [{ label: 'Format' }, { label: 'Parser' }, { label: 'Notes' }], rows: [['<span class="mono">Fountain</span>', 'Deterministic', 'Plain-text screenplay syntax'],['<span class="mono">FDX</span>', 'Deterministic', 'Final Draft XML. DTDs and entities disabled.'],['<span class="mono">PDF</span>', 'Gemini-assisted', 'Scanned pages use Gemini with per-page confidence.'],['<span class="mono">Paste</span>', 'Deterministic', 'Paste screenplay text directly. Max 500K characters.']]})}` },
      { id: 'deploy-gcp', title: 'Deploy to Google Cloud', body: `<p>A typical Google Cloud deployment uses:</p><div class="lp-notes gap-t-4">${[['Cloud Run', 'Run clearcut-api and clearcut-web as separate services.'],['Cloud SQL', 'Managed PostgreSQL 15+ for evidence and audit.'],['Cloud Storage', 'Script artifacts, snapshots, and exports.'],['Secret Manager', 'API keys and credentials.'],['Cloud Tasks', 'Durable async work: detection, research, monitoring, export.'],['Cloud Scheduler', 'Monitoring cadence and scheduled runs.']].map(([what, why]) => '<div class="lp-stack-item"><strong class="small">' + esc(what) + '</strong><span class="small muted">' + esc(why) + '</span></div>').join('')}</div>` },
      { id: 'deploy-docker', title: 'Deploy to any Docker host', body: `<ol class="stack-sm gap-t-2"><li>Run <span class="mono">clearcut-web</span>, <span class="mono">clearcut-api</span>, and PostgreSQL with persistent volumes.</li><li>Put a TLS-terminating reverse proxy in front of the services.</li><li>Set <span class="mono">OBJECT_STORAGE_PROVIDER=local</span> for single-host; use <span class="mono">gcs</span> for durability.</li><li>Provide a durable worker for async jobs.</li><li>Back up PostgreSQL and object storage regularly.</li></ol>` },
      { id: 'updating', title: 'Updating', body: `<div class="lp-code-block"><pre class="mono"><code>cd clearcut\ngit pull\ndocker compose build\ndocker compose up -d</code></pre></div><p class="small muted gap-t-4">Database migrations run automatically on startup. Back up PostgreSQL before upgrading.</p>` },
    ];
    const rail = sections.map((s) => `<a class="docs-rail-link" href="#doc-${s.id}" data-section="doc-${s.id}">${esc(s.title)}</a>`).join('');
    return `<div class="lp"><div class="docs-layout">
      <div class="docs-main">
        <header class="docs-section"><p class="lp-section-eyebrow">Self-hosted setup</p><h1 id="route-heading" tabindex="-1" class="lp-h2">Documentation</h1><p class="lp-lede">From zero to running in three commands. Deploy on Google Cloud, any Docker host, or locally.</p></header>
        ${sections.map((s) => `<section class="docs-section" id="doc-${s.id}" aria-labelledby="doc-h-${s.id}"><h2 id="doc-h-${s.id}" class="lp-h2">${esc(s.title)}</h2>${s.body}</section>`).join('')}
      </div>
      <aside class="docs-rail" aria-label="On this page"><div class="docs-rail-inner"><span class="docs-rail-title">On this page</span>${rail}</div></aside>
    </div>
    <footer class="lp-footer"><div class="lp-footer-brand"><strong>ClearCut</strong><span>Open-source screenplay clearance evidence workspace.</span></div><nav class="lp-footer-nav" aria-label="Footer navigation"><a href="#marketing">Home</a><a href="#features">Features</a><a href="https://github.com/clearcut" target="_blank" rel="noopener">GitHub</a></nav><p class="lp-footer-legal">\u00a9 2026 ClearCut \u00b7 MIT License \u00b7 Nothing here is legal advice; clearance decisions belong to qualified humans.</p></footer></div>`;
  }


  /* What a sign-in attempt can end as. The surface only had the happy path and a
     single generic 'access error', so the states that actually need distinct
     handling — an unverified account, a suspended one, an identity provider that
     is down — all looked alike. Addressable as #auth?state=suspended.

     Invalid credentials deliberately do not say whether the account exists: telling
     an attacker which addresses are registered is account enumeration. */
  const AUTH_STATES = {
    invalid: { tone: 'is-danger', icon: '✗', title: 'That email and password do not match',
      message: 'Check both and try again. For your safety ClearCut does not say whether an account exists for that address.',
      retry: true },
    unverified: { tone: 'is-warning', icon: '◔', title: 'Confirm your email address first',
      message: 'We sent a confirmation link when the account was created. Signing in needs a verified address so an invitation can be matched to it.',
      action: `<button class="button button-secondary" type="button" data-action="auth-resend-verification">Send the link again</button>` },
    suspended: { tone: 'is-danger', icon: '⊘', title: 'This account is suspended',
      message: 'An Owner deactivated it. Historical attribution is intact and nothing has been deleted, but it cannot be used to sign in. An Owner can reactivate it from Team &amp; roles.' },
    'provider-down': { tone: 'is-warning', icon: '⚠', title: 'The identity provider is not responding',
      message: 'This is not a problem with your account. Nothing was recorded and retrying is safe.',
      retry: true },
    expired: { tone: '', icon: '○', title: 'Your session ended',
      message: 'Sessions are revocable and expire on their own. Signing in again issues a new one; it does not change anything you recorded.',
      retry: true },
    recovery: { tone: 'is-success', icon: '✓', title: 'Check your email',
      message: 'If an account exists for that address, a recovery link is on its way. The link expires in 30 minutes and can be used once.' },
  };

  function renderAuth() {
    const authState = Object.hasOwn(AUTH_STATES, routeQuery().state || '') ? routeQuery().state : null;
    const problem = authState ? AUTH_STATES[authState] : null;
    const busy = routeQuery().state === 'authenticating';

    return page({
      width: 'narrow',
      eyebrow: 'Secure access',
      title: 'Sign in to ClearCut',
      lede: 'The prototype uses a simulated production identity. Authentication represents the deployment’s configured provider — local PostgreSQL by default, or Firebase where selected.',
      body: `${problem ? `<div class="gap-b-6">${banner(problem)}</div>` : ''}
      ${card({
        accent: !problem,
        body: `${problem ? '' : `${banner({ tone: 'is-accent', icon: '◉', title: 'Demo identity', message: `${esc(ACTOR.name)} · Executive producer · ${esc(ACTOR.role)} of ${esc(state.org.name)}` })}
        <p class="small muted gap-t-4">Signing in as ${esc(ACTOR.role)} grants ${esc(ROLE_MATRIX.find((r) => r.role === ACTOR.role)?.can || 'full access')}. You can preview other roles from Team &amp; roles once inside.</p>`}
        <div class="cluster gap-t-5" aria-busy="${busy ? 'true' : 'false'}">
          ${busy
            ? `<span class="spinner" role="status" aria-label="Signing in"></span><span class="small muted">Signing in…</span>`
            : `<button class="button button-primary" type="button" data-action="sign-in">${problem && problem.retry ? 'Try again' : 'Continue'}</button>
               <button class="button button-secondary" type="button" data-action="go" data-route="auth?state=recovery">Forgotten password</button>`}
        </div>
        <p class="small muted gap-t-4">No credentials are collected. Nothing leaves this browser.</p>`,
      })}
      <p class="small muted gap-t-4">Prototype: append <span class="mono">?state=</span> with ${['authenticating', ...Object.keys(AUTH_STATES)].map((k) => `<span class="mono">${k}</span>`).join(', ')} to review each outcome.</p>`,
    });
  }

  /* After sign-in the reader may belong to several organizations, or none. Routing
     every success straight to onboarding assumed the last case was the only one. */
  function renderResolver() {
    const orgs = [
      { id: 'northlight', name: state.org.name, role: 'Owner', projects: PROJECT_DEFS.length, status: 'Active' },
      { id: 'harbour', name: 'Harbour Lane Films', role: 'Reviewer', projects: 1, status: 'Active' },
      { id: 'lapsed', name: 'Fathom Pictures', role: 'Viewer', projects: 0, status: 'Suspended' },
    ];
    return page({
      width: 'narrow',
      eyebrow: 'Signed in',
      title: 'Choose an organization',
      lede: 'Your account can belong to more than one. Everything inside — projects, evidence, decisions, audit — belongs to the one you pick.',
      body: `<div class="list">${orgs.map((o) => `<button class="list-row" type="button" data-action="resolve-org" data-org="${esc(o.id)}"${o.status !== 'Active' ? ' aria-describedby="org-' + esc(o.id) + '"' : ''}>
        <span class="notif-dot informational" aria-hidden="true">◈</span>
        <div class="list-main">
          <span class="list-title">${esc(o.name)}</span>
          <span class="list-meta"><span>${esc(o.role)}</span><span>${o.projects} project${o.projects === 1 ? '' : 's'}</span></span>
          ${o.status !== 'Active' ? `<span class="small text-warning" id="org-${esc(o.id)}">Your membership here is suspended, so it cannot be opened.</span>` : ''}
        </div>
        <div class="list-aside">${badge(o.status, o.status === 'Active' ? 'is-success' : '')}</div>
      </button>`).join('')}</div>
      <div class="gap-t-6">${card({ quiet: true,
        body: `<span class="field-label">Not in the right one?</span>
        <p class="small gap-t-2">An organization is created once and invitations bring people into it. Creating a second one when you meant to join an existing one splits your evidence across two records.</p>`,
        actions: `<button class="button button-secondary" type="button" data-action="go" data-route="onboarding">Create a new organization</button>`,
      })}</div>`,
    });
  }

  /* The outcomes an invitation link can actually have. The surface only ever
     rendered the accept path, so a forwarded, expired, revoked or already-used
     link looked like a valid invitation — and possession of a token read as
     authority. Addressable as #invite?state=expired so each can be reviewed. */
  const INVITE_LINK_STATES = {
    valid: null,
    'wrong-account': {
      tone: 'is-warning', icon: '⚠', title: 'This invitation is for a different account',
      message: 'It was sent to a different address than the account you are signed in as. Holding the link does not grant access.',
      action: `<button class="button button-secondary" type="button" data-action="go" data-route="auth">Sign out and use another account</button>`,
    },
    expired: {
      tone: '', icon: '◔', title: 'This invitation has expired',
      message: 'Invitations are valid for 14 days. This one lapsed on Aug 16. An Owner or Admin can send a new one, which issues a new link.',
      action: `<button class="button button-secondary" type="button" data-action="go" data-route="marketing">Ask for a new invitation</button>`,
    },
    revoked: {
      tone: '', icon: '⊘', title: 'This invitation was withdrawn',
      message: 'An Owner or Admin revoked it, which invalidated the link. The withdrawal is on the organization record.',
      action: `<button class="button button-secondary" type="button" data-action="go" data-route="marketing">Back to ClearCut</button>`,
    },
    accepted: {
      tone: 'is-success', icon: '✓', title: 'This invitation has already been accepted',
      message: 'You are already a member of Northlight Pictures. Repeating the link does not create a second membership.',
      action: `<button class="button button-primary" type="button" data-action="go" data-route="projects">Go to your projects</button>`,
    },
    declined: {
      tone: '', icon: '✕', title: 'This invitation was declined',
      message: 'Declining invalidated the link and created no membership or project access. A later invitation would be a new record.',
      action: `<button class="button button-secondary" type="button" data-action="go" data-route="marketing">Back to ClearCut</button>`,
    },
    malformed: {
      tone: 'is-danger', icon: '✗', title: 'This link is not a valid invitation',
      message: 'The token is missing or malformed, so there is nothing to resolve. Check the link in the original email rather than retyping it.',
      action: `<button class="button button-secondary" type="button" data-action="go" data-route="marketing">Back to ClearCut</button>`,
    },
  };

  function renderInvite() {
    // The invitation is driven from state and the capability model, not fixed
    // copy: the inviter is the org's first active non-owner reviewer, the org
    // name comes from state, and the can/can't lists are derived from the role
    // being offered — so they cannot drift from what the role actually gates.
    const invitedRole = 'Reviewer';
    const inviter = state.members.find((m) => m.role === 'Reviewer' && m.status === 'Active')
      || state.members.find((m) => m.role !== 'Owner') || state.members[0];
    const caps = Object.keys(CAPABILITY_LABELS);
    const held = caps.filter((c) => CAPABILITIES[c] && CAPABILITIES[c].includes(invitedRole));
    const lacked = caps.filter((c) => CAPABILITIES[c] && !CAPABILITIES[c].includes(invitedRole));
    const capList = (list) => `<ul class="stack-sm small muted cap-list">${list.map((c) => `<li>${esc(CAPABILITY_LABELS[c].replace(/^./, (ch) => ch.toUpperCase()))}</li>`).join('')}</ul>`;

    /* Resolve the real pending invitation record instead of repeating a hardcoded
       address: the design requires the invited email, role, projects and timestamps
       to come from invitation state. */
    const record = (state.invitations || []).find((i) => i.status === 'Pending')
      || (state.invitations || [])[0]
      || { email: 'invitee@example.com', role: invitedRole, access: projInfo(PROJECT_DEFS[0].id).title, sentAt: '—', expiresAt: '—', status: 'Pending' };
    const linkState = Object.hasOwn(INVITE_LINK_STATES, routeQuery().state || '') ? routeQuery().state : 'valid';
    const problem = INVITE_LINK_STATES[linkState];

    /* An unusable link shows what happened and what to do instead, and never the
       Accept control — offering it would imply the link still carries authority. */
    if (problem) {
      return page({
        width: 'narrow',
        eyebrow: 'Invitation',
        title: `Join ${esc(state.org.name)}`,
        body: `${banner(problem)}
        <div class="gap-t-6">${card({ quiet: true, body: `<span class="field-label">What was offered</span>
          <p class="small gap-t-2">${esc(invitedRole)} on ${esc(projInfo(PROJECT_DEFS[0].id).title)}, invited by ${esc(inviter.name)}. Shown for reference; this link cannot be used.</p>` })}</div>
        <p class="small muted gap-t-4">Prototype: append <span class="mono">?state=</span> with ${Object.keys(INVITE_LINK_STATES).filter((k) => k !== 'valid').map((k) => `<span class="mono">${k}</span>`).join(', ')} to review each outcome.</p>`,
      });
    }

    return page({
      width: 'narrow',
      eyebrow: 'Invitation',
      title: `Join ${esc(state.org.name)}`,
      lede: `${esc(inviter.name)} invited you to review clearance evidence on ${esc(projInfo(PROJECT_DEFS[0].id).title)}.`,
      body: `${card({
        body: `<div class="stack">
          <div class="cluster-between">
            <div class="cluster">${avatar(inviter.initials, inviter.name)}<div><strong class="small">${esc(inviter.name)}</strong><p class="small muted">Clearance reviewer</p></div></div>
            ${badge(`${invitedRole} role`, 'is-accent')}
          </div>
          <div class="divider"></div>
          <dl class="invite-meta">
            <div><dt>Invited email</dt><dd class="mono">${esc(record.email)}</dd></div>
            <div><dt>Project access</dt><dd>${esc(record.access)}</dd></div>
            <div><dt>Sent</dt><dd>${esc(record.sentAt)}</dd></div>
            <div><dt>Expires</dt><dd>${esc(record.expiresAt)}</dd></div>
            <div><dt>Status</dt><dd>${badge(record.status, INVITE_STATES[record.status]?.tone || '')}</dd></div>
          </dl>
          <div class="divider"></div>
          <div>
            <span class="field-label">As a ${esc(invitedRole)}, you will be able to</span>
            ${capList(held)}
          </div>
          <div>
            <span class="field-label">You will not be able to</span>
            ${capList(lacked)}
          </div>
        </div>`,
        actions: `<button class="button button-primary" type="button" data-action="accept-invite">Accept invitation</button><button class="button button-quiet" type="button" data-action="decline-invite">Decline</button>`,
      })}
      <p class="small muted gap-t-4">Acceptance needs a signed-in account whose verified email matches the invitation. Invitations expire after 14 days; an Owner can resend one from Team &amp; roles, which issues a new link.</p>
      <p class="small muted gap-t-2">Prototype: append <span class="mono">?state=</span> with ${Object.keys(INVITE_LINK_STATES).filter((k) => k !== 'valid').map((k) => `<span class="mono">${k}</span>`).join(', ')} to review each outcome.</p>`,
    });
  }

  function renderOnboarding() {
    return page({
      width: 'narrow',
      eyebrow: 'Step 1 of 1',
      title: 'Create your organization',
      lede: 'An organization owns projects, members, policies, and exports. Roles are fixed so review authority stays legible.',
      body: `${card({
        body: `<div class="form-grid">
          <label class="field field-full"><span class="field-label">Organization name</span><input id="org-name" value="${esc(state.org.name)}"></label>
          <label class="field"><span class="field-label">Owner</span><input value="${esc(ACTOR.name)}" readonly></label>
          <label class="field"><span class="field-label">Default monitoring cadence</span><select id="org-cadence">${['weekly', 'daily', 'manual'].map((v) => `<option value="${v}" ${v === state.org.cadence ? 'selected' : ''}>${esc(cadenceLabel(v))}</option>`).join('')}</select></label>
          <label class="field field-full"><span class="field-label">Invite a reviewer (optional)</span><input id="org-invite" type="email" value="mara@northlight.example"><span class="field-hint">They receive a Reviewer invitation you can revoke at any time.</span></label>
        </div>`,
      })}
      ${section({
        title: 'Fixed roles',
        description: 'Five roles instead of custom permission combinations.',
        body: rolesTable(),
      })}
      <div class="cluster gap-t-8">
        <button class="button button-primary" type="button" data-action="finish-onboarding">Create organization</button>
      </div>`,
    });
  }

  /* ═══════════════════════════ ORGANIZATION SURFACES ═══════════════════════════ */

  function renderProjects() {
    const rows = PROJECT_DEFS.map((def) => {
      const p = state.projects[def.id];
      const verified = verifiedCountFor(p);
      const stage = !p.versions.length ? 'Not imported'
        : !p.runComplete ? 'Research pending'
        : p.dossier ? 'Report released'
        : 'In review';
      const pct = !p.versions.length ? 0
        : Math.min(100, (p.runComplete ? 40 : 10) + Math.round((verified / VERIFIABLE_ITEMS.length) * 40) + (p.dossier ? 20 : 0));
      return { def, p, stage, pct, verified };
    });
    const totals = {
      open: rows.reduce((n, r) => n + (r.p.runComplete ? Math.max(0, VERIFIABLE_ITEMS.length - r.verified) : 0), 0),
      blocked: rows.reduce((n, r) => n + (r.p.runComplete && !r.p.rewriteApproved ? 1 : 0), 0),
      exports: rows.filter((r) => r.p.dossier).length,
    };

    return page({
      trail: [{ label: state.org.name, route: 'projects' }, { label: 'Projects' }],
      eyebrow: state.org.name,
      title: 'Projects',
      lede: 'Active clearance work, open human gates, and delivery readiness across the organization.',
      actions: gated('project-create', `<button class="button button-primary" type="button" data-action="new-project">New project</button>`),
      notice: prerequisiteNotice('projects'),
      body: `${statGrid([
        { label: 'Active projects', value: PROJECT_DEFS.length },
        { label: 'Open reviews', value: totals.open, tone: totals.open ? 'is-warning' : '', hint: 'current project', route: 'items?status=attention' },
        { label: 'Blocked items', value: totals.blocked, tone: totals.blocked ? 'is-danger' : '', hint: 'current project', route: 'items?status=Must%20fix' },
        { label: 'Released reports', value: totals.exports, tone: totals.exports ? 'is-success' : '', route: 'report' },
      ])}
      ${section({
        title: 'Your projects',
        description: 'Each project keeps its own script versions, evidence, and decisions.',
        body: `<div class="list">${rows.map(({ def, p, stage, pct }) => `<button class="list-row" type="button" data-action="open-project" data-project="${def.id}">
          <div class="list-main">
            <span class="list-title">${esc(def.title)}${def.id === state.activeProjectId ? ' <span class="badge is-accent">Current</span>' : ''}</span>
            <span class="list-meta"><span>${esc(def.type)}</span><span>${esc(def.stage)}</span><span>${p.versions.length} version${p.versions.length === 1 ? '' : 's'}</span><span>Lock ${esc(def.lock)}</span></span>
          </div>
          <div class="list-aside">
            <div class="progress-inline">${progress(pct)}<span class="mono">${pct}%</span></div>
            ${badge(stage, p.dossier ? 'is-success' : p.versions.length ? 'is-warning' : '')}
          </div>
        </button>`).join('')}</div>`,
      })}`,
    });
  }

  /** What a screen reader hears on arrival. '<Surface> loaded' says nothing about
      what is waiting there, and a second write from the surface itself only raced
      this one — so the state belongs in this single announcement. */
  function routeAnnouncement(meta) {
    if (meta.id === 'notifications') {
      const n = unreadCount();
      return n
        ? `Notifications loaded. ${n} need${n === 1 ? 's' : ''} your attention.`
        : 'Notifications loaded. Nothing needs your attention.';
    }
    if (meta.id === 'items') {
      const open = flags().filter((i) => !proj().evidenceDecisions[i.id]).length;
      return `Flags loaded. ${flags().length} flag${flags().length === 1 ? '' : 's'}, ${open} still open.`;
    }
    return `${meta.label} loaded.`;
  }

  function renderNotifications() {
    const rows = notifications().map((n) => ({ ...n, unread: !state.readNotifications.includes(n.id) && (n.generated ? true : n.unread) }));
    const tierFilter = state.notifTierFilter || 'all';
    const projectFilter = state.notifProjectFilter || 'all';
    const filtered = rows.filter((n) => {
      if (tierFilter !== 'all' && (n.tier || 'informational') !== tierFilter) return false;
      if (projectFilter !== 'all' && n.project !== projectFilter) return false;
      return true;
    });
    const urgent = filtered.filter((n) => n.tier === 'urgent');
    const action = filtered.filter((n) => n.tier === 'action');
    const info = filtered.filter((n) => !n.tier || n.tier === 'informational');
    const anyUnread = filtered.some((n) => n.unread);

    const TIER_GLYPH = { urgent: '■', action: '◎', informational: '○' };
    const renderRow = (n) => `<button class="list-row" type="button" data-action="open-notification" data-id="${n.id}" data-route="${esc(n.destination ? destinationRoute(n.destination) : (n.route || 'records'))}"${destinationBlock(n.destination) ? ` aria-describedby="nb-${esc(n.id)}"` : ''}>
      <span class="notif-dot ${n.tier || 'informational'}" aria-hidden="true">${TIER_GLYPH[n.tier] || '○'}</span>
      <div class="list-main">
        <span class="list-title">${esc(n.title)}</span>
        <span class="list-meta">${n.project ? `<span class="notif-project-label">${esc(n.project)}</span>` : ''}<span>${esc(n.detail)}</span><time datetime="${esc(n.atISO || '')}">${esc(n.at)}</time></span>
        ${destinationBlock(n.destination) ? `<span class="small text-warning" id="nb-${esc(n.id)}">${esc(destinationBlock(n.destination))}</span>` : ''}
      </div>
      <div class="list-aside">${n.unread ? badge('New', n.tier === 'urgent' ? 'is-danger' : 'is-accent') : ''}</div>
    </button>`;

    const tierGroup = (heading, list) => list.length ? `<div class="notif-tier-group"><h2 class="notif-tier-heading">${esc(heading)} <span class="muted small">${list.length}</span></h2><div class="list">${list.map(renderRow).join('')}</div></div>` : '';

    const tierBtns = ['all', 'urgent', 'action', 'informational'].map((v) => {
      const label = { all: 'All', urgent: 'Urgent', action: 'Needs action', informational: 'Informational' }[v];
      return `<button class="button button-sm ${tierFilter === v ? 'button-primary' : 'button-secondary'}" type="button" data-action="notif-tier" data-tier="${v}" aria-pressed="${tierFilter === v}">${esc(label)}</button>`;
    }).join('');

    const projects = [...new Set(rows.map((n) => n.project).filter(Boolean))];
    const projOpts = ['<option value="all">All projects</option>', ...projects.map((p) => `<option value="${esc(p)}" ${projectFilter === p ? 'selected' : ''}>${esc(p)}</option>`)].join('');

    return page({
      trail: orgTrail('Notifications'),
      eyebrow: 'Organization',
      title: 'Notifications',
      lede: 'Assignments, monitoring changes, referrals, and run outcomes that need your attention.',
      /* Delivery is a standing preference, not something you change while triaging,
         so the control lives in Settings and this only says where to find it. */
      actions: `<span class="small muted">Delivered ${esc(PUSH_PREF_LABELS[state.pushPref || 'in-app'])}</span><button class="button button-quiet button-sm" type="button" data-action="go" data-route="settings">Change</button>${anyUnread ? `<button class="button button-secondary" type="button" data-action="mark-all-read">Mark all read</button>` : ''}`,
      notice: prerequisiteNotice('notifications'),
      body: `${!state.orgReady ? `${banner({
        tone: 'is-warning', icon: '◔',
        title: 'No organization yet, so these are sample entries',
        message: 'An inbox belongs to an organization. Until one exists there is nothing addressed to you, and the rows below are a sample of what will arrive.',
        action: `<button class="button button-secondary button-sm" type="button" data-action="go" data-route="onboarding">Create your organization</button>`,
      })}<div class="gap-t-6"></div>` : ''}
      <div class="notif-filters cluster-between"><div class="cluster">${tierBtns}</div><select class="notif-project-select" data-action="notif-project" aria-label="Filter by project">${projOpts}</select></div>
      ${tierGroup('Urgent', urgent)}
      ${tierGroup('Needs your action', action)}
      ${tierGroup('Informational', info)}
      ${!filtered.length ? emptyState({ icon: '◔', title: tierFilter !== 'all' || projectFilter !== 'all' ? 'No matching notifications' : 'Nothing to review', description: tierFilter !== 'all' || projectFilter !== 'all' ? 'Try changing the filters.' : 'Notifications appear when work is assigned to you or a monitored source changes.' }) : ''}`,
    });
  }

  function renderTeam() {
    /* Three tabs named by the design: members, invitations, roles. Membership and
       invitation are different records with different lifecycles, and mixing them
       in one table meant an invitation had nowhere to keep its state. */
    const tab = ['members', 'invitations', 'roles'].includes(state.teamTab) ? state.teamTab : 'members';
    const invites = state.invitations || [];
    const pending = invites.filter((i) => i.status === 'Pending').length;
    const members = state.members.filter((m) => m.status !== 'Invited');

    const inviteAction = (inv, kind) => {
      const map = {
        edit: gated('team', `<button class="button button-secondary button-sm" type="button" data-action="edit-invite-dialog" data-email="${esc(inv.email)}" data-member="${esc(inv.email)}">Edit</button>`),
        resend: gated('team', `<button class="button button-secondary button-sm" type="button" data-action="resend-invite" data-id="${esc(inv.id)}">Resend</button>`),
        revoke: gated('team', `<button class="button button-quiet button-sm" type="button" data-action="revoke-invite" data-email="${esc(inv.email)}">Revoke</button>`),
        receipt: `<button class="button button-quiet button-sm" type="button" data-action="go" data-route="records">View receipt</button>`,
        new: gated('team', `<button class="button button-secondary button-sm" type="button" data-action="invite-dialog">New invitation</button>`),
        member: `<button class="button button-quiet button-sm" type="button" data-action="set-team-tab" data-value="members">View member</button>`,
      };
      return map[kind] || '';
    };

    return page({
      trail: orgTrail('Team & roles'),
      eyebrow: 'Organization',
      title: 'Team & roles',
      lede: 'Membership, fixed roles, and project access. Role changes are recorded in the organization audit.',
      actions: gated('team', `<button class="button button-primary" type="button" data-action="invite-dialog">Invite member</button>`),
      notice: prerequisiteNotice('team'),
      body: `${tabsBar({
        items: [
          { label: 'Members', value: 'members', count: members.length },
          { label: 'Invitations', value: 'invitations', count: pending },
          { label: 'Roles', value: 'roles' },
        ],
        active: tab,
        action: 'set-team-tab',
        label: 'Team sections',
      })}
      <div class="gap-t-6">
      ${tab === 'members' ? section({
        title: `Members (${members.length})`,
        description: 'Active and deactivated organization memberships. A pending invitation is not a membership — it lives on the Invitations tab.',
        body: dataTable({
          caption: 'Organization members',
          columns: [{ label: 'Member' }, { label: 'Role' }, { label: 'Project access' }, { label: 'Status' }, { label: 'Last active' }, { label: 'Actions', align: 'right' }],
          rows: members.map((m) => [
            `<div class="cluster">${avatar(m.initials, m.name)}<div><strong class="small">${esc(m.name)}</strong><br><span class="mono muted">${esc(m.email)}</span></div></div>`,
            badge(m.role, m.role === 'Owner' ? 'is-accent' : ''),
            `<span class="small">${esc(m.access)}</span>`,
            badge(m.status, m.status === 'Active' ? 'is-success' : ''),
            `<span class="mono small">${esc(m.lastActive || '—')}</span>`,
            /* Three member actions, per the design. A deactivated membership is
               reactivated rather than edited in place: the reactivation flow has to
               review role and project access explicitly. */
            `<div class="cluster cluster-end">${m.status === 'Deactivated'
              ? gated('team', `<button class="button button-secondary button-sm" type="button" data-action="reactivate-member" data-member="${esc(m.name)}">Reactivate…</button>`)
              : `${gated('team', `<button class="button button-secondary button-sm" type="button" data-action="role-dialog" data-member="${esc(m.name)}">Change role</button>`)}${gated('team', `<button class="button button-quiet button-sm" type="button" data-action="access-dialog" data-member="${esc(m.name)}">Project access</button>`)}${gated('team', `<button class="button button-quiet button-sm" type="button" data-action="deactivate-dialog" data-member="${esc(m.name)}">Deactivate</button>`)}`}</div>`,
          ]),
        }),
      }) : ''}
      ${tab === 'invitations' ? section({
        title: `Invitations (${invites.length})`,
        description: 'Invitations keep their history after they end, so an expired or declined one stays readable. What you can do depends on the state.',
        body: invites.length ? dataTable({
          caption: 'Organization invitations',
          columns: [{ label: 'Invitee' }, { label: 'Proposed role' }, { label: 'Project access' }, { label: 'Invited by' }, { label: 'Sent' }, { label: 'Expires' }, { label: 'Status' }, { label: 'Actions', align: 'right' }],
          rows: invites.map((inv) => [
            `<span class="mono small">${esc(inv.email)}</span>`,
            badge(inv.role, inv.role === 'Owner' ? 'is-accent' : ''),
            `<span class="small">${esc(inv.access)}</span>`,
            `<span class="small">${esc(inv.invitedBy)}</span>`,
            `<span class="mono small">${esc(inv.sentAt)}</span>`,
            `<span class="mono small">${esc(inv.expiresAt)}</span>`,
            `${badge(inv.status, INVITE_STATES[inv.status]?.tone || '')}${inv.tokenVersion > 1 ? `<span class="mono muted small"> token v${inv.tokenVersion}</span>` : ''}`,
            `<div class="cluster cluster-end">${(INVITE_STATES[inv.status]?.actions || []).map((k) => inviteAction(inv, k)).join('')}</div>`,
          ]),
        }) : emptyState({ icon: '✉', title: 'No invitations yet', description: 'Invite a reviewer or editor and the record appears here.', action: gated('team', `<button class="button button-primary" type="button" data-action="invite-dialog">Invite member</button>`) }),
      }) : ''}
      ${tab === 'roles' ? `${section({
        title: 'What each role can do',
        description: 'Fixed roles keep review authority auditable.',
        body: rolesTable({ markCurrent: true }),
      })}
      ${section({
        title: 'Preview as a role',
        description: 'A demo control: switch the role you are acting as to see how authority changes. Controls a role cannot use are disabled with a reason — nothing is hidden.',
        body: card({
          quiet: true,
          body: `<div class="cluster cluster-wrap" role="group" aria-label="Preview as role">
            ${ROLE_ORDER.map((r) => `<button class="button ${r === actorRole() ? 'button-primary' : 'button-secondary'} button-sm" type="button" data-action="set-actor-role" data-role="${r}" aria-pressed="${r === actorRole()}">${esc(r)}</button>`).join('')}
          </div>
          <p class="small muted gap-t-3">Acting as <strong>${esc(actorRole())}</strong>. This is a prototype affordance, not a real sign-in.</p>`,
        }),
      })}` : ''}
      </div>`,
    });
  }

  function renderSettings() {
    /* Four tabs, named by the design: general, integrations, data, governance.
       An earlier pass invented a six-item rail with its own ?s= parameter before
       reading the spec; this is the addressable TabsBar the rest of the product
       already uses. */
    const tab = ['general', 'integrations', 'data', 'governance'].includes(state.settingsTab) ? state.settingsTab : 'general';
    return page({
      trail: orgTrail('Settings'),
      eyebrow: 'Organization',
      title: 'Settings',
      lede: 'Organization profile, integrations, what ClearCut stores, and the governance contracts in force.',
      notice: prerequisiteNotice('settings'),
      body: `${tabsBar({
        items: [
          { label: 'General', value: 'general' },
          { label: 'Integrations', value: 'integrations' },
          { label: 'Data & privacy', value: 'data' },
          { label: 'Governance', value: 'governance' },
        ],
        active: tab,
        action: 'set-settings-tab',
        label: 'Settings sections',
      })}
      <div class="gap-t-6">
      ${tab === 'general' ? `
      ${section({
        title: 'Profile',
        body: card({ body: `<div class="form-grid">
          <label class="field field-full"><span class="field-label">Organization name</span><input id="set-name" value="${esc(state.org.name)}"></label>
          <label class="field"><span class="field-label">Plan</span><input value="${esc(state.org.plan)}" readonly></label>
          <label class="field"><span class="field-label">Primary jurisdiction</span><input id="set-jurisdiction" value="${esc(state.org.jurisdiction)}"></label>
          <div class="field"><span class="field-label">Evidence retention</span><p class="small gap-t-1">Kept until an Owner deletes the project or organization. There is no age-based expiry.</p></div>
          <label class="field"><span class="field-label">Default monitoring cadence</span><select id="set-cadence">${['weekly', 'daily', 'manual'].map((v) => `<option value="${v}" ${v === state.org.cadence ? 'selected' : ''}>${esc(cadenceLabel(v))}</option>`).join('')}</select></label>
        </div>`, actions: gated('settings', `<button class="button button-primary" type="button" data-action="save-settings">Save changes</button>`) }),
      })}
      ${section({
        title: 'Notifications',
        description: 'Where ClearCut reaches you when something needs attention.',
        body: deliveryPreferenceCard(),
      })}` : ''}
      ${tab === 'integrations' ? `
      ${section({
        title: 'Integrations',
        description: 'Credentials are environment-managed. The prototype simulates all provider calls.',
        body: dataTable({
          columns: [{ label: 'Provider' }, { label: 'Purpose' }, { label: 'Status' }, { label: 'Actions', align: 'right' }],
          rows: [
            ['<strong>Gemini</strong>', '<span class="small muted">Detection and rewrite proposals</span>', badge('Connected', 'is-success'), ''],
            /* Operational retry history lives in Records, not here. Settings held a
               second copy with its own Inspect action, so two surfaces owned the
               same operational state. This links to the ledger that owns it. */
            ['<strong>Parallel research</strong>', '<span class="small muted">Source retrieval</span>', badge('Retrying', 'is-warning'), `<button class="button button-secondary button-sm" type="button" data-action="go" data-route="records?view=operations">See in Records</button>`],
            ['<strong>Cloud Storage</strong>', '<span class="small muted">Scripts and exports</span>', badge('Connected', 'is-success'), ''],
            ['<strong>Firebase Auth</strong>', '<span class="small muted">Identity</span>', badge('Connected', 'is-success'), ''],
          ],
        }),
      })}` : ''}
      ${tab === 'data' ? `
      ${section({
        title: 'Data & privacy',
        description: 'What ClearCut stores, and the only way it leaves.',
        body: `${dataTable({
          caption: 'Stored data classes',
          columns: [{ label: 'What is stored' }, { label: 'Retention' }, { label: 'Removed by' }],
          rows: [
            ['<strong>Original scripts and parsed structure</strong>', '<span class="small">Kept indefinitely</span>', '<span class="small">Project deletion</span>'],
            ['<strong>Source snapshots and evidence</strong>', '<span class="small">Kept indefinitely</span>', '<span class="small">Project deletion</span>'],
            ['<strong>Decisions and audit events</strong>', '<span class="small">Kept indefinitely</span>', badge('Never selectively', 'is-warning')],
            ['<strong>Reports and export artifacts</strong>', '<span class="small">Kept indefinitely</span>', '<span class="small">Project deletion</span>'],
            ['<strong>Operational logs and provider payloads</strong>', '<span class="small">Bounded telemetry window</span>', '<span class="small">Automatic</span>'],
          ],
        })}
        <div class="gap-t-5">${banner({ tone: 'is-accent', icon: 'ℹ', title: 'Private scripts are never used for shared-model training',
          message: 'Signed download links are short-lived and regenerated on demand. A link expiring does not delete the artifact.' })}</div>
        <div class="gap-t-5" id="sec-deletion" tabindex="-1">${card({
          eyebrow: 'Deletion',
          title: 'Only an Owner can delete a project or organization',
          body: `<p class="small">Individual claims, snapshots, decisions, and audit events cannot be deleted on their own — removing one link would make the remaining record misleading. Deletion takes the whole project or the whole organization.</p>
          <ul class="stack-sm gap-t-3">
            <li class="small">Scheduling makes the resource read-only, blocks new jobs and governed actions, and revokes signed links.</li>
            <li class="small">A 30-day grace period follows, during which an Owner can restore it.</li>
            <li class="small">Final purge removes sensitive content and blobs, keeping only the minimum tombstone the audit boundary needs.</li>
            <li class="small">Any report whose source material was purged becomes explicitly unavailable rather than claiming it is still reproducible.</li>
          </ul>`,
          actions: (proj().deletionScheduled
            ? `<button class="button button-secondary button-sm" type="button" data-action="restore-project">Restore project</button>`
            : gated('settings', `<button class="button button-danger button-sm" type="button" data-action="delete-project-dialog">Schedule project deletion…</button>`)),
        })}</div>
        ${proj().deletionScheduled ? `<div class="gap-t-4">${banner({ tone: 'is-danger', icon: '⚠', title: 'Deletion scheduled',
          message: `${esc(projInfo().title)} is read-only and will be purged after the grace period. Restoring it writes a new audit event rather than rewriting history.` })}</div>` : ''}`,
      })}` : ''}
      ${tab === 'governance' ? `
      ${section({
        title: 'Global catalogs',
        description: 'Defined by the platform and read-only for every organization. A category does not establish a source’s authority, and source authority does not establish a legal conclusion — they are separate protected policies.',
        body: dataTable({
          caption: 'Global read-only catalogs',
          columns: [{ label: 'Catalog' }, { label: 'What it governs' }, { label: 'Version' }, { label: '', align: 'right' }],
          rows: GLOBAL_CATALOGS.map((c) => [
            `<strong class="small">${esc(c.name)}</strong>`,
            `<span class="small muted">${esc(c.detail)}</span>`,
            `<span class="mono small">${esc(c.version)}</span>`,
            badge('Read-only', ''),
          ]),
        }),
      })}
      ${section({
        title: 'Organization policy',
        description: 'Owner-governed and versioned. An active version is immutable: changing one supersedes it and writes an audit event in the same transaction. Admin may inspect; only an Owner may validate or activate.',
        body: `${dataTable({
          caption: 'Organization-owned protected configuration',
          columns: [{ label: 'Policy' }, { label: 'Active version' }, { label: 'Status' }, { label: 'Activated' }, { label: 'Validation' }, { label: 'History' }, { label: 'Actions', align: 'right' }],
          rows: ORG_POLICIES.map((c) => [
            `<strong class="small">${esc(c.name)}</strong><br><span class="small muted">${esc(c.rationale)}</span>`,
            `<span class="mono small">${esc(c.version)}</span>`,
            badge(CONFIG_STATUS[c.status].label, CONFIG_STATUS[c.status].tone),
            `<span class="mono small">${esc(c.at)}</span><br><span class="small muted">${esc(c.author)}</span>`,
            `<span class="small">${esc(c.validation)}</span>`,
            `<button class="button button-quiet button-sm" type="button" data-action="go" data-route="records?view=policies">${c.history} version${c.history === 1 ? '' : 's'}</button>`,
            `<div class="cluster cluster-end">${c.status === 'validated'
              ? gated('settings-protected', `<button class="button button-primary button-sm" type="button" data-action="activate-policy-dialog" data-policy="${esc(c.id)}">Activate</button>`)
              : c.status === 'draft'
                ? gated('settings-protected', `<button class="button button-secondary button-sm" type="button" data-action="validate-policy" data-policy="${esc(c.id)}">Validate</button>`)
                : gated('settings-protected', `<button class="button button-secondary button-sm" type="button" data-action="draft-policy" data-policy="${esc(c.id)}">New draft</button>`)}</div>`,
          ]),
        })}
        <div class="gap-t-5">${banner({ tone: 'is-danger', icon: '⚖',
          title: 'These are never changed by an automated process',
          message: 'Permissions, sign-off policy, category definitions, source-authority tiers, evidence schemas, blocking rules and legal-boundary language are human-only and Owner-governed. A learning candidate can propose query phrasing and examples; it cannot touch anything on this list.' })}</div>`,
      })}
      ${section({
        title: 'Data handling',
        /* This used to read 'Retention is set in the profile above', pointing at a
           duration selector that no longer exists — and contradicting the stored
           data table, which says evidence is kept until the project is deleted. */
        description: 'Evidence is kept until the project is deleted, as set out above. These rules govern everything else.',
        body: card({ body: `<div class="stack">
          <div class="toggle-row"><div><strong class="small">Script content in training</strong><p class="small muted">Private scripts are never used to train shared models.</p></div>${badge('Never', 'is-success')}</div>
          <div class="toggle-row"><div><strong class="small">Export expiry</strong><p class="small muted">Signed download links expire automatically.</p></div><span class="mono">30 days</span></div>
        </div>` }),
      })}` : ''}
      </div>`,
    });
  }

  function renderRecords() {
    const receipts = state.receipts;
    const runs = allRuns();
    const view = ['activity', 'runs', 'evaluations', 'policies', 'operations'].includes(state.recordsView) ? state.recordsView : 'activity';
    return page({
      trail: orgTrail('Records'),
      eyebrow: 'Trust & records',
      title: 'Records',
      lede: 'Everything that happened, in order — every call you made, every background operation, and the research that ran. If it mattered, it is written down here.',
      actions: receipts.length ? `<button class="button button-secondary" type="button" data-action="open-receipts">Open the ledger</button>` : '',
      notice: prerequisiteNotice('records'),
      body: `${tabsBar({
        items: [
          { label: 'Activity', value: 'activity', count: state.receipts.length },
          { label: 'Runs & tools', value: 'runs', count: runs.length },
          { label: 'Evaluations', value: 'evaluations', count: proj().runComplete ? 1 : 0 },
          { label: 'Policies', value: 'policies' },
          { label: 'Operations', value: 'operations' },
        ],
        active: view,
        action: 'set-records-view',
        label: 'Record views',
      })}
      <div class="gap-t-6">
      ${view === 'activity' ? `${section({
        title: 'Your calls and actions',
        description: 'Every decision you record gets an entry. Pop-ups are just acknowledgements — this list is the real record.',
        body: receipts.length
          ? `<div class="card">${receipts.map((r) => `<div class="receipt"><span class="receipt-icon" aria-hidden="true">✓</span><div><strong class="small">${esc(r.title)}</strong><p class="small muted">${esc(r.detail)}</p><span class="mono muted">${esc(r.id)} · ${esc(r.actor)}</span></div><time>${fmtStamp(r.at)}</time></div>`).join('')}</div>`
          : emptyState({ icon: '≡', title: 'Nothing recorded yet', description: 'Verify a source, approve a rewrite, or release the report and it will appear here.', action: `<button class="button button-secondary" type="button" data-action="go" data-route="items">Open the flags</button>` }),
      })}` : ''}
      ${view === 'runs' ? `${section({
        title: 'Research activity',
        description: 'Every lookup ClearCut ran, with what it cost and what it found.',
        actions: gated('research', `<button class="button button-primary button-sm" type="button" data-action="run-research">Run a research batch</button>`),
        body: runs.length
          ? dataTable({
            caption: 'Research history',
            columns: [{ label: 'When' }, { label: 'What it covered' }, { label: 'Sources' }, { label: 'Cost' }, { label: 'Status' }, { label: 'Calls', align: 'right' }],
            rows: runs.map((r) => {
              const t = runTotals(r.id);
              return [
                `<strong class="mono">${esc(r.id)}</strong><br><span class="small muted">${esc(r.started)}</span>`,
                `<span class="small">${esc(r.scope)}</span>`,
                `<span class="mono">${t.sources}</span>`,
                `<span class="mono">${esc(r.cost)}</span>`,
                badge(r.status, r.status === 'Complete' ? 'is-success' : 'is-warning'),
                // Every run opens to the calls that produced its totals.
                `<button class="button button-secondary button-sm" type="button" data-action="open-tool-calls" data-run="${esc(r.id)}">${t.calls} call${t.calls === 1 ? '' : 's'}</button>`,
              ];
            }),
          })
          : emptyState({ icon: '⚗', title: 'No research yet', description: 'Finish checking a script, or run a batch against the open flags.' }),
      })}` : ''}
      ${view === 'evaluations' ? `${section({
        title: 'Evaluations',
        description: 'Each evaluation binds a run to the gates that ran first, the judge verdict, and the exact rubric, prompt, policy and model versions used. A missing binding is an invalid evaluation, not a partial one.',
        body: proj().runComplete ? `${(() => {
          /* Selectable rather than one static latest run: an evaluation is bound to
             the run that produced it, so the reader has to be able to choose which
             one they are reading. A run without a full set of bindings is reported
             as incomplete, never as a partial success. */
          const evaluated = allRuns();
          const chosen = evaluated.find((r) => r.id === state.evaluationRun) || evaluated[0];
          return `<div class="cluster cluster-wrap gap-b-4" role="group" aria-label="Choose an evaluation">
            ${evaluated.map((r) => `<button class="button ${r.id === chosen.id ? 'button-primary' : 'button-secondary'} button-sm" type="button" data-action="set-evaluation" data-run="${esc(r.id)}" aria-pressed="${r.id === chosen.id}">${esc(r.id)}</button>`).join('')}
          </div>
          ${chosen.status === 'Complete with exceptions' || chosen.status === 'Recovered'
            ? ''
            : banner({ tone: 'is-warning', icon: '⚠', title: 'This run has no complete evaluation',
                message: `${esc(chosen.id)} finished as ${esc(chosen.status)}. Without every binding present this is an incomplete evaluation, not a partial score.` })}
          <p class="small muted gap-b-3">Reading <span class="mono">${esc(chosen.id)}</span> · ${esc(chosen.scope)}</p>`;
        })()}
        ${dataTable({
          caption: 'Evaluation bindings',
          columns: [{ label: 'Binding' }, { label: 'Value' }],
          rows: [
            ['<span class="small">Run</span>', '<span class="mono small">run_01 \u00b7 full detection and research</span>'],
            ['<span class="small">Deterministic gates</span>', `${badge('Ran first', 'is-success')}<span class="mono muted small"> a high score never overrides a blocker</span>`],
            ['<span class="small">Judge verdict</span>', `<span class="mono small">${judgeScore()} / 100 across ${JUDGE_RUBRIC.length} dimensions</span>`],
            /* Read from EVAL_PROVENANCE, the same constant the tool ledger cites,
               so the evaluation record and the run that produced it cannot claim
               different versions. */
            ['<span class="small">Rubric version</span>', `<span class="mono small">${esc(EVAL_PROVENANCE.rubric)}</span>`],
            ['<span class="small">Prompt version</span>', `<span class="mono small">${esc(EVAL_PROVENANCE.prompt)}</span>`],
            ['<span class="small">Policy version</span>', `<span class="mono small">${esc(EVAL_PROVENANCE.policy)}</span>`],
            ['<span class="small">Judge model</span>', `<span class="mono small">${esc(EVAL_PROVENANCE.judge)} \u00b7 ${esc(EVAL_PROVENANCE.latency)} \u00b7 ${esc(EVAL_PROVENANCE.cost)}</span>`],
            ['<span class="small">Candidate impact</span>', `${badge('None promoted', '')}<span class="mono muted small"> learning stage: ${esc(state.learning.stage)}</span>`],
          ],
        })}
        <div class="gap-t-4">${banner({ tone: '', icon: '\u2139', title: 'Bindings are what make a score checkable',
          message: 'A verdict without the rubric, prompt, policy and model it was produced under cannot be reproduced or challenged later.' })}</div>` : emptyState({ icon: '\u25ce', title: 'No evaluations yet', description: 'An evaluation is written when a check completes.', action: `<button class="button button-secondary" type="button" data-action="go" data-route="new">Run a check</button>` }),
      })}` : ''}
      ${view === 'policies' ? `${section({
        title: 'The rules ClearCut follows',
        description: 'The rules every check runs under — and the only people who may change them.',
        body: `${dataTable({
          columns: [{ label: 'Rule' }, { label: 'Version' }, { label: 'Who can change it' }],
          rows: [
            ['<strong>What needs a human sign-off</strong>', '<span class="mono">3.2</span>', badge('People only', 'is-danger')],
            ['<strong>How sources are searched</strong>', '<span class="mono">cc-research-17</span>', badge('Tested, then adopted', 'is-success')],
            ['<strong>How ClearCut grades itself</strong>', '<span class="mono">2.4</span>', badge('People only', 'is-danger')],
            ['<strong>The ten clearance categories</strong>', '<span class="mono">1.6</span>', badge('People only', 'is-danger')],
            ['<strong>How long sources are kept</strong>', '<span class="small">Until an Owner deletes the project</span>', badge('Owner only', 'is-warning')],
          ],
        })}
        <div class="gap-t-5">${banner({
          tone: 'is-danger', icon: '⚖', title: 'Never changed automatically',
          message: 'Permissions, sign-off rules, categories, source rankings, blocking rules, privacy and retention settings, and legal-boundary language are only ever changed by an accountable person.',
        })}</div>`,
      })}` : ''}
      ${view === 'operations' ? `${section({
        title: 'Behind the scenes',
        description: 'Background operations and how they recovered. Failures are shown, never hidden.',
        body: `<div class="grid grid-3">
          ${card({ badge: badge('Recovered', 'is-success'), title: 'Music registry retry', body: '<p class="small">The second try worked. Results from the first try were kept.</p>' })}
          ${card({ badge: badge('Retryable', 'is-warning'), title: 'Provider sign-in refresh', body: '<p class="small">Automatic retry, safely tracked so nothing runs twice.</p>', actions: `<button class="button button-secondary button-sm" type="button" data-action="retry-provider">Retry now</button>` })}
          ${card({ badge: badge('Needs a person', 'is-danger'), title: 'Quotation source unavailable', body: '<p class="small">This source forbids automatic access. A reviewer has to check it by hand.</p>' })}
        </div>`,
      })}` : ''}
      ${view === 'activity' ? `${section({
        title: 'Demo controls',
        body: card({
          quiet: true,
          body: '<p class="small">Reset clears this browser\'s simulated project state. Your appearance choice is kept.</p>',
          actions: `${gated('research', `<button class="button button-secondary button-sm" type="button" data-action="rescan-fail-next">Make the next re-check fail</button>`)}${gated('reset', `<button class="button button-danger" type="button" data-action="reset-dialog">Reset demo state</button>`)}`,
        }),
      })}` : ''}
      </div>`,
    });
  }

  function renderNew() {
    const imported = proj().versions.length > 0;
    /* Derived per project, where a single global flag used to answer for both:
       saving details on one project reported step 1 complete on the other. */
    const detailsReady = proj().details !== null;
    const step = !detailsReady ? 1 : !imported ? 2 : 3;
    const modes = ['Paste', 'Fountain', 'PDF', 'FDX'];
    const modeCopy = {
      Paste: 'Paste screenplay text. Scene and dialogue structure is inferred, then confirmed before import.',
      Fountain: 'Fountain scene headings, characters, dialogue, notes, and source offsets are preserved.',
      PDF: 'Text and page coordinates are extracted. Scanned pages are flagged for visual confirmation.',
      FDX: 'Final Draft scene, paragraph, and element identifiers are preserved for exact lineage.',
    };
    const pct = Math.round((proj().runStep / RUN_STEPS.length) * 100);
    const stepHead = (n, title, done, current) => `<div class="cluster step-head"${current ? ' aria-current="step"' : ''}>
      <span class="step-num ${done ? 'is-done' : current ? 'is-current' : ''}" aria-hidden="true">${done ? '✓' : n}</span>
      <h2 class="step-title">${esc(title)}<span class="sr-only"> — step ${n} of 3${done ? ', done' : current ? ', current step' : ''}</span></h2>${done ? badge('Done', 'is-success') : ''}
    </div>`;

    return page({
      width: 'narrow',
      trail: orgTrail('New clearance'),
      eyebrow: 'Start here',
      title: 'New clearance',
      lede: 'Three steps: describe the production, bring in the script, and let ClearCut check it. You make every call after that.',
      notice: prerequisiteNotice('new'),
      body: `
      <section class="section">
        ${stepHead(1, 'Describe the production', detailsReady, step === 1)}
        ${card({
          body: (() => {
            const info = projInfo();
            const typeOpts = ['Independent feature', 'Limited series', 'Series', 'Documentary', 'Short'];
            const stageOpts = ['Pre-production', 'Development', 'Production', 'Post'];
            const opt = (v, cur) => `<option ${v === cur ? 'selected' : ''}>${esc(v)}</option>`;
            return `<div class="form-grid">
            <label class="field field-full"><span class="field-label">Project title</span><input id="np-title" value="${esc(info.title)}"></label>
            <label class="field"><span class="field-label">Production type</span><select id="np-type">${typeOpts.map((v) => opt(v, info.type)).join('')}</select></label>
            <label class="field"><span class="field-label">Stage</span><select id="np-stage">${stageOpts.map((v) => opt(v, info.stage)).join('')}</select></label>
            <label class="field"><span class="field-label">Jurisdiction</span><input id="np-jurisdiction" value="${esc(info.jurisdiction)}"></label>
            <label class="field"><span class="field-label">Target lock date</span><input type="date" id="np-lock" value="${esc(lockInputValue(info.lock))}"></label>
            <label class="field field-full"><span class="field-label">Review brief</span><textarea id="np-brief">${esc(info.brief || '')}</textarea><span class="field-hint">Guides what your reviewers see first.</span></label>
          </div>`;
          })(),
          actions: detailsReady
            ? `<span class="small muted">Details saved.</span><button class="button button-secondary button-sm" type="button" data-action="go" data-route="projects">Done for now</button>`
            : gated('import', `<button class="button button-primary" type="button" data-action="save-project">Continue</button>`),
        })}
      </section>
      <section class="section">
        ${stepHead(2, 'Bring in the script', imported, step === 2)}
        ${step < 2
          ? card({ quiet: true, body: '<p class="small muted">Available once the production details are saved.</p>' })
          : imported
            ? card({ body: banner({ tone: 'is-success', icon: '✓', title: `${proj().versions[0].label} imported`, message: 'The script is saved as a permanent snapshot. Importing again starts a new project.' }) })
            : `${tabsBar({ items: modes.map((m) => ({ label: m, value: m })), active: state.importMode, action: 'set-import-mode', label: 'Import format' })}
        <div class="gap-t-5">${(() => {
          const fmt = importFormat();
          const pasting = state.importMode === 'Paste';
          const chosen = pasting || state.fileChosen;
          return card({
            eyebrow: `${state.importMode} import`,
            title: chosen && !pasting ? esc(fmt.file) : pasting ? 'Paste the screenplay' : `Choose a ${state.importMode} file`,
            /* Ingestion #4: the badge read "Validated" before anything had been
               selected, let alone checked. Validation is a server result, so it
               cannot be shown until there are bytes to validate. */
            badge: chosen
              ? badge(fmt.deterministic ? 'Ready to parse' : 'Ready to parse · model-assisted', 'is-accent')
              : badge('Nothing selected', ''),
            body: `<p class="small">${esc(modeCopy[state.importMode])}</p>
            ${pasting
              ? `<label class="field gap-t-4"><span class="field-label">Screenplay text</span><textarea id="paste-source" rows="5">${esc(proj().pastedSource || 'INT. VELEZ CAMERA SHOP — DUSK\n\nMINA lifts the Vega Camera from a glass case.')}</textarea><span class="field-hint">What you paste here is what the import records.</span></label>`
              : chosen
                ? `<div class="gap-t-4">${banner({ icon: '✓', tone: 'is-accent', title: esc(fmt.file), message: `${esc(fmt.size)} · ${SCRIPT_META.scenes} scenes · ${SCRIPT_META.words} words · ${esc(fmt.detail)}` })}</div>
                   <p class="small muted gap-t-2">Extension, type, and size are checked here as a courtesy. The server re-checks the bytes it actually stores.</p>`
                /* Ingestion #3: there was no way to choose a file at all — the card
                   asserted one was ready. A real target with a keyboard-reachable
                   control replaces the assertion. */
                : `<div class="gap-t-4"><button class="drop-target" type="button" data-action="choose-file" aria-describedby="accept-hint">
                     <span class="drop-glyph" aria-hidden="true">⇧</span>
                     <span class="drop-main">Drop a ${esc(state.importMode)} file here, or choose one</span>
                     <span class="drop-sub" id="accept-hint">Accepts ${state.importMode === 'FDX' ? '.fdx' : state.importMode === 'PDF' ? '.pdf' : '.fountain, .spmd, .txt'} · up to 50 MB</span>
                   </button></div>`}`,
            actions: `${gated('import', `<button class="button button-primary" type="button" data-action="create-v1" ${chosen ? '' : 'aria-disabled="true" data-blocked="1"'}>Import this script</button>`)}<button class="button button-secondary" type="button" data-action="import-error">Preview a damaged file</button>`,
          });
        })()}</div>`}
      </section>
      <section class="section">
        ${stepHead(3, 'Check the script', proj().runComplete, step === 3)}
        ${step < 3
          ? card({ quiet: true, body: '<p class="small muted">Available once the script is imported.</p>' })
          : (() => {
            const running = proj().running;
            const started = running || proj().runComplete;
            return `<div class="cluster-between gap-b-3">
          ${progress(pct)}
          ${running ? `<span class="mono muted small" id="run-elapsed" role="status" aria-live="off">0.0s elapsed</span>` : proj().runComplete ? `<span class="mono muted small">check complete</span>` : ''}
        </div>
        <div class="grid grid-3 gap-t-5" aria-live="polite" aria-busy="${running ? 'true' : 'false'}">${RUN_STEPS.map((s, i) => {
          const done = i < proj().runStep || proj().runComplete;
          const active = running && i === proj().runStep && !proj().runComplete;
          return card({
            accent: active,
            badge: badge(done ? 'Done' : active ? 'Working…' : 'Waiting', done ? 'is-success' : active ? 'is-accent' : ''),
            title: s.label,
            body: `<p class="small">${esc(s.detail)}</p>${
              done
                ? `<div class="gap-t-3">${banner({ tone: 'is-success', icon: '✓', message: esc(s.result) })}</div>`
                : active
                  ? `<div class="cluster gap-t-3"><span class="spinner" role="status" aria-label="Working"></span><span class="small muted">${esc(s.working)}</span></div>
                     <div class="stack-sm gap-t-3" aria-hidden="true"><div class="skeleton" style="width:82%"></div><div class="skeleton" style="width:64%"></div></div>`
                  : ''
            }`,
          });
        }).join('')}</div>
        <div class="cluster gap-t-5">
          ${proj().runComplete
            ? `<button class="button button-primary" type="button" data-action="open-workspace">Read the screenplay</button><button class="button button-secondary" type="button" data-action="go" data-route="items">See the flags</button>`
            : running
              ? `<button class="button button-secondary" type="button" data-action="cancel-run">Cancel check</button><span class="small muted">The agent is working. You can cancel and re-run at any time.</span>`
              : gated('import', `<button class="button button-primary" type="button" data-action="start-run">Start checking</button>`)}
          <button class="button button-secondary" type="button" data-action="open-trace">What happened behind the scenes</button>
        </div>`;
          })()}
      </section>`,
    });
  }

  /* ═══════════════════════════ PROJECT ANALYSIS ═══════════════════════════ */

  function renderProject() {
    const verified = verifiedCount();
    const pct = Math.round((verified / VERIFIABLE_ITEMS.length) * 100);
    const own = flags();
    const attention = own.filter(isAttention);
    const nextStep = !proj().runComplete ? { route: 'new', label: 'Finish checking the script' }
      : !proj().rewriteApproved ? { route: 'items?status=attention', label: 'Work the flags that need you' }
      : !proj().rescanComplete ? { route: 'versions', label: 'Re-check the changed scenes' }
      : !proj().monitoring.reviewed ? { route: 'watch', label: 'Review the source change' }
      : !proj().dossier ? { route: 'report', label: 'Release the clearance report' }
      : { route: 'records', label: 'Read the record of actions' };

    const info = projInfo();
    return page({
      trail: [{ label: state.org.name, route: 'projects' }, { label: info.title }],
      eyebrow: info.type,
      title: info.title,
      lede: `${esc(info.stage)} · ${esc(info.jurisdiction)} · lock ${esc(info.lock)}`,
      actions: `<button class="button button-secondary" type="button" data-action="go" data-route="workspace">Open screenplay</button><button class="button button-primary" type="button" data-action="go" data-route="${nextStep.route}">${esc(nextStep.label)}</button>`,
      notice: prerequisiteNotice('project'),
      body: `${statGrid([
        // An unchecked project has no findings to count, so the stats read as
        // dashes rather than reporting another project's numbers.
        { label: 'Flags raised', value: own.length || '—', hint: own.length ? 'across 10 categories' : 'no check has run', route: 'items' },
        { label: 'Sources verified', value: own.length ? `${verified}/${VERIFIABLE_ITEMS.length}` : '—', hint: 'flags needing a call', tone: own.length && verified >= VERIFIABLE_ITEMS.length ? 'is-success' : '', route: 'items?status=Verified' },
        { label: 'Needs attention', value: own.length ? attention.length : '—', hint: 'blocked, conflict, referred', tone: attention.length ? 'is-warning' : '', route: 'items?status=attention' },
        { label: 'Current version', value: proj().versions.length ? proj().versions.at(-1).label : '—', hint: proj().versions.length ? 'immutable' : 'not imported', route: 'versions' },
      ])}

      <div class="grid grid-2 gap-t-8">
          ${section({
            title: 'Needs a decision',
            description: 'Flags waiting on a person before delivery.',
            actions: `<button class="button button-quiet button-sm" type="button" data-action="go" data-route="items">View all flags</button>`,
            body: attention.length
              ? `<div class="list">${attention.map((i) => `<button class="list-row" type="button" data-action="open-item" data-item="${i.id}">
                  <div class="list-main"><span class="list-title">${esc(i.term)}</span><span class="list-meta"><span class="mono">${i.id}</span><span>${esc(SHORT[i.category])}</span><span>Scene ${i.scene}</span><span>Due ${esc(effectiveDue(i))}</span></span></div>
                  <div class="list-aside">${badge(itemStatus(i), statusTone(itemStatus(i)))}</div>
                </button>`).join('')}</div>`
              : emptyState({ icon: '✓', title: 'Nothing blocking', description: 'All flagged items have a recorded human decision.' }),
          })}
          ${section({
            title: 'Progress',
            body: card({ body: `<div class="stack">
              <div class="cluster-between"><span class="small">Sources verified</span><span class="mono">${pct}%</span></div>
              ${progress(pct)}
              <div class="divider"></div>
              <div class="stack-sm">
                ${[['Script imported', proj().versions.length > 0], ['Sources checked', proj().runComplete], ['Rewrite approved', proj().rewriteApproved], ['Changes re-checked', proj().rescanComplete], ['Source change reviewed', proj().monitoring.reviewed], ['Report released', Boolean(proj().dossier)]]
                  .map(([label, done]) => `<div class="cluster-between"><span class="small ${done ? '' : 'muted'}">${esc(label)}</span>${done ? badge('Done', 'is-success') : badge('Pending')}</div>`).join('')}
              </div>
            </div>` }),
          })}
      </div>`,
    });
  }

  /** Renders a script line, converting a flagged term into a margin-marked
      underline rather than an inline chip, so the reading line stays intact. */
  function scriptLine(line, sceneNumber) {
    const cls = { action: 'script-action', character: 'script-character', dialogue: 'script-dialogue', paren: 'script-paren' }[line.type] || 'script-action';
    if (!line.flag) return `<p class="${cls}">${esc(line.text)}</p>`;

    /* Reads the project's flags. Reading ITEMS meant an unchecked project still
       underlined ten terms in its script pages while the rail beside them
       counted zero. */
    const item = flags().find((i) => i.id === line.flag);
    if (!item) return `<p class="${cls}">${esc(line.text)}</p>`;

    const sev = severityOf(item);
    const selected = proj().activeItem === item.id;
    const resolved = itemStatus(item) === 'Fixed in v2';
    // Prefer the text the reviewer actually approved over the pre-drafted line,
    // or an approved edit never appears in v2.
    const approved = proj().rewriteText || line.rewritten;
    const rewritten = resolved && approved;
    const text = rewritten ? approved : line.text;

    // Underline only the flagged term inside the line, never the whole line.
    const term = item.term;
    const at = text.toLowerCase().indexOf(term.toLowerCase());
    const marked = at >= 0
      ? `${esc(text.slice(0, at))}<button class="flag ${sev.cls} ${selected ? 'is-selected' : ''} ${resolved ? 'is-resolved' : ''}" type="button" data-action="select-flag" data-item="${item.id}" data-scene="${sceneNumber}" aria-pressed="${selected}" title="${esc(item.category)} — ${esc(itemStatus(item))}">${esc(text.slice(at, at + term.length))}</button>${esc(text.slice(at + term.length))}`
      : `<button class="flag ${sev.cls} ${selected ? 'is-selected' : ''}" type="button" data-action="select-flag" data-item="${item.id}" data-scene="${sceneNumber}" aria-pressed="${selected}">${esc(text)}</button>`;

    return `<p class="${cls}">
      <span class="margin-mark ${sev.cls} ${selected ? 'is-selected' : ''}" aria-hidden="true"><span class="mark-glyph">${sev.glyph}</span>${esc(SHORT[item.category])}</span>
      ${marked}
      ${rewritten ? '<span class="revision-mark" aria-hidden="true">*</span>' : ''}
    </p>`;
  }

  function renderWorkspace() {
    /* Resolve against this project's flags, not the global ITEMS array. Reading
       the global set meant a project whose check had never run still rendered
       Borrowed Light's Vega Camera evidence in its drawer — the same leak class
       fixed on the item surface. */
    const active = flags().find((i) => i.id === proj().activeItem) || flags()[0] || null;
    const stock = currentStock();
    const v = currentVersion();
    const grouped = scenesWithItems();
    const paneClass = state.paneTab === 'items' ? 'pane-rail' : state.paneTab === 'evidence' ? 'pane-evidence' : '';
    const drawerOpen = state.drawerOpen !== false;

    const rail = `<aside class="scene-rail" aria-label="Scene navigator">
      <div class="scene-rail-head">
        <h2>Scenes &amp; flags</h2>
        <span class="mono muted">${flags().length}</span>
      </div>
      ${grouped.map((scene) => `<div class="scene-group">
        <button class="scene-group-head" type="button" data-action="goto-scene" data-scene="${scene.number}">
          <span class="scene-number-inline mono">${String(scene.number).padStart(2, '0')}</span>
          <span class="scene-slug-text">${esc(scene.slug)}</span>
          <span class="scene-count">${scene.items.length}</span>
        </button>
        ${scene.items.map((i) => {
          const sev = severityOf(i);
          return `<button class="scene-flag" type="button" data-action="select-flag" data-item="${i.id}" data-scene="${scene.number}" aria-current="${proj().activeItem === i.id}">
            <span class="flag-glyph ${sev.cls}" aria-hidden="true">${sev.glyph}</span>
            <span class="flag-term">${esc(i.term)}</span>
            ${badge(SHORT[i.category])}
          </button>`;
        }).join('')}
      </div>`).join('')}
    </aside>`;

    const pages = grouped.map((scene) => `${scene.pageBreakBefore ? `<div class="page-break"><span>${esc(String(scene.page - 1))}.</span></div>` : ''}
      <section class="script-page" style="--stock:var(--rev-${stock})" aria-label="Page ${scene.page}">
        <span class="stock-strip" aria-hidden="true"></span>
        <span class="page-number" aria-hidden="true">${scene.page}.</span>
        <article class="script-scene" id="scene-${scene.number}">
          <p class="scene-heading">
            <span class="scene-number is-left" aria-hidden="true">${scene.number}</span>
            ${esc(scene.slug)}
            <span class="scene-number is-right" aria-hidden="true">${scene.number}</span>
          </p>
          ${scene.lines.map((l) => scriptLine(l, scene.number)).join('')}
        </article>
      </section>`).join('');

    /* No flags on this project yet — either the check has not run or it found
       nothing. The drawer says which, instead of borrowing another project's item. */
    const drawer = !active ? `<aside class="evidence-drawer" aria-label="Evidence workbench" ${drawerOpen ? '' : 'hidden'}>
      <div class="drawer-head">
        <div class="min-w-0">
          <span class="slug-heading">Evidence</span>
          <h2 class="gap-t-1">${proj().runComplete ? 'Nothing flagged' : 'No check yet'}</h2>
          <p class="small muted gap-t-1">${esc(projInfo().title)}</p>
        </div>
        <button class="icon-button is-bare" type="button" data-action="close-drawer-pane" aria-label="Close evidence panel"><span aria-hidden="true">✕</span></button>
      </div>
      <div class="drawer-body">
        <div class="drawer-phase">
          ${proj().runComplete
            ? banner({ tone: 'is-success', icon: '✓', title: 'No flags on this version', message: 'The check completed and found nothing that needs research.' })
            : banner({ tone: '', icon: '○', title: 'Research has not run', message: 'Flags appear here once the script has been checked. Nothing has been assessed yet.' })}
        </div>
      </div>
      <div class="drawer-foot">
        <div class="stack-sm">
          ${proj().runComplete
            ? `<button class="button button-secondary button-sm" type="button" data-action="go" data-route="items">See all flags</button>`
            : `<button class="button button-primary" type="button" data-action="go" data-route="ingest">Check this script</button>`}
        </div>
      </div>
    </aside>` : `<aside class="evidence-drawer" aria-label="Evidence workbench" ${drawerOpen ? '' : 'hidden'}>
      <div class="drawer-head">
        <div class="min-w-0">
          <span class="slug-heading">${esc(active.category)}</span>
          <h2 class="gap-t-1">${esc(active.term)}</h2>
          <p class="mono muted gap-t-1">${active.id} · Scene ${active.scene} · p.${active.page}</p>
        </div>
        <button class="icon-button is-bare" type="button" data-action="close-drawer-pane" aria-label="Close evidence panel"><span aria-hidden="true">✕</span></button>
      </div>
      <div class="drawer-body">
        ${(() => {
          /* The drawer adapts to the item's evidence phase. It previously rendered
             one confident layout for every case, so a bounded search that found
             nothing looked identical to a verified source, and an item still being
             researched offered a Verify button with nothing behind it. */
          const phase = evidencePhase(active);
          const statusRow = `<div class="cluster">${badge(itemStatus(active), statusTone(itemStatus(active)))}${badge(`${active.severity} priority`, active.severity === 'High' ? 'is-warning' : '')}</div>`;
          const ownership = `<div class="cluster-between">
              <span class="slug-heading">Assignee</span>
              <div class="cluster">${avatar(effectiveOwner(active).split(' ').map((n) => n[0]).join(''), effectiveOwner(active))}<span class="small">${esc(effectiveOwner(active))}</span></div>
            </div>
            <div class="cluster-between"><span class="slug-heading">Due</span><span class="mono small">${esc(effectiveDue(active))}</span></div>`;

          if (phase === 'running') {
            return `${statusRow}
            <div class="drawer-phase">
              <div class="cluster"><span class="spinner" role="status" aria-label="Searching"></span><strong class="small">Searching for sources…</strong></div>
              <p class="small muted gap-t-2">Detection has flagged this passage. Research has not returned yet, so there is nothing to assess.</p>
              <div class="stack-sm gap-t-3" aria-hidden="true"><div class="skeleton" style="width:86%"></div><div class="skeleton" style="width:62%"></div></div>
            </div>
            ${ownership}`;
          }

          if (phase === 'empty') {
            return `${statusRow}
            <div class="drawer-phase">
              ${banner({ tone: '', icon: '⊘', title: 'No attributable source found',
                message: 'A bounded search ended without a source that can be cited. This is unresolved — not a clearance result.' })}
              <p class="small muted gap-t-3">There is nothing to verify or rule out. A human decision here would have no evidence under it.</p>
            </div>
            ${ownership}`;
          }

          if (phase === 'referred') {
            return `${statusRow}
            <div class="drawer-phase">
              ${banner({ tone: 'is-warning', icon: '↗', title: 'With a music specialist',
                message: 'Referred for a bounded second look. The verified evidence is held pending, not withdrawn.' })}
              <p class="small muted gap-t-3">The specialist’s response is recorded on the full record. No further call is expected here until it arrives.</p>
            </div>
            ${ownership}`;
          }

          const sourceCard = `<div class="source-card">
              <div class="cluster-between"><span class="slug-heading">Best available source</span>${badge(active.authority)}</div>
              <p class="small gap-t-2"><strong>${esc(active.source)}</strong></p>
              <blockquote class="small">${esc(active.excerpt)}</blockquote>
              <div class="source-foot"><span class="mono muted">retrieved Aug 19</span><button class="button button-quiet button-sm" type="button" data-action="open-source">Provenance</button></div>
            </div>`;

          const summary = (() => {
            const all = sourcesFor(active.id);
            const disagreeing = all.filter((s) => s.stance === 'conflicts').length;
            if (!all.length) return '';
            return `<button class="drawer-source-summary" type="button" data-action="open-item" data-item="${active.id}">
              <span><strong>${all.length}</strong> source${all.length === 1 ? '' : 's'} retrieved${disagreeing ? ` · <strong>${disagreeing}</strong> disagree${disagreeing === 1 ? 's' : ''}` : ''}</span>
              <span class="drawer-source-go" aria-hidden="true">→</span>
            </button>`;
          })();

          const confidence = `<div>
              <div class="cluster-between"><span class="slug-heading">Confidence</span><span class="mono">${active.confidence}%</span></div>
              <div class="meter gap-t-2"><span style="width:${active.confidence}%"></span></div>
            </div>`;

          if (phase === 'decided') {
            const decision = proj().evidenceDecisions[active.id];
            return `${statusRow}
            <div class="drawer-phase">
              ${banner({ tone: 'is-success', icon: '✓',
                title: decision === 'resolved-on-v2' ? 'Fixed in v2' : 'Verified',
                message: decision === 'resolved-on-v2'
                  ? 'The passage was rewritten and the new version carries the fix. The original remains readable.'
                  : (() => {
                      const b = proj().decisionBinding[active.id];
                      return b
                        ? `Recorded by ${esc(b.actor)} against ${esc(b.version)} with a stated reason.`
                        : 'Recorded with a stated reason.';
                    })() })}
            </div>
            ${sourceCard}
            ${summary}
            ${confidence}
            ${ownership}`;
          }

          return `${statusRow}
          ${sourceCard}
          ${summary}
          ${active.conflict ? banner({ tone: 'is-warning', icon: '⚠', title: uncertaintyTitle(active), message: esc(active.conflict) }) : ''}
          ${confidence}
          ${ownership}`;
        })()}
      </div>
      <div class="drawer-foot">
        ${(() => {
          /* Actions follow the phase. Offering Verify while research is still
             running, or on an item with no attributable source, invited a decision
             with nothing under it. */
          const phase = evidencePhase(active);
          const full = `<button class="button button-secondary button-sm" type="button" data-action="open-item" data-item="${active.id}">Full record</button>`;
          /* Reading an earlier draft: a new call here would bind evidence to text
             that is no longer current, so the actions are withdrawn and say why
             rather than being silently absent. */
          if (viewingSuperseded()) {
            return `<div class="stack-sm">
              <p class="small muted">${esc(currentVersion().label)} has been superseded by ${esc(latestVersion().label)}. Decisions are recorded on the current version.</p>
              <button class="button button-secondary button-sm" type="button" data-action="set-version" data-version="${esc(latestVersion().label)}">Return to ${esc(latestVersion().label)}</button>
              ${full}
            </div>`;
          }
          if (phase === 'running') {
            return `<div class="stack-sm"><p class="small muted">Actions open once research returns.</p>${full}</div>`;
          }
          if (phase === 'empty' || phase === 'referred' || phase === 'decided') {
            return `<div class="stack-sm">${full}</div>`;
          }
          return `<div class="stack-sm">
            ${gated('decide', `<button class="button button-primary" type="button" data-action="evidence-dialog" data-decision="accepted" data-item="${active.id}">Verify this source</button>`)}
            <div class="cluster">
              ${gated('decide', `<button class="button button-secondary button-sm" type="button" data-action="evidence-dialog" data-decision="rejected" data-item="${active.id}">Rule this source out</button>`)}
              ${full}
            </div>
          </div>`;
        })()}
      </div>
    </aside>`;

    return page({
      trail: projectTrail('Screenplay'),
      title: `Screenplay — ${projInfo().title}`,
      srTitle: true,
      width: 'flush is-stage',
      notice: viewingSuperseded()
        ? `<div class="page-notice">${banner({
            tone: 'is-warning', icon: '◔',
            title: `Reading ${esc(currentVersion().label)} — not the current version`,
            message: `${esc(latestVersion().label)} is current. Evidence and decisions shown here belong to ${esc(currentVersion().label)}. This view is read-only.`,
            action: `<button class="button button-secondary button-sm" type="button" data-action="set-version" data-version="${esc(latestVersion().label)}">Return to ${esc(latestVersion().label)}</button>`,
          })}</div>`
        : prerequisiteNotice('workspace'),
      body: `<div class="mobile-pane-tabs">${tabsBar({
        items: [{ label: 'Script', value: 'script' }, { label: 'Scenes', value: 'items' }, { label: 'Evidence', value: 'evidence' }],
        active: state.paneTab, action: 'set-pane', label: 'Workspace view',
      })}</div>
      <div class="script-surface ${paneClass} ${drawerOpen ? 'is-drawer-open' : ''}">
        ${rail}
        <div class="script-scroll">
          <div class="script-stage">
            <div class="cluster-between script-stage-head">
              <span class="slug-heading">${esc(projInfo().title)} — ${stageVersionLabel(v, stock)}</span>
              ${drawerOpen ? '' : `<button class="button button-secondary button-sm" type="button" data-action="open-drawer-pane">Show evidence</button>`}
            </div>
            ${pages}
            <div class="page-break script-stage-end"><span>END OF EXCERPT — ${EXCERPT.scenes} of ${SCRIPT_META.scenes} scenes, pages ${EXCERPT.firstPage}–${EXCERPT.lastPage} of ${SCRIPT_META.pages}</span></div>
          </div>
        </div>
        ${drawer}
      </div>`,
    });
  }

  /** Free-text match over the fields a reviewer would search: term, id,
      category, owner, and the script line. Empty query matches everything. */
  function matchesItemSearch(item) {
    const q = (state.itemsSearch || '').trim().toLowerCase();
    if (!q) return true;
    return [item.term, item.id, item.category, effectiveOwner(item), item.context, item.source]
      .some((v) => String(v || '').toLowerCase().includes(q));
  }

  function renderItems() {
    const q = (state.itemsSearch || '').trim();
    const searched = flags().filter(matchesItemSearch);
    const attention = searched.filter(isAttention);
    const filtered = state.itemFilter === 'all' ? searched
      : state.itemFilter === 'attention' ? attention
      : searched.filter((i) => itemStatus(i) === state.itemFilter);
    // Counts reflect the current search so the filter tabs never promise rows
    // the search has already excluded.
    const counts = { all: searched.length, attention: attention.length };
    ITEM_STATUSES.forEach((s) => { counts[s] = searched.filter((i) => itemStatus(i) === s).length; });
    const filters = [
      { label: 'All', value: 'all', count: counts.all },
      { label: 'Attention', value: 'attention', count: counts.attention },
      ...ITEM_STATUSES.filter((s) => counts[s]).map((s) => ({ label: s, value: s, count: counts[s] })),
    ];
    const sorted = sortItems(filtered);

    const sortBar = `<div class="cluster cluster-wrap gap-b-3" role="group" aria-label="Sort items">
        <span class="field-label flush-margin">Sort</span>
        ${Object.keys(SORT_LABELS).map((key) => {
          const active = state.itemsSort.key === key;
          return `<button class="sort-btn ${active ? 'is-active' : ''}" type="button" data-action="set-items-sort" data-key="${key}" aria-pressed="${active}">${SORT_LABELS[key]}${active ? `<span class="sort-dir" aria-hidden="true">${state.itemsSort.dir === 'asc' ? '↑' : '↓'}</span>` : ''}</button>`;
        }).join('')}
        <span class="field-label sort-group-label">Group</span>
        <select class="select-inline" data-action="set-items-group" aria-label="Group items by">
          ${Object.entries({ none: 'No grouping', scene: 'Scene', category: 'Category', owner: 'Owner', due: 'Due date' }).map(([v, l]) => `<option value="${v}" ${state.itemsGroup === v ? 'selected' : ''}>${l}</option>`).join('')}
        </select>
      </div>`;

    const sel = state.selectedItems || [];
    const bulkBar = sel.length ? `<div class="banner is-accent gap-b-4">
        <span class="banner-icon" aria-hidden="true">☑</span>
        <div class="banner-body"><strong>${sel.length} item${sel.length === 1 ? '' : 's'} selected</strong><p>Bulk actions apply one governed decision per item and write a receipt for each.</p></div>
        <div class="cluster">
          ${gated('reassign', `<button class="button button-primary button-sm" type="button" data-action="bulk-assign">Assign…</button>`)}
          <button class="button button-secondary button-sm" type="button" data-action="bulk-clear">Clear</button>
        </div>
      </div>` : '';

    const itemRow = (i) => {
      const status = itemStatus(i);
      const tone = status === 'Must fix' ? 'is-row-danger' : isAttention(i) ? 'is-row-warning' : status === 'Needs your call' ? 'is-row-accent' : '';
      return `<div class="list-row is-static${tone ? ` ${tone}` : ''}">
      <label class="bulk-check" title="Select ${esc(i.term)}">
        <input type="checkbox" data-action="toggle-select" data-item="${i.id}" ${sel.includes(i.id) ? 'checked' : ''} aria-label="Select ${esc(i.term)}">
      </label>
      <button class="list-main list-main-button" type="button" data-action="open-item" data-item="${i.id}">
        <span class="list-title">${esc(i.term)}</span>
        <span class="list-meta"><span class="mono">${i.id}</span><span>${esc(i.category)}</span><span>Scene ${i.scene} · p.${i.page}</span><span class="notif-project-label">${sourcesFor(i.id).length} sources${sourcesFor(i.id).some((s) => s.stance === 'conflicts') ? ' · conflict' : ''}</span><span>${i.confidence}%</span></span>
      </button>
      <div class="list-aside">${avatar(effectiveOwner(i).split(' ').map((n) => n[0]).join(''), effectiveOwner(i))}${badge(i.severity, i.severity === 'High' ? 'is-warning' : '')}${badge(status, statusTone(status))}</div>
    </div>`;
    };

    /* Three distinct empty states, not one. A project with no completed check
       has no flags to filter, so offering "clear the filter" pointed at a
       control that could not help. */
    const emptyList = !flags().length
      ? emptyState({ icon: '☰', title: 'No flags yet', description: 'Flags appear once a script has been imported and checked.', action: `<button class="button button-primary" type="button" data-action="go" data-route="new">Check a script</button>` })
      : q
      ? emptyState({ icon: '☰', title: `No flags match “${esc(q)}”`, description: 'Try a different term, or clear the search to see every flag.', action: `<button class="button button-secondary" type="button" data-action="clear-items-search">Clear search</button>` })
      : emptyState({ icon: '☰', title: 'No items match this filter', description: 'Clear the filter to see all clearance items.', action: `<button class="button button-secondary" type="button" data-action="set-item-filter" data-value="all">Show all items</button>` });

    const listView = filtered.length
      ? groupItems(sorted).map((g) => `${g.label ? `<div class="group-head"><h3>${esc(g.label)}</h3><span class="mono muted">${g.items.length} item${g.items.length === 1 ? '' : 's'}</span></div>` : ''}<div class="list">${g.items.map(itemRow).join('')}</div>`).join('')
      : emptyList;

    const boardCounts = {};
    ITEM_STATUSES.forEach((s) => { boardCounts[s] = filtered.filter((i) => itemStatus(i) === s).length; });
    const boardView = `<div class="board">${ITEM_STATUSES.filter((s) => boardCounts[s]).map((status) => `<div class="board-column">
      <div class="board-head"><h3>${esc(status)}</h3><span class="mono muted">${boardCounts[status]}</span></div>
      ${sortItems(filtered.filter((i) => itemStatus(i) === status)).map((i) => `<button class="board-card" type="button" data-action="open-item" data-item="${i.id}">
        <strong>${esc(i.term)}</strong>
        <span class="list-meta"><span class="mono">${i.id}</span><span>Sc ${i.scene}</span></span>
      </button>`).join('')}
    </div>`).join('')}</div>`;

    return page({
      trail: projectTrail('Clearance items'),
      eyebrow: 'Analysis',
      title: 'Clearance flags',
      lede: 'Everything the check flagged, with its scene, owner, and where your call stands.',
      actions: tabsBar({ items: [{ label: 'List', value: 'list' }, { label: 'Board', value: 'board' }], active: state.itemsView, action: 'set-items-view', label: 'Item view' }),
      notice: prerequisiteNotice('items'),
      body: `<div class="cluster-between cluster-wrap worklist-toolbar">
        <div class="search-field">
          <label class="search-field">
            <span class="search-icon" aria-hidden="true">⌕</span>
            <input type="search" id="items-search" data-action="set-items-search" value="${esc(q)}" placeholder="Search flags — term, scene text, owner…" aria-label="Search flags">
          </label>
        </div>
        ${q ? `<span class="small muted" role="status">${searched.length} match${searched.length === 1 ? '' : 'es'} for “${esc(q)}”${searched.length ? '' : ' — nothing found'}</span>` : ''}
      </div>
      <div class="gap-b-5">${tabsBar({ items: filters, active: state.itemFilter, action: 'set-item-filter', label: 'Filter by status' })}</div>
      ${bulkBar}
      ${state.itemsView === 'board' ? boardView : `${sortBar}${listView}`}`,
    });
  }

  function renderItem() {
    /* Resolution order: an explicit ?id= wins, then the last selection. A missing
       or unknown id renders not-found naming what was asked for — substituting
       another record made a wrong link look like a working one, which is how the
       audit found a CC-110 assignment notification opening CC-101. */
    const requested = state.requestedItem || proj().activeItem;
    const item = flags().find((i) => i.id === requested)
      || (state.requestedItem ? null : flags()[0] || null);

    if (!item) {
      const scoped = flags();
      return page({
        trail: [{ label: state.org.name, route: 'projects' }, { label: projInfo().title, route: 'project' }, { label: 'Items', route: 'items' }, { label: esc(requested || 'Unknown') }],
        eyebrow: 'Clearance flag',
        title: 'That flag is not on this project',
        lede: 'The address names a record this project does not hold.',
        notice: prerequisiteNotice('item'),
        body: emptyState({
          icon: '⊘',
          title: requested ? `No flag ${esc(requested)} in ${esc(projInfo().title)}` : 'No flag selected',
          description: scoped.length
            ? `This project has ${scoped.length} flag${scoped.length === 1 ? '' : 's'}. The id may belong to another project, or the flag may have been removed by a later version.`
            : 'This project has no flags yet. A check has to run before any flag exists.',
          action: `<button class="button button-primary" type="button" data-action="go" data-route="items">See this project’s flags</button>`,
        }),
      });
    }

    const status = itemStatus(item);
    const comments = proj().comments.filter((c) => c.item === item.id);
    const assignee = proj().assignments[item.id] || item.owner;

    return page({
      trail: [{ label: state.org.name, route: 'projects' }, { label: projInfo().title, route: 'project' }, { label: 'Items', route: 'items' }, { label: item.id }],
      eyebrow: item.category,
      title: item.term,
      lede: `Scene ${item.scene}, page ${item.page} · ${esc(item.severity)} priority`,
      actions: `${(() => {
        /* Walking a queue is the common case: a reviewer filters to "needs your
           call" and works down the list. Without prev/next they must return to
           the worklist between every item, losing their place each time. The
           cycle follows the same filter the worklist is showing, so the position
           readout and the list agree. */
        const q = (state.itemsSearch || '').trim();
        const searched = flags().filter(matchesItemSearch);
        const scope = state.itemFilter === 'all' ? searched
          : state.itemFilter === 'attention' ? searched.filter(isAttention)
          : searched.filter((i) => itemStatus(i) === state.itemFilter);
        const ordered = sortItems(scope);
        const at = ordered.findIndex((i) => i.id === item.id);
        if (at < 0 || ordered.length < 2) return '';
        const prev = ordered[at - 1];
        const next = ordered[at + 1];
        const label = state.itemFilter === 'all' ? 'flags' : state.itemFilter === 'attention' ? 'needing attention' : state.itemFilter.toLowerCase();
        return `<div class="item-stepper">
          ${prev ? `<button class="icon-button" type="button" data-action="open-item" data-item="${prev.id}" aria-label="Previous flag: ${esc(prev.term)}"><span aria-hidden="true">←</span></button>` : '<span class="icon-button is-spent" aria-hidden="true">←</span>'}
          <span class="item-stepper-count small muted">${at + 1} of ${ordered.length} ${esc(label)}</span>
          ${next ? `<button class="icon-button" type="button" data-action="open-item" data-item="${next.id}" aria-label="Next flag: ${esc(next.term)}"><span aria-hidden="true">→</span></button>` : '<span class="icon-button is-spent" aria-hidden="true">→</span>'}
        </div>`;
      })()}${badge(status, statusTone(status))}<button class="button button-secondary" type="button" data-action="print-record" data-item="${item.id}">Print this record</button><button class="button button-secondary" type="button" data-action="go" data-route="items">Back to items</button>`,
      notice: prerequisiteNotice('item'),
      /* Paper carries no address bar, so a printed record has to say what it is,
         which project and version it belongs to, and when it was printed. */
      body: `<div class="print-only print-provenance">
        <p class="mono small">${esc(state.org.name)} · ${esc(projInfo().title)} · ${esc(boundVersionLabel())}</p>
        <p class="mono small">Flag ${esc(item.id)} · printed by ${esc(ACTOR.name)} · <span data-print-stamp>${esc(fmtStamp(new Date().toISOString()))}</span></p>
        <p class="small">A working record, not a clearance. Decisions belong to qualified humans.</p>
      </div>
      <div class="grid grid-sidebar">
        <div>
          ${section({
            title: 'Script context',
            body: card({ quiet: true, body: `<p class="script-quote">${esc(item.context)}</p><p class="small muted gap-t-3">Anchored to a stable span, so the record survives revisions.</p>` }),
          })}
${section({
            title: 'Evidence',
            description: `Sourced claims with authority tier and retrieval metadata. ${sourcesFor(item.id).length} sources retrieved for this flag.`,
            body: `<div class="source-card">
              <div class="cluster-between"><span class="field-label">Primary source</span>${badge(item.authority)}</div>
              <p class="small gap-t-2"><strong>${esc(item.source)}</strong></p>
              <blockquote class="small">${esc(item.excerpt)}</blockquote>
              <div class="source-foot">
                <span class="mono muted">retrieved Aug 19 · 15:42 · snapshot retained</span>
                <button class="button button-quiet button-sm" type="button" data-action="open-source">Where this came from</button>
              </div>
            </div>
            <!-- Every retrieved source, including the ones that disagree: the
                 record is the whole set, not the one that reads best. -->
            <div class="gap-t-4">${dataTable({
              caption: `Sources retrieved for ${item.id}`,
              columns: [{ label: 'Source' }, { label: 'Authority' }, { label: 'What it says' }, { label: 'Bearing' }],
              rows: sourcesFor(item.id).map((s) => [
                `<strong class="small">${esc(s.title)}</strong><br><span class="mono muted">${esc(s.id)} · ${esc(s.retrieved)}</span>`,
                badge(s.authority),
                `<span class="small">${esc(s.claim)}</span>`,
                badge(s.stance === 'conflicts' ? 'Disagrees' : s.stance === 'supports' ? 'Supports' : 'Context', s.stance === 'conflicts' ? 'is-warning' : ''),
              ]),
            })}</div>
            <div class="gap-t-4">
              <div class="cluster-between"><span class="field-label">Confidence</span><span class="mono">${item.confidence}%</span></div>
              <div class="meter gap-t-2"><span style="width:${item.confidence}%"></span></div>
            </div>
            ${item.conflict ? `<div class="gap-t-4">${banner({ tone: 'is-warning', icon: '⚠', title: `${uncertaintyTitle(item)}, not resolved automatically`, message: esc(item.conflict) })}</div>` : ''}`,
          })}
          ${section({
            title: `Review record (${comments.length} comment${comments.length === 1 ? '' : 's'})`,
            lede: 'What was said and what was done, in the order it happened.',
            body: `${(() => {
              const entries = itemTimeline(item.id);
              if (!entries.length) return `<p class="small muted">Nothing recorded on this flag yet.</p>`;
              /* Replies hang off their parent, one level only. Deeper nesting turns
                 a review record into a forum nobody can audit at a glance. */
              const replies = (parentId) => proj().comments.filter((c) => c.parent === parentId);
              return `<ol class="record-timeline">${entries.map((e) => {
                if (e.type === 'action') {
                  return `<li class="record-entry is-action">
                    <span class="record-mark" aria-hidden="true">◈</span>
                    <div class="record-main">
                      <div class="cluster-between">
                        <strong class="small">${esc(e.receipt.title)}</strong>
                        <span class="mono muted small">${esc(fmtStamp(e.at))}</span>
                      </div>
                      <p class="small muted gap-t-1">${esc(e.receipt.actor)} · ${esc(e.receipt.detail)}</p>
                      <p class="mono muted small gap-t-1">receipt ${esc(e.receipt.id)}</p>
                    </div>
                  </li>`;
                }
                const c = e.comment;
                if (c.parent) return '';
                const kids = replies(c.id);
                return `<li class="record-entry">
                  <span class="record-mark" aria-hidden="true">○</span>
                  <div class="record-main">
                    <div class="cluster-between">
                      <strong class="small">${esc(c.actor)}</strong>
                      <span class="mono muted small">${esc(fmtStamp(c.at))}${c.editedAt ? ' · edited' : ''}</span>
                    </div>
                    <p class="small gap-t-1">${commentBody(c.text)}</p>
                    ${c.revisions && c.revisions.length ? `<details class="record-history gap-t-2">
                      <summary class="small muted">Edit history (${c.revisions.length})</summary>
                      ${c.revisions.map((r) => `<p class="small muted gap-t-2"><span class="mono">${esc(fmtStamp(r.at))}</span> — ${esc(r.text)}</p>`).join('')}
                    </details>` : ''}
                    <div class="cluster gap-t-2">
                      ${gated('comment', `<button class="button button-quiet button-sm" type="button" data-action="reply-dialog" data-comment="${c.id}" data-item="${item.id}">Reply</button>`)}
                      ${c.actor === ACTOR.name ? `<button class="button button-quiet button-sm" type="button" data-action="edit-comment-dialog" data-comment="${c.id}">Edit</button>` : ''}
                    </div>
                    ${kids.length ? `<ul class="record-replies">${kids.map((k) => `<li>
                      <div class="cluster-between">
                        <strong class="small">${esc(k.actor)}</strong>
                        <span class="mono muted small">${esc(fmtStamp(k.at))}${k.editedAt ? ' · edited' : ''}</span>
                      </div>
                      <p class="small gap-t-1">${commentBody(k.text)}</p>
                      ${k.revisions && k.revisions.length ? `<details class="record-history gap-t-2">
                        <summary class="small muted">Edit history (${k.revisions.length})</summary>
                        ${k.revisions.map((r) => `<p class="small muted gap-t-2"><span class="mono">${esc(fmtStamp(r.at))}</span> — ${esc(r.text)}</p>`).join('')}
                      </details>` : ''}
                      ${k.actor === ACTOR.name ? `<div class="cluster gap-t-2"><button class="button button-quiet button-sm" type="button" data-action="edit-comment-dialog" data-comment="${k.id}">Edit</button></div>` : ''}
                    </li>`).join('')}</ul>` : ''}
                  </div>
                </li>`;
              }).join('')}</ol>`;
            })()}
            <div class="gap-t-4 screen-only">
              <label class="field"><span class="field-label">Add a comment to the review record</span><textarea id="item-comment" placeholder="Context, a question, or an instruction. Type @ and a name to bring somebody in…"></textarea></label>
              <p class="small muted gap-t-1">Mentioning a member notifies them. ${state.members.filter((m) => m.status === 'Active').map((m) => `<span class="mono">@${esc(m.name.split(' ')[0])}</span>`).join(' ')}</p>
              <div class="cluster gap-t-3">${gated('comment', `<button class="button button-secondary" type="button" data-action="add-comment" data-item="${item.id}">Add comment</button>`)}</div>
            </div>`,
          })}
        </div>
        <div class="stack-lg">
          ${card({
            eyebrow: 'Your call',
            body: `<p class="small muted">Each call is recorded with your name, the script version, and the reason.</p>${can('decide') ? '' : `<p class="small gap-t-2 text-warning">You are viewing as ${esc(actorRole())}. Recording calls needs a Reviewer or higher.</p>`}`,
            actions: `<div class="grid grid-2 full">
              ${gated('decide', `<button class="button button-primary" type="button" data-action="evidence-dialog" data-decision="accepted" data-item="${item.id}">Verify this source</button>`)}
              ${gated('decide', `<button class="button button-secondary" type="button" data-action="evidence-dialog" data-decision="rejected" data-item="${item.id}">Rule this source out</button>`)}
              ${gated('refer', `<button class="button button-secondary" type="button" data-action="referral-dialog">Refer to specialist</button>`)}
              ${(() => {
                /* The control follows the two-hand flow. Gating the whole thing on
                   'rewrite' locked the approver out of the approval step: a
                   Reviewer cannot propose, and was therefore unable to open the
                   dialog they are the only one allowed to finish. */
                const prop = proposalFor(item.id);
                if (!prop) return gated('rewrite', `<button class="button button-secondary" type="button" data-action="rewrite-dialog" data-item="${item.id}">Propose a rewrite</button>`);
                if (prop.approvedAt || (item.id === 'CC-110' && proj().rewriteApproved)) {
                  return `<button class="button button-secondary" type="button" data-action="rewrite-dialog" data-item="${item.id}">Approved rewrite record</button>`;
                }
                const label = can('approve-rewrite') ? 'Review proposed rewrite' : 'Proposed rewrite · awaiting approval';
                return gated(can('approve-rewrite') ? 'approve-rewrite' : 'rewrite',
                  `<button class="button button-secondary" type="button" data-action="rewrite-dialog" data-item="${item.id}">${label}</button>`);
              })()}
            </div>`,
          })}
          ${card({
            eyebrow: 'Ownership',
            body: `<div class="stack-sm">
              <div class="cluster-between"><span class="small">Assignee</span><div class="cluster">${avatar(assignee.split(' ').map((n) => n[0]).join(''), assignee)}<span class="small">${esc(assignee)}</span></div></div>
              <div class="cluster-between"><span class="small">Due</span><span class="mono">${esc(effectiveDue(item))}</span></div>
              <div class="cluster-between"><span class="small">Priority</span>${badge(item.severity, item.severity === 'High' ? 'is-warning' : '')}</div>
            </div>`,
            actions: gated('reassign', `<button class="button button-secondary button-sm" type="button" data-action="assign-dialog" data-item="${item.id}">Reassign</button>`),
          })}
          ${card({
            eyebrow: 'Related',
            body: `<div class="stack-sm">${flags().filter((i) => i.category === item.category && i.id !== item.id).slice(0, 3).map((i) => `<button class="list-row list-row-tight" type="button" data-action="open-item" data-item="${i.id}"><div class="list-main"><span class="list-title">${esc(i.term)}</span><span class="list-meta"><span class="mono">${i.id}</span></span></div></button>`).join('') || '<p class="small muted">No other items in this category.</p>'}</div>`,
          })}
        </div>
      </div>`,
    });
  }


  /* ═══════════════════════════ REVIEW & GOVERNANCE ═══════════════════════════ */

  function renderVersions() {
    const versions = proj().versions;
    return page({
      trail: projectTrail('Versions'),
      eyebrow: 'Saved snapshots',
      title: 'Script versions',
      lede: 'Think of each version as a saved copy of the script that can never be changed. A rewrite never edits the old copy — it saves a new one, and only the changed scenes get re-checked.',
      notice: prerequisiteNotice('versions'),
      body: `${versions.length ? `${section({
        title: 'Version history',
        description: 'The coloured dot is a film convention: revised script pages are printed on coloured stock — white first, then blue, pink, yellow — so crews can see at a glance who has the current pages.',
        body: `${dataTable({
          columns: [{ label: 'Version' }, { label: 'Where it came from' }, { label: 'Based on' }, { label: 'State' }],
          rows: [...versions].reverse().map((v, i) => [
            `${versionChip(v)}<br><span class="small muted stock-note">${stockFor(v.label)} pages</span>`,
            `<span class="small">${esc(v.source)}</span>`,
            v.parent ? `<span class="mono">${esc(v.parent)}</span>` : '<span class="muted small">first</span>',
            i === 0 ? badge('Current', 'is-success') : badge('Locked'),
          ]),
        })}
        <details class="tech-details gap-t-3">
          <summary>Snapshot IDs (technical)</summary>
          <div class="stack-sm gap-t-2">${versions.map((v) => `<span class="mono">${esc(v.label)} · ${esc(v.hash)}</span>`).join('')}</div>
        </details>`,
      })}
      ${versions.length > 1 ? section({
        title: 'What the rewrite changed',
        description: 'Only the flagged passage changed. Every other scene, source, and decision carried forward untouched.',
        body: `<div class="diff">
          <section><div class="cluster-between"><span class="field-label">v1 · original</span>${badge('Locked')}</div><p class="diff-text"><del>Her relapse began after she left the East Mercer clinic, room 214.</del></p><p class="small muted gap-t-3">Blocked by the privacy rule. Source history preserved.</p></section>
          <section><div class="cluster-between"><span class="field-label">v2 · approved</span>${badge('Current', 'is-success')}</div><p class="diff-text"><ins>She struggled again after she left treatment.</ins></p><p class="small muted gap-t-3">Approved by ${esc(ACTOR.name)} with a recorded rationale.</p></section>
        </div>
        <div class="gap-t-5">${statGrid([
          { label: 'Passages changed', value: 1, hint: `of ${SCRIPT_META.passages}` },
          { label: 'Flags re-checked', value: rescanScope().all.length, hint: `${rescanScope().direct.map((a) => a.id).join(', ') || 'none'} direct, ${rescanScope().nearby.map((a) => a.id).join(', ') || 'none'} nearby` },
          { label: 'Sources reused', value: DEMO_FACTS.rescanUntouched, hint: 'no re-checking needed' },
        ], 3)}</div>`,
      }) : `${section({
        title: 'What this version contains',
        description: 'The first import establishes the anchor every later decision refers back to.',
        body: `${statGrid([
          { label: 'Scenes', value: SCRIPT_META.scenes, hint: 'parsed and numbered' },
          { label: 'Pages', value: SCRIPT_META.pages, hint: 'production count' },
          { label: 'Passages', value: SCRIPT_META.passages, hint: 'addressable spans' },
          { label: 'Words', value: SCRIPT_META.words, hint: 'in the imported draft' },
        ], 4)}`,
      })}
      ${section({
        title: 'How the next version gets created',
        description: 'There are exactly two paths. Both leave this version locked and readable forever.',
        body: `<div class="grid grid-2">
          ${card({
            eyebrow: 'Path one',
            title: 'An approved rewrite',
            body: `<p class="small">An Editor proposes replacement text on a flag. A Reviewer approves it. Approval writes the next version, computes what changed, and queues a re-check of only the affected flags.</p>
            <p class="small muted gap-t-3">The proposer cannot approve their own rewrite — that separation is what makes the new version accountable.</p>`,
            actions: `<button class="button button-secondary button-sm" type="button" data-action="go" data-route="items">Open the flags</button>`,
          })}
          ${card({
            eyebrow: 'Path two',
            title: 'A re-import',
            body: `<p class="small">Upload a new draft when the rewrite happened outside ClearCut. The parser diffs stable element identities to work out which flags moved, changed, or disappeared.</p>
            <p class="small muted gap-t-3">Re-import never replaces a version. It appends the next one and carries settled evidence forward where the text is unchanged.</p>`,
            actions: `<button class="button button-secondary button-sm" type="button" data-action="go" data-route="new">Import a draft</button>`,
          })}
        </div>`,
      })}`}
      ${rescanSection()}`
      : emptyState({ icon: '⑂', title: 'No versions yet', description: 'Bring in a screenplay to create the first saved snapshot.', action: `<button class="button button-primary" type="button" data-action="go" data-route="new">Start a new clearance</button>` })}`,
    });
  }

  /** The re-check that follows an approved rewrite — now part of Versions,
      since it is the consequence of a version change, not its own surface. */
  function rescanSection() {
    const done = proj().rescanComplete;
    if (!proj().rewriteApproved) {
      return banner({ icon: 'ℹ', title: 'Re-check runs after a rewrite is approved', message: 'When you approve a rewrite, only the affected flags are re-checked — everything you already settled stays settled.' });
    }
    /* Every figure derives from the computed scope and the flag count, so the
       card, its prose, and selectiveRescan's receipt can never disagree. */
    const scope = rescanScope();
    const affected = scope.all.length;
    const untouched = scope.untouched;
    const directNames = scope.direct.map((a) => a.id).join(' and ');
    const nearbyNames = scope.nearby.map((a) => a.id).join(' and ');
    const saved = `${Math.round((untouched / DEMO_FACTS.flags) * 100)}%`;
    return section({
      title: done ? 'Changed scenes re-checked' : proj().rescanFailed ? 'The re-check stopped partway' : 'Re-check the changed scenes',
      description: 'Only what changed gets re-checked. Re-running everything would churn decisions you already made.',
      body: `${statGrid([
        { label: 'Directly affected', value: scope.direct.length, hint: `${directNames || 'none'} rewritten` },
        { label: 'Nearby, re-checked', value: scope.nearby.length, hint: `${nearbyNames || 'none'} same scene` },
        { label: 'Left untouched', value: untouched, hint: 'sources reused as-is' },
        { label: 'Checks saved', value: saved, hint: 'versus starting over', tone: 'is-success' },
      ], 4)}
      <div class="gap-t-5">${card({
        eyebrow: 'Scope',
        title: done ? 'Everything affected is current on v2' : `${affected} flags are ready to re-check`,
        body: `<p class="small">${done
          ? `${directNames} is fixed in ${esc(latestVersion()?.label || 'the new version')}${nearbyNames ? ` and ${nearbyNames} is still open for review` : ''}. The other ${untouched} flags kept their original source records, so nothing you settled was disturbed.`
          : `ClearCut will re-check ${directNames}${nearbyNames ? ` and its neighbour ${nearbyNames}` : ''} against ${esc(latestVersion()?.label || 'the new version')}. The remaining ${untouched} flags keep their existing source history without another lookup.`}</p>
        <div class="gap-t-4">${dataTable({
          columns: [{ label: 'Flag' }, { label: 'Why' }, { label: 'Result' }],
          rows: scope.all.map((a) => {
            const item = ITEMS.find((i) => i.id === a.id);
            return [
              `<strong>${esc(a.id)}</strong> ${esc(item ? item.term : '')}`,
              `<span class="small muted">${esc(a.why)}</span>`,
              (() => {
                if (done) return badge(itemStatus(item), statusTone(itemStatus(item)));
                if (proj().rescanFailed === a.id) return badge('Failed', 'is-danger');
                if (proj().rescanDone.includes(a.id)) return badge('Re-read', 'is-success');
                if (proj().rescanning) return `<span class="cluster"><span class="spinner is-sm" role="status" aria-label="Re-reading"></span>${badge('Re-reading', 'is-accent')}</span>`;
                return badge('Queued', 'is-warning');
              })(),
            ];
          }),
        })}</div>`,
        actions: done
          ? `<button class="button button-primary" type="button" data-action="go" data-route="watch">Watch the sources</button>`
          : proj().rescanning
            ? `<button class="button button-secondary" type="button" data-action="cancel-rescan">Cancel re-check</button>
               <span class="small muted" role="status">Re-read ${proj().rescanDone.length} of ${affected}. Cancelling keeps every existing decision.</span>`
            : proj().rescanFailed
              ? `${gated('research', `<button class="button button-primary" type="button" data-action="selective-rescan">Retry the re-check</button>`)}
                 <span class="small muted">Retrying is safe: ${esc(proj().rescanFailed)} was not recorded, and nothing already settled was touched.</span>`
              : gated('research', `<button class="button button-primary" type="button" data-action="selective-rescan">Re-check the changed scenes</button>`),
      })}</div>`,
    });
  }

  function allRuns() {
    return [...state.researchRuns, ...RESEARCH_RUNS.filter((r) => Boolean(proj()[r.needs]))];
  }

  function renderWatch() {
    const m = proj().monitoring;
    return page({
      trail: projectTrail('Source watch'),
      eyebrow: 'Keeping sources current',
      title: 'Source watch',
      lede: 'Registries and sources change after you check them. ClearCut keeps an eye on the ones behind your decisions and tells you when something moved — it never changes a decision on its own.',
      notice: prerequisiteNotice('watch'),
      body: `<div class="grid grid-3">
        ${card({
          eyebrow: 'How often',
          body: `<div class="choice-row">${['off', 'manual', 'daily', 'weekly'].map((v) => `<label class="choice"><input type="radio" name="cadence" value="${v}" ${m.cadence === v ? 'checked' : ''} data-action="set-cadence"><span>${esc(cadenceLabel(v))}</span></label>`).join('')}</div>
            <p class="small muted gap-t-3" id="cadence-rationale" role="status">${esc(cadenceRationale(m.cadence))}</p>`,
        })}
        ${card({ eyebrow: 'Who follows up', body: `<div class="cluster">${avatar('MV', 'Mara Voss')}<div><strong class="small">Mara Voss</strong><p class="small muted">Escalates after 48 hours</p></div></div>` })}
        ${card({ eyebrow: 'Next look', body: `<p><strong>${esc(nextLookLabel(m.cadence))}</strong></p><p class="small muted">${SOURCES.length} sources behind your decisions are watched</p>${m.checking ? `<p class="small gap-t-2"><span class="spinner is-sm" role="status" aria-label="Checking"></span> re-read ${m.checked} of ${SOURCES.length}</p>` : ''}` })}
      </div>

      <div class="gap-t-8">${card({
        accent: !m.reviewed,
        eyebrow: 'A source changed',
        title: m.checkRun ? `${esc(WATCHED_CHANGE.source)} changed` : 'Try a source check now',
        badge: m.checkRun
          ? `${badge(MATERIALITY[WATCHED_CHANGE.materiality].label, MATERIALITY[WATCHED_CHANGE.materiality].tone)}${badge(m.reviewed ? 'Reviewed' : 'Your call needed', m.reviewed ? 'is-success' : 'is-warning')}`
          : badge('Ready', ''),
        body: m.checkRun
          ? `<p class="small"><button class="button button-quiet button-sm" type="button" data-action="open-item" data-item="${esc(WATCHED_CHANGE.item)}">${esc(WATCHED_CHANGE.item)}</button> relied on this source. <strong>${esc(MATERIALITY[WATCHED_CHANGE.materiality].label)}:</strong> ${esc(MATERIALITY[WATCHED_CHANGE.materiality].meaning)}</p>
            <p class="small muted gap-t-2">${esc(WATCHED_CHANGE.why)}</p>
            <div class="diff gap-t-4">
              <section><span class="field-label">What you verified · ${esc(WATCHED_CHANGE.verifiedOn)}</span><p class="small gap-t-2">${esc(WATCHED_CHANGE.before)}</p></section>
              <section><span class="field-label">What it says now · ${esc(WATCHED_CHANGE.changedOn)}</span><p class="small gap-t-2"><ins>${esc(WATCHED_CHANGE.after)}</ins></p></section>
            </div>
            <div class="gap-t-4">${banner({
              tone: m.reviewed ? 'is-success' : 'is-warning', icon: m.reviewed ? '✓' : '◔',
              /* Previously titled 'Your verified source is unchanged', which read as
                 reassurance while reporting a material change to the exact fact the
                 decision relied on. The registration is still active; what changed
                 is that it is now contested. */
              title: m.reviewed ? 'Review recorded' : 'Your decision still stands, but the fact behind it moved',
              message: m.reviewed
                ? esc(m.reviewEffect || 'Kept verified evidence; a follow-up was created.')
                : 'No decision has been changed. Nothing changes until you record what this means.',
            })}</div>`
          : '<p class="small">Run the demo check to see what a source change looks like — ClearCut shows you the difference and asks what to do, rather than deciding itself.</p>',
        actions: m.checkRun
          ? `<button class="button button-primary" type="button" data-action="monitor-review-dialog">${m.reviewed ? 'See the review' : 'Review the change'}</button>`
          : m.checking
            ? `<button class="button button-secondary" type="button" data-action="cancel-monitor">Stop the check</button>
               <span class="small muted" role="status">Re-read ${m.checked} of ${SOURCES.length} sources.</span>`
            : gated('research', `<button class="button button-primary" type="button" data-action="manual-monitor">Check sources now</button>`),
      })}</div>

      ${(proj().followUps || []).length ? section({
        title: 'Open follow-ups',
        description: 'Created when a review kept its evidence but wanted a second look later.',
        body: dataTable({
          columns: [{ label: 'Follow-up' }, { label: 'Flag' }, { label: 'Why' }, { label: 'Owner' }, { label: 'Due' }],
          rows: proj().followUps.map((f) => [
            `<span class="mono">${esc(f.id)}</span>`,
            `<button class="button button-quiet button-sm" type="button" data-action="open-item" data-item="${esc(f.item)}">${esc(f.item)}</button>`,
            `<span class="small">${esc(f.reason)}</span>`,
            `<span class="small">${esc(f.owner)}</span>`,
            `<span class="mono">${esc(f.due)}</span>`,
          ]),
        }),
      }) : ''}

      ${(proj().supersededDecisions || []).length ? section({
        title: 'Superseded decisions',
        description: 'A reopened decision does not erase the earlier call. The original stays on the record with the reason it stopped governing.',
        body: dataTable({
          columns: [{ label: 'Flag' }, { label: 'Earlier call' }, { label: 'Superseded by' }, { label: 'Reason' }, { label: 'Recorded by' }],
          rows: proj().supersededDecisions.map((s) => [
            `<button class="button button-quiet button-sm" type="button" data-action="open-item" data-item="${esc(s.item)}">${esc(s.item)}</button>`,
            badge(s.decision === 'accepted' ? 'Verified' : esc(s.decision), 'is-success'),
            `<span class="small">Monitoring review</span>`,
            `<span class="small">${esc(s.reason)}</span>`,
            `<span class="small">${esc(s.actor)}</span>`,
          ]),
        }),
      }) : ''}

      ${section({
        title: 'Check history',
        body: dataTable({
          columns: [{ label: 'When' }, { label: 'Sources' }, { label: 'Changes' }, { label: 'Reviews opened' }, { label: 'Outcome' }],
          rows: m.checkRun
            ? [['<span class="mono">Aug 19 · asked for</span>', `<span class="mono">${SOURCES.length}</span>`, '<span class="mono">1</span>', '<span class="mono">1</span>', badge(m.reviewed ? 'Reviewed' : 'Awaiting your call', m.reviewed ? 'is-success' : 'is-warning')]]
            : [['<span class="mono">Aug 12 · weekly</span>', `<span class="mono">${SOURCES.length}</span>`, '<span class="mono">0</span>', '<span class="mono">0</span>', badge('No change', 'is-success')]],
        }),
      })}`,
    });
  }

  function renderTrust() {
    const stage = state.learning.stage;
    const stageLabel = { candidate: 'Idea', canary: 'Testing on 10%', promoted: 'Adopted', 'rolled-back': 'Reverted' }[stage];
    return page({
      trail: orgTrail('AI trust'),
      eyebrow: 'How ClearCut stays careful',
      title: 'AI trust',
      lede: 'ClearCut checks its own work. Every research pass is graded by a separate reviewer, and improvements are tested on a small slice before they are adopted — and can be undone in seconds.',
      notice: prerequisiteNotice('trust'),
      body: (() => {
        const score = judgeScore();
        const weakest = weakestDimension();
        const warns = JUDGE_GATES.filter((g) => g.result === 'Warn').length;
        const headline = warns === 0 ? 'Strong, no warnings'
          : warns === 1 ? 'Strong, one warning'
          : `Strong, ${warns} warnings`;
        return `<div class="grid grid-3">
        ${card({
          accent: true,
          body: `<div class="cluster score-summary"><div class="score-ring" style="--score:${score}" data-score="${score}" role="img" aria-label="Quality score ${score} out of 100, the mean of ${JUDGE_RUBRIC.length} graded dimensions"></div><div><h2>${esc(headline)}</h2><p class="small muted">Mean of ${JUDGE_RUBRIC.length} graded dimensions. Weakest: ${esc(weakest.label.toLowerCase())} at ${weakest.score}.</p></div></div>`,
        })}
        ${card({
          eyebrow: 'Safety checks on every pass',
          body: `<div class="stack-sm">${JUDGE_GATES.map((g) => `<div class="cluster-between"><span class="small">${esc(g.label)}</span>${badge(g.result, g.tone)}</div>`).join('')}</div>`,
        })}
        ${card({
          eyebrow: 'For the record',
          body: `<div class="stack-sm"><p class="mono small">rubric ${esc(EVAL_PROVENANCE.rubric)}<br>prompt ${esc(EVAL_PROVENANCE.prompt)}<br>policy ${esc(EVAL_PROVENANCE.policy)}<br>judge ${esc(EVAL_PROVENANCE.judge)}<br>${esc(EVAL_PROVENANCE.latency)} · ${esc(EVAL_PROVENANCE.cost)}</p><p class="small muted">The exact versions this check was graded against. A released report carries the same ones.</p></div>`,
        })}
      </div>

      ${section({
        title: 'What the judge grades',
        description: `Ten dimensions, scored by a separate model on a separate prompt. The headline above is their mean, so it cannot disagree with this table.`,
        body: dataTable({
          caption: 'Judge rubric scores for the most recent graded run',
          columns: [{ label: 'Graded on' }, { label: 'Score' }, { label: 'Rubric dimension' }],
          rows: JUDGE_RUBRIC.map((d) => [
            esc(d.label),
            `<div class="score-cell"><span class="meter"><span style="width:${d.score}%"></span></span><span class="mono">${d.score}</span></div>`,
            `<span class="small muted">${esc(d.formal)}</span>`,
          ]),
        }),
      })}

      <div class="gap-t-8">${card({
        eyebrow: 'A small improvement is waiting',
        title: 'Better music searches',
        badge: badge(stageLabel, stage === 'promoted' ? 'is-success' : stage === 'rolled-back' ? 'is-danger' : 'is-accent'),
        body: `<p class="small">ClearCut learned a better way to search for song titles. Before it is adopted, it is checked against every past case, tried in secret, then tried on 10% of real searches. It touches nothing else — no permissions, no rules, no categories.</p>
        <div class="gap-t-5">${statGrid([
          { label: 'Old cases', value: '148/148', hint: 'still pass', tone: 'is-success' },
          { label: 'Quality', value: '+6.1%', hint: 'better retrieval' },
          { label: 'Real-world trial', value: stage === 'candidate' ? 'Not started' : stage === 'canary' ? '10%, healthy' : 'Completed' },
          { label: 'Undo', value: '<30s', hint: 'if anything looks off' },
        ])}</div>`,
        actions: stage === 'candidate'
          ? gated('learning-governance', `<button class="button button-primary" type="button" data-action="promote-learning">Test on 10% of searches</button>`)
          : stage === 'canary'
          ? `${gated('learning-governance', `<button class="button button-primary" type="button" data-action="promote-learning">Adopt it</button>`)}${gated('learning-governance', `<button class="button button-danger" type="button" data-action="rollback-learning">Revert</button>`)}`
          : stage === 'promoted'
          ? gated('learning-governance', `<button class="button button-danger" type="button" data-action="rollback-learning">Revert to the old way</button>`)
          : gated('settings', `<button class="button button-secondary" type="button" data-action="promote-learning">Restart the trial</button>`),
      })}</div>

      <div class="gap-t-6">${banner({
        tone: 'is-danger', icon: '⚖', title: 'Some things only a person may change',
        message: 'A suggestion to loosen the privacy rule was blocked automatically. Safety rules, permissions, and legal-boundary language are always changed by an accountable person — never by the system.',
      })}</div>`;
      })(),
    });
  }

  function renderReport() {
    const d = proj().dossier;
    const info = projInfo();
    const version = boundVersionLabel();
    const open = openItems();
    const decided = flags().filter((i) => !open.includes(i));
    return page({
      trail: projectTrail('Clearance report'),
      eyebrow: 'The delivery package',
      title: 'Clearance report',
      // Marks the page so print can reduce it to the document itself.
      width: 'report-page',
      lede: 'The package you hand to lawyers, insurers, and distributors: what the script contained, what you checked, what you decided, and what risks you accepted. Built from exact saved versions, so it can be reproduced later if anyone asks.',
      notice: prerequisiteNotice('report'),
      body: `${statGrid([
        { label: 'Script snapshot', value: version, route: 'versions' },
        { label: 'Flags documented', value: flags().length || '—', route: 'items' },
        { label: 'Calls recorded', value: projectReceipts().length, route: 'records' },
        { label: 'Still open', value: open.length, hint: 'listed in an appendix, not hidden', tone: open.length ? 'is-warning' : 'is-success', route: 'items?status=attention' },
      ])}
      ${(() => {
        const snap = proj().snapshot;
        const drift = snapshotDrift();
        const badgeFor = d ? badge('Released', 'is-success') : snap ? badge('Snapshot ready', 'is-accent') : badge('Draft preview', 'is-warning');
        const noteFor = d
          ? `Released ${esc(fmtStamp(d.releasedAt || d.at))} by ${esc(d.releasedBy || ACTOR.name)} · frozen at ${esc(d.hash)}`
          : snap
            ? `Frozen ${esc(fmtStamp(snap.at))} · preview it, then release when the record is right.`
            : 'Live preview of current state. Generate a snapshot to freeze it.';
        const actionsFor = d
          ? `<button class="button button-primary" type="button" data-action="dossier-dialog">Inspect the export record</button><button class="button button-secondary" type="button" data-action="go" data-route="records">See the record</button>`
          : snap
            ? gated('release', `<button class="button button-primary" type="button" data-action="dossier-dialog">Release</button>`) + gated('release', `<button class="button button-secondary" type="button" data-action="regenerate-snapshot">Re-freeze</button>`)
            : gated('release', `<button class="button button-primary" type="button" data-action="generate-snapshot">Generate snapshot</button>`);
        return `<div class="cluster-between cluster-wrap report-toolbar">
          <div class="cluster"><div class="stack-sm">${badgeFor}</div><span class="small muted">${noteFor}</span></div>
          <div class="cluster">${actionsFor}</div>
        </div>
        ${drift ? `<div class="gap-t-3">${banner({ tone: 'is-warning', icon: '⚠', title: d ? 'State has changed since release' : 'State has changed since the snapshot was frozen', message: `${esc(drift)}. The ${d ? 'released document stays frozen' : 'frozen snapshot is unchanged'} — generate a new snapshot to capture the current record.` })}</div>` : ''}`;
      })()}
      ${reportDocument({ info, version, open, decided, d })}`,
    });
  }

  /** Flags still needing a person: anything not verified or fixed in a later
      version. Ruling a source out is not closure — itemStatus returns the flag
      to 'Needs your call', so counting it as decided would make the report
      contradict the register printed beside it. */
  function openItems() {
    return flags().filter((i) => {
      const s = itemStatus(i);
      return s !== 'Verified' && s !== 'Fixed in v2';
    });
  }

  /** The rendered clearance-report document — title block, Exhibits A–E built
      from live state, the open-items appendix, the version-binding table, and
      the boundary note. This is the artifact the product promises, shown rather
      than described; every figure derives from the same state the rest of the
      app reads, so the report cannot disagree with the worklist or the ledger. */
  function reportDocument({ info, version, open, decided, d }) {
    const activeTab = state.reportTab || 'A';
    const exhibit = (letter, title, body) => `<section class="report-exhibit ${activeTab === letter ? '' : 'is-tab-hidden'}" id="exhibit-${letter}" data-exhibit="${letter}">
      <div class="report-exhibit-head"><span class="report-exhibit-tag">Exhibit ${letter}</span><h3>${esc(title)}</h3></div>
      ${body}
    </section>`;

    // Exhibit A — script versions and their revision stock.
    /* A released report reads its frozen set; a draft reads live state. Same
       shape either way, so one renderer serves both without a second document. */
    const frozen = d && d.frozen ? d.frozen : null;
    const versionsSrc = frozen ? frozen.versions : proj().versions.map((v) => ({ label: v.label, source: v.source, hash: v.hash, stock: stockFor(v.label) }));
    const versionsRows = versionsSrc.length
      ? versionsSrc.map((v) => [`<span class="mono">${esc(v.label)}</span>`, esc(v.source), `<span class="stock-dot" style="--stock:var(--rev-${v.stock})" aria-hidden="true"></span>${esc(v.stock)}`, `<span class="mono">${esc(v.hash)}</span>`])
      : [['<span class="mono">v1</span>', 'Not yet imported', '—', '—']];

    // Exhibit B — the full flags register.
    const flagSrc = frozen ? frozen.flags : flags().map((i) => ({ id: i.id, term: i.term, category: SHORT[i.category], scene: i.scene, status: itemStatus(i), owner: effectiveOwner(i) }));
    const flagRows = flagSrc.length
      ? flagSrc.map((i) => [`<span class="mono">${i.id}</span>`, esc(i.term), esc(i.category), `Sc ${i.scene}`, badge(i.status, statusTone(i.status)), esc(i.owner)])
      : [['—', 'No flags on record', '—', '—', badge('No check has run', ''), '—']];

    /* Exhibit C — every retrieved source, not one line per flag. The stance
       column is the point of the exhibit: it shows where sources disagreed
       rather than presenting a single tidy answer per flag. */
    const STANCE_LABEL = { supports: ['Supports', ''], conflicts: ['Disagrees', 'is-warning'], context: ['Context', ''] };
    const sourceSrc = frozen ? frozen.sources : SOURCES;
    const sourceRows = sourceSrc.map((s) => {
      const [label, tone] = STANCE_LABEL[s.stance] || ['Context', ''];
      return [
        `<span class="mono">${esc(s.id)}</span><br><span class="mono muted">${esc(s.item)}</span>`,
        badge(s.authority),
        `<strong class="small">${esc(s.title)}</strong><br><span class="mono muted">retrieved ${esc(s.retrieved)}</span>`,
        `<span class="small">${esc(s.claim)}</span>`,
        badge(label, tone),
      ];
    });

    /* Exhibit D — this project's decision ledger. Scoped to the project so one
       production's report cannot enumerate another's decisions, and complete
       rather than silently truncated: the count above it must match the rows. */
    const projReceipts = frozen ? frozen.receipts : projectReceipts();
    const receiptRows = projReceipts.length
      ? projReceipts.map((r) => [`<span class="mono">${esc(r.id)}</span>`, esc(r.title), `<span class="small">${esc(r.detail)}</span>`, `<span class="mono muted">${esc(fmtStamp(r.at))}</span>`])
      : [['—', 'No calls recorded yet', 'Decisions appear here as they are made', '—']];

    // Exhibit E — monitoring and AI-trust posture.
    const m = proj().monitoring;
    const watchCadence = frozen ? d.cadence : cadenceLabel(m.cadence);
    const watchReviewed = frozen ? frozen.monitoringReviewed : m.reviewed;
    const learningStage = frozen ? frozen.learningStage : state.learning.stage;
    const watchRows = [
      ['Source watch', `Cadence: ${esc(watchCadence)}`, watchReviewed ? badge('Change reviewed', 'is-success') : badge('No open changes', '')],
      ['AI trust', `Learning stage: ${esc(learningStage)}`, badge('Protected controls untouched', 'is-success')],
    ];

    return `<article class="report-doc" aria-label="Clearance report document">
      <header class="report-titleblock">
        <p class="report-kicker">Screenplay Clearance Report · Errors &amp; Omissions support</p>
        <h2>${esc(info.title)}</h2>
        <dl class="report-meta">
          <div><dt>Production</dt><dd>${esc(info.type)} · ${esc(info.stage)}</dd></div>
          <div><dt>Jurisdiction</dt><dd>${esc(info.jurisdiction)}</dd></div>
          <div><dt>Script snapshot</dt><dd>${esc(version)}</dd></div>
          <div><dt>Prepared by</dt><dd>${esc(ACTOR.name)}, ${esc(ACTOR.role)}</dd></div>
          <div><dt>Flags</dt><dd>${frozen ? frozen.flags.length : flags().length} total · ${frozen ? frozen.flags.length - frozen.open.length : decided.length} resolved · ${frozen ? frozen.open.length : open.length} open</dd></div>
          <div><dt>Status</dt><dd>${d ? `Released ${esc(fmtStamp(d.at))}` : 'Draft preview'}</dd></div>
        </dl>
        <div class="report-titleblock-actions screen-only">
          ${gated('release', `<button class="button button-secondary button-sm" type="button" data-action="print-record">Print or save as PDF</button>`)}
          <span class="small muted">Prints every exhibit, not just the one open.</span>
        </div>
      </header>

      ${(() => {
        /* The nav was seven undifferentiated words. A reader could not tell an
           exhibit from a supplementary view, nor how much was inside any of them,
           so every tab had to be opened to find out. Each now carries its count,
           and the lettered exhibits are separated from the two views that are not
           exhibits. */
        const totalFlags = frozen ? frozen.flags.length : flags().length;
        const openCount = frozen ? frozen.open.length : open.length;
        const exhibits = [
          ['A', 'A', 'Versions', frozen ? frozen.versions.length : proj().versions.length],
          ['B', 'B', 'Flags', totalFlags],
          ['C', 'C', 'Sources', SOURCES.length],
          ['D', 'D', 'Decisions', projReceipts.length],
          ['E', 'E', 'Trust', JUDGE_RUBRIC.length],
        ];
        const views = [
          ['open', 'Open items', openCount],
          ['bind', 'Binding', null],
        ];
        const tab = (k, letter, label, count) => `<button type="button" role="tab" id="tab-${k}"
          class="report-tab ${activeTab === k ? 'is-active' : ''}"
          data-action="set-report-tab" data-tab="${k}"
          aria-selected="${activeTab === k}" aria-controls="exhibit-${k}"
          tabindex="${activeTab === k ? '0' : '-1'}">
          ${letter ? `<span class="report-tab-letter" aria-hidden="true">${letter}</span>` : ''}
          <span class="report-tab-label">${esc(label)}</span>
          ${count === null ? '' : `<span class="report-tab-count">${count}</span>`}
        </button>`;
        return `<nav class="report-exhibit-nav" role="tablist" aria-label="Exhibit navigation">
          <span class="report-nav-group-label" aria-hidden="true">Exhibits</span>
          ${exhibits.map(([k, letter, label, count]) => tab(k, letter, label, count)).join('')}
          <span class="report-nav-divider" aria-hidden="true"></span>
          ${views.map(([k, label, count]) => tab(k, '', label, count)).join('')}
        </nav>`;
      })()}

      ${exhibit('A', 'Script versions', dataTable({ columns: [{ label: 'Version' }, { label: 'Source' }, { label: 'Stock' }, { label: 'Snapshot ID' }], rows: versionsRows }))}
      ${exhibit('B', 'Flags register', dataTable({ columns: [{ label: 'ID' }, { label: 'Term' }, { label: 'Category' }, { label: 'Scene' }, { label: 'Status' }, { label: 'Owner' }], rows: flagRows }))}
      ${exhibit('C', `Sources & authority — ${sourceSrc.length} retrieved, ${DEMO_FACTS.conflicts} flags with disagreement`, dataTable({ columns: [{ label: 'Source' }, { label: 'Authority' }, { label: 'Record' }, { label: 'What it says' }, { label: 'Bearing' }], rows: sourceRows }))}
      ${exhibit('D', 'Decisions & receipts', dataTable({ columns: [{ label: 'Receipt' }, { label: 'Action' }, { label: 'Detail' }, { label: 'When' }], rows: receiptRows }))}
      ${exhibit('E', 'Source watch & AI trust', dataTable({ columns: [{ label: 'Area' }, { label: 'State' }, { label: 'Note' }], rows: watchRows }))}

      <section class="report-exhibit report-appendix ${activeTab === 'open' ? '' : 'is-tab-hidden'}" id="exhibit-open" data-exhibit="open">
        <div class="report-exhibit-head"><span class="report-exhibit-tag">Appendix</span><h3>Open items — carried, not hidden</h3></div>
        ${(() => {
          const openSrc = frozen ? frozen.open : open.map((i) => ({ id: i.id, term: i.term, status: itemStatus(i), owner: effectiveOwner(i) }));
          return openSrc.length
          ? `<p class="small">These ${openSrc.length} flag${openSrc.length === 1 ? '' : 's'} do not yet have a final human call. They are disclosed here rather than omitted from the report.</p>
             <div class="gap-t-3">${dataTable({
               columns: [{ label: 'ID' }, { label: 'Term' }, { label: 'Why still open' }, { label: 'Owner' }],
               rows: openSrc.map((i) => [`<span class="mono">${i.id}</span>`, esc(i.term), badge(i.status, statusTone(i.status)), esc(i.owner)]),
             })}</div>`
          : banner({ tone: 'is-success', icon: '✓', message: 'Every flag has a recorded human decision. Nothing is outstanding.' });
        })()}
      </section>

      <section class="report-exhibit ${activeTab === 'bind' ? '' : 'is-tab-hidden'}" id="exhibit-bind" data-exhibit="bind">
        <div class="report-exhibit-head"><span class="report-exhibit-tag">Binding</span><h3>Exact inputs this report is bound to</h3></div>
        <p class="small">The report is reproducible from these exact versions. Re-running them reproduces this document.</p>
        <div class="stack-gap-sm">${(() => {
          const bind = reportBinding(d, version);
          return dataTable({
            columns: [{ label: 'Input' }, { label: 'Version' }],
            rows: [
              ['Script snapshot', `<span class="mono">${esc(bind.script)}</span>`],
              ['Sign-off rules', `<span class="mono">${esc(bind.policy)}</span>`],
              ['Search method', `<span class="mono">${esc(bind.prompt)}</span>`],
              ['Grading method', `<span class="mono">${esc(bind.rubric)}</span>`],
              ['Graded by', `<span class="mono">${esc(bind.judge)}</span>`],
              ['Grade recorded', `<span class="mono">${bind.score}/100</span>`],
              ['Snapshot ID', `<span class="mono">${esc(bind.hash)}</span>`],
            ],
          });
        })()}</div>
      </section>

      <footer class="report-boundary">
        ${banner({ tone: '', icon: 'ℹ', title: 'What this report is — and is not', message: 'A production record of what was checked, decided, and left open. It is not legal advice and does not certify clearance. Final legal judgement rests with counsel. This prototype simulates the export in the browser; no file is written.' })}
      </footer>
    </article>`;
  }

  /* ═══════════════════════════ META SURFACES ═══════════════════════════ */

  function renderSitemap() {
    const groups = [...new Set(ROUTES.map((r) => r.group))];
    return page({
      eyebrow: 'Prototype tool',
      title: 'All surfaces',
      lede: `Every one of the ${ROUTES.length} surfaces in the prototype. Open any of them directly — navigation is advisory, never blocked.`,
      body: groups.map((group) => section({
        title: group,
        body: `<div class="sitemap-grid">${ROUTES.filter((r) => r.group === group).map((r) => {
          const done = state.completed.includes(r.id);
          const pending = Boolean(prerequisiteFor(r.id));
          return `<button class="sitemap-card" type="button" data-action="go" data-route="${r.id}">
            <div class="cluster-between"><span class="nav-icon" aria-hidden="true">${r.icon}</span>${done ? badge('Visited', 'is-success') : pending ? badge('Sample data', 'is-warning') : badge('Ready')}</div>
            <strong>${esc(r.label)}</strong>
            <code>#${esc(r.id)}</code>
          </button>`;
        }).join('')}</div>`,
      })).join(''),
    });
  }

  function renderStates() {
    return page({
      eyebrow: 'Prototype tool',
      title: 'UI states',
      lede: 'Empty, loading, error, and not-found treatments used across the application.',
      body: `${section({
        title: 'Empty',
        description: 'Explains the concept and offers the action that resolves it.',
        body: emptyState({ icon: '▤', title: 'No projects yet', description: 'Create a project to establish production context and review ownership.', action: `<button class="button button-primary" type="button" data-action="go" data-route="new">Start a clearance</button>` }),
      })}
      ${section({
        title: 'Loading',
        description: 'Skeletons preserve layout so content does not jump.',
        body: card({ body: `<div class="cluster gap-b-5"><span class="spinner" role="status" aria-label="Loading"></span><span class="small muted">Researching sources…</span></div><div class="stack-sm"><div class="skeleton" style="width:70%"></div><div class="skeleton" style="width:90%"></div><div class="skeleton" style="width:55%"></div></div>` }),
      })}
      ${section({
        title: 'Recoverable error',
        body: banner({ tone: 'is-warning', icon: '⟳', title: 'Music registry timed out', message: 'Retry 2 of 3 is scheduled. Sources already retrieved are preserved.', action: `<button class="button button-secondary button-sm" type="button" data-action="retry-provider">Retry now</button>` }),
      })}
      ${section({
        title: 'Permanent error',
        body: banner({ tone: 'is-danger', icon: '⚠', title: 'Automated retrieval not permitted', message: 'This source disallows automated access. A reviewer must supply evidence manually.' }),
      })}
      ${section({
        title: 'Not found',
        body: emptyState({ icon: '◌', title: 'Not found', description: 'That surface does not exist. It may have been renamed.', action: `<button class="button button-secondary" type="button" data-action="go" data-route="sitemap">Browse all surfaces</button>` }),
      })}
      ${section({
        title: 'Addressable domain states',
        description: 'The states above are the generic vocabulary. These are the specific outcomes each surface can reach, every one addressable by URL so it can be reviewed directly rather than clicked into.',
        body: `<div class="stack">${[
          ['Sign in', 'auth', ['authenticating', 'invalid', 'unverified', 'suspended', 'provider-down', 'expired', 'recovery'], 'state'],
          ['Invitation link', 'invite', ['wrong-account', 'expired', 'revoked', 'accepted', 'declined', 'malformed'], 'state'],
          ['Settings sections', 'settings', ['general', 'integrations', 'data', 'governance'], 'tab'],
          ['Team sections', 'team', ['members', 'invitations', 'roles'], 'tab'],
          ['Record views', 'records', ['activity', 'runs', 'evaluations', 'policies', 'operations'], 'view'],
          ['Worklist filter', 'items', ['all', 'attention', 'Must fix', 'Verified'], 'filter'],
          ['Inbox tier', 'notifications', ['urgent', 'action', 'informational'], 'tier'],
        ].map(([label, route, values, param]) => `<div class="cluster-between state-index-row">
          <span class="small"><strong>${esc(label)}</strong> <span class="mono muted">#${esc(route)}?${esc(param)}=</span></span>
          <span class="cluster cluster-wrap">${values.map((v) => `<button class="button button-quiet button-sm" type="button" data-action="go" data-route="${esc(route)}?${esc(param)}=${encodeURIComponent(v)}">${esc(v)}</button>`).join('')}</span>
        </div>`).join('')}</div>
        <div class="gap-t-5">${card({ quiet: true,
          body: `<span class="field-label">States that need a set-up step</span>
          <p class="small gap-t-2">The evidence drawer's phases follow the flag: an unchecked project shows <span class="mono">no check yet</span>, CC-105 shows no attributable source, CC-104 shows a referral once one exists, and a decided flag shows its binding. A re-scan failure is armed from Records → Activity → Demo controls. A superseded version read appears once an approved rewrite has created v2.</p>` })}</div>`,
      })}`,
    });
  }

  /** Reached when the hash names no known surface. Shows the same not-found
      treatment the states gallery documents, but names the hash the visitor
      actually typed so a dead link or typo is visible rather than hidden. */
  function renderNotFound(raw) {
    return page({
      eyebrow: 'Not found',
      title: 'That surface does not exist',
      lede: 'The address in the location bar does not match any surface in the prototype.',
      body: emptyState({
        icon: '◌',
        title: `No surface at #${esc(raw)}`,
        description: 'It may have been renamed, or the link may be mistyped. Every surface is listed on the sitemap.',
        action: `<button class="button button-primary" type="button" data-action="go" data-route="sitemap">Browse all surfaces</button><button class="button button-secondary" type="button" data-action="go" data-route="marketing">Back to start</button>`,
      }),
    });
  }

  const RENDERERS = {
    marketing: renderMarketing, 'marketing-a': renderMarketingA, 'marketing-b': renderMarketingB, 'marketing-c': renderMarketingC, features: renderFeatures, docs: renderDocs, auth: renderAuth, resolver: renderResolver, invite: renderInvite, onboarding: renderOnboarding,
    projects: renderProjects, notifications: renderNotifications, team: renderTeam, settings: renderSettings,
    trust: renderTrust, records: renderRecords,
    new: renderNew,
    project: renderProject, workspace: renderWorkspace, items: renderItems, item: renderItem,
    versions: renderVersions, watch: renderWatch, report: renderReport,
    sitemap: renderSitemap, states: renderStates,
  };

  /* Replacing a container's contents while focus sits inside it can leave the
     browser mid-blur as the subtree detaches, and Chrome then refuses the
     assignment: "The node to be removed is no longer a child of this node.
     Perhaps it was moved in a 'blur' event handler?" Clicking "Clear search"
     while the search box held focus hit this on every activation — the control
     still worked, because the render had already happened, but the page threw.
     Dropping focus first is enough. Handlers that want focus back, such as live
     search restoring the caret, re-focus deliberately after the render. */
  function releaseFocusInside(container) {
    const active = document.activeElement;
    if (active && active !== document.body && container.contains(active)) active.blur();
  }

  function renderRoute() {
    currentRoute = routeFromHash();
    /* Deep-link support: #items?status=Must%20fix&group=scene pre-sets the worklist.
       Applied only when the location itself changes, so the in-page filter and
       grouping controls are not overwritten by a stale query on re-render. */
    if (location.hash !== appliedQueryHash) {
      appliedQueryHash = location.hash;
      /* Tab state lives in the URL for every tabbed surface, so a notification or a
         record can deep-link to the view it means and the back button agrees. */
      if (currentRoute === 'settings') {
        const want = routeQuery().tab;
        if (want && ['general', 'integrations', 'data', 'governance'].includes(want)) state.settingsTab = want;
      }
      if (currentRoute === 'team') {
        const want = routeQuery().tab;
        if (want && ['members', 'invitations', 'roles'].includes(want)) state.teamTab = want;
      }
      if (currentRoute === 'records') {
        const want = routeQuery().view;
        if (want && ['activity', 'runs', 'evaluations', 'policies', 'operations'].includes(want)) state.recordsView = want;
      }
      if (currentRoute === 'notifications') {
        const q = routeQuery();
        if (q.tier && ['all', 'urgent', 'action', 'informational'].includes(q.tier)) state.notifTierFilter = q.tier;
        if (q.project) state.notifProjectFilter = q.project;
      }
      if (currentRoute === 'watch') {
        /* #watch?review=open addresses the review record itself. A governed action
           that only exists behind a click cannot be linked to from a notification
           or handed to a colleague. */
        if (routeQuery().review === 'open' && proj().monitoring.checkRun) {
          requestAnimationFrame(() => monitorReviewDialog());
        }
      }
      if (currentRoute === 'item') {
        /* Deep-link support: #item?id=CC-103 selects that item. An unknown id is
           left in place so renderItem can show a not-found naming what was typed,
           rather than silently substituting a different record. */
        const wanted = routeQuery().id;
        if (wanted) state.requestedItem = wanted;
        else state.requestedItem = null;
      }
      if (currentRoute === 'items') {
        const q = routeQuery();
        /* The design specifies #items?filter=attention&sort=due. `status` and
           `group` are kept as accepted aliases so links already written against the
           prototype keep working. */
        const status = q.filter !== undefined ? q.filter : q.status;
        const group = q.group;
        const sort = q.sort;
        if (status !== undefined && (status === 'all' || status === 'attention' || ITEM_STATUSES.includes(status))) state.itemFilter = status;
        if (group !== undefined && Object.hasOwn(GROUPERS, group)) state.itemsGroup = group;
        if (sort !== undefined && Object.hasOwn(SORT_LABELS, sort)) {
          state.itemsSort = { key: sort, dir: SORT_DEFAULT_DIR[sort] || 'asc' };
        }
      }
    }
    // Unknown surface: render not-found in the public shell without recording
    // it as a visited route or coercing the hash to another surface.
    if (!isKnownRoute(currentRoute)) {
      renderShell();
      releaseFocusInside(el.root);
      el.root.innerHTML = renderNotFound(currentRoute);
      document.title = 'Not found · ClearCut';
      requestAnimationFrame(() => {
        document.querySelector('#route-heading')?.focus({ preventScroll: true });
        window.scrollTo({ top: 0, behavior: 'auto' });
        el.assertive.textContent = `No surface at ${currentRoute}. Not found.`;
      });
      return;
    }
    if (!state.visited.includes(currentRoute)) { state.visited.push(currentRoute); saveState(); }
    renderShell();
    releaseFocusInside(el.root);
    el.root.innerHTML = RENDERERS[currentRoute]();
    const meta = routeMeta(currentRoute);
    document.title = currentRoute === 'marketing'
      ? 'ClearCut — Open-source screenplay clearance'
      : `${meta.label} · ClearCut`;

    // Live API Synchronization with FastAPI backend at http://127.0.0.1:8000
    if (typeof window !== 'undefined' && window.fetch) {
      const apiEndpointMap = {
        'projects': '/api/v1/organizations/northlight/projects',
        'project': '/api/v1/organizations/northlight/projects/borrowed-light/items',
        'workspace': '/api/v1/organizations/northlight/projects/borrowed-light/items',
        'items': '/api/v1/organizations/northlight/projects/borrowed-light/items',
        'item': `/api/v1/organizations/northlight/projects/borrowed-light/items/${encodeURIComponent(state.requestedItem || 'CC-101')}`,
        'watch': '/api/v1/organizations/northlight/projects/borrowed-light/watch',
        'records': '/api/v1/organizations/northlight/records',
        'trust': '/api/v1/organizations/northlight/trust',
        'report': '/api/v1/organizations/northlight/projects/borrowed-light/report',
        'notifications': '/api/v1/organizations/northlight/notifications',
        'team': '/api/v1/organizations/northlight/team',
        'settings': '/api/v1/organizations/northlight/settings',
      };
      const ep = apiEndpointMap[currentRoute] || '/api/v1/session-context';
      fetch(`http://127.0.0.1:8000${ep}`)
        .then(async (r) => {
          const json = await r.json().catch(() => ({}));
          console.log(`[ClearCut Live API Sync] GET ${ep} (HTTP ${r.status})`, json);
        })
        .catch((e) => console.warn(`[ClearCut API Sync Offline] GET ${ep}`, e));
    }
    if (suppressRouteFocus) return;
    requestAnimationFrame(() => {
      /* An addressed section is where the reader asked to be, so focus and scroll
         go there instead of to the top of the surface. Both used to run and the
         scroll-to-top won, which made a rail link look broken. */
      const anchored = currentRoute === 'settings' && routeQuery().s
        ? document.querySelector(`#sec-${routeQuery().s}`)
        : null;
      if (anchored) {
        anchored.scrollIntoView({ behavior: 'auto', block: 'start' });
        anchored.focus({ preventScroll: true });
      } else {
        document.querySelector('#route-heading')?.focus({ preventScroll: true });
        window.scrollTo({ top: 0, behavior: 'auto' });
      }
      el.polite.textContent = routeAnnouncement(meta);
    });
  }


  /* ═══════════════════════════════ DIALOGS ═══════════════════════════════ */

  function setInert(value) {
    [el.publicHeader, el.appHeader, el.sidebar, el.main, el.mobileNav].forEach((node) => {
      node.inert = value;
      if (value) node.setAttribute('aria-hidden', 'true');
      else node.removeAttribute('aria-hidden');
    });
  }

  function openDialog({ title, description = '', body = '', actions = '', wide = false }) {
    lastFocus = document.activeElement;
    el.dialogHost.innerHTML = `<div class="backdrop" data-backdrop>
      <div class="dialog ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-labelledby="dialog-title" ${description ? 'aria-describedby="dialog-desc"' : ''}>
        <header class="dialog-head">
          <div><h2 id="dialog-title">${esc(title)}</h2>${description ? `<p id="dialog-desc">${description}</p>` : ''}</div>
          <button class="icon-button is-bare" type="button" data-action="close-dialog" aria-label="Close dialog"><span aria-hidden="true">✕</span></button>
        </header>
        <div class="dialog-body">${body}</div>
        <footer class="dialog-actions">${actions || '<button class="button button-primary" type="button" data-action="close-dialog">Done</button>'}</footer>
      </div>
    </div>`;
    document.body.classList.add('dialog-open');
    setInert(true);
    document.addEventListener('keydown', trapFocus);
    requestAnimationFrame(() => {
      const focusable = el.dialogHost.querySelector('.dialog-body button, .dialog-body a[href], .dialog-body input, .dialog-body select, .dialog-body textarea')
        || el.dialogHost.querySelector('[data-action="close-dialog"]');
      focusable?.focus();
    });
  }

  /** Returns focus to the control that opened the dialog. */
  function restoreFocus() {
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
    lastFocus = null;
  }

  function closeDialog() {
    if (!el.dialogHost.firstElementChild) return;
    el.dialogHost.innerHTML = '';
    document.body.classList.remove('dialog-open');
    setInert(false);
    document.removeEventListener('keydown', trapFocus);
    restoreFocus();
  }

  function trapFocus(event) {
    if (!el.dialogHost.firstElementChild) return;
    if (event.key === 'Escape') { event.preventDefault(); closeDialog(); return; }
    if (event.key !== 'Tab') return;
    const nodes = [...el.dialogHost.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')];
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function setTheme(id) {
    const theme = THEMES.find((t) => t.id === id);
    if (!theme) return;
    document.documentElement.dataset.theme = id;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', id === 'night' ? '#14161b' : '#f6f3ea');
    try { localStorage.setItem(THEME_KEY, id); } catch (_) {}
    toast(`${theme.label} appearance active.`);
  }

  function openAppearanceDialog() {
    const current = document.documentElement.dataset.theme || 'script';
    openDialog({
      title: 'Workspace appearance',
      description: 'Applies to this browser only. Project data and team settings are unaffected.',
      body: `<div class="stack">${THEMES.map((t) => `<button class="appearance-option" type="button" data-action="set-theme" data-appearance="${t.id}" aria-pressed="${t.id === current}">
        <span class="appearance-preview" data-preview="${t.id}" aria-hidden="true"><i></i><i></i><i class="is-flag"></i><i></i></span>
        <span class="appearance-copy">
          <span class="appearance-name"><strong>${esc(t.label)}</strong><span class="appearance-current" ${t.id === current ? '' : 'hidden'}>Current</span></span>
          <span class="small muted">${esc(t.tagline)}</span>
        </span>
      </button>`).join('')}</div>`,
    });
  }

  function openReceiptsDialog() {
    openDialog({
      title: 'Record of actions',
      description: `${state.receipts.length} action${state.receipts.length === 1 ? '' : 's'} on the record.`,
      wide: true,
      body: state.receipts.length
        ? state.receipts.map((r) => `<div class="receipt"><span class="receipt-icon" aria-hidden="true">✓</span><div><strong class="small">${esc(r.title)}</strong><p class="small muted">${esc(r.detail)}</p><span class="mono muted">${esc(r.id)} · ${esc(r.kind)} · ${esc(r.actor)}</span></div><time>${fmtStamp(r.at)}</time></div>`).join('')
        : banner({ icon: '≡', title: 'No receipts yet', message: 'Actions like verifying a source or releasing the report are recorded here permanently.' }),
    });
  }

  function evidenceDialog(decision, itemId) {
    const item = ITEMS.find((i) => i.id === itemId) || ITEMS[0];
    const accepting = decision === 'accepted';
    const version = boundVersionLabel();
    openDialog({
      title: `${accepting ? 'Verify this source' : 'Rule this source out'} for ${item.term}?`,
      description: `Records your call on <span class="mono">${esc(item.id)}</span> against script <span class="mono">${esc(version)}</span>.`,
      body: `${banner({
        tone: accepting ? 'is-success' : 'is-danger', icon: accepting ? '✓' : '✕', title: 'What this means',
        message: accepting
          ? 'This becomes the source you stand behind for this flag. Any disagreement stays visible on the record.'
          : 'The source stays in the history, but it cannot support the final decision.',
      })}
      <label class="field gap-t-5"><span class="field-label">Decision rationale</span><textarea id="decision-rationale">${accepting ? 'Primary registry record is current and directly supports the bounded factual claim.' : 'Source authority or scope is insufficient for this claim.'}</textarea></label>`,
      actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button>
        <button class="button ${accepting ? 'button-primary' : 'button-danger'}" type="button" data-action="confirm-evidence" data-decision="${decision}" data-item="${item.id}">${accepting ? 'Verify &amp; record' : 'Rule out &amp; record'}</button>`,
    });
  }

  /* ═══════════════════════════ STATE INVARIANTS ═══════════════════════════ */

  /* ── Staged script check (the agent seen working) ──
     A real, timed run: each step completes after its own elapsed time, the
     working step shows a spinner and skeleton, and a cancel path clears the
     pending work. Timer ids live in module scope (runTimers/runTicker) because
     they cannot be persisted; the step index and start time are persisted so a
     completed run survives a reload. */
  function clearRunTimers() {
    runTimers.forEach((t) => clearTimeout(t));
    runTimers = [];
    if (runTicker) { clearInterval(runTicker); runTicker = null; }
    runProjectId = null;
  }
  /** The project slice the in-flight run belongs to, or null if it is gone. */
  function runTarget() {
    return (runProjectId && state.projects[runProjectId]) || null;
  }

  function startRun() {
    clearRunTimers();
    runProjectId = state.activeProjectId;
    proj().runStep = 0;
    proj().runComplete = false;
    proj().running = true;
    proj().runStartedAt = Date.now();
    saveState();
    // Schedule each step's completion at its cumulative elapsed time.
    let elapsed = 0;
    RUN_STEPS.forEach((s, i) => {
      elapsed += s.ms;
      runTimers.push(setTimeout(() => finishRunStep(i), elapsed));
    });
    // A light ticker refreshes only the elapsed-time readout while working, so
    // the reviewer sees real time passing without a full re-render each frame.
    runTicker = setInterval(updateRunElapsed, 250);
    renderRoute();
  }

  function finishRunStep(index) {
    /* Resolve the project that started the run, not whatever is active now:
       switching projects mid-check would otherwise land the completion, the
       stage advance, and the receipt on a project the check never ran against. */
    const target = runTarget();
    if (!target) { clearRunTimers(); return; }
    // Advance to the step after the one that just completed.
    target.runStep = index + 1;
    if (target.runStep >= RUN_STEPS.length) {
      target.runStep = RUN_STEPS.length;
      target.runComplete = true;
      target.running = false;
      clearRunTimers();
      completeStage('new');
      // Derived, not asserted: openItems() is what every other surface counts.
      addReceipt('run', 'Script check finished', `${DEMO_FACTS.flags} flags · ${DEMO_FACTS.sources} sources · ${DEMO_FACTS.conflicts} where sources disagree · ${openItems().length} need a person`);
    }
    saveState();
    // Only re-render if the reviewer is still watching the wizard; the state is
    // saved regardless, so returning to #new shows the run's real progress.
    if (currentRoute === 'new') renderRoute();
  }

  function cancelRun() {
    const target = runTarget() || proj();
    clearRunTimers();
    target.running = false;
    target.runStep = 0;
    target.runComplete = false;
    target.runStartedAt = null;
    saveState();
    addReceipt('run', 'Script check cancelled', 'No flags recorded · re-runnable · nothing partially saved');
    renderRoute();
  }

  /** Updates just the elapsed-time readout during a run, avoiding a full render. */
  function updateRunElapsed() {
    const node = document.querySelector('#run-elapsed');
    if (!node) return;
    if (!proj().running || !proj().runStartedAt) return;
    const secs = ((Date.now() - proj().runStartedAt) / 1000).toFixed(1);
    node.textContent = `${secs}s elapsed`;
  }

  function createVersionTwo(proposed) {
    if (proposed) proj().rewriteText = proposed;
    if (!proj().versions.some((v) => v.label === 'v2')) {
      proj().versions.push({ label: 'v2', source: 'Approved rewrite of CC-110', hash: 'b2fd7a61c918', createdAt: new Date().toISOString(), parent: 'v1' });
    }
    proj().rewriteApproved = true;
    completeStage('items');
    /* Name both hands in the receipt. 'Approved' without an author and an
       approver cannot be audited later. */
    const prop = proposalFor('CC-110');
    const authorship = prop && prop.by
      ? `proposed by ${prop.by} (${prop.byRole || 'unknown role'}) · approved by ${ACTOR.name} (${actorRole()})`
      : `approved by ${ACTOR.name} (${actorRole()})`;
    addReceipt('rewrite', 'Rewrite approved; immutable v2 created', `CC-110 · Scene 18 · ${authorship} · v1 preserved unchanged · v2 b2fd…918`, 'CC-110');
    saveState();
  }

  /** Re-reads the affected flags one at a time, so the surface can show which one
      is in hand. Mirrors startRun: an interrupted re-scan cannot survive a reload
      because its timers are gone, so loadState resets it rather than leaving a row
      stuck on 'Re-reading'. */
  function startRescan() {
    clearRescanTimers();
    rescanProjectId = state.activeProjectId;
    const scope = rescanScope();
    if (!scope.all.length) { toast('Nothing to re-check — no rewrite has been approved.', true); return; }
    proj().rescanning = true;
    proj().rescanDone = [];
    proj().rescanFailed = null;
    proj().rescanComplete = false;
    saveState();
    let elapsed = 0;
    scope.all.forEach((a) => {
      elapsed += 900;
      rescanTimers.push(setTimeout(() => finishRescanItem(a.id), elapsed));
    });
    renderRoute();
  }

  function finishRescanItem(itemId) {
    // Ignore a stale timer from a project the reviewer has since left.
    if (rescanProjectId !== state.activeProjectId) return;
    /* A durable job can fail. When a re-read cannot complete, the flag is recorded
       as failed rather than silently counted as done — a re-scan that reports
       success for work it did not do is worse than one that stops. */
    if (proj().rescanFailAt === itemId) {
      proj().rescanning = false;
      proj().rescanFailed = itemId;
      addReceipt('rescan', 'Selective re-scan failed', `${itemId} · provider unavailable · no decision changed · retry is safe`, itemId);
      saveState(); renderRoute();
      toast(`Re-check stopped at ${itemId}. Nothing was changed.`, true);
      return;
    }
    if (!proj().rescanDone.includes(itemId)) proj().rescanDone.push(itemId);
    const scope = rescanScope();
    if (proj().rescanDone.length >= scope.all.length) {
      proj().rescanning = false;
      selectiveRescan();
    } else {
      saveState();
    }
    renderRoute();
  }

  /** Re-reads the watched sources a few at a time. A sweep that completed the
      instant it was asked for could not show how many sources were actually
      re-read, which is the only thing that makes the result checkable. */
  function startMonitorSweep() {
    clearMonitorTimers();
    monitorProjectId = state.activeProjectId;
    const total = SOURCES.length;
    proj().monitoring.checking = true;
    proj().monitoring.checked = 0;
    saveState();
    const step = Math.max(1, Math.ceil(total / 8));
    let done = 0;
    let elapsed = 0;
    while (done < total) {
      done = Math.min(total, done + step);
      elapsed += 260;
      const at = done;
      monitorTimers.push(setTimeout(() => advanceMonitorSweep(at, total), elapsed));
    }
  }

  function advanceMonitorSweep(count, total) {
    if (monitorProjectId !== state.activeProjectId) return;
    proj().monitoring.checked = count;
    if (count >= total) {
      proj().monitoring.checking = false;
      proj().monitoring.checkRun = true;
      const mat = MATERIALITY[WATCHED_CHANGE.materiality];
      addReceipt('monitoring', 'Monitoring check completed',
        `${total} sources re-read · 1 change on ${WATCHED_CHANGE.item} classified ${mat.label.toLowerCase()} · no decision changed`);
      saveState(); renderRoute();
      toast(`${WATCHED_CHANGE.item}: one ${mat.label.toLowerCase()} change needs your review.`, true);
      return;
    }
    saveState(); renderRoute();
  }

  /** The monitoring review record. Named rather than inline so #watch?review=open
      can address it directly. */
  function monitorReviewDialog() {
    const m = proj().monitoring;
    const mat = MATERIALITY[WATCHED_CHANGE.materiality];
    openDialog({
      title: m.reviewed ? 'Source change — review record' : `Review the ${WATCHED_CHANGE.source} change`,
      description: 'The verified snapshot stays unchanged unless you record a new evidence decision.',
      wide: true,
      body: `<div class="cluster gap-b-4">${badge(mat.label, mat.tone)}<span class="small muted">${esc(mat.meaning)}</span></div>
        <div class="diff">
          <section><span class="field-label">Accepted snapshot · ${esc(WATCHED_CHANGE.verifiedOn)}</span><p class="small gap-t-2">${esc(WATCHED_CHANGE.before)}</p></section>
          <section><span class="field-label">Current source · ${esc(WATCHED_CHANGE.changedOn)}</span><p class="small gap-t-2">${esc(WATCHED_CHANGE.after)}</p></section>
        </div>
        <p class="small muted gap-t-3">${esc(WATCHED_CHANGE.why)}</p>
        ${m.reviewed
          ? `<div class="gap-t-5">${banner({ tone: 'is-success', icon: '✓', title: 'Review recorded', message: esc(m.reviewEffect || 'Kept verified evidence; follow-up created.') })}${m.rationale ? `<p class="small muted gap-t-2"><strong>Rationale:</strong> ${esc(m.rationale)}</p>` : ''}
            <p class="mono muted small gap-t-3">Linkable at #watch?review=open</p></div>`
          : `<label class="field gap-t-5"><span class="field-label">Review effect</span><select id="monitor-effect">
              <option value="keep">Keep verified evidence; create a follow-up</option>
              <option value="reopen">Reopen the evidence decision</option>
              <option value="refer">Refer to a trademark specialist</option>
            </select></label>
            <label class="field gap-t-4"><span class="field-label">Rationale</span><textarea id="monitor-rationale" rows="2" placeholder="Why you chose this effect — recorded with your name and the review."></textarea></label>`}`,
      actions: m.reviewed
        ? '<button class="button button-primary" type="button" data-action="close-dialog">Done</button>'
        : `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-monitor-review">Record review</button>`,
    });
  }

  function cancelMonitorSweep() {
    clearMonitorTimers();
    proj().monitoring.checking = false;
    proj().monitoring.checked = 0;
    saveState(); renderRoute();
  }

  function clearMonitorTimers() {
    monitorTimers.forEach(clearTimeout);
    monitorTimers = [];
  }

  /** Cancelling abandons the re-read without touching anything already settled:
      a partial re-scan must not leave half a version's worth of new verdicts. */
  function cancelRescan() {
    clearRescanTimers();
    proj().rescanning = false;
    proj().rescanDone = [];
    saveState();
    renderRoute();
  }

  function clearRescanTimers() {
    rescanTimers.forEach(clearTimeout);
    rescanTimers = [];
  }

  function selectiveRescan() {
    const scope = rescanScope();
    proj().rescanComplete = true;
    /* Only the directly rewritten passages are resolved by the rewrite. A
       contextual neighbour is re-read, not fixed — marking it resolved would
       claim a decision nobody made. */
    scope.direct.forEach((a) => { proj().evidenceDecisions[a.id] = 'resolved-on-v2'; });
    completeStage('versions');
    addReceipt('rescan', 'Selective re-scan completed on v2', `${scope.all.length} affected items re-evaluated · ${scope.untouched} evidence records reused unchanged`);
    saveState();
  }

  function reviewMonitoringChange(effect = 'keep', rationale = '') {
    proj().monitoring.reviewed = true;
    proj().monitoring.rationale = rationale;
    completeStage('watch');
    // The chosen effect actually changes state and the receipt, so the review
    // is a real decision rather than a fixed acknowledgement.
    if (effect === 'reopen') {
      /* Supersede, never delete. The earlier verification was a governed decision
         with an accountable name on it; erasing the row would make the history
         claim the call was never made. The prior decision stays readable and the
         superseding record explains why it no longer governs. */
      const prior = proj().evidenceDecisions['CC-101'];
      proj().supersededDecisions = proj().supersededDecisions || [];
      proj().supersededDecisions.push({
        item: 'CC-101',
        decision: prior || 'accepted',
        supersededBy: 'monitoring-review',
        reason: rationale || 'Source changed after verification.',
        at: new Date().toISOString(),
        actor: ACTOR.name,
      });
      proj().evidenceDecisions['CC-101'] = 'reopened';
      proj().monitoring.reviewEffect = 'Reopened the CC-101 evidence decision; the earlier verification is retained as superseded.';
      addReceipt('monitoring', 'Source change reviewed — decision reopened', 'CC-101 · cancellation petition · prior verification retained as superseded · awaiting new call');
    } else if (effect === 'refer') {
      proj().monitoring.reviewEffect = 'Referred CC-101 to a trademark specialist for a bounded second look.';
      addReceipt('monitoring', 'Source change reviewed — referred to specialist', 'CC-101 · cancellation petition · trademark specialist engaged · verified evidence held pending');
    } else {
      /* A follow-up is a real record with an owner and a date, not prose in a
         receipt — otherwise "a follow-up was created" points at nothing. */
      proj().followUps = proj().followUps || [];
      proj().followUps.push({
        id: `FU-${String(proj().followUps.length + 1).padStart(3, '0')}`,
        item: 'CC-101',
        due: 'Aug 29',
        owner: 'Mara Voss',
        reason: rationale || 'Cancellation petition filed; verified evidence unchanged for now.',
        open: true,
        at: new Date().toISOString(),
      });
      const fu = proj().followUps.at(-1);
      proj().monitoring.reviewEffect = `Kept verified evidence; follow-up ${fu.id} created (due ${fu.due}).`;
      addReceipt('monitoring', 'Source change reviewed — evidence kept', `CC-101 · cancellation petition noted · verified evidence unchanged · ${fu.id} due ${fu.due}`);
    }
    saveState();
  }

  function promoteLearningCandidate() {
    state.learning.stage = state.learning.stage === 'canary' ? 'promoted' : 'canary';
    completeStage('trust');
    addReceipt('learning', state.learning.stage === 'promoted' ? 'Learning candidate promoted' : 'Learning candidate entered 10% canary',
      'Query examples only · regression 148/148 · protected controls untouched');
    saveState();
  }

  function rollbackLearningCandidate() {
    state.learning.stage = 'rolled-back';
    completeStage('trust');
    /* No prompt id, model name or rubric version in notification content: receipts
       feed the inbox, and internal identifiers there tell the reader nothing they
       can act on. The identifiers stay on the AI trust surface. */
    addReceipt('learning', 'Learning candidate rolled back', 'Traffic returned to the previous prompt version in under 30 seconds');
    saveState();
  }

  /* An export is a reproducible snapshot tied to exact script, evidence,
     decision, rubric and policy versions. The record asserted script "v2" and
     literal policy, prompt and rubric strings, so a project released at v1 filed
     a report naming a version it had never created, and the grading versions
     could drift from the ones the trust surface showed. Everything now derives,
     and the judge and its score are recorded too: a reader can see not just what
     graded the run but how well it scored. */
  /** Phase one: freeze the current state into an immutable snapshot artifact.
      Generation is not release — the snapshot exists and can be previewed, but
      nothing is attested or delivered until a human releases it. */
  function generateSnapshot() {
    const script = boundVersionLabel();
    proj().snapshot = {
      file: `${projInfo().title.replace(/\s+/g, '-')}_Clearance-Report_${script}.pdf`,
      hash: '52b44c9fd0ae…e1c7',
      at: new Date().toISOString(),
      script,
      policy: EVAL_PROVENANCE.policy,
      prompt: EVAL_PROVENANCE.prompt,
      rubric: EVAL_PROVENANCE.rubric,
      judge: EVAL_PROVENANCE.judge,
      score: judgeScore(),
      // The snapshot records what was open at generation time, so a later
      // decision cannot silently change what the frozen document disclosed.
      openCount: openItems().length,
      receiptCount: projectReceipts().length,
      cadence: cadenceLabel(proj().monitoring.cadence),
      /* The exhibit contents are frozen here, not read at render time. Recording
         only the counts left the released document reading live state, so
         changing the watch cadence after release silently rewrote Exhibit E while
         the snapshot hash stayed the same — exactly what a reproducible report
         must not do. */
      frozen: {
        versions: proj().versions.map((v) => ({ label: v.label, source: v.source, hash: v.hash, parent: v.parent, stock: stockFor(v.label) })),
        flags: flags().map((i) => ({ id: i.id, term: i.term, category: SHORT[i.category], scene: i.scene, status: itemStatus(i), owner: effectiveOwner(i) })),
        sources: SOURCES.map((s) => ({ id: s.id, item: s.item, authority: s.authority, title: s.title, retrieved: s.retrieved, claim: s.claim, stance: s.stance })),
        receipts: projectReceipts().map((r) => ({ id: r.id, title: r.title, detail: r.detail, at: r.at })),
        open: openItems().map((i) => ({ id: i.id, term: i.term, status: itemStatus(i), owner: effectiveOwner(i) })),
        learningStage: state.learning.stage,
        monitoringReviewed: proj().monitoring.reviewed,
      },
    };
    const s = proj().snapshot;
    addReceipt('export', 'Report snapshot generated',
      `${s.file} · script ${s.script} · ${s.openCount} open · frozen at ${s.hash}`);
    saveState();
  }

  /** Phase two: the governed attestation. Reads the frozen snapshot rather than
      current state, so the released document cannot drift after the fact. */
  function releaseDossier() {
    if (!proj().snapshot) generateSnapshot();
    if (!proj().dossier) {
      proj().dossier = { ...proj().snapshot, releasedAt: new Date().toISOString(), releasedBy: ACTOR.name };
      const d = proj().dossier;
      completeStage('report');
      addReceipt('export', 'Clearance report released',
        `${d.file} · script ${d.script} · policy ${d.policy} · prompt ${d.prompt} · rubric ${d.rubric} · graded ${d.score} by ${d.judge} · attested by ${d.releasedBy}`);
    }
    saveState();
  }

  /** True when state moved after the snapshot was frozen, so the toolbar can say
      exactly what changed rather than a vague "state has changed". */
  function snapshotDrift() {
    const s = proj().snapshot;
    if (!s) return null;
    const parts = [];
    const receipts = projectReceipts().length;
    // The generation receipt itself is not drift.
    const newDecisions = receipts - s.receiptCount - 1 - (proj().dossier ? 1 : 0);
    if (newDecisions > 0) parts.push(`${newDecisions} new decision${newDecisions === 1 ? '' : 's'}`);
    if (openItems().length !== s.openCount) parts.push(`open items now ${openItems().length}, was ${s.openCount}`);
    if (cadenceLabel(proj().monitoring.cadence) !== s.cadence) parts.push(`watch cadence now ${cadenceLabel(proj().monitoring.cadence)}`);
    if (boundVersionLabel() !== s.script) parts.push(`script now ${boundVersionLabel()}`);
    return parts.length ? parts.join(' · ') : null;
  }

  /** The inputs a report is bound to. A released report reads its own stored
      snapshot; a draft reads current state. Both go through here, so a preview
      cannot promise a binding the release would not record. */
  function reportBinding(d, version) {
    return {
      script: d ? d.script : version,
      policy: d ? d.policy : EVAL_PROVENANCE.policy,
      prompt: d ? d.prompt : EVAL_PROVENANCE.prompt,
      rubric: d ? d.rubric : EVAL_PROVENANCE.rubric,
      judge: d ? d.judge : EVAL_PROVENANCE.judge,
      score: d ? d.score : judgeScore(),
      hash: d ? d.hash : 'computed at release',
    };
  }

  /* ═══════════════════════════════ ACTIONS ═══════════════════════════════ */

  /** Actions that require a capability, enforced centrally so a role that lacks
      authority is stopped even if a control is triggered outside the UI. The
      buttons are already disabled for these roles; this is the matching guard. */
  const ACTION_CAPABILITY = {
    'confirm-assign': 'reassign', 'confirm-bulk-assign': 'reassign', 'bulk-assign': 'reassign', 'assign-dialog': 'reassign',
    'confirm-evidence': 'decide', 'evidence-dialog': 'decide',
    'confirm-referral': 'refer',
    'confirm-rewrite': 'rewrite',
    'confirm-dossier': 'release',
    'generate-snapshot': 'release',
    'regenerate-snapshot': 'release',
    'confirm-role': 'team', 'role-dialog': 'team', 'edit-invite-dialog': 'team', 'confirm-edit-invite': 'team',
    'delete-project-dialog': 'settings', 'confirm-delete-project': 'settings', 'restore-project': 'settings', 'confirm-invite': 'team', 'invite-dialog': 'team', 'revoke-invite': 'team',
    'save-settings': 'settings', 'set-cadence': 'settings',
    'run-research': 'research',
    'confirm-reset': 'reset', 'reset-dialog': 'reset',
    'confirm-monitor-review': 'decide',
    // The declared import capability had no enforcement anywhere, so any role
    // could mint v1 and run the check.
    'save-project': 'import', 'create-v1': 'import', 'start-run': 'import', 'cancel-run': 'import',
    'choose-file': 'import', 'reject-import': 'import',
    'selective-rescan': 'research', 'manual-monitor': 'research',
    // Recording how the production proceeds is the production's final call.
    'disposition-dialog': 'decide', 'confirm-disposition': 'decide',
    // Adopting or reverting a learning candidate changes how checks behave.
    'promote-learning': 'settings', 'rollback-learning': 'settings',
    'add-comment': 'comment',
  };
  /* Deliberately absent above: dossier-dialog, referral-dialog, rewrite-dialog
     and monitor-review-dialog. Each opens the write form before its record
     exists and the read-only record afterwards, so gating the opener refused a
     Viewer the "Read records and exports" the role matrix grants them. The
     mutating confirm-* actions above carry the guard instead. */

  function handleAction(action, node) {
    const need = ACTION_CAPABILITY[action];
    if (need && !can(need)) {
      toast(`${actorRole()} cannot ${CAPABILITY_LABELS[need] || 'do this'}.`, true);
      return;
    }
    switch (action) {
      case 'go': go(node.dataset.route); break;
      case 'set-actor-role':
        state.actorRole = node.dataset.role;
        saveState(); renderRoute();
        toast(`Now previewing as ${state.actorRole}.`);
        break;
      /* aria-disabled controls stay focusable, so activating one must do
         nothing except restate why — announced, not silently swallowed. */
      case 'gated-blocked': {
        const reason = document.querySelector(`#${node.getAttribute('aria-describedby')}`)?.textContent
          || `${actorRole()} cannot do this`;
        toast(reason.trim(), true);
        break;
      }
      /* Swaps the landing evidence card in place. Deliberately does not call
         renderRoute(), which would reset scroll and move focus to the heading. */
      case 'lp-show-evidence': {
        const flag = node.dataset.flag;
        document.querySelectorAll('[data-action="lp-show-evidence"]').forEach((b) => {
          b.setAttribute('aria-pressed', String(b.dataset.flag === flag));
        });
        /* All cards share one grid cell and stay in flow, so swapping cannot
           change the document height or nudge the scroll position. */
        document.querySelectorAll('.lp-note[data-flag]').forEach((card) => {
          card.dataset.shown = String(card.dataset.flag === flag);
        });
        el.polite.textContent = `Showing the source evidence for ${node.textContent.trim()}.`;
        break;
      }
      /* Focuses the main landmark directly. Following the href would push
         #app-main through the hash router, which would reroute to marketing. */
      case 'skip-main':
        el.main.focus({ preventScroll: true });
        el.main.scrollIntoView({
          behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
          block: 'start',
        });
        break;
      /* Enter the product, not a sign-in form. The hero promises "No account
         required" and then put an authentication step between that promise and
         the artifact the page is about — six clicks from the landing page to a
         flag with its evidence. The sign-in and organization-setup surfaces stay
         reachable from the footer and the sitemap, so both remain demonstrable. */
      case 'start-demo': {
        completeStage('marketing');
        state.auth = true;
        state.orgReady = true;
        // Enter on a project whose check has completed, so the first surface the
        // visitor sees is a populated one rather than an empty shell.
        const seeded = PROJECT_DEFS.find((d) => state.projects[d.id].runComplete);
        if (seeded) state.activeProjectId = seeded.id;
        saveState();
        go('project'); break;
      }
      /* Signing in resolves which organization you are working in. Going straight to
         onboarding assumed everyone signing in has none, which is only true once. */
      case 'sign-in': state.auth = true; completeStage('auth'); addReceipt('auth', 'Signed in', `${ACTOR.name} · ${ACTOR.role}`); go(state.orgReady ? 'resolver' : 'onboarding'); break;
      case 'resolve-org': {
        if (node.dataset.org !== 'northlight') { toast('Your membership there is suspended, so it cannot be opened.', true); break; }
        addReceipt('auth', 'Organization selected', esc(state.org.name));
        go('projects');
        break;
      }
      case 'auth-resend-verification':
        addReceipt('auth', 'Verification link resent', 'sent to the address on the account');
        toast('Link sent. It expires in 30 minutes.');
        break;
      // Accepting an invitation joins an organization that already exists, so
      // the setup stage is satisfied without walking the onboarding surface.
      case 'accept-invite': state.auth = true; state.orgReady = true; completeStage('auth'); addReceipt('membership', 'Invitation accepted', 'Reviewer role on Borrowed Light'); toast('Invitation accepted.'); go('projects'); break;
      case 'finish-onboarding': {
        const name = document.querySelector('#org-name')?.value.trim();
        const cadence = document.querySelector('#org-cadence')?.value;
        const invite = document.querySelector('#org-invite')?.value.trim();
        if (!name) { toast('Enter an organization name.', true); document.querySelector('#org-name')?.focus(); break; }
        state.org.name = name;
        if (cadence) state.org.cadence = cadence;
        if (invite && !state.members.some((m) => m.email === invite)) {
          state.members.push({
            name: invite.split('@')[0].replace(/^\w/, (c) => c.toUpperCase()),
            initials: invite.slice(0, 2).toUpperCase(),
            email: invite, role: 'Reviewer', access: 'All projects', status: 'Invited',
          });
        }
        state.orgReady = true;
        completeStage('onboarding');
        addReceipt('organization', 'Organization created', `${name} · ${ACTOR.name} owner · ${invite ? `${invite} invited as Reviewer` : 'no invitations'}`);
        go('projects'); break;
      }
      /* Start the wizard on a project that has not been started. Borrowed Light
         ships with a script, so running the guided flow against it would have
         asked the visitor to import over a version the surfaces already cite. */
      case 'new-project': {
        completeStage('projects');
        const unstarted = PROJECT_DEFS.find((d) => !state.projects[d.id].versions.length);
        if (unstarted) state.activeProjectId = unstarted.id;
        saveState();
        go('new'); break;
      }
      case 'save-project': {
        const val = (id) => document.querySelector(id)?.value.trim() || '';
        const title = val('#np-title') || projDef().title;
        const details = {
          title,
          type: val('#np-type') || projDef().type,
          stage: val('#np-stage') || projDef().stage,
          jurisdiction: val('#np-jurisdiction') || projDef().jurisdiction,
          lock: lockDisplay(val('#np-lock')) || projDef().lock,
          brief: val('#np-brief') || projDef().brief,
        };
        proj().details = details;
        // The org's default cadence seeds this project's source watch, so the
        // one setting the org chose is the one the project starts with.
        proj().monitoring.cadence = state.org.cadence;
        completeStage('new');
        addReceipt('project', 'Project details saved', `${details.title} · ${details.type} · ${details.jurisdiction} · lock ${details.lock}`);
        go('new'); break;
      }
      case 'set-import-mode': state.importMode = node.dataset.value; saveState(); renderRoute(); break;
      case 'import-error': {
        const fmt = importFormat();
        openDialog({
          title: fmt.errorTitle,
          description: `Preview of a permanent ${state.importMode} ingest failure.`,
          body: `${banner({ tone: 'is-danger', icon: '⚠', title: 'No version was created', message: esc(fmt.errorBody) })}
          <p class="mono small muted gap-t-4">error ${esc(fmt.errorCode)} · safe to retry with another file</p>
          <p class="small muted gap-t-3">A failed parse creates no version. The uploaded artifact and the failure detail are kept so the cause stays diagnosable.</p>`,
        });
        break;
      }
      case 'create-v1': {
        /* A Paste import records what was actually pasted: its size is measured
           from the text, so the receipt describes the reviewer's input rather
           than a fixed file. Other modes keep the sample file's details. */
        const pasting = state.importMode === 'Paste';
        const pasted = pasting ? (document.querySelector('#paste-source')?.value.trim() || '') : '';
        if (pasting && !pasted) { toast('Paste some screenplay text first.', true); document.querySelector('#paste-source')?.focus(); break; }
        if (!pasting && !state.fileChosen) { toast('Choose a file to import first.', true); break; }
        /* Ingestion #6: v1 was committed the moment Import was pressed, so parser
           warnings were recorded onto a version nobody had accepted. The warnings
           are shown first and the version waits for an explicit confirmation. */
        if (!proj().versions.length && !state.parseWarnings) {
          const fmt = importFormat();
          state.parseWarnings = fmt.warnings;
          saveState();
          const rows = fmt.warnings.map((w) => `<div class="cluster-between gap-t-2"><span class="small">${esc(w.text)}</span>${badge(w.level, w.level === 'Warning' ? 'is-warning' : '')}</div>`).join('');
          openDialog({
            title: 'Review what the parser found',
            description: 'These are recorded against the version permanently. Accepting does not relabel them as clean.',
            wide: true,
            body: `<div class="cluster-between"><span class="field-label">Source</span><span class="mono small">${esc(pasting ? 'pasted text' : fmt.file)}</span></div>
            <div class="gap-t-4">${rows}</div>
            ${banner({ tone: 'is-accent', icon: 'ℹ', title: 'No errors blocked the parse',
              message: 'An error would stop v1 entirely — there is no threshold that waives one. These are info and warning results, which you may accept.' })}`,
            actions: `<button class="button button-secondary" type="button" data-action="reject-import">Reject and re-import</button><button class="button button-primary" type="button" data-action="create-v1">Accept with warnings</button>`,
          });
          break;
        }
        if (!proj().versions.length) {
          if (pasting) proj().pastedSource = pasted;
          const words = pasted ? pasted.split(/\s+/).filter(Boolean).length : 0;
          proj().versions = [{ label: 'v1', source: `${state.importMode} import`, hash: '9c7a23d08e41', createdAt: new Date().toISOString(), parent: null }];
          addReceipt('version', 'Immutable v1 created', pasting
            ? `Paste import · ${words} word${words === 1 ? '' : 's'} received · SHA 9c7a…e41`
            : `${state.importMode} import · ${importFormat().file} · ${(state.parseWarnings || []).length} parser note${(state.parseWarnings || []).length === 1 ? '' : 's'} attached · SHA 9c7a…e41`);
        }
        state.parseWarnings = null;
        saveState();
        closeDialog();
        completeStage('versions'); renderRoute(); break;
      }
      case 'reject-import': {
        /* Rejection keeps the artifact and the parse result for diagnosis but
           creates no version, matching the approved ingestion semantics. */
        state.parseWarnings = null;
        state.fileChosen = false;
        saveState();
        addReceipt('version', 'Import rejected at parse review', `${state.importMode} import · ${importFormat().file} · no version created · artifact retained for diagnosis`);
        closeDialog(); renderRoute();
        toast('Import rejected. No version was created.');
        break;
      }
      case 'choose-file': {
        /* A file picker cannot be simulated honestly in a prototype, so this
           records the selection the same way a picker would and says so. */
        state.fileChosen = true;
        saveState(); renderRoute();
        toast(`${importFormat().file} selected. The prototype does not read a real file.`);
        break;
      }
      case 'start-run': startRun(); toast('Check started — the agent is reading the script.'); break;
      case 'cancel-run': cancelRun(); toast('Check cancelled. Nothing was recorded.'); break;
      case 'open-workspace': go('workspace'); break;
      case 'open-trace': openDialog({
        title: 'What happened behind the scenes', description: 'The first check · Borrowed Light', wide: true,
        body: `<div class="timeline">
          <div class="timeline-row is-done"><span class="timeline-dot" aria-hidden="true">✓</span><div><strong class="small">Parser</strong><p class="small muted">Normalized ${SCRIPT_META.scenes} scenes, retained element identifiers.</p><span class="mono muted">input SHA 9c7a…e41 · 182ms</span></div>${badge('Complete', 'is-success')}</div>
          <div class="timeline-row is-done"><span class="timeline-dot" aria-hidden="true">✓</span><div><strong class="small">Category detectors</strong><p class="small muted">Created ${DEMO_FACTS.flags} item records across all ten categories.</p><span class="mono muted">policy 3.2 · prompt detect-11</span></div>${badge('Complete', 'is-success')}</div>
          <div class="timeline-row is-active"><span class="timeline-dot" aria-hidden="true">!</span><div><strong class="small">Source research</strong><p class="small muted">${DEMO_FACTS.sources} sources retained. One timeout recovered, one source requires manual review.</p><span class="mono muted">provider trace prl_81bf</span></div>${badge('Bounded', 'is-warning')}</div>
        </div>`,
      }); break;
      case 'select-item': proj().activeItem = node.dataset.item; state.paneTab = 'evidence'; saveState(); renderRoute(); break;
      case 'select-flag': {
        proj().activeItem = node.dataset.item;
        if (node.dataset.scene) proj().activeScene = Number(node.dataset.scene);
        state.drawerOpen = true;
        if (window.matchMedia('(max-width: 900px)').matches) state.paneTab = 'evidence';
        saveState(); renderRoute(); break;
      }
      case 'goto-scene': {
        proj().activeScene = Number(node.dataset.scene);
        saveState();
        if (window.matchMedia('(max-width: 900px)').matches) { state.paneTab = 'script'; renderRoute(); }
        else renderRoute();
        requestAnimationFrame(() => {
          document.querySelector(`#scene-${node.dataset.scene}`)?.scrollIntoView({
            behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
            block: 'start',
          });
        });
        break;
      }
      case 'open-drawer-pane': state.drawerOpen = true; saveState(); renderRoute(); break;
      case 'close-drawer-pane': state.drawerOpen = false; saveState(); renderRoute(); break;
      /* The address has to name the record. Storing the id only in state meant
         #item resolved to whatever was last clicked, so a link to CC-110 opened
         CC-101 for the next reader and a reload lost the item entirely. */
      case 'open-item': proj().activeItem = node.dataset.item; saveState(); go(`item?id=${encodeURIComponent(node.dataset.item)}`); break;
      case 'set-pane': state.paneTab = node.dataset.value; saveState(); renderRoute(); break;
      case 'set-items-view': state.itemsView = node.dataset.value; saveState(); renderRoute(); break;
      case 'toggle-select': {
        const id = node.dataset.item;
        state.selectedItems = node.checked
          ? [...new Set([...(state.selectedItems || []), id])]
          : (state.selectedItems || []).filter((x) => x !== id);
        saveState(); renderRoute(); break;
      }
      case 'bulk-clear': state.selectedItems = []; saveState(); renderRoute(); break;
      case 'bulk-assign': openDialog({
        title: `Assign ${state.selectedItems.length} item${state.selectedItems.length === 1 ? '' : 's'}`,
        description: 'One assignment receipt is written per item.',
        body: `<div class="form-grid">
            <label class="field"><span class="field-label">Assignee</span><select id="bulk-to">${state.members.filter((m) => m.role !== 'Viewer').map((m) => `<option>${esc(m.name)}</option>`).join('')}</select></label>
            <label class="field"><span class="field-label">Due date</span><input type="date" id="bulk-due" value="${esc(dueInputValue(state.selectedItems[0]))}"></label>
          </div>
          <p class="small muted gap-t-3">${state.selectedItems.map(esc).join(', ')}</p>`,
        actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-bulk-assign">Assign all</button>`,
      }); break;
      case 'confirm-bulk-assign': {
        const who = document.querySelector('#bulk-to')?.value || 'Mara Voss';
        // Bulk now stamps a due date like single assignment, so the two produce
        // the same record for the same operation.
        const due = document.querySelector('#bulk-due')?.value || '';
        const ids = [...state.selectedItems];
        ids.forEach((id) => {
          proj().assignments[id] = who;
          if (due) {
            proj().assignmentDue = proj().assignmentDue || {};
            proj().assignmentDue[id] = due;
          }
          addReceipt('assignment', 'Clearance item assigned', `${id} · ${who}${due ? ` · due ${fmtDueDate(due)}` : ''} · bulk action`);
        });
        state.selectedItems = [];
        saveState(); closeDialog(); renderRoute();
        toast(`${ids.length} item${ids.length === 1 ? '' : 's'} assigned to ${who}${due ? `, due ${fmtDueDate(due)}` : ''}.`);
        break;
      }
      case 'set-item-filter': state.itemFilter = node.dataset.value; saveState(); renderRoute(); break;
      case 'set-items-sort': {
        const key = node.dataset.key;
        if (state.itemsSort.key === key) {
          state.itemsSort.dir = state.itemsSort.dir === 'asc' ? 'desc' : 'asc';
        } else {
          state.itemsSort = { key, dir: SORT_DEFAULT_DIR[key] || 'asc' };
        }
        saveState(); renderRoute(); break;
      }
      case 'set-items-group': state.itemsGroup = node.value; saveState(); renderRoute(); break;
      case 'set-items-search': {
        /* Typing must not move the page or the caret. renderRoute() scrolls to
           top, focuses the route heading and announces the surface, which is
           right for navigation and wrong for a keystroke — so the view is
           preserved around it and the selection restored exactly. */
        const box = node;
        const start = box.selectionStart;
        const end = box.selectionEnd;
        const scrollY = window.scrollY;
        state.itemsSearch = box.value;
        saveState();
        suppressRouteFocus = true;
        renderRoute();
        suppressRouteFocus = false;
        const restored = document.querySelector('#items-search');
        if (restored) {
          restored.focus({ preventScroll: true });
          try { restored.setSelectionRange(start, end); } catch (_) { /* unsupported type */ }
        }
        window.scrollTo({ top: scrollY, behavior: 'auto' });
        break;
      }
      case 'clear-items-search': {
        state.itemsSearch = '';
        saveState();
        renderRoute();
        requestAnimationFrame(() => document.querySelector('#items-search')?.focus());
        break;
      }
      case 'open-source': {
        const item = ITEMS.find((i) => i.id === proj().activeItem) || ITEMS[0];
        openDialog({
          title: `Provenance · ${item.term}`, description: esc(item.source),
          body: `<div class="stack">
            ${card({ quiet: true, body: `<span class="field-label">Authority</span><p class="small">${esc(item.authority)} — retrieved from the source owner or an official index where available.</p>` })}
            ${card({ quiet: true, body: `<span class="field-label">Normalized claim</span><p class="small">${esc(item.excerpt)}</p>` })}
            ${card({ quiet: true, body: `<span class="field-label">Reproducibility</span><p class="mono small">snapshot src_${item.id.toLowerCase().replace('-', '_')} · retrieved Aug 19 · 15:42 · content hash retained</p>` })}
          </div>`,
        }); break;
      }
      case 'assign-dialog': openDialog({
        title: 'Reassign item', description: `Item <span class="mono">${esc(node.dataset.item)}</span>`,
        body: `<div class="form-grid">
          <label class="field"><span class="field-label">Assignee</span><select id="assign-to">${state.members.filter((m) => m.role !== 'Viewer').map((m) => `<option>${esc(m.name)}</option>`).join('')}</select></label>
          <label class="field"><span class="field-label">Due date</span><input type="date" id="assign-due" value="${esc(dueInputValue(node.dataset.item))}"></label>
        </div>`,
        actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-assign" data-item="${esc(node.dataset.item)}">Save assignment</button>`,
      }); break;
      case 'confirm-assign': {
        const who = document.querySelector('#assign-to')?.value || 'Mara Voss';
        const dueRaw = document.querySelector('#assign-due')?.value || '';
        const due = fmtDueDate(dueRaw);
        proj().assignments[node.dataset.item] = who;
        if (due) proj().assignmentDue[node.dataset.item] = due;
        addReceipt('assignment', 'Clearance item assigned', `${node.dataset.item} · ${who}${due ? ` · due ${due}` : ''}`, node.dataset.item);
        closeDialog(); renderRoute(); toast('Assignment recorded.'); break;
      }
      case 'add-comment': {
        const field = document.querySelector('#item-comment');
        const text = field?.value.trim();
        if (!text) { toast('Write a comment before adding it.', true); field?.focus(); break; }
        const named = mentionsIn(text);
        proj().comments.push({
          id: nextCommentId(), item: node.dataset.item, text, actor: ACTOR.name,
          at: new Date().toISOString(), parent: null, editedAt: null, revisions: [],
        });
        addReceipt('comment', 'Review comment added', `${node.dataset.item} · ${text.slice(0, 70)}`, node.dataset.item);
        /* A mention is a request for somebody's attention, so it is recorded as
           its own action — otherwise the person named has no way to find it. */
        named.forEach((m) => addReceipt('comment', `${m.name} mentioned`, `${node.dataset.item} · asked to look by ${ACTOR.name}`, node.dataset.item));
        saveState(); renderRoute();
        toast(named.length ? `Comment recorded. ${named.map((m) => m.name.split(' ')[0]).join(', ')} notified.` : 'Comment added to the review record.');
        break;
      }
      case 'reply-dialog': {
        const parent = proj().comments.find((c) => c.id === node.dataset.comment);
        if (!parent) { toast('That comment is no longer on the record.', true); break; }
        openDialog({
          title: `Reply to ${parent.actor}`,
          description: 'Replies stay one level deep, so the record reads in order.',
          body: `<blockquote class="small">${commentBody(parent.text)}</blockquote>
            <label class="field gap-t-4"><span class="field-label">Your reply</span><textarea id="reply-text" rows="4" placeholder="Answer the question or add what is missing…"></textarea></label>`,
          actions: `<button class="button button-quiet" type="button" data-action="close-dialog">Cancel</button>
            <button class="button button-primary" type="button" data-action="confirm-reply" data-comment="${parent.id}" data-item="${parent.item}">Post reply</button>`,
        });
        break;
      }
      case 'confirm-reply': {
        const field = document.querySelector('#reply-text');
        const text = field?.value.trim();
        if (!text) { toast('Write a reply before posting it.', true); field?.focus(); break; }
        const named = mentionsIn(text);
        proj().comments.push({
          id: nextCommentId(), item: node.dataset.item, text, actor: ACTOR.name,
          at: new Date().toISOString(), parent: node.dataset.comment, editedAt: null, revisions: [],
        });
        addReceipt('comment', 'Reply added', `${node.dataset.item} · ${text.slice(0, 70)}`, node.dataset.item);
        named.forEach((m) => addReceipt('comment', `${m.name} mentioned`, `${node.dataset.item} · asked to look by ${ACTOR.name}`, node.dataset.item));
        closeDialog(); renderRoute(); toast('Reply recorded.');
        break;
      }
      case 'edit-comment-dialog': {
        const c = proj().comments.find((x) => x.id === node.dataset.comment);
        if (!c) { toast('That comment is no longer on the record.', true); break; }
        if (c.actor !== ACTOR.name) { toast('You can only edit your own comments.', true); break; }
        openDialog({
          title: 'Edit your comment',
          description: 'The previous wording is kept. A review record that can be quietly rewritten is not a record.',
          body: `<label class="field"><span class="field-label">Comment</span><textarea id="edit-text" rows="4">${esc(c.text)}</textarea></label>`,
          actions: `<button class="button button-quiet" type="button" data-action="close-dialog">Cancel</button>
            <button class="button button-primary" type="button" data-action="confirm-edit-comment" data-comment="${c.id}">Save change</button>`,
        });
        break;
      }
      case 'confirm-edit-comment': {
        const c = proj().comments.find((x) => x.id === node.dataset.comment);
        const field = document.querySelector('#edit-text');
        const text = field?.value.trim();
        if (!c) { toast('That comment is no longer on the record.', true); break; }
        if (!text) { toast('A comment cannot be emptied. Write the new wording.', true); field?.focus(); break; }
        if (text === c.text) { closeDialog(); toast('No change to save.'); break; }
        // Keep what it said before, so the edit is visible rather than silent.
        c.revisions = [...(c.revisions || []), { text: c.text, at: c.editedAt || c.at }];
        c.text = text;
        c.editedAt = new Date().toISOString();
        addReceipt('comment', 'Comment edited', `${c.item} · previous wording retained`, c.item);
        closeDialog(); renderRoute(); toast('Comment updated. The previous wording is kept.');
        break;
      }
      case 'evidence-dialog': evidenceDialog(node.dataset.decision, node.dataset.item); break;
      case 'confirm-evidence': {
        const itemId = node.dataset.item;
        const decision = node.dataset.decision;
        proj().evidenceDecisions[itemId] = decision;
        /* Bind the call to the draft it answered, so it still reads truthfully
           after a rewrite creates a newer version. */
        proj().decisionBinding[itemId] = { version: boundVersionLabel(), actor: ACTOR.name, at: new Date().toISOString() };
        completeStage('items');
        addReceipt('evidence', decision === 'accepted' ? 'Source verified' : 'Source ruled out', `${itemId} · ${boundVersionLabel()} · rationale retained`, itemId);

        // Live POST mutation to FastAPI backend
        if (typeof window !== 'undefined' && window.fetch) {
          fetch(`http://127.0.0.1:8000/api/v1/organizations/northlight/projects/borrowed-light/items/${encodeURIComponent(itemId)}/decisions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_id: itemId, decision, rationale: 'Source verified from primary registry record', actor: ACTOR.name }),
          })
          .then(async (r) => {
            const json = await r.json().catch(() => ({}));
            console.log(`[ClearCut Live API Decision Sync] POST /decisions (HTTP ${r.status})`, json);
          })
          .catch((e) => console.warn('[ClearCut Live API Decision Sync Offline]', e));
        }

        closeDialog(); renderRoute(); toast('Your call is on the record.'); break;
      }
      case 'referral-dialog': openDialog({
        title: proj().referralCreated ? 'Referral record' : 'Refer CC-104 to a music specialist?',
        description: 'A referral preserves the search history and names the unanswered question.',
        body: proj().referralCreated
          ? `${banner({ tone: 'is-success', icon: '✓', title: 'Referral recorded', message: 'CC-104 assigned to Eli Chen. The item appears in the unresolved appendix until answered.' })}${proj().referralBrief ? `<div class="field gap-t-4"><span class="field-label">Brief sent to the specialist</span><p class="small preserve-lines">${esc(proj().referralBrief)}</p></div>` : ''}`
          : `<label class="field"><span class="field-label">Specialist brief</span><textarea id="referral-brief" rows="4">Identify the composition and publisher for the "Blue Monday" lyric fragment. Review all three candidate works and preserve correspondence.</textarea></label>`,
        actions: proj().referralCreated
          ? '<button class="button button-primary" type="button" data-action="close-dialog">Done</button>'
          : `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-referral">Create referral</button>`,
      }); break;
      case 'confirm-referral': {
        const brief = document.querySelector('#referral-brief')?.value.trim() || '';
        if (!brief) { toast('Add a brief before creating the referral.', true); document.querySelector('#referral-brief')?.focus(); break; }
        proj().referralCreated = true;
        proj().referralBrief = brief;
        completeStage('items');
        // The receipt carries the first line of the actual brief the reviewer wrote,
        // so the record reflects the instruction the specialist received.
        const firstLine = brief.split('\n')[0].slice(0, 90);
        addReceipt('referral', 'Music specialist referral created', `CC-104 · Eli Chen · ${firstLine}`, 'CC-104');
        closeDialog(); renderRoute(); toast('Referral recorded.'); break;
      }
      case 'rewrite-dialog': {
        const rid = node.dataset.item || 'CC-110';
        const ritem = ITEMS.find((i) => i.id === rid) || ITEMS[0];
        const line = scriptLineFor(rid);
        // CC-110 is the designed lower-risk rewrite that drives the v2 re-scan
        // demonstration; approving it creates the immutable v2. Every other flag
        // can still propose a rewrite — the reviewer drafts the replacement line,
        // which is recorded against the flag without fabricating a second version.
        const isPrimary = rid === 'CC-110';
        const alreadyDone = isPrimary && proj().rewriteApproved;
        const proposal = proposalFor(rid);
        const block = proposal && !proposal.approvedAt ? rewriteApprovalBlock(rid) : null;
        openDialog({
          title: alreadyDone ? 'Approved rewrite record' : proposal ? `Proposed rewrite for ${rid}` : `Propose a rewrite for ${rid}`,
          description: alreadyDone
            ? 'The approved change and the line it replaced.'
            : proposal
              ? 'A proposal is on the record. Approving it is a separate, accountable step.'
              : 'Proposing records the replacement line against this flag. It does not edit the script or create a version — approval is a separate step by another reviewer.',
          wide: true,
          body: alreadyDone
            ? `<div class="diff">
                <section><div class="cluster-between"><span class="field-label">v1 · blocked</span>${badge('Policy P-12', 'is-danger')}</div><p class="diff-text"><del>${esc(line.text)}</del></p></section>
                <section><div class="cluster-between"><span class="field-label">v2</span>${badge('Lower risk', 'is-success')}</div><p class="diff-text"><ins>${esc(proj().rewriteText || line.rewritten || '')}</ins></p></section>
              </div>
              ${proposal && proposal.by ? `<p class="small muted gap-t-4">Proposed by ${esc(proposal.by)} (${esc(proposal.byRole || 'unknown role')})${proposal.at ? ` · ${esc(fmtStamp(proposal.at))}` : ''}. Approved by ${esc(proposal.approvedBy || ACTOR.name)}${proposal.approvedRole ? ` (${esc(proposal.approvedRole)})` : ''}${proposal.approvedAt ? ` · ${esc(fmtStamp(proposal.approvedAt))}` : ''}.</p>` : ''}`
            : `<div class="diff">
                <section><div class="cluster-between"><span class="field-label">Current line · ${esc(rid)}</span>${badge(ritem.severity, ritem.severity === 'High' ? 'is-warning' : '')}</div><p class="diff-text"><del>${esc(line.text)}</del></p></section>
                ${proposal ? `<section><div class="cluster-between"><span class="field-label">Proposed</span>${badge('Awaiting approval', 'is-warning')}</div><p class="diff-text"><ins>${esc(proposal.text)}</ins></p></section>` : ''}
              </div>
              ${proposal
                ? `<div class="stack-sm gap-t-4">
                    <p class="small muted">Proposed by ${esc(proposal.by || 'an earlier session')}${proposal.byRole ? ` (${esc(proposal.byRole)})` : ''}${proposal.at ? ` · ${esc(fmtStamp(proposal.at))}` : ''}.</p>
                    ${block ? banner({ tone: 'is-warning', icon: '◔', title: 'This is not yours to approve', message: block }) : banner({ tone: '', icon: '○', title: 'Separate hands', message: `You are approving as ${esc(actorRole())}, a different hand from the ${esc(proposal.byRole || 'author')} who proposed it.` })}
                    <details><summary class="small muted">Revise the proposal instead</summary>
                      <label class="field gap-t-3"><span class="field-label">Replacement line</span><textarea id="rewrite-text" rows="3">${esc(proposal.text)}</textarea></label>
                      <p class="small muted">Revising replaces the proposal and restarts approval, so nobody approves wording they did not read.</p>
                    </details>
                  </div>`
                : `<label class="field gap-t-4"><span class="field-label">Proposed replacement line</span><textarea id="rewrite-text" rows="3">${esc(line.rewritten || line.text)}</textarea></label>`}
              ${isPrimary ? `<div class="gap-t-4">${banner({ tone: 'is-warning', icon: 'ℹ', title: 'Downstream effect', message: 'Approval creates v2. CC-110 and its contextual neighbour CC-109 will need a selective re-scan; the other flags keep their settled evidence.' })}</div>` : ''}`,
          actions: alreadyDone
            ? '<button class="button button-primary" type="button" data-action="close-dialog">Done</button>'
            : proposal
              ? `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button>
                 <button class="button button-secondary" type="button" data-action="revise-rewrite" data-item="${esc(rid)}">Save revision</button>
                 ${block
                   ? `<button class="button button-primary" type="button" disabled aria-disabled="true" title="${esc(block)}">Approve${isPrimary ? ' &amp; create v2' : ''}</button>`
                   : `<button class="button button-primary" type="button" data-action="approve-rewrite" data-item="${esc(rid)}">Approve${isPrimary ? ' &amp; create v2' : ''}</button>`}`
              : `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button>
                 ${gated('rewrite', `<button class="button button-primary" type="button" data-action="confirm-rewrite" data-item="${esc(rid)}">Record proposal</button>`)}`,
        }); break;
      }
      /* Proposing is the first of two hands. It records the wording, its author and
         the time, and creates no version — approval does that, and only by
         somebody else. */
      case 'confirm-rewrite': {
        const rid = node.dataset.item || 'CC-110';
        const proposed = document.querySelector('#rewrite-text')?.value.trim() || '';
        if (!proposed) { toast('Write the replacement line first.', true); document.querySelector('#rewrite-text')?.focus(); break; }
        proj().rewriteProposals = proj().rewriteProposals || {};
        proj().rewriteProposals[rid] = { text: proposed, by: ACTOR.name, byRole: actorRole(), at: new Date().toISOString(), approvedBy: null, approvedRole: null, approvedAt: null };
        addReceipt('rewrite', 'Rewrite proposed', `${rid} · "${proposed.slice(0, 70)}" · awaiting approval`, rid);
        closeDialog(); renderRoute(); toast('Proposal recorded. It needs another reviewer to approve it.');
        break;
      }
      case 'revise-rewrite': {
        const rid = node.dataset.item || 'CC-110';
        const revised = document.querySelector('#rewrite-text')?.value.trim() || '';
        const existing = proposalFor(rid);
        if (!revised) { toast('Write the replacement line first.', true); document.querySelector('#rewrite-text')?.focus(); break; }
        if (existing && revised === existing.text) { closeDialog(); toast('No change to the proposal.'); break; }
        proj().rewriteProposals[rid] = { text: revised, by: ACTOR.name, byRole: actorRole(), at: new Date().toISOString(), approvedBy: null, approvedRole: null, approvedAt: null };
        addReceipt('rewrite', 'Proposal revised', `${rid} · "${revised.slice(0, 70)}" · approval restarted`, rid);
        closeDialog(); renderRoute(); toast('Proposal revised. Approval starts again.');
        break;
      }
      case 'approve-rewrite': {
        const rid = node.dataset.item || 'CC-110';
        const blocked = rewriteApprovalBlock(rid);
        // Re-checked at the moment of the action, not only when the button was
        // drawn: the role can change while the dialog is open.
        if (blocked) { toast(blocked, true); break; }
        const proposal = proposalFor(rid);
        proj().rewriteProposals[rid] = { ...proposal, approvedBy: ACTOR.name, approvedRole: actorRole(), approvedAt: new Date().toISOString() };
        if (rid === 'CC-110') {
          createVersionTwo(proposal.text);
          closeDialog(); renderRoute(); toast('Approved. v2 created — v1 untouched.');
        } else {
          addReceipt('rewrite', 'Rewrite approved', `${rid} · approved by ${ACTOR.name} (${actorRole()}) · awaiting next snapshot`, rid);
          closeDialog(); renderRoute(); toast('Approved. It lands in the next snapshot.');
        }
        break;
      }
      case 'disposition-dialog': openDialog({
        title: 'Record the final decision',
        description: 'An accountable production record, not a legal conclusion.',
        body: `<label class="field"><span class="field-label">The call</span><select id="disposition-value">${['Proceed with conditions', 'Hold for specialist review', 'Revise before production'].map((o) => `<option ${o === proj().disposition ? 'selected' : ''}>${o}</option>`).join('')}</select></label>
        <label class="field gap-t-4"><span class="field-label">Rationale</span><textarea id="disposition-rationale" rows="3">${esc(proj().dispositionRationale || 'Proceed with the approved privacy rewrite. Preserve the music referral and monitor the Vega registration.')}</textarea><span class="field-hint">Recorded with the call, and shown on the overview.</span></label>`,
        actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-disposition">Record the final decision</button>`,
      }); break;
      case 'confirm-disposition': {
        // The rationale is the part that matters on a final call, so it is
        // required, stored, and carried into the receipt and the record.
        const rationale = document.querySelector('#disposition-rationale')?.value.trim() || '';
        if (!rationale) { toast('Give a reason for the final call.', true); document.querySelector('#disposition-rationale')?.focus(); break; }
        proj().disposition = document.querySelector('#disposition-value')?.value || 'Proceed with conditions';
        proj().dispositionRationale = rationale;
        completeStage('items');
        addReceipt('disposition', 'Final decision recorded', `${proj().disposition} · ${rationale.slice(0, 90)}`);
        closeDialog(); renderRoute(); toast('Final decision recorded.'); break;
      }
      case 'selective-rescan': startRescan(); break;
      case 'cancel-rescan': cancelRescan(); toast('Re-check cancelled. Nothing was changed.'); break;
      case 'rescan-fail-next':
        /* Prototype affordance: arm the next re-read to fail, so the durable-job
           failure state can be reviewed without waiting for a real provider fault. */
        proj().rescanFailAt = rescanScope().all[1]?.id || rescanScope().all[0]?.id || null;
        saveState(); renderRoute();
        toast(proj().rescanFailAt ? `Armed: the re-check will stop at ${proj().rescanFailAt}.` : 'Nothing to arm — approve a rewrite first.', true);
        break;
      /* Changing how often sources are watched is a governed setting, so it
         leaves a receipt like every other one — but only when the value really
         changes, or re-selecting the current option would litter the ledger. */
      case 'set-cadence': {
        const before = proj().monitoring.cadence;
        const next = node.value;
        if (next === before) break;
        proj().monitoring.cadence = next;
        saveState();
        addReceipt('monitoring', 'Source-watch cadence changed', `${cadenceLabel(before)} → ${cadenceLabel(next)}`);
        renderRoute();
        toast(`Source watch: ${cadenceLabel(next).toLowerCase()}.`);
        break;
      }
      case 'manual-monitor': startMonitorSweep(); break;
      case 'cancel-monitor': cancelMonitorSweep(); toast('Check stopped. Nothing was recorded.'); break;
      case 'monitor-review-dialog': monitorReviewDialog(); break;
      case 'confirm-monitor-review': {
        const effect = document.querySelector('#monitor-effect')?.value || 'keep';
        const rationale = document.querySelector('#monitor-rationale')?.value || '';
        reviewMonitoringChange(effect, rationale);
        closeDialog(); renderRoute();
        toast(effect === 'reopen' ? 'Review recorded. CC-101 reopened for a fresh call.'
          : effect === 'refer' ? 'Review recorded. CC-101 referred to a specialist.'
          : 'Review recorded. Accepted evidence unchanged.');
        break;
      }
      case 'promote-learning': promoteLearningCandidate(); renderRoute(); toast(state.learning.stage === 'canary' ? 'Candidate entered the 10% canary.' : 'Candidate promoted with rollback retained.'); break;
      case 'rollback-learning': rollbackLearningCandidate(); renderRoute(); toast('Candidate rolled back.'); break;
      case 'dossier-dialog': openDialog({
        title: proj().dossier ? 'Export record' : 'Generate and release the clearance report?',
        description: 'The report captures this exact moment and lists anything still open.',
        /* Both cards used to be fixed text: "Script snapshot v2" regardless of
           the version, and a two-line open list naming CC-104 and CC-101 while
           the report's own appendix derived eight. */
        body: (() => {
          const bind = reportBinding(proj().dossier, boundVersionLabel());
          const stillOpen = openItems();
          return `<div class="grid grid-2">
          ${card({ quiet: true, body: `<span class="field-label">Made from</span><div class="stack-gap-sm"><p class="small">Script snapshot <span class="mono">${esc(bind.script)}</span>, graded ${bind.score}/100 against rubric <span class="mono">${esc(bind.rubric)}</span> under sign-off rules <span class="mono">${esc(bind.policy)}</span>.</p></div>` })}
          ${card({ quiet: true, body: `<span class="field-label">Still open (${stillOpen.length})</span><div class="stack-gap-sm">${stillOpen.length
            ? `<p class="small">${stillOpen.slice(0, 3).map((i) => `${esc(i.id)} — ${esc(itemStatus(i).toLowerCase())}`).join('<br>')}${stillOpen.length > 3 ? `<br><span class="muted">and ${stillOpen.length - 3} more, all listed in the appendix</span>` : ''}</p>`
            : '<p class="small">Nothing outstanding. Every flag has a recorded human decision.</p>'}</div>` })}
        </div>
        <div class="stack-gap">${banner({ tone: 'is-warning', icon: '⚠', title: 'Attestation', message: `${esc(ACTOR.name)} confirms this report accurately represents ${esc(state.org.name)}'s decisions — and that it is not legal advice.` })}</div>`;
        })(),
        actions: proj().dossier
          ? '<button class="button button-primary" type="button" data-action="close-dialog">Done</button>'
          : `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-dossier">Generate &amp; release</button>`,
      }); break;
      case 'generate-snapshot': generateSnapshot(); renderRoute(); toast('Snapshot frozen. Preview it, then release.'); break;
      case 'regenerate-snapshot': proj().snapshot = null; generateSnapshot(); renderRoute(); toast('New snapshot frozen from current state.'); break;
      case 'confirm-dossier': releaseDossier(); closeDialog(); renderRoute(); toast('Clearance report released — it is on the record.'); break;
      /* A manual batch records its own tool calls, so its ledger totals derive
         the same way the seeded runs' do. Writing literal totals here produced a
         run whose "5 sources" no reader could open and check. */
      case 'run-research': {
        const n = state.researchRuns.length + 1;
        const id = `run_1${n}`;
        const calls = [
          { tool: 'parallel.search', target: 'open flags · authority refresh', ms: 6200, sources: 3, result: '3 sources', status: 'ok' },
          { tool: 'parallel.search', target: 'open flags · recency sweep', ms: 5900, sources: 2, result: '2 sources', status: 'ok' },
          { tool: 'evidence.normalise', target: '5 retrieved sources', ms: 1100, claims: 7, result: '7 claims', status: 'ok' },
        ];
        state.researchRuns.unshift({
          id, started: fmtStamp(new Date().toISOString()), scope: 'Manual batch (open items)',
          cost: '$0.011', model: 'gemini-2.5-flash', prompt: 'cc-research-17', status: 'Complete', calls,
        });
        const t = runTotals(id);
        addReceipt('research', 'Research batch completed', `Manual batch · ${t.sources} sources · ${t.claims} claims · $0.011`);
        saveState(); renderRoute(); toast(`Research batch complete. ${t.sources} sources retained.`);
        break;
      }
      /* Every tool call a run made, with the argument it was given and what came
         back. The run summary said a run "recovered" without letting anyone see
         from what; this is that record. */
      case 'open-tool-calls': {
        const runId = node.dataset.run;
        const run = allRuns().find((r) => r.id === runId);
        if (!run) break;
        const calls = toolCallsFor(runId);
        const t = runTotals(runId);
        openDialog({
          wide: true,
          title: `Tool calls · ${runId}`,
          description: `${esc(run.scope)} · model <span class="mono">${esc(run.model)}</span> · prompt <span class="mono">${esc(run.prompt)}</span>`,
          body: `${statGrid([
            { label: 'Calls', value: t.calls },
            { label: 'Sources', value: t.sources },
            { label: 'Claims', value: t.claims },
            { label: 'Total time', value: fmtDuration(t.ms) },
          ])}
          <div class="stack-gap">${t.exceptions
            ? banner({ tone: 'is-warning', icon: '⚠', title: `${t.exceptions} exception${t.exceptions === 1 ? '' : 's'} on this run`, message: 'Shown in place below. A failed call never becomes invented evidence — it either retries or becomes work for a person.' })
            : banner({ icon: '✓', tone: 'is-success', title: 'Every call was accepted', message: 'No retries, timeouts or bounded results on this run.' })}</div>
          <div class="gap-t-4">${banner({ tone: '', icon: '◑', title: 'What this ledger deliberately does not show',
            message: 'Arguments and results are summaries. Raw provider payloads, screenplay text, full source bodies, credentials, tokens and signed URLs are never rendered here — a debugging view is not a place to leak the material it was checking. Model reasoning is not shown at all.' })}</div>
          ${dataTable({
            caption: `Tool calls for ${runId}`,
            columns: [{ label: '#' }, { label: 'Tool' }, { label: 'Given (redacted summary)' }, { label: 'Took' }, { label: 'Returned (redacted summary)' }, { label: 'Status' }],
            rows: calls.map((c, i) => [
              `<span class="mono muted">${i + 1}</span>`,
              `<span class="mono">${esc(c.tool)}</span>`,
              `<span class="small">${esc(c.target)}</span>`,
              `<span class="mono">${fmtDuration(c.ms)}</span>`,
              `<span class="small">${esc(c.result)}</span>`,
              badge(TOOL_STATUS[c.status].label, TOOL_STATUS[c.status].tone),
            ]),
          })}
          <p class="small muted stack-gap">Totals above are the sum of these rows, so a run cannot report a figure its calls do not account for.</p>`,
        });
        break;
      }
      case 'retry-provider': openDialog({
        title: 'Provider recovery', description: 'Retry only the failed call and preserve successful output.',
        body: `<div class="timeline">
          <div class="timeline-row is-done"><span class="timeline-dot" aria-hidden="true">✓</span><div><strong class="small">Existing checkpoint</strong><p class="small muted">${DEMO_FACTS.sources} sources and all evidence hashes remain intact.</p></div></div>
          <div class="timeline-row is-active"><span class="timeline-dot" aria-hidden="true">↻</span><div><strong class="small">Token refresh</strong><p class="small muted">Bounded retry with idempotency key run_01_music_02.</p></div></div>
        </div>`,
        actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-provider-retry">Retry failed call</button>`,
      }); break;
      case 'confirm-provider-retry': addReceipt('provider', 'Provider call recovered', 'Research token refreshed · checkpoint preserved · retry succeeded'); closeDialog(); renderRoute(); toast('Provider call recovered.'); break;
      case 'invite-dialog': openDialog({
        title: 'Invite a member', description: 'Choose one fixed role and explicit project access.',
        body: `<div class="form-grid">
          <label class="field field-full"><span class="field-label">Email</span><input id="invite-email" type="email" value="producer@northlight.example"></label>
          <label class="field"><span class="field-label">Role</span><select id="invite-role"><option>Admin</option><option>Editor</option><option selected>Reviewer</option><option>Viewer</option></select></label>
          <label class="field"><span class="field-label">Project access</span><select id="invite-access"><option>All projects</option>${PROJECT_DEFS.map((d) => `<option>${esc(d.title)}</option>`).join('')}</select></label>
        </div>`,
        actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-invite">Send invitation</button>`,
      }); break;
      case 'delete-project-dialog': openDialog({
        title: `Schedule deletion of ${esc(projInfo().title)}?`,
        description: 'The impact preview names what stops being reproducible. Nothing is purged until the grace period ends.',
        wide: true,
        body: `${banner({ tone: 'is-danger', icon: '⚠', title: 'This removes the whole project, not selected records',
          message: 'Individual claims, snapshots, decisions, and audit events cannot be deleted on their own. Deletion takes everything below.' })}
        <div class="gap-t-4">${dataTable({
          caption: 'What will be purged',
          columns: [{ label: 'What' }, { label: 'Count' }],
          rows: [
            ['Script versions and parsed structure', `<span class="mono">${proj().versions.length}</span>`],
            ['Clearance flags and their evidence', `<span class="mono">${flags().length}</span>`],
            ['Source snapshots', `<span class="mono">${SOURCES.length}</span>`],
            ['Recorded decisions', `<span class="mono">${projectReceipts().length}</span>`],
            ['Released reports', `<span class="mono">${proj().dossier ? 1 : 0}</span>`],
          ],
        })}</div>
        <div class="gap-t-4">${banner({ tone: 'is-warning', icon: 'ℹ', title: 'Reproducibility you will lose',
          message: proj().dossier
            ? 'The released clearance report will be marked unavailable. It cannot be regenerated once its source material is purged.'
            : 'No report has been released yet, so no external party is holding a document that depends on this evidence.' })}</div>
        <label class="field gap-t-4"><span class="field-label">Type the project name to confirm</span><input id="delete-confirm" placeholder="${esc(projInfo().title)}"></label>
        <p class="small muted gap-t-2">You may export the retained record before scheduling. A 30-day grace period follows, during which you can restore.</p>`,
        actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-danger" type="button" data-action="confirm-delete-project">Schedule deletion</button>`,
      }); break;
      case 'confirm-delete-project': {
        const typed = (document.querySelector('#delete-confirm')?.value || '').trim();
        if (typed !== projInfo().title) {
          toast('Type the project name exactly to confirm.', true);
          break;
        }
        proj().deletionScheduled = new Date().toISOString();
        saveState();
        addReceipt('settings', 'Project deletion scheduled', `${projInfo().title} · read-only · 30-day grace period · ${flags().length} flags and ${SOURCES.length} sources affected`);
        closeDialog(); renderRoute();
        toast('Deletion scheduled. The project is read-only and restorable for 30 days.');
        break;
      }
      case 'restore-project': {
        proj().deletionScheduled = null;
        saveState();
        addReceipt('settings', 'Project deletion cancelled', `${projInfo().title} · restored before purge · history unchanged`);
        renderRoute();
        toast('Project restored. The cancellation is on the record.');
        break;
      }
      case 'edit-invite-dialog': {
        const who = node.dataset.member || '';
        const email = node.dataset.email || '';
        const inv = state.members.find((m) => m.email === email);
        openDialog({
          title: 'Edit invitation',
          description: 'Editing reissues the invitation. The previous link stops working.',
          body: `<div class="stack">
            <div class="cluster-between"><span class="field-label">Invitee</span><span class="mono small">${esc(email)}</span></div>
            <label class="field"><span class="field-label">Proposed role</span>
              <select id="invite-role">${ROLE_MATRIX.map((r) => `<option ${inv && r.role === inv.role ? 'selected' : ''}>${esc(r.role)}</option>`).join('')}</select></label>
            ${banner({ tone: 'is-warning', icon: '⚠', title: 'The current link is invalidated',
              message: 'Saving issues a new single-use token. Anyone holding the earlier link will need the new one.' })}
          </div>`,
          actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-edit-invite" data-email="${esc(email)}" data-member="${esc(who)}">Reissue invitation</button>`,
        });
        break;
      }
      case 'confirm-edit-invite': {
        const email = node.dataset.email;
        const next = document.querySelector('#invite-role')?.value || 'Reviewer';
        const inv = state.members.find((m) => m.email === email);
        if (inv) {
          const before = inv.role;
          inv.role = next;
          saveState();
          addReceipt('team', 'Invitation reissued', `${email} · ${before === next ? `role unchanged (${next})` : `role ${before} → ${next}`} · previous token invalidated`);
        }
        closeDialog(); renderRoute();
        toast('Invitation reissued. The previous link no longer works.');
        break;
      }
      case 'role-dialog': openDialog({
        title: `Change role · ${esc(node.dataset.member || '')}`,
        description: 'Role changes are recorded in the organization audit.',
        body: (() => {
          /* Defaulting to the first option meant opening this on a Viewer and
             pressing Save promoted them to Owner. The current role is selected,
             and the access consequence is stated before the change is committed. */
          const who = node.dataset.member || '';
          const current = state.members.find((m) => m.name === who);
          const cur = current ? current.role : 'Reviewer';
          const inherits = (r) => r === 'Owner' || r === 'Admin';
          return `<label class="field"><span class="field-label">Role</span>
            <select id="new-role">${ROLE_MATRIX.map((r) => `<option ${r.role === cur ? 'selected' : ''}>${esc(r.role)}</option>`).join('')}</select></label>
          <div class="gap-t-4">${banner({ tone: 'is-accent', icon: 'ℹ', title: `Currently ${esc(cur)}`,
            message: `${esc(ROLE_MATRIX.find((r) => r.role === cur)?.can || '')}${inherits(cur) ? ' Access to every project is inherited from this role.' : ' Project access is granted explicitly.'}` })}</div>
          <p class="small muted gap-t-3">Moving ${esc(who)} out of Owner or Admin removes inherited project access. Grant any projects they should keep before saving.</p>`;
        })(),
        actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-role" data-member="${esc(node.dataset.member || '')}">Save role</button>`,
      }); break;
      case 'confirm-role': {
        const who = node.dataset.member;
        const next = document.querySelector('#new-role')?.value || 'Reviewer';
        const member = state.members.find((m) => m.name === who);
        if (member) {
          const owners = state.members.filter((m) => m.role === 'Owner');
          if (member.role === 'Owner' && next !== 'Owner' && owners.length === 1) {
            closeDialog();
            toast('An organization must keep at least one Owner.', true);
            break;
          }
          const before = member.role;
          member.role = next;
          saveState();
          addReceipt('membership', 'Member role changed', `${who}: ${before} → ${next}`);
          closeDialog(); renderRoute(); toast(`${who} is now ${next}.`);
        } else { closeDialog(); }
        break;
      }
      case 'confirm-invite': {
        const email = document.querySelector('#invite-email')?.value.trim();
        const role = document.querySelector('#invite-role')?.value || 'Reviewer';
        const access = document.querySelector('#invite-access')?.value || 'All projects';
        if (!email) { toast('Enter an email address.', true); break; }
        if (state.members.some((m) => m.email === email)) { toast('That person is already a member.', true); break; }
        state.members.push({
          name: email.split('@')[0].replace(/^\w/, (c) => c.toUpperCase()),
          initials: email.slice(0, 2).toUpperCase(),
          email, role, access, status: 'Invited',
        });
        saveState();
        addReceipt('membership', 'Invitation sent', `${email} · ${role} · ${access}`);
        closeDialog(); renderRoute(); toast('Invitation sent and recorded.');
        break;
      }
      case 'revoke-invite': {
        const email = node.dataset.email;
        state.members = state.members.filter((m) => m.email !== email);
        saveState();
        addReceipt('membership', 'Invitation revoked', email);
        renderRoute(); toast('Invitation revoked.');
        break;
      }
      case 'save-settings': {
        const before = { ...state.org };
        const name = document.querySelector('#set-name')?.value.trim();
        if (!name) { toast('Organization name cannot be empty.', true); break; }
        state.org.name = name;
        state.org.jurisdiction = document.querySelector('#set-jurisdiction')?.value.trim() || state.org.jurisdiction;
        state.org.cadence = document.querySelector('#set-cadence')?.value || state.org.cadence;
        const changes = Object.keys(state.org).filter((k) => before[k] !== state.org[k]);
        saveState();
        // Report changes in the same vocabulary the surfaces use: the ledger
        // previously recorded the canonical 'weekly' while every screen said
        // 'Weekly'. cadenceLabel is the single exit for that value.
        const showValue = (k, v) => (k === 'cadence' ? cadenceLabel(v) : v);
        addReceipt('settings', 'Organization settings updated', changes.length
          ? changes.map((k) => `${k}: ${showValue(k, before[k])} → ${showValue(k, state.org[k])}`).join(' · ')
          : 'no fields changed');
        renderRoute();
        toast(changes.length ? `Saved ${changes.length} change${changes.length === 1 ? '' : 's'}.` : 'No changes to save.');
        break;
      }
      case 'decline-invite':
        /* Declining creates no membership and no project access, invalidates the
           link, and is recorded. It is a real outcome, not a way out of the page. */
        {
          const inv = (state.invitations || []).find((i) => i.status === 'Pending');
          if (inv) inv.status = 'Declined';
          addReceipt('membership', 'Invitation declined', `${inv ? inv.email : 'the invitee'} · no membership or project access created · token invalidated`);
        }
        go('invite?state=declined');
        toast('Invitation declined. Nothing was created.');
        break;
      case 'resend-invite': {
        const inv = (state.invitations || []).find((i) => i.id === node.dataset.id);
        if (!inv) { toast('That invitation is no longer on the record.', true); break; }
        /* Resending invalidates the previous token and issues a new version, so the
           old link stops working rather than two links being live at once. */
        inv.tokenVersion += 1;
        inv.status = 'Pending';
        inv.sentAt = 'Just now';
        addReceipt('membership', 'Invitation resent', `${inv.email} · previous token invalidated · now token v${inv.tokenVersion}`);
        saveState(); renderRoute(); toast(`Invitation resent. The earlier link no longer works.`);
        break;
      }
      case 'set-settings-tab': state.settingsTab = node.dataset.value; saveState(); go(`settings?tab=${node.dataset.value}`); break;
      case 'set-team-tab': state.teamTab = node.dataset.value; saveState(); go(`team?tab=${node.dataset.value}`); break;
      case 'access-dialog': {
        const m = state.members.find((x) => x.name === node.dataset.member);
        if (!m) break;
        openDialog({
          title: `Project access · ${esc(m.name)}`,
          description: 'Owner and Admin reach every project by their role. Editor, Reviewer and Viewer need an explicit grant per project.',
          body: m.role === 'Owner' || m.role === 'Admin'
            ? banner({ tone: '', icon: 'ℹ', title: `${esc(m.role)} reaches every project`, message: 'Access is inherited from the organization role, so there is nothing to grant here. Changing it means changing the role.' })
            : `<div class="stack">${PROJECT_DEFS.map((d) => `<label class="toggle-row"><div><strong class="small">${esc(d.title)}</strong><p class="small muted">${esc(d.type)} · ${esc(d.stage)}</p></div><input type="checkbox" ${m.access === 'All projects' || m.access === d.title ? 'checked' : ''} data-access-project="${esc(d.id)}"></label>`).join('')}</div>
              <p class="small muted gap-t-3">A grant is recorded against the membership and appears in the organization audit.</p>`,
          actions: m.role === 'Owner' || m.role === 'Admin'
            ? '<button class="button button-primary" type="button" data-action="close-dialog">Done</button>'
            : `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-access" data-member="${esc(m.name)}">Save access</button>`,
        });
        break;
      }
      case 'confirm-access': {
        const m = state.members.find((x) => x.name === node.dataset.member);
        const picked = Array.from(document.querySelectorAll('[data-access-project]'))
          .filter((c) => c.checked)
          .map((c) => PROJECT_DEFS.find((d) => d.id === c.dataset.accessProject)?.title)
          .filter(Boolean);
        if (!m) break;
        if (!picked.length) { toast('A member needs access to at least one project, or deactivate them instead.', true); break; }
        m.access = picked.length === PROJECT_DEFS.length ? 'All projects' : picked.join(', ');
        addReceipt('role', 'Project access changed', `${m.name} · now ${m.access}`);
        closeDialog(); renderRoute(); toast('Project access recorded.');
        break;
      }
      case 'deactivate-dialog': {
        const m = state.members.find((x) => x.name === node.dataset.member);
        if (!m) break;
        /* An organization must keep an active Owner, and a pending Owner invitation
           does not count towards it. */
        const activeOwners = state.members.filter((x) => x.role === 'Owner' && x.status === 'Active').length;
        if (m.role === 'Owner' && activeOwners <= 1) {
          toast('This is the only active Owner. Promote another Owner first — a pending invitation does not count.', true);
          break;
        }
        openDialog({
          title: `Deactivate ${esc(m.name)}?`,
          description: 'Deactivation is not deletion. Everything they decided stays attributed to them.',
          body: `${banner({ tone: 'is-warning', icon: '⚠', title: 'What deactivation does',
            message: 'They lose access immediately and their sessions are revoked. Their comments, evidence decisions and audit entries remain under their name, because removing them would make the remaining record misleading.' })}
          <p class="small muted gap-t-4">Reactivating later reviews role and project access explicitly rather than restoring what they had.</p>`,
          actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-danger" type="button" data-action="confirm-deactivate" data-member="${esc(m.name)}">Deactivate</button>`,
        });
        break;
      }
      case 'confirm-deactivate': {
        const m = state.members.find((x) => x.name === node.dataset.member);
        if (!m) break;
        m.status = 'Deactivated';
        addReceipt('role', 'Membership deactivated', `${m.name} · access revoked · historical attribution retained`);
        closeDialog(); renderRoute(); toast('Deactivated. Their past decisions stay on the record.');
        break;
      }
      case 'reactivate-member': {
        const m = state.members.find((x) => x.name === node.dataset.member);
        if (!m) break;
        openDialog({
          title: `Reactivate ${esc(m.name)}?`,
          description: 'A deactivated membership is never silently restored. Role and project access are set again deliberately.',
          body: `<label class="field"><span class="field-label">Organization role</span><select id="reactivate-role">${ROLE_ORDER.map((r) => `<option ${r === m.role ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select></label>
          <label class="field gap-t-4"><span class="field-label">Project access</span><select id="reactivate-access">${['All projects', ...PROJECT_DEFS.map((d) => d.title)].map((a) => `<option ${a === m.access ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select></label>
          <p class="small muted gap-t-3">Shown as it was, but recorded as a new decision — not a restoration of the old one.</p>`,
          actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-reactivate" data-member="${esc(m.name)}">Reactivate</button>`,
        });
        break;
      }
      case 'confirm-reactivate': {
        const m = state.members.find((x) => x.name === node.dataset.member);
        if (!m) break;
        m.role = document.querySelector('#reactivate-role')?.value || m.role;
        m.access = document.querySelector('#reactivate-access')?.value || m.access;
        m.status = 'Active';
        addReceipt('role', 'Membership reactivated', `${m.name} · ${m.role} · ${m.access} · reviewed on reactivation`);
        closeDialog(); renderRoute(); toast('Reactivated with role and access reviewed.');
        break;
      }
      case 'draft-policy': {
        const c = ORG_POLICIES.find((x) => x.id === node.dataset.policy);
        openDialog({
          title: `New draft · ${c ? c.name : 'policy'}`,
          description: 'An active version is immutable. A change starts as a draft copied from it, which leaves the version in force untouched until activation.',
          body: banner({ tone: '', icon: 'ℹ', title: 'The prototype stops here',
            message: 'Editing protected configuration needs the validation service and the audit transaction behind it. What is shown is the lifecycle and who may act at each step, not a working editor.' }),
        });
        break;
      }
      case 'validate-policy': {
        const c = ORG_POLICIES.find((x) => x.id === node.dataset.policy);
        openDialog({
          title: `Validate · ${c ? c.name : 'policy'}`,
          description: 'Validation checks a draft against the required fields and the rules it must not weaken.',
          body: banner({ tone: '', icon: 'ℹ', title: 'The prototype stops here',
            message: 'A real validation run reports which checks passed and which failed, and a failure moves the draft to validation_failed rather than blocking silently.' }),
        });
        break;
      }
      case 'activate-policy-dialog': {
        const c = ORG_POLICIES.find((x) => x.id === node.dataset.policy);
        if (!c) break;
        openDialog({
          title: `Activate ${esc(c.name)} ${esc(c.version)}?`,
          description: 'Activation supersedes the version in force and writes the audit event in the same transaction.',
          body: `${banner({ tone: 'is-warning', icon: '⚠', title: 'This changes what future runs bind to',
            message: 'Research runs, evidence decisions, reports and judge evaluations bind to the exact configuration versions used. Work already recorded keeps the version it was decided under.' })}
          <label class="field gap-t-4"><span class="field-label">Why this is being activated</span><textarea id="activate-rationale" rows="2" placeholder="Recorded with your name and the activation."></textarea></label>
          <label class="field gap-t-4"><span class="field-label">Type ACTIVATE to confirm</span><input id="activate-confirm" autocomplete="off"></label>
          <p class="small muted gap-t-2">A protected change also requires recent reauthentication in the hosted product.</p>`,
          actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-primary" type="button" data-action="confirm-activate-policy" data-policy="${esc(c.id)}">Activate</button>`,
        });
        break;
      }
      case 'confirm-activate-policy': {
        const c = ORG_POLICIES.find((x) => x.id === node.dataset.policy);
        const why = document.querySelector('#activate-rationale')?.value.trim() || '';
        const typed = document.querySelector('#activate-confirm')?.value.trim() || '';
        if (!why) { toast('Record why this is being activated.', true); document.querySelector('#activate-rationale')?.focus(); break; }
        if (typed !== 'ACTIVATE') { toast('Type ACTIVATE to confirm.', true); document.querySelector('#activate-confirm')?.focus(); break; }
        addReceipt('organization', 'Protected configuration activated', `${c.name} ${c.version} · prior version superseded · ${why.slice(0, 60)}`);
        closeDialog(); renderRoute();
        toast('Activated. The prior version is superseded, not deleted.');
        break;
      }
      case 'set-evaluation': state.evaluationRun = node.dataset.run; saveState(); renderRoute(); break;
      case 'set-records-view': state.recordsView = node.dataset.value; saveState(); go(`records?view=${node.dataset.value}`); break;
      case 'set-push-pref': {
        state.pushPref = node.value;
        /* Ask the browser only when the reviewer chooses push, and record what it
           answered rather than assuming yes. */
        if (node.value === 'push' && typeof Notification !== 'undefined' && Notification.permission === 'default') {
          Notification.requestPermission().then((result) => {
            state.pushPermission = result;
            saveState(); renderRoute();
            toast(result === 'granted'
              ? 'Permission granted. This prototype still delivers nothing outside the tab.'
              : 'Permission was not granted, so push cannot be used.', result !== 'granted');
          }).catch(() => {
            state.pushPermission = 'unavailable';
            saveState(); renderRoute();
          });
        }
        addReceipt('organization', 'Notification delivery preference changed', `now ${node.value}`);
        saveState(); renderRoute(); break;
      }
      case 'print-record':
        /* Hand off to the browser's own print dialog rather than pretending to
           generate a file. What it produces is the print stylesheet's work. */
        window.print();
        break;
      case 'open-notification': {
        const entry = notifications().find((x) => x.id === node.dataset.id);
        const dest = entry && entry.destination;
        const blocked = destinationBlock(dest);
        if (blocked) { toast(blocked, true); break; }
        if (!state.readNotifications.includes(node.dataset.id)) state.readNotifications.push(node.dataset.id);
        /* Switch to the project the event belongs to before navigating. Without
           this, opening a Borrowed Light notification while another project was
           active landed on that other project's surface under the right title. */
        if (dest && dest.project && dest.project !== state.activeProjectId && state.projects[dest.project]) {
          state.activeProjectId = dest.project;
        }
        saveState();
        go(dest ? destinationRoute(dest) : (node.dataset.route || 'records'));
        break;
      }
      case 'set-report-tab': state.reportTab = node.dataset.tab; renderRoute(); return;
      case 'notif-tier': state.notifTierFilter = node.dataset.tier; renderRoute(); return;
      case 'notif-project': state.notifProjectFilter = node.value; renderRoute(); return;
      case 'mark-all-read': state.readNotifications = notifications().map((n) => n.id); saveState(); renderRoute(); toast('All notifications marked read.'); break;
      case 'open-appearance': openAppearanceDialog(); break;
      /* Stays open: an appearance picker is only useful if you can flip between
         the options and watch the surface change. 'Done' closes it. */
      case 'set-theme': {
        setTheme(node.dataset.appearance);
        document.querySelectorAll('[data-action="set-theme"]').forEach((option) => {
          const isCurrent = option.dataset.appearance === node.dataset.appearance;
          option.setAttribute('aria-pressed', String(isCurrent));
          const chip = option.querySelector('.appearance-current');
          if (chip) chip.hidden = !isCurrent;
        });
        break;
      }
      case 'open-receipts': openReceiptsDialog(); break;
      case 'open-drawer': openDrawer(); break;
      case 'open-project':
        state.activeProjectId = node.dataset.project;
        completeStage('projects'); completeStage('project');
        saveState(); go('project'); break;
      case 'switch-version-dialog': openDialog({
        title: 'Read a different version',
        description: 'Evidence and decisions belong to the version they were gathered against. An earlier version is readable, not decidable.',
        body: `<div class="stack">${proj().versions.slice().reverse().map((v) => {
          const isLatest = v.label === latestVersion().label;
          const isViewed = v.label === currentVersion().label;
          const decidedHere = Object.keys(proj().decisionBinding).filter((id) => proj().decisionBinding[id].version === v.label).length;
          return `<button class="switch-row${isViewed ? ' is-current' : ''}" type="button" data-action="set-version" data-version="${esc(v.label)}" ${isViewed ? 'aria-current="true"' : ''}>
            <span class="switch-row-main">
              <span class="cluster">${versionChip(v)}${isLatest ? badge('Current', 'is-success') : badge('Superseded')}</span>
              <span class="small muted">${esc(v.source)}</span>
              <span class="mono small muted">${esc(v.hash)} · ${decidedHere} decision${decidedHere === 1 ? '' : 's'} bound here</span>
            </span>
            ${isViewed ? '<span class="switch-row-mark" aria-hidden="true">✓</span>' : ''}
          </button>`;
        }).join('')}</div>`,
      }); break;
      case 'set-version': {
        const label = node.dataset.version;
        // Pinning the latest clears the pin, so the reader returns to following
        // the newest draft rather than freezing on today's newest forever.
        proj().viewingVersion = label === latestVersion().label ? null : label;
        saveState(); closeDialog(); renderRoute();
        toast(proj().viewingVersion ? `Reading ${label}. This version is read-only.` : `Reading ${label}, the current version.`);
        break;
      }
      case 'switch-project-dialog': openDialog({
        title: 'Switch project',
        description: 'Each project keeps its own versions, evidence, decisions, and monitoring.',
        body: `<div class="stack">${PROJECT_DEFS.map((def) => {
          const p = state.projects[def.id];
          const active = def.id === state.activeProjectId;
          return `<button class="appearance-option" type="button" data-action="confirm-switch-project" data-project="${def.id}" aria-pressed="${active}">
            <span class="appearance-swatch is-stock" style="--stock:var(--rev-${p.versions.length ? stockFor(p.versions.at(-1).label) : 'white'})" aria-hidden="true"></span>
            <span><strong>${esc(def.title)}</strong><br><span class="small muted">${esc(def.type)} · ${p.versions.length ? esc(p.versions.at(-1).label) : 'not imported'} · ${esc(def.stage)}</span></span>
          </button>`;
        }).join('')}</div>`,
      }); break;
      case 'confirm-switch-project':
        state.activeProjectId = node.dataset.project;
        saveState(); closeDialog(); renderRoute();
        toast(`Switched to ${projInfo().title}.`); break;
      case 'toggle-sidebar':
        state.sidebarCollapsed = !state.sidebarCollapsed;
        saveState();
        renderSidebar(routeMeta(currentRoute));
        toast(state.sidebarCollapsed ? 'Sidebar collapsed.' : 'Sidebar expanded.');
        break;
      case 'close-drawer': closeDrawer(); break;
      case 'close-dialog': closeDialog(); break;
      case 'reset-dialog': openDialog({
        title: 'Reset demo state?',
        description: 'Clears simulated project data in this browser. Your appearance choice is kept.',
        body: banner({ tone: 'is-danger', icon: '⚠', message: 'All simulated versions, decisions, receipts, monitoring reviews, learning state, and export records will be removed.' }),
        actions: `<button class="button button-secondary" type="button" data-action="close-dialog">Cancel</button><button class="button button-danger" type="button" data-action="confirm-reset">Reset demo state</button>`,
      }); break;
      case 'confirm-reset': resetDemo(); closeDialog(); go('marketing'); renderRoute(); toast('Demo state reset.'); break;
      default: break;
    }
  }

  /* ═══════════════════════════════ INIT ═══════════════════════════════ */

  document.addEventListener('click', (event) => {
    const target = event.target.closest('[data-action]');
    if (!target) return;
    if (target.tagName !== 'INPUT') event.preventDefault();
    handleAction(target.dataset.action, target);
  });

  document.addEventListener('change', (event) => {
    const target = event.target.closest('[data-action]');
    if (target && (target.tagName === 'INPUT' || target.tagName === 'SELECT')) handleAction(target.dataset.action, target);
  });

  // Live search filters as the reviewer types, without waiting for blur/Enter.
  document.addEventListener('input', (event) => {
    const target = event.target.closest('[data-action="set-items-search"]');
    if (target) handleAction(target.dataset.action, target);
  });

  el.dialogHost.addEventListener('click', (event) => {
    if (event.target.matches('[data-backdrop]')) closeDialog();
  });

  el.drawer.addEventListener('click', (event) => {
    if (event.target === el.drawer) closeDrawer();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && el.drawer.dataset.open === 'true') closeDrawer();

    /* A role="tablist" has to answer the arrow keys. The exhibit nav declared the
       role without them, so a keyboard reader could reach one tab and then had no
       way to move along the row. Home and End jump to the ends, and the roving
       tabindex keeps a single stop in the tab order. */
    const tab = event.target.closest && event.target.closest('.report-tab');
    if (!tab) return;
    const keys = ['ArrowRight', 'ArrowLeft', 'Home', 'End'];
    if (!keys.includes(event.key)) return;
    const tabs = Array.from(document.querySelectorAll('.report-tab'));
    const at = tabs.indexOf(tab);
    const next = event.key === 'ArrowRight' ? tabs[(at + 1) % tabs.length]
      : event.key === 'ArrowLeft' ? tabs[(at - 1 + tabs.length) % tabs.length]
      : event.key === 'Home' ? tabs[0]
      : tabs[tabs.length - 1];
    if (!next) return;
    event.preventDefault();
    state.reportTab = next.dataset.tab;
    saveState();
    renderRoute();
    // Re-query after the render: the old node is gone.
    requestAnimationFrame(() => document.querySelector(`#tab-${next.dataset.tab}`)?.focus());
  });

  window.addEventListener('hashchange', () => { closeDrawer(); renderRoute(); });

  if (!location.hash) history.replaceState(null, '', '#marketing');
  renderRoute();
})();
