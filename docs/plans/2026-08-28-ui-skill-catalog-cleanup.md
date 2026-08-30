# UI Skill Catalog Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove six incompatible vendored skills, replace the two UI skills with one active ClearCut-specific mock-to-TanStack skill, align the approved headless-accessibility boundary across canonical guidance, and regenerate verified Kiro output.

**Architecture:** `.agents/` remains canonical and `.kiro/` remains generated. The replacement skill preserves the mock as the visual source of truth, keeps ClearCut-owned components as the only application-facing UI API, prefers native HTML, and permits at most one approved headless accessibility implementation behind internal adapters; this change does not select or install that dependency.

**Tech Stack:** Markdown agent skills and steering, TOML profile selection, JSON catalog/lock metadata, Bun/Node agent generators and checks, TanStack Start target architecture, custom CSS design system.

---

## Constraints

- Preserve all unrelated uncommitted audit work.
- Do not touch untracked `.github/`, `.pi/`, or `README.md`.
- Do not hand-edit generated `.kiro/` files or `AGENTS.md`; regenerate them from `.agents/`.
- Do not add React Aria, Base UI, Radix, shadcn, Tailwind, or another dependency in this change.
- Preserve `.agents/lock.json` values `source_revision: "611b7231a3c329dde06b73da04ecd952eaf5ad9c"` and `source_dirty: true`.
- Do not create a commit unless the user explicitly requests one.

### Task 1: Add the ClearCut mock-to-TanStack skill

**Files:**
- Create: `.agents/skills/mock-to-tanstack/SKILL.md`
- Modify: `.agents/profile.toml`

**Step 1: Create the skill entrypoint**

Create `.agents/skills/mock-to-tanstack/SKILL.md` with valid frontmatter:

```markdown
---
name: mock-to-tanstack
description: Implements ClearCut's authoritative mock UI as production TanStack Start components while preserving visual fidelity, themes, responsive behavior, accessibility, states, print behavior, and the boundary around approved headless accessibility primitives. Use when building or reviewing ClearCut workspace UI, extracting components from misc/clearcut-flow, or deciding whether a UI dependency fits the design system.
---
```

The body must define these enforceable sections:

1. **Source of truth** — `misc/clearcut-flow/`, 20 surfaces, two themes, 320–1440px, and the 366-check mock audit.
2. **Public component vocabulary** — `Page`, `Section`, `Card`, `StatGrid`, `DataTable`, `EmptyState`, `Banner`, `TabsBar`, `Badge`, `Progress`, and `Avatar` remain ClearCut-owned APIs.
3. **Implementation order** — semantic native HTML first; ClearCut-owned native component second; approved headless behavior behind a ClearCut adapter only when native behavior is insufficient.
4. **Dependency boundary** — no shadcn, external visual component system, Tailwind assumption, icon-library substitution, direct primitive imports in feature code, or mixing headless systems. No headless package is approved merely by this skill.
5. **State and governance requirements** — loading, empty, recoverable/permanent error, success, not-found, and focusable capability-gated controls.
6. **Accessibility** — keyboard behavior, visible focus, focus trap/restoration, background inertness, live regions, 44px coarse-pointer targets, safe areas, and reduced motion.
7. **Motion and layout** — animation only when required; compositor properties; documented stacking scale; no persistent `will-change`; no inline geometry except approved runtime-computed values.
8. **Responsive and print parity** — sidebar/bottom-nav behavior and report print isolation.
9. **Workflow** — inspect the matching mock surface and shared primitives before implementation; map repeated patterns to the design-system package; do not redesign.
10. **Verification** — mock audit for the prototype plus targeted component/accessibility/Playwright checks only when those production targets exist.

Include concise correct/incorrect examples showing that feature code imports a ClearCut `Dialog` adapter rather than a headless package directly. Keep examples dependency-neutral because no headless library has been selected.

**Step 2: Activate the replacement skill**

