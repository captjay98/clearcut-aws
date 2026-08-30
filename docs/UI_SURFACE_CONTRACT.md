# ClearCut UI Surface Contract

**Status:** approved consolidation of existing UI plans and the authoritative mock  
**Source of truth:** `misc/clearcut-flow/`  
**Production target:** Astro public site plus TanStack Start authenticated workspace

## Shared contract

Every production surface:

- renders through the ClearCut-owned `Page` composition and shared primitives;
- preserves Script and Night shoot themes, production-script typography, revision stock, margin marks, two-layer navigation, and text/CSS glyphs;
- supports loading, empty, recoverable error, permanent error, success, and access-safe not-found states appropriate to the resource;
- keeps capability-gated controls focusable with a precise explanation;
- remains keyboard-operable with visible focus, live status, dialog/drawer focus restoration, reduced motion, and 44px coarse-pointer targets;
- has no horizontal page overflow at 320, 375, 768, 1024, and 1440px;
- uses generated clients and server authorization rather than duplicating domain rules;
- never presents confidence, status, a judge score, or a released report as legal clearance.

## Canonical 20 surfaces

| Surface | Production route responsibility | Owning active plan |
|---|---|---|
| `#marketing` | Explain audience, problem, evidence loop, product boundary, and runtime stack truthfully | 06, 12 |
| `#auth` | Configuration-aware sign-in, recovery, verification, suspension, invitation continuation | 02, 06 |
| `#invite` | Resolve one invitation, show role/project scope, handle five terminal states safely | 02, 06 |
| `#onboarding` | Authenticated atomic organization bootstrap and optional first invitation | 02, 06 |
| `#projects` | Authorized organization/project chooser, aggregates, empty/no-grant states | 02, 06 |
| `#notifications` | Organization inbox with event tiers, structured destinations, read state, push/SSE/poll | 09 |
| `#team` | Members, invitations, fixed roles, project grants, deactivation/reactivation | 02, 07 |
| `#settings` | General, governance, data/privacy, integrations; protected/operational separation | 02, 10 |
| `#trust` | Evaluation bindings, deterministic gates, judge rubric, bounded learning | 10 |
| `#records` | Scoped/redacted activity, runs/tools, evaluations, policies, operations | 10 |
| `#new` | Project details, four imports, parse confirmation, sequential detection/research | 03, 06 |
| `#project` | Project summary, derived stats, next accountable action | 07 |
| `#workspace` | Versioned screenplay, scene rail, margin flags, adaptive evidence drawer | 07 |
| `#items` | Addressable filter/sort/group/list/board and safe bulk operations | 07 |
| `#item` | Stable item detail, full provenance, governed actions, discussion, print | 07 |
| `#versions` | Immutable version ledger, diff, lineage, durable selective re-scan | 08 |
| `#watch` | Cadence, monitoring runs, material changes, governed review/follow-up | 09 |
| `#report` | Frozen snapshot generation, preview, separate release, download and print | 11 |
| `#sitemap` | Prototype review index only; not a production route unless explicitly retained | 06 |
| `#states` | Prototype state gallery only; production state tests remain per-surface | 06 |

The mock also contains marketing variants, a features page, documentation page, and organization resolver renderer. These are supporting prototype routes, not additions to the canonical 20-surface count. The production router may give the resolver a real route/state, but reporting must keep the canonical count consistent.

## Component boundary

Feature code imports only ClearCut-owned components:

```tsx
import {
  Badge,
  Banner,
  Card,
  DataTable,
  EmptyState,
  Page,
  Progress,
  Section,
  StatGrid,
  TabsBar,
} from "@clearcut/design-system";
```

No shadcn, external visual component system, Tailwind assumption, icon library, or direct headless-library import enters feature code. One headless accessibility library may be selected only after an SSR/hydration, DOM-fidelity, keyboard, screen-reader, reduced-motion, bundle, maintenance, and license proof; it stays behind ClearCut adapters.

## Mock versus production boundary

The prototype may simulate time, roles, provider calls, persistence, and exports to demonstrate interaction. Production must replace those simulations with generated-client calls and truthful durable state. A browser receipt is not an `AuditEvent`; sample sources are not a live Parallel run; a simulated snapshot is not a released artifact.

## Production UI acceptance

Each surface ships only when its plan proves:

1. the happy path against the generated client;
2. every required state and access-safe direct link;
3. both themes at the five target widths;
4. keyboard, focus, live-region, coarse-pointer, and reduced-motion behavior;
5. unknown/unauthorized resource parity;
6. no direct provider or headless dependency leakage;
7. visual comparison to the matching mock surface;
8. print behavior for item and report surfaces.
