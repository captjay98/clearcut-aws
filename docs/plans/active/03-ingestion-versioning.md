# Ingestion and Initial Versioning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Safely accept paste, Fountain, FDX, and PDF screenplays and commit one immutable normalized script version with stable elements/spans.

**Architecture:** Upload capability and artifact finalization precede parsing. Deterministic formats use bounded parsers; PDF uses an isolated/model-assisted adapter behind the same typed parse port. Warnings require human acceptance before version commit.

**Tech Stack:** FastAPI, PostgreSQL, GCS adapter, defused/safe XML tooling, isolated PDF worker, Gemini adapter where approved, property-based parser tests.

---

**Depends on:** Plans 01–02  
**Checkpoint:** R2

### Task 1: Define artifact/version/element contracts test first

**Files:** Create import/version schemas, domain models, migrations, parser fixtures, and `test_version_immutability.py`.

```python
def test_committed_version_cannot_change_text(committed_version):
    with pytest.raises(ImmutableVersionError):
        committed_version.replace_element(...)
```

Include stable element/span IDs, source locations, scene/page references, artifact/server hashes, parser version, warnings, and lineage.

### Task 2: Build one-time upload capability and finalization

**Files:** Create `scripts/storage/ports.py`, GCS/local adapters, upload routes/services, replay/object-swap tests.

Bind org/project/actor/key/size/type/hash/nonce/expiry/generation. Test oversized, wrong MIME/magic/extension, expired/replayed capability, changed object generation, and cross-project finalization.

### Task 3: Implement deterministic paste/Fountain/FDX parsers

**Files:** Create parser ports/adapters and golden corpora.

Write failing cases for scenes, actions, characters, parentheticals, dialogue, transitions, props/locations/music cues, line/page anchors, encodings, malformed input, XML entities/DTD/XInclude/network, depth/node/text limits. Then implement minimal parsers.

### Task 4: Implement isolated PDF path

**Files:** Create PDF worker/adaptor contract, resource-limit tests, Gemini structured-output adapter tests.

No embedded action/script/link/form/attachment executes. Test timeout, memory/page limit, invalid model schema, provider failure, prompt injection, and redacted logging. A failure creates a visible import error, never invented structure.

### Task 5: Implement parse warning review and atomic v1 commit

**Files:** Create import application service/routes and `apps/web/src/routes/.../new` components/tests.

The UI uses a real file input/drop target, reports client checks as advisory, shows server verification separately, and confirms warnings. Version commit, project/script link, normalized rows, run completion, and audit commit together.

### Verification

Run four parser suites, property tests for stable identities, PostgreSQL/GCS integration, hostile file corpus, contract/client drift, and E2E for every format plus warning/retry/cancel/access cases.

```bash
uv run pytest services/api/tests/scripts services/api/tests/security/test_uploads.py -q
pnpm --filter @clearcut/web test -- ingestion
pnpm --filter @clearcut/web test:e2e -- new-clearance
```

Expected: all commands exit 0 and the corpus reports all four formats.

### Exit criteria

- Authorized users import all four formats into only their project.
- Every accepted import creates immutable v1 and normalized elements/spans.
- Server-byte verification defeats replay/object swap/type spoofing.
- FDX/PDF hostile cases fail safely and visibly.
- No parse/provider failure creates partial version success.