In `.agents/profile.toml`:

- add `"mock-to-tanstack"` to `skills_include` in alphabetical order;
- remove all six deleted names from `skills_exclude`;
- retain `skills_exclude = []` so the profile schema stays explicit.

Expected active skill count after generation: **16**.

**Step 3: Validate the canonical skill and profile before deletion**

Run:

```bash
node -e 'const fs=require("node:fs"); const p=".agents/skills/mock-to-tanstack/SKILL.md"; const s=fs.readFileSync(p,"utf8"); if(!s.startsWith("---\nname: mock-to-tanstack\n")) process.exit(1); const profile=fs.readFileSync(".agents/profile.toml","utf8"); if(!profile.includes("\"mock-to-tanstack\"")) process.exit(1); console.log("mock-to-tanstack canonical skill: ok")'
```

Expected: `mock-to-tanstack canonical skill: ok`.

### Task 2: Align the canonical UI policy with the approved boundary

**Files:**
- Modify: `.agents/steering/ui-standards.md:11-14`
- Modify: `.agents/steering/tech.md:20-25`

**Step 1: Update UI standards**

Replace the absolute external-library prohibition with the approved boundary:

- the mock defines the visual vocabulary;
- no external **visual** component library, including shadcn;
- native HTML is preferred;
- at most one explicitly approved headless accessibility system may be used for complex behavior;
- it must be isolated behind ClearCut-owned adapters;
- feature code must not import it directly;
- multiple primitive systems must not be mixed;
- icons remain text glyphs and CSS shapes.

Keep the existing component vocabulary and all other UI constraints intact.

**Step 2: Update the planned frontend stack**

Change `.agents/steering/tech.md` so the styling line says the custom mock-derived design system has no external visual component library and allows one approved headless accessibility implementation only behind ClearCut adapters. Do not state that React Aria or any other package has already been selected.

**Step 3: Check canonical policy consistency**

Run:

```bash
node -e 'const fs=require("node:fs"); for (const p of [".agents/steering/ui-standards.md",".agents/steering/tech.md"]) { const s=fs.readFileSync(p,"utf8"); if(!s.includes("headless") || !s.includes("ClearCut")) throw new Error(`missing approved boundary: ${p}`); } console.log("UI primitive policy: ok")'
```

Expected: `UI primitive policy: ok`.

### Task 3: Remove the six incompatible vendored skills and stale catalog metadata

**Files:**
- Delete: `.agents/skills/baseline-ui/`
- Delete: `.agents/skills/financial-patterns/`
- Delete: `.agents/skills/frontend-design/`
- Delete: `.agents/skills/multi-currency/`
- Delete: `.agents/skills/neon-postgres/`
- Delete: `.agents/skills/shadcn/`
- Modify: `.agents/skills-manifest.json`
- Modify: `.agents/lock.json`

**Step 1: Delete the six canonical directories**

Use dedicated file deletion operations for every file in the six directories, then remove empty directories if the environment requires it. Do not delete similarly named active skills.

**Step 2: Clean the external skill manifest**

Remove these entries from `.agents/skills-manifest.json` when present:

- `neon-postgres`
- `shadcn`
- `baseline-ui`
- `frontend-design`

`financial-patterns` and `multi-currency` are not currently represented in this manifest; do not invent records for them. Preserve valid JSON and all unrelated catalog entries.

Do not add `mock-to-tanstack` to this file: it is ClearCut-authored, while this manifest records externally installed catalog skills.

**Step 3: Clean upstream-delivery file records**

Remove every `.agents/lock.json` `delivered_files` object whose `path` begins with any of these prefixes:

```text
.agents/skills/baseline-ui/
.agents/skills/financial-patterns/
.agents/skills/frontend-design/
.agents/skills/multi-currency/
.agents/skills/neon-postgres/
.agents/skills/shadcn/
```

Preserve all unrelated records, `source_revision`, and `source_dirty: true`. Do not add the local replacement skill to upstream-delivery records.

