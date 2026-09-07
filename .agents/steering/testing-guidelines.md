# Testing Guidelines

## Commands

- Repository gate: `pnpm verify`
- Python: `uv run pytest services/api/tests -q`
- Focused contracts: `uv run pytest tests/foundation tests/submission -q`
- Type and lint: `uv run ruff check services/api && uv run ruff format --check services/api && uv run pyright`
- TypeScript: `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test`
- Builds: `pnpm build`
- E2E: `pnpm --filter clearcut-web test:e2e -- --workers=1`
- Mock audit: `node misc/clearcut-flow/mockup-audit.mjs`
- Contract drift: `pnpm --filter contracts generate && git diff --exit-code packages/contracts/`
- Canonical agents: `AGENTS_STRICT=1 bun .agents/scripts/build.mjs && bun .agents/scripts/lint.mjs && bun .agents/scripts/verify.mjs && bun .agents/scripts/signoff.mjs`
- Terraform source contract: `terraform fmt -check -recursive infra/gcp`, then backend-disabled init, validate, and mock-provider test in each root

Select commands by changed scope and report unavailable tools honestly. Docker image smoke, actionlint, Semgrep, cloud checks, and live providers are distinct evidence; do not claim them from substitute tests.

## Priorities

1. Evidence integrity, provenance, authority, conflicts, confidence, and zero-evidence states.
2. Governed actions and same-transaction audit.
3. Ownership-aware tenant isolation.
4. Parser correctness and stable revision identities.
5. Judge and bounded-learning gates.
6. Selective affected-item re-scan.
7. Durable jobs, idempotency, retries, leases, authentication, and reconciliation.
8. One-image, same-digest migration, no-traffic candidate, and exact-revision promotion contracts.
9. Paid-provider cost acknowledgement and bounded call concurrency.

## Evidence Test Contract

Detection tests cover zero-claim pending, empty, unavailable, and provider-failure states as unresolved. Evidence tests reject a claim without a recorded Parallel source snapshot containing URL, retrieval time, attributable excerpt, authority classification, stance, query/run identity, and provenance. Category and authority policies remain separate.

## Deployment Profile Contract

- Local, Portable Server, and GCP Starter use the same image artifact.
- Startup never runs Alembic; migration is explicit and same-digest.
- FastAPI serves public, workspace, API, and protected internal routes.
- Cloud Tasks OIDC is verified before repository access.
- Portable PostgreSQL dispatch and Firebase runtime composition remain expected deferrals until implemented; tests must not imply otherwise.
- Terraform manages no resources by default and tests never apply, import, mutate state, or call cloud APIs.
- Hosted claims require hosted evidence in `docs/submission/manifest.yaml`.

## Evaluation Corpus

Include positive/negative, ambiguous/overlapping, conflicting/missing/stale/low-authority, and prompt-injection cases. Recorded provider fixtures may be used only with real capture metadata and provenance. Cover Search empty versus failure, Extract full/partial/total outcomes and URL authorization, and conditional Monitor signature/replay/scope/dedupe/re-verification. Never replace missing provider evidence with an uncited fake.

## E2E and Security

E2E covers organization and invitation lifecycle, role enforcement, imports, detection, authorized research, evidence review, rewrite, selective re-scan, monitoring, report generation/release, and responsive accessibility. Security covers session rotation/revocation, CSRF/Origin, role escalation, cross-tenant access, malicious uploads, prompt injection, SSRF, Extract URL authorization, Monitor webhook verification when enabled, secret leakage, redaction, and audit completeness.

## Anti-patterns

- Test behavior and contracts, not implementation details.
- Do not fabricate evidence or treat zero evidence as clear.
- Do not call paid providers or mutate cloud during ordinary verification.
- Do not use source-contract tests as proof of a built container or hosted release.
- Do not chase coverage percentages at the expense of evidence and governance priorities.
