# Agentic Cinema Competition and Judging

**Verified:** 2026-08-30 against the official Devpost rules and contest page  
**Track:** Parallel  
**Deadline:** September 9, 2026 at 2:00 PM Pacific time

Official sources:

- https://agentic-cinema.devpost.com/rules
- https://agentic-cinema.devpost.com/

## Stage One — pass/fail

The submission must include every required artifact, address the challenge, and reasonably apply both Google Cloud products and the chosen partner. Automated screening may assist. ClearCut must therefore make package/runtime use, hosted behavior, repository completeness, and the Parallel integration machine-detectable as well as understandable to a human.

## Stage Two — equal 25% criteria

| Criterion | What judges ask | ClearCut proof target |
|---|---|---|
| Technological Implementation (first tie-break) | Is it well built and does it use Google Cloud and Parallel effectively? | Live Gemini/ADK + Parallel calls, typed tool traces, cited source snapshots, durable jobs, security/governance, reproducible repo/deploy |
| Design | Is it a complete coherent product, not a technical proof? | Hosted 20-surface journey, accessible/responsive themes, persistent projects/team/revision/report loop, honest states |
| Potential Impact | Is the audience/problem credible and addressed by the demonstrated solution? | Specific independent-producer workflow, time/rework reduction story, original screenplay, real sourced evidence, no fabricated traction |
| Quality of the Idea | Is the use creative/non-obvious and grounded in the problem? | Pre-clearance evidence desk connecting script, research, review, revision, monitoring, and delivery—not a chat wrapper/content generator |

Ties compare criteria in the listed order, so Technological Implementation is the first tie-break.

## Required submission artifacts

- Hosted web project URL.
- Public YouTube/Vimeo demo, maximum three minutes, English or English subtitles.
- Public GitHub/GitLab/Bitbucket repository containing all source/assets/run instructions.
- Open-source license visible at repository root/About area.
- Text description of features, technology, other data sources, findings, and learnings.
- Selected Parallel partner track.
- Repository proof that an accepted Google package/runtime and Parallel Search are imported/configured and actually called at runtime—not merely named in README.

## Runtime technology constraints

The project may use only Google Cloud AI tools and built-in AI features of the selected partner. No other AI models, agent frameworks, or AI APIs may be part of the submitted runtime. Non-AI third-party frameworks/services are allowed subject to their licenses/terms.

For Parallel, the rules require active runtime Search API use through the official SDK or a supported integration/configuration. Search remains the mandatory first research call even when bounded Extract or conditional Monitor is enabled. ClearCut's evidence path must fail visibly when Search fails; cached/sample evidence cannot masquerade as the current run.

ClearCut's open-source architecture exposes typed model and capability-specific research ports, but the submitted source and production profile implement only Gemini through Google ADK and the approved Parallel capabilities in `docs/PARALLEL_INTEGRATION.md`. Task, FindAll, Responses/Chat, Interactions, Deep Research, snapshot Monitor, alternate providers/selectors, and silent fallbacks are excluded. Extensibility is an internal quality boundary, not a claim that the partner is interchangeable in the submission.

## Originality and functionality

- The project must be newly created during July 27–September 9, 2026, not an extension of prior work.
- It must run consistently as described and function as depicted in video/text.
- Third-party SDKs/data require authorization under their terms.
- A team may have at most four eligible individuals.

## Open compliance risk

The official rules phrase the AI restriction as a restriction on the submitted **project/runtime**. A repository verification note records an organizer briefing interpreted as also limiting development assistants. Those positions are not fully reconciled. Do not assert eligibility is resolved. Obtain written Devpost/organizer clarification and retain it with submission evidence.

## Evidence plan

Capture one immutable submission manifest containing:

```text
git SHA and clean status
deployed image digests and Cloud Run revisions
hosted URLs
Gemini model/SDK/runtime trace
Parallel Search ID/session/call/source-snapshot trace
Parallel Extract ID/results/errors trace or truthful not-enabled status
Parallel Monitor go/no-go and deployed event/cancellation proof when claimed
golden-path E2E recording timestamp
test/security/accessibility/contract gate results
license and repository visibility
video URL/duration/visibility
Devpost field checklist
known limitations and unresolved compliance correspondence
```

The demo should show actual behavior first and architecture proof second. Mock calls must never be presented as runtime evidence.
