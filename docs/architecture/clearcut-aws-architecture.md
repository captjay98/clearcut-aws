# ClearCut architecture

Screenplay pre-clearance research with accountable human review.

Solid nodes describe application components present in the codebase; they do not claim live-provider verification. The dashed AWS hosting section is the deployment target, not a verified deployment. AWS account suspension currently blocks hosted verification. No OpenRouter fallback is depicted because it has not been implemented or verified here.

```mermaid
flowchart TB
    U[Filmmaker / clearance reviewer] --> UI[Astro public site + React / TanStack workspace]
    UI --> API[FastAPI same-origin API\nOpaque sessions · tenant and project scope]
    API --> IMPORT[pypdf / screenplay parsers\nVersioned script elements and revision diffs]
    API --> JOB[Persisted jobs\nAttempts · leases · checkpoints · local dispatch]
    IMPORT --> DET[Detection adapter]
    JOB --> DET
    JOB --> AGENT[Strands research agent\nScoped tools · bounded calls and tokens · step receipts]
    AGENT --> PLAN[Research planning]
    AGENT --> SEARCH[Parallel Search + bounded Extract\nCited source snapshots]
    SEARCH --> SYNTH[Claim synthesis]
    SYNTH --> JUDGE[Evidence quality judge]
    PLAN --> BR[Amazon Bedrock adapters\nDetection · planning · synthesis · evaluation]
    DET --> BR
    SYNTH --> BR
    JUDGE --> BR
    JUDGE --> VALIDATE[Deterministic completion validation\nMissing evidence stays unresolved]
    VALIDATE --> DB[(PostgreSQL\nVersions · jobs · sources · claims · audit)]
    API <--> DB
    DB --> REVIEW[Human review\nDecisions · rewrites · referrals]
    U --> REVIEW
    REVIEW --> REPORT[Version-bound reports\nSeparate generation and release actions]
    REVIEW --> DB
    REPORT --> STORAGE[(Object-storage adapters\nScript imports and report artifacts)]
    subgraph TARGET["AWS deployment target — not yet verified"]
      HOST[HTTPS ALB → ECS Fargate web + private worker]
      TRANSPORT[Transactional outbox → SQS + dead-letter queue]
      DATA[RDS PostgreSQL · S3 · Secrets Manager]
      OPS[ECR immutable image · Alembic migration task\nIAM task roles · CloudWatch · Terraform]
    end
    JOB -. planned delivery .-> TRANSPORT
    API -. planned hosting .-> HOST
    DB -. planned managed database .-> DATA
    STORAGE -. planned storage .-> DATA
    style TARGET fill:#f8fafc,stroke:#64748b,stroke-dasharray:6 4
```

## Boundaries

- Gemini/GCP and Bedrock/AWS adapters are separate runtime choices; this diagram focuses on the AWS port.
- Strands coordinates bounded application tools. PostgreSQL remains authoritative for workflow state.
- Parallel Search supplies attributable evidence; Extract adds context. Model output alone is not a source.
- Human decisions and their audit events commit transactionally. AI does not grant clearance.
- AWS deployment services shown in the target section still require provisioning and live acceptance checks.
