# Hosted Release, Demo, and Submission Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prove the exact hosted revision and assemble a compliant original public submission.  
**Architecture:** One immutable manifest binds source SHA, image digests, Cloud Run revisions, tests, runtime traces, video, repository, and Devpost fields.  
**Tech Stack:** Git, GCP, Playwright, Gemini/ADK, Parallel, YouTube/Vimeo, Devpost.

---

**Files:** Create `demo/original-screenplay/`, `demo/runbook.md`, `docs/submission/manifest.yaml`, `demo-script.md`, `devpost-copy.md`, `limitations.md`, `docs/reviews/<date>-r9-release.md`; test `scripts/verify-submission.mjs`, `apps/web/tests/e2e/hosted-golden-path.spec.ts`.

1. Add failing manifest tests for clean SHA/remote parity/digests, public license/repo, hosted URL, ≤3-minute public English/subtitled video, exact Gemini/ADK trace, mandatory Parallel Search ID/session/trace/snapshots, truthful Extract status, conditional Monitor go/no-go/proof, and no alternate provider or excluded Parallel API.
2. Run full local gates, deploy exact digests, then run authenticated hosted golden path plus role/tenant/security/recovery/accessibility/operational negatives.
3. Record an entrant-owned screenplay demo showing one live mandatory Search completion, bounded Extract outcome, evidence/conflict, human review, separate-actor rewrite, selective re-scan, and separate report generation/release. Show a previously delivered Monitor signal only when the exact deployed candidate passed Monitor GO and label the subsequent Search/Extract verification; never wait for a scheduled event or imply Monitor made a decision.
4. Verify all links/visibility/duration/copy and DG-05 correspondence; issue GO only when every hard artifact matches the manifest.
5. Stage and commit `docs/submission/`, demo documentation, and release evidence only after owner review; expect the verification script to exit 0, then freeze the candidate and submit with contingency buffer.

**Exit:** Video behavior, hosted behavior, source, traces, and claims describe the same exact candidate.
