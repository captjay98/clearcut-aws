---
title: Avoid Barrel File Imports
impact: CRITICAL
impactDescription: Avoid loading unrelated modules and slowing development or cold starts
tags: bundle, imports, tree-shaking, barrel-files, performance
---

## Avoid Barrel File Imports

Import directly from source modules instead of broad barrel files when a barrel pulls unrelated code into the graph. ClearCut does not use an external component or icon library; this rule applies to the planned internal design-system and feature packages.

**Incorrect — broad package barrel:**

```tsx
import { badge, card, dataTable, page, progress, statGrid } from "@clearcut/design-system";
```

If the package root eagerly re-exports every primitive, importing one helper can force the bundler and development server to analyze all of them.

**Correct — direct internal modules:**

```tsx
import { badge } from "@clearcut/design-system/badge";
import { page } from "@clearcut/design-system/page";
```

Use a package-level import only when the package is proven side-effect-free and the configured bundler reliably tree-shakes it. Measure the actual bundle and development graph before claiming a performance gain; do not introduce an icon/component dependency to demonstrate this rule.
