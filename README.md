# ClearCut

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![AWS Bedrock](https://img.shields.io/badge/AWS-Amazon%20Bedrock-orange.svg)](https://aws.amazon.com/bedrock/)
[![Strands Agents](https://img.shields.io/badge/Agents-Strands%20SDK-emerald.svg)](https://strandsagents.com/)

**A screenplay pre-clearance evidence workspace powered by Amazon Bedrock, Strands Agents, and Parallel.**

ClearCut reads screenplay drafts, detects clearance concerns across ten protected categories (trademarks, brands, real people, music, copyrighted works, and more), and autonomously gathers cited, real-world evidence using bounded agentic research loops. It coordinates accountable human review, re-evaluates the script as revisions occur, and produces immutable, audit-ready clearance reports.

> *ClearCut supports factual research and qualified human review. It does not provide legal advice or guarantee legal clearance.*

---

## Architecture

```mermaid
flowchart TB
    subgraph Clients["1. Frontend & Client Workspace"]
        Writer["Screenwriter\n(Script Upload & Rewrites)"]
        Clearance["Clearance Reviewer\n(Evidence & Dispositions)"]
        Producer["Producer / Legal\n(Sign-off & Report Export)"]
        UI["TanStack Start & React Workspace\n(Side-by-Side Passage & Evidence)"]
        Astro["Astro Public Site\n(Documentation & Portal)"]
        
        Writer --> UI
        Clearance --> UI
        Producer --> UI
    end

    subgraph Runtime["2. FastAPI Application Runtime"]
        Gateway["FastAPI Modular Gateway\n(/app/* and /api/*)"]
        Composition["Runtime Composition\n(Decoupled Web & Worker Lifespans)"]
        Drainer["Local Job Drainer Loop\n(Durable In-Process Queue)"]
        RescanEngine["Selective Rescan Engine\n(Deterministic Script Passage Diff)"]
        Validator["Deterministic Completion Validator\n(Anti-Self-Certification Guard)"]
        PermitPool["_SharedPermitPool\n(Leaf-Only Lock & USD Budget Caps)"]

        UI --> Gateway
        Gateway --> Composition
        Composition --> Drainer
        Composition --> RescanEngine
        Composition --> Validator
        Composition --> PermitPool
    end

    subgraph AI["3. Amazon Bedrock & Strands Agents SDK"]
        subgraph BedrockRoles["Amazon Bedrock (Converse API)"]
            M1["1. Detection Runtime\n(Clearance Item Extraction)"]
            M2["2. Research Planner\n(Bounded Query Formulation)"]
            M3["3. Claim Synthesizer\n(Fact Extraction from Sources)"]
            M4["4. Evaluation Judge\n(Legal Risk & Uncertainty Rubrics)"]
        end

        subgraph Strands["Strands Agentic Orchestrator"]
            AgentLoop["Strands Research Agent Loop"]
            ToolScope["Server-Side Tool Scoping\n(org_id & project_id injected)\n(extra='forbid' prevents SSRF/Injection)"]
            Receipts["Persistent Step Receipts\n(research_step_receipts)"]

            AgentLoop --> ToolScope
            ToolScope --> Receipts
        end

        PermitPool --> BedrockRoles
        Drainer --> Strands
        Strands --> BedrockRoles
    end

    subgraph External["4. Evidence Discovery Port"]
        ParallelSearch["Parallel Search API\n(Attributable Web Sources)"]
        ParallelExtract["Parallel Bounded Extract\n(Full Document Context)"]
        
        ToolScope --> ParallelSearch
        ToolScope --> ParallelExtract
    end

    subgraph Storage["5. AWS Cloud & Durability Layer"]
        PG[("PostgreSQL 17\n• Tenancy & Auth Schemas\n• Research Step Receipts\n• Atomic Audit Events\n• Sourced Snapshots")]
        S3[("Amazon S3\n• Screenplay Drafts & Diffs\n• Immutable Clearance Reports")]
        Secrets[("AWS Secrets Manager\n• Parallel & Bedrock Credentials\n• Bounded TTL Caching (Zero Env Fallback)")]

        Composition --> PG
        Composition --> S3
        Composition --> Secrets
        Receipts --> PG
        Validator --> PG
    end

    classDef aws fill:#ff9900,stroke:#232f3e,stroke-width:2px,color:#000;
    classDef strands fill:#10b981,stroke:#064e3b,stroke-width:2px,color:#fff;
    classDef client fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff;
    classDef db fill:#6366f1,stroke:#312e81,stroke-width:2px,color:#fff;

    class BedrockRoles,S3,Secrets aws;
    class Strands,AgentLoop strands;
    class UI,Astro,Writer,Clearance,Producer client;
    class PG db;
```

---

## Key Features

1. **Ten Protected Clearance Categories**: Identifies real people, brands, copyrighted works, music, locations, and sensitive contact info.
2. **Amazon Bedrock Model Roles**: Specialized capability adapters for Detection, Research Planning, Claim Synthesis, and Judging using the Converse API with truthful model reflection.
3. **Bounded Strands Agentic Orchestration**: Autonomous research loops using the Strands Agents SDK and Parallel Search/Extract with strict server-side tenant scoping and leaf-only permit locks.
4. **Deterministic Selective Rescan**: Re-evaluates only modified script passages on new drafts, preserving existing verified evidence and human decisions by reference.
5. **Human-in-the-Loop Governance**: Immutable PostgreSQL audit trail where writers cannot approve their own rewrites, ensuring complete production accountability.
6. **Deterministic Completion Validation**: Server-side validation guarantees an agent cannot self-certify completion or clear items without cited evidence.

---

## Quickstart Setup Instructions

### Prerequisites
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and [pnpm](https://pnpm.io/)
- Bun (for contract checks)
- Docker Desktop (optional, for local PostgreSQL 17)

### 1. Clone & Install
```bash
git clone https://github.com/captjay98/clearcut-aws.git
cd clearcut-aws

# Install Python backend dependencies
uv sync --all-packages --dev

# Install frontend web dependencies
corepack enable
pnpm install
```

### 2. Configure Environment
Copy the example environment configuration:
```bash
cp .env.example .env
```
Key settings:
```bash
CLEARCUT_DEPLOYMENT_PROFILE=local   # 'local' for dev or 'aws' for hosted AWS
DATABASE_URL=sqlite+aiosqlite:///./clearcut.db
# Optional live provider keys (fail-closed when omitted)
BEDROCK_MODEL_DETECTION=amazon.nova-lite-v1:0
PARALLEL_API_KEY=your_key_here
```

### 3. Run Database Migrations
```bash
uv run alembic upgrade head
```

### 4. Start Local Development
```bash
# Start the FastAPI monolithic backend
uv run uvicorn clearcut.main:app --reload --port 8000

# In a separate terminal, start the web workspace
pnpm --filter clearcut-web dev
```
Open [http://localhost:3000](http://localhost:3000) to view the workspace.

---

## Running the Verification Test Suite

ClearCut includes an extensive automated test suite covering unit, integration, architecture, and browser contracts:

```bash
# Run the complete Python test suite
uv run pytest services/api/tests -q

# Run client contract sync check
pnpm contract:check

# Run linter
uv run ruff check services/api

# Run web unit tests
pnpm --filter clearcut-web test

# Build production container packages
pnpm build
```

---

## License

This project is licensed under the [MIT License](LICENSE).
