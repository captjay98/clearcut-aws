# Contributing to ClearCut

Thank you for your interest in contributing to ClearCut! ClearCut is an open-source screenplay pre-clearance evidence workspace built for independent filmmakers, screenwriters, and production clearance teams.

ClearCut is distributed under the [MIT License](LICENSE). By contributing to ClearCut, you agree that your contributions will be licensed under the same terms.

---

## 1. Core Principles and Invariants

ClearCut is designed around strict architectural, legal, and security invariants. All contributions—whether from humans or AI agent pair-programmers—must uphold these rules:

1. **Evidence Provenance is Mandatory**:
   - Every `EvidenceClaim` must cite an immutable Parallel `SourceSnapshot` with URL, retrieval timestamp, attributable excerpt, publisher/authority classification, and stance.
   - Zero evidence is *unresolved*, never cleared. **No fallback, mocked, or fabricated evidence may ever be introduced.**
2. **Deterministic Security and Multi-Tenant Isolation**:
   - Every project-scoped read and write must strictly enforce authenticated `org_id` and `project_id`.
   - Capabilities are guarded by deterministic, fixed roles (`Owner`, `Admin`, `Editor`, `Reviewer`), never decided by LLMs.
3. **Accountable Human Governance**:
   - Reviewer decisions, rewrite sign-offs, referrals, and report releases require an accountable human trigger and commit with an immutable `AuditEvent` in a single database transaction.
4. **Typed Provider Boundaries**:
   - External provider ports (Google ADK for Gemini, `parallel-web` for Parallel Search/Extract) must return typed results or typed error taxonomies. No raw untyped dictionaries cross module boundaries.
5. **No Legal Conclusions**:
   - ClearCut assists qualified humans with structured research and evidence collection. It does not provide legal advice or guarantee legal clearance.

---

## 2. Development Prerequisites

* **Python 3.12+** with [`uv`](https://github.com/astral-sh/uv) package manager
* **Node.js 20+** with [`pnpm`](https://pnpm.io/) package manager
* **Bun** (for `.agents/` validation and generation toolchains)
* **Docker** (for local PostgreSQL and testing services)

---

## 3. Contribution Workflow

### Step 1: Open an Issue or Review Plans
Before starting large refactors or implementing new features:
* Check existing issues and active implementation packets under `docs/plans/implementation/`.
* Align with the active delivery milestones in `docs/IMPLEMENTATION_PLAN.md` and `docs/DECISION_GAPS.md`.

### Step 2: Branching Strategy
Create a feature branch from `main`:
```bash
git checkout -b feat/your-feature-name
# or: fix/issue-description
```

### Step 3: Contract-First & Test-Driven Development (TDD)
1. If modifying an API endpoint or event shape, update `packages/contracts/openapi.yaml` or relevant JSON schemas first.
2. Write a failing behavioral or contract test proving the missing behavior or bug.
3. Implement the minimal clean code to make the test pass.
4. Verify tenant scoping, audit emission, and error handling paths.

### Step 4: Quality Checks & Linting
Ensure all automated checks pass locally:
* **Agents & Skills**: `bun .agents/scripts/build.mjs && bun .agents/scripts/lint.mjs && bun .agents/scripts/verify.mjs`
* **Python**: `uv run ruff check . && uv run pyright`
* **TypeScript / Web**: `pnpm lint && pnpm typecheck`
* **Tests**: `uv run pytest` and `pnpm test`

---

## 4. Commit Message Guidelines

ClearCut follows the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```text
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

**Allowed Types:**
* `feat`: A new feature or capability
* `fix`: A bug fix
* `docs`: Documentation changes
* `test`: Adding or refactoring tests
* `refactor`: Code changes that neither fix a bug nor add a feature
* `chore`: Build scripts, CI changes, toolchain configurations

**Examples:**
* `feat(detection): implement brand and trademark category extractor`
* `fix(auth): enforce org_id validation on project creation route`
* `docs(contracts): update OpenAPI schema for ReportRelease`

---

## 5. Submitting a Pull Request (PR)

1. Push your branch to your fork and submit a PR against `main`.
2. Provide a clear summary of what the PR accomplishes and link any relevant issues or implementation packets.
3. Include explicit evidence of passing test runs and note any intentional limitations or non-claims.
4. Ensure CI validation passes.

Thank you for helping build ClearCut!
