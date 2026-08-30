---
trigger: file_edit
---

# Prefer Composition Over Inheritance

Use composition and dependency injection instead of deep inheritance hierarchies. Keep module boundaries explicit and pass typed ports/services into application code.

## TypeScript Pattern

```typescript
// Good — composition via hooks and explicit dependencies
function useEvidenceReview() {
  const evidence = useEvidenceQuery()
  const decisions = useDecisionActions()
  const receipts = useAuditReceipts()

  return { evidence, decisions, receipts }
}
```

## Python Pattern

```python
# Good — composition through typed provider ports
@dataclass(frozen=True)
class ResearchService:
    provider: ResearchProvider
    repository: ResearchRepository
    audit: AuditWriter

    async def run(self, query: ResearchQuery) -> ResearchResult | ResearchError:
        return await self.provider.search(query)
```

```python
# Avoid — deep inheritance hiding dependencies and policy boundaries
class ParallelResearchService(BaseResearchService, PolicyMixin, AuditMixin):
    ...
```

## ClearCut Guidance

- Compose FastAPI application services from repositories, capability guards, and typed provider ports.
- Compose TanStack components from query/action hooks and design-system primitives.
- Keep cross-module communication in typed events/application services; do not inherit storage behavior across bounded modules.
- Do not use composition to bypass organization/project authorization, evidence provenance, or governed-action approval.

## Benefits

- Easier testing with explicit ports and recorded Parallel fixtures.
- Clearer tenant scope and approval dependencies.
- Fewer fragile base-class contracts.
- Better replacement and rollback of provider implementations.
