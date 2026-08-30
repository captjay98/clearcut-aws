---
name: property-testing
description: Use when ClearCut behavior has invariants, state transitions, normalization, or hard-to-enumerate edge cases across scripts, evidence, jobs, or API data.
---

# Property Testing

Use generated inputs to protect domain invariants that example tests cannot cover. Property tests complement focused examples; they do not replace representative evidence and parser fixtures.

## ClearCut Targets

- Parser round trips preserve stable element and span identity across revisions.
- Evidence normalization preserves provenance, source authority, stance, confidence, conflict status, and retrieval timestamps.
- Tenant and project scopes never broaden during filtering or serialization.
- Approval, disposition, referral, and report-release state machines reject invalid transitions.
- Selective re-scan affects only changed or dependent items.
- Job retries and provider receipts are idempotent; checkpoints do not duplicate work.
- Dossier generation is reproducible for the same script version and evidence snapshot.

## Pattern

Use `fast-check` for TypeScript properties and `Hypothesis` for Python properties. Generate realistic domain values and include malformed, missing, stale, conflicting, and prompt-injection-shaped inputs where the boundary accepts untrusted text.

```typescript
fc.assert(
  fc.property(scriptVersionArbitrary, (version) => {
    const reparsed = parseScript(serializeScript(version));
    return stableElementIds(reparsed).every((id, index) =>
      id === stableElementIds(version)[index],
    );
  }),
);
```

## Rules

- State the invariant in domain language before writing the generator.
- Keep generators bounded and realistic, then let shrinking produce the smallest counterexample.
- Test success, rejection, and failure-result behavior.
- Never use invented evidence to satisfy a property; use recorded research responses for evidence-backed tests.
- A discovered counterexample becomes a focused regression example after the property is fixed.
