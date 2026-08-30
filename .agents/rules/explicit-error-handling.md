---
trigger: always
globs: ['**/*.py', '**/*.ts', '**/*.tsx']
---

# Explicit Error Handling

Every error must be handled explicitly. No silent catches, bare excepts, swallowed provider failures, fabricated evidence, or authorization fallbacks.

## ClearCut Failure Boundary

A failed Parallel/Gemini/Cloud Storage/Cloud Tasks call returns a typed provider error or creates a visible review item with retryability and receipt context. It must not become an empty success, a false `ClearanceItem` clearance, or invented `EvidenceClaim`. A `ClearanceItem` with zero claims is valid only when its explicit evidence state says pending, no results, unavailable, or failed. Claims still require a cited Parallel `SourceSnapshot`.

## Python Pattern

```python
@dataclass(frozen=True)
class ResearchError:
    kind: Literal['timeout', 'rate_limit', 'auth_failure', 'permanent']
    message: str
    retryable: bool

async def search(query: ResearchQuery) -> ResearchResult | ResearchError:
    try:
        response = await parallel_client.search(query.text)
        return normalize_parallel_response(response)
    except TimeoutError:
        return ResearchError(kind='timeout', message='Parallel search timed out', retryable=True)
    except AuthError as error:
        return ResearchError(kind='auth_failure', message=str(error), retryable=False)
```

```python
# Governed actions must scope the owner and commit decision + audit atomically.
async with db.transaction() as tx:
    item = await tx.get_clearance_item(
        item_id=item_id,
        org_id=actor.org_id,
        project_id=project_id,
    )
    if item is None:
        raise NotFoundError('Clearance item not found in this project')
    result = item.apply_decision(decision, actor=actor)
    if isinstance(result, PolicyViolation):
        raise ForbiddenError(result.reason)
    tx.add(AuditEvent.for_decision(item, decision, actor))
```

## TypeScript Pattern

```typescript
type Result<T, E> = { readonly ok: true; readonly value: T } | { readonly ok: false; readonly error: E }

async function loadEvidence(projectId: string, itemId: string): Promise<Result<EvidenceView, ApiError>> {
  try {
    const response = await client.evidence.get({ projectId, itemId })
    return { ok: true, value: response.data }
  } catch (error: unknown) {
    return { ok: false, error: toApiError(error) }
  }
}
```

UI states must distinguish loading, recoverable error/retry, permanent error, empty/no-result, not-found, and success. An empty evidence list is not a successful legal conclusion.

## Rules

- Python catches specific exceptions; TypeScript handles every rejection and narrows `unknown`.
- Provider ports return typed results/errors, never booleans, `None`, or raw external responses.
- Organization-owned reads use `org_id`; project-owned reads use `org_id` + `project_id`; global catalog reads are explicit and non-tenant.
- Critical decisions roll back together with their audit record on transaction failure.
