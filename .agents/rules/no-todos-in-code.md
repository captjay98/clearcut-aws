---
trigger: file_edit
---

# No TODO Markers in Production Code

Never leave `TODO`, `FIXME`, `HACK`, or `XXX` comments in committed production code. This rule applies to all generated stubs and has no scaffolder exception.

## What To Do Instead

- Finish the implementation before committing it, or stop and report the missing prerequisite.
- Create a tracked issue/backlog entry outside production source when work must be scheduled.
- For an explicitly delegated boundary stub, use a typed, deliberate error such as `NotImplementedError('Research provider adapter is not configured')`; do not disguise it as success and do not claim the feature is complete.
- Keep phase-gated scaffolding out of absent target directories until Plan 01 and a real sibling pattern exist.

## Anti-Patterns

```typescript
// TODO: Implement the evidence receipt later
// FIXME: Ignore the Parallel timeout for now
// HACK: Treat no sources as verified
```

```python
# ❌ WRONG — fabricated fallback hides a failed research run
return EvidenceClaim(excerpt='No issues found')
```

A provider failure must produce a typed error or visible review item. A zero-evidence `ClearanceItem` is valid only with an explicit unresolved state; it is not a reason to add an uncited claim.