**Step 4: Validate physical and metadata removal**

Run:

```bash
node -e 'const fs=require("node:fs"); const names=["baseline-ui","financial-patterns","frontend-design","multi-currency","neon-postgres","shadcn"]; for(const n of names){if(fs.existsSync(`.agents/skills/${n}`)) throw new Error(`still exists: ${n}`)} const text=[fs.readFileSync(".agents/profile.toml","utf8"),fs.readFileSync(".agents/skills-manifest.json","utf8"),fs.readFileSync(".agents/lock.json","utf8")].join("\n"); for(const n of names){if(text.includes(`.agents/skills/${n}/`)) throw new Error(`stale path: ${n}`)} const lock=JSON.parse(fs.readFileSync(".agents/lock.json","utf8")); if(lock.source_dirty!==true) throw new Error("source_dirty changed"); console.log("incompatible skill removal: ok")'
```

Expected: `incompatible skill removal: ok`.

Also parse both JSON files:

```bash
node -e 'JSON.parse(require("node:fs").readFileSync(".agents/skills-manifest.json","utf8")); JSON.parse(require("node:fs").readFileSync(".agents/lock.json","utf8")); console.log("skill metadata JSON: ok")'
```

Expected: `skill metadata JSON: ok`.

### Task 4: Regenerate canonical consumers

**Files:**
- Generated: `.kiro/**`
- Generated: `AGENTS.md`
- Generated: `.agents/render-manifest.json`

**Step 1: Run strict regeneration**

Run:

```bash
AGENTS_STRICT=1 bun .agents/scripts/build.mjs
```

Expected: successful strict generation with **16 skills**. Let the generator update hashes and inventory; do not manually edit generated files.

**Step 2: Verify generated skill inventory**

Run:

```bash
node -e 'const fs=require("node:fs"); const deleted=["baseline-ui","financial-patterns","frontend-design","multi-currency","neon-postgres","shadcn"]; for(const n of deleted){if(fs.existsSync(`.kiro/skills/${n}`)) throw new Error(`generated stale skill: ${n}`)} if(!fs.existsSync(".kiro/skills/mock-to-tanstack/SKILL.md")) throw new Error("replacement skill missing"); const manifest=JSON.parse(fs.readFileSync(".agents/render-manifest.json","utf8")); if(manifest.counts.skills!==16) throw new Error(`expected 16 skills, got ${manifest.counts.skills}`); console.log("generated UI skill inventory: ok")'
```

Expected: `generated UI skill inventory: ok`.

**Step 3: Verify generated guidance reflects the approved policy**

Confirm `.kiro/steering/ui-standards.md`, `.kiro/steering/tech.md`, and `.kiro/skills/mock-to-tanstack/SKILL.md` contain the headless-adapter boundary and retain the mock source-of-truth language.

### Task 5: Run full sign-off and regression checks

**Files:**
- No additional source changes expected unless a check exposes a defect.

**Step 1: Run agent sign-off**

Run:

```bash
node .agents/scripts/signoff.mjs
```

Expected:

- generated drift check passes;
- agent lint passes;
- agent verification passes;
- package-manager policy passes;
- consumer `node:test` suite passes.

If sign-off fails, fix only the concrete canonical defect, regenerate, and rerun sign-off.

**Step 2: Run the mock structural audit**

Run:

```bash
node misc/clearcut-flow/mockup-audit.mjs
```

Expected: `366/366 checks passed`.

**Step 3: Check patch integrity**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

**Step 4: Verify requested scope against the final diff**

Run:

```bash
git status --short
```

Confirm:

- the six `.agents/skills/` directories are deleted;
- `.agents/skills/mock-to-tanstack/SKILL.md` exists;
- canonical policy and metadata changes are present;
- generated output contains the replacement and none of the six deleted skills;
- `.github/`, `.pi/`, and root `README.md` remain untouched;
- no commit was created.
