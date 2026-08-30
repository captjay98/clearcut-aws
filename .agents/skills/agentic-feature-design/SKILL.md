---
name: agentic-feature-design
description: Design features for dual consumption — humans (UI) and agents (API)
---

# Agentic Feature Design

Features must be designed for **dual consumption**: Humans (UI) and Agents (API/MCP).

## The "Headless First" Rule

Every feature must be fully functional via API _before_ any UI is built.

**Test:** Can an agent complete the entire user story using only API calls?

## The "Intention" Pattern

Expose semantic actions, not generic CRUD:

```
// ❌ Generic — agent can't infer intent
updateItem(id, { status: 'verified' })

// ✅ Semantic — agent understands the action
verifyEvidence(itemId, { decision: 'accept', rationale: '...' })
```

## ClearCut Action Classification

ClearCut classifies all tools into three tiers (baseline §9):

| Tier | Example | Agent can auto-execute? |
|------|---------|------------------------|
| **Read** | Retrieve flags, view evidence, list sources | Yes |
| **Draft** | Propose a rewrite, generate search queries, draft a referral, prepare a non-exportable report preview | Yes, when policy allows |
| **Governed write** | Verify evidence, approve rewrite, generate a version-bound dossier/export, release/export the report, set disposition | **No — requires human approval** |

### Governed Actions (human-only)

A non-exportable preview may be prepared automatically when policy allows. Triggering version-bound dossier/report generation and release/export are governed operations requiring an accountable human.

- Accept or reject evidence
- Approve a rewrite
- Refer an item to a specialist
- Set final disposition
- Generate a version-bound dossier/report
- Release or export a clearance report

The server enforces this through capability guards. The agent and client cannot supply or override authorization decisions.

### Agent Integration Points

ClearCut's agent (Gemini/ADK) participates in the research pipeline:

```
Agent detects items → plans searches → calls Parallel → normalizes evidence → proposes actions
Human reviews → decides → records receipt
```

The agent does the research work. The human does the decision work. The API supports both flows through the same typed endpoints.

## Design Checklist

- [ ] All actions available via API (not just UI)
- [ ] Responses are structured and machine-parseable (Pydantic models, not raw dicts)
- [ ] Errors include actionable context — typed error envelope with kind, message, and retryable flag
- [ ] State transitions are explicit and observable — every status change is an event
- [ ] Governed actions have capability guards checked server-side
- [ ] Tool calls are recorded with duration, result, and provenance
- [ ] Evidence claims carry source URL, authority, stance, and retrieval time — not just a text summary

## ClearCut API Design Rules

- **OpenAPI-first**: Define the endpoint shape in `packages/contracts/openapi.yaml` before implementing.
- **Ownership-aware scope**: Classify each resource before designing its endpoint. Organization-owned resources require authenticated `org_id`; project-owned resources require authenticated `org_id` plus URL `project_id` and a project-membership check; explicitly global catalogs contain no tenant content and must not receive invented project scope. Generic policy/version names do not make organization-specific policy, prompt, preference, retention, or governance records global.
- **Typed ports**: External calls (Parallel, Gemini, GCS) go through typed provider ports. No raw HTTP in route handlers.
- **Semantic names**: `verifyEvidence`, `approveRewrite`, `releaseReport` — not `updateItem`, `patchFlag`, `postExport`.
- **Audit trail**: Governed writes produce `AuditEvent` records transactionally. Draft actions produce `AgentToolCall` records.

## Decision Guide

**Use when:**
- Designing a new feature that the ADK agent or a human will execute
- Adding a new API endpoint
- Feature logic lives in UI components instead of the service layer
- Building a new governed action

**Don't use when:**
- Purely presentational features (styling, layout, animation)
- Mock prototype changes (it's a design artifact, not an API)

**Decision tree:**
- Can an agent complete this via API? → If no, move logic to the service layer
- New endpoint? → Start with OpenAPI spec, use semantic action names
- Generic CRUD? → Rename to domain action (verifyEvidence, not updateItem)
- Consequential action? → Add capability guard + transactional audit
- Read-only? → Allow agent auto-execution, return structured data

**Failure modes:**
- Logic in components → agent can't execute the workflow
- Generic names → agent calls the wrong endpoint or misinterprets the action
- No capability guard → agent bypasses human approval on governed actions
- No audit trail → consequential actions leave no record
- Raw dicts → consumers can't type-check responses, drift goes undetected
