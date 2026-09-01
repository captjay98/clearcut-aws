# ClearCut Submission Strategy

*Migrated 2026-08-28 from hackathons/clearcut · Updated with confirmed rules and baseline design*
*Competition: Agentic Cinema · Deadline: Sep 9, 2026, 2:00 PM PT (confirmed from official rules §5)*

## Competition Fit

### Theme framing

The hackathon page frames the theme as: *"Every enterprise has the same problem: five tools, one workflow, zero of them talking to each other. Agentic Cinema is Google Cloud betting that an agent can be the thing that finally connects them."*

**ClearCut is exactly this story, told for film.** The indie producer's clearance workflow today is five disconnected tools: the script lives in Final Draft, research happens in browser tabs, evidence lands in a spreadsheet, review happens over email, and the dossier is assembled by hand. None of them talk to each other — and every script revision re-breaks the whole chain. ClearCut is the agent that connects them: it reads the script, runs the research (Parallel), tracks the evidence, proposes rewrites, manages review, and exports the packet — one workflow instead of five.

Use this framing in the video's opening and the submission description. It maps directly onto **Quality of the Idea** (non-obvious agent-as-connective-tissue use) and **Potential Impact** (a fragmented workflow every production recognizes).

### Selected partner track: Parallel

ClearCut's core loop — script → detect clearance items → live web evidence → human review → re-scan — requires a current, source-backed research layer. That is exactly what Parallel Search provides. The partner is not a checkbox; the product cannot function without it.

## Prize Paths

ClearCut competes only within the Parallel track.

| Prize | Amount | Assessment |
|---|---|---|
| 1st | $7,500 + social media promotion | Reach — requires a complete, polished product and a thin Parallel field |
| 2nd | $4,500 | Achievable target if the evidence loop and workflow are complete |
| 3rd | $3,000 | Floor if the core product works but polish is light |

No cross-track grand prize. The ceiling is $7,500.

## Judging Strategy

### Stage One (pass/fail gate)
Submission includes all requirements, reasonably addresses the challenge, reasonably applies both partner data and Google Cloud products. May use automated screening tools.

### Stage Two (four equal 25% criteria)

**Technological Implementation (25%, tie-break)**
*"How well is the project built, and how effectively does it use Google Cloud and the Partner services as part of the solution?"*
- Parallel Search API called at runtime, visible in tool traces and evidence cards.
- Accepted Google SDK (`google-adk` and/or `google-genai`) called at runtime.
- Agent does real work: detection, search planning, evidence synthesis, re-evaluation — not a chat wrapper.
- Deterministic pipeline decoupled from model judgment.
- Judge-driven evaluation with 10-dimension rubric and deterministic gates.

**Design (25%)**
*"Does the project deliver a complete, coherent product experience not just a technical proof of concept?"*
- 20-surface product experience demonstrated in the mock prototype.
- Persistent projects, statuses, revision loop, team workflow.
- Annotated screenplay workspace with evidence review.
- Two visual themes, responsive, accessible.

**Potential Impact (25%)**
*"Does the project make a credible, specific case for solving a real problem for a real audience and does the solution actually address it based on what's demonstrated?"*
- Independent producers without clearance departments are a real, underserved audience.
- The demo script demonstrates several real clearance-item types.
- Evidence is sourced from Parallel, not fabricated.

**Quality of the Idea (25%)**
*"Is this a creative, non-obvious use of Google Cloud and the Partner services and does the team show genuine understanding of the problem space?"*
- Pre-clearance research workspace, not a content generator.
- Genuine understanding of the clearance workflow problem.
- Agent-as-connective-tissue: five tools, one workflow.

## Candidate Three-Minute Demo

- **0:00–0:20** — The clearance problem for independent producers. Five tools, zero talking to each other.
- **0:20–0:40** — Import an original screenplay; structured extraction.
- **0:40–1:45** — Flagged items across categories. Actual Parallel searches, returned sources, conflicting evidence, confidence, action status.
- **1:45–2:20** — Accept a replacement; re-scan; affected item changes.
- **2:20–2:40** — Generate and release the clearance report.
- **2:40–3:00** — Google Cloud + Parallel architecture; hosted-product URL.

## Compliance Checklist

### Eligibility and originality
- [ ] Individual entry (or team up to 4).
- [ ] Project created during Jul 27 – Sep 9 contest period; no modification or extension of existing work.
- [ ] Disclose any pre-existing code incorporated (target: none). The mock prototype is design source material, not submitted code.

### Required technology
- [ ] Parallel Search API called at runtime in code (via `parallel-web` SDK, Vercel AI SDK integration, LangChain integration, or Grounding configuration).
- [ ] Accepted Google SDK (`google-adk` / `google-genai` / `google-generativeai` / `google-cloud-aiplatform`) called at runtime.
- [ ] Gemini via Vertex AI or Gemini API.
- [ ] Runtime evidence in code and logs.
- [ ] No non-Google AI models, agent frameworks, or AI APIs at runtime.

### Repository
- [ ] Public repo with all source.
- [ ] Open-source license at the root.
- [ ] Run instructions.
- [ ] Architecture diagram.
- [ ] Data sources, authority ranking, and limitations documented.

### Submission
- [ ] Hosted web URL (web platform).
- [ ] Text description: features, tech, data sources, learnings.
- [ ] Public video, max 3 minutes, English or English subtitles, on YouTube or Vimeo.
- [ ] Parallel partner track selected on Devpost.

### AI tooling note
The competition rules restrict AI/agent tooling in the **project at runtime**: "This restriction applies only to AI/agent tooling; it does not restrict your use of other non-AI third-party services." Using a coding assistant (any vendor) to write source code is a development tool — like an IDE — not a runtime AI component. The submitted product's AI must use Google Cloud (Gemini/ADK) at runtime. If there is any doubt, request a written clarification from Devpost support.

## Risks and Mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Appears to provide legal advice | Trust/product risk | Position as research triage; preserve uncertainty; require specialist review; legal-boundary language enforced by deterministic gates |
| Parallel returns weak/inconsistent evidence | Unconvincing demo | Validate representative queries before committing; show unresolved state honestly |
| Demo is visually quiet | Lower Design score | Rich annotated screenplay workspace, evidence cards, revision diff, clearance report |
| Becomes "upload PDF, receive report" | Weak product coherence | Persistent projects, statuses, revision loop, team workflow, monitoring |
| Original script contains third-party marks | IP risk | Entrant-owned synthetic script with neutral demo entities |
| Build window pressure | Incomplete product | 8-plan structure with dependency gates; golden path prioritized |

## Key Dates

| Date | Event |
|---|---|
| Jul 27, 2026 | Contest period opens |
| Sep 9, 2026, 2:00 PM PT | **Submission deadline** (confirmed from official rules §5) |
| Sep 23 – Oct 7, 2026 | Judging period |
| ~Oct 7, 2026 | Winners notified |
