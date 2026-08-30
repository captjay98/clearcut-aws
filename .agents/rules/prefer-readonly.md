---
trigger: file_edit
---

# Prefer Readonly and Immutability

Use `readonly`, `Final`, frozen dataclasses, and `const` wherever possible. Mutability must be explicit at governed domain transitions; immutable script versions, source snapshots, audit events, and version-bound reports must never be mutated in place.

## TypeScript

```typescript
interface EvidenceClaim {
  readonly id: string
  readonly sourceSnapshotId: string
  readonly retrievedAt: string
  readonly stance: 'supports' | 'disagrees' | 'context'
}

const ROLES = ['owner', 'admin', 'editor', 'reviewer', 'viewer'] as const

type Role = (typeof ROLES)[number]
```

## Python

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class SourceSnapshot:
    url: str
    retrieved_at: datetime
    authority: str
    excerpt: str
```

Use SQLAlchemy/Pydantic models with explicit update methods for legitimate lifecycle transitions. A new rewrite creates a new immutable `ScriptVersion`; it does not mutate the source version.

## ClearCut Guidance

- Treat `EvidenceClaim`, `SourceSnapshot`, `EvidenceConflict`, `AuditEvent`, and released dossier inputs as immutable records.
- A `ClearanceItem` can transition through an explicit domain method from zero-evidence states to researched/reviewed states; do not smuggle evidence into mutable fields.
- Never use immutability to bypass human approval, transactional audit, or organization/project scope checks.
