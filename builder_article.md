# Agents for Humans: How ClearCut Uses Amazon Bedrock & Strands Agents to Protect Independent Filmmakers

In independent filmmaking, an innocent detail in a screenplay can easily trigger catastrophic liabilities: an uncleared classic song playing in a diner jukebox, a distinctive designer trademark on an actor’s clothing, or a fictional criminal whose name and town inadvertently match a living private citizen. 

For independent productions operating without deep studio legal pockets, screenplay clearance is historically tedious, manual, and fragmented across endless browser tabs, spreadsheets, and emails. Even worse: screenplays are revised dozens of times during pre-production. Each new draft previously meant discarding past research and starting over from scratch.

I built **ClearCut** as an open-source solution designed around a foundational principle: **What if the script passage, its cited factual evidence, and the human clearance decision stayed permanently linked—even as the screenplay changes?**

---

## 1. The Core Architecture: Separating Intelligence from Governance

In high-stakes legal clearance, unconstrained autonomous agents are dangerous—an LLM that hallucinates an imaginary licensing agreement or falsely declares an entity "cleared" creates real liability. 

To solve this, ClearCut pairs **Amazon Bedrock** and the **Strands Agents SDK** with strict deterministic governance:

```
[ Screenplay (FDR/FDX) ] ──> [ Amazon Bedrock Detection ]
                                        │
                                        ▼
                             [ Candidate Concerns (10 Categories) ]
                                        │
                                        ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │       Bounded Strands Research Orchestrator (AWS SDK)            │
    │  • Server-Side Tenant Scoping (org_id & project_id injected)     │
    │  • Parallel Search & Bounded Extract                             │
    │  • Leaf-Only Lock Discipline (Zero Nested-Acquire Deadlocks)     │
    │  • Persistent Step Receipts (research_step_receipts in PG 17)   │
    └──────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
               [ Deterministic Completion Validator ]
            (Rejects self-certification without citations)
                                        │
                                        ▼
       [ Side-by-Side Human Review Workspace & Versioned Reports ]
```

---

## 2. Multi-Model Specialization with Amazon Bedrock

Rather than relying on one massive, generalized prompt, ClearCut uses Amazon Bedrock's Converse API across four discrete capability roles:

1. **Detection Runtime:** Identifies potential clearance concerns in screenplay passages across ten protected categories (brands, music, real people, copyrighted works, locations, and contact info).
2. **Research Planner:** Formulates bounded, targeted search strategies for detected items.
3. **Claim Synthesizer:** Extracts concrete, attributable factual claims from retrieved source documents.
4. **Evaluation Judge:** Evaluates candidate evidence against legal risk rubrics while rigorously preserving uncertainty.

Each adapter strictly records the **truthful model ARN** returned by Amazon Bedrock, ensuring a transparent audit trail of how AI findings were generated.

---

## 3. Bounded Agentic Research with Strands Agents

ClearCut uses the **Strands Agents SDK** to empower autonomous research agents while maintaining ironclad safety:

* **Server-Side Tenant Scoping:** Tenant credentials (`org_id`, `project_id`) are never passed to LLM prompts or accepted from agent arguments. They are injected into tool closures on the server, while Pydantic model schemas specify `extra="forbid"` to completely block prompt-injection attacks.
* **Immutable Step Receipts:** Every agent turn, tool invocation, and observation is persisted to a PostgreSQL `research_step_receipts` table with unique replay deduplication indexes. If a container restarts or an execution crashes, the agent recovers instantly without duplicating external calls.
* **Leaf-Only Permit Discipline:** Bedrock inference concurrency permits are acquired exclusively during LLM generation turns and explicitly released *before* child tool execution, preventing nested-acquire deadlocks.
* **Deterministic Completion Validator:** ClearCut enforces that an agent cannot self-certify an item as cleared. The validator inspects the database to ensure required search steps executed and cited real, verifiable source snapshots. If no evidence exists, the item remains explicitly **UNRESOLVED**.

---

## 4. Solving the Revision Cycle: Deterministic Selective Rescan

Screenwriters constantly revise their scripts. ClearCut calculates passage-level diffs classifying every scene as *unchanged*, *moved*, *modified*, *added*, or *removed*. 

When an authorized reviewer starts a **selective rescan**, fresh Bedrock and Strands research runs **only on the modified passages**. Unchanged and moved scenes carry forward their verified evidence and past review history by reference. You change one scene—you don't re-clear the whole movie.

---

## 5. Agents for Humans, Not Agents Instead of Humans

ClearCut demonstrates the true potential of the "Agents for Humans" philosophy:
* **The Agent's Job:** Autonomously scour public records, discover citations, extract context, and present factual evidence.
* **The Human's Job:** Producers, screenwriters, and attorneys evaluate the evidence, propose and review rewrites (where a writer cannot approve their own rewrite), and issue signed clearance reports.

By combining the reasoning power of Amazon Bedrock and the autonomous capabilities of Strands Agents with deterministic human governance, ClearCut makes independent filmmaking safer, faster, and legally protected.

---

### Project & Open Source Links
* **GitHub Repository:** https://github.com/captjay98/clearcut-aws
* **Built With:** Amazon Bedrock, Strands Agents SDK, AWS S3, AWS Secrets Manager, PostgreSQL 17, FastAPI, TanStack Start, and React.
