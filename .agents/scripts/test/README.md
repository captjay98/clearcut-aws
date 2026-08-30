# Consumer Tooling Tests

The consumer test suite exercises the scripts shipped inside this repository. Tests use Node's built-in test runner and create isolated temporary repositories; they must never modify tracked workspace files.

## Run

```bash
node --test .agents/scripts/test/*.test.mjs
```

`node .agents/scripts/signoff.mjs` runs the same suite after generated-drift, lint, verify, package-manager, and MCP configuration checks.

## Current Coverage

`hardening.test.mjs` verifies:

- strict consumer generation preserves the intentional Kiro `@builtin`/MCP autonomy contract;
- stale root MCP output is removed when canonical servers become empty;
- MCP smoke respects enabled/local-disabled toolchains, validates the canonical source, and skips a valid empty server map;
- `pnpm` is accepted while alternate installs and non-exact remote executors are rejected in actionable project surfaces;
- signoff discovers nested tests and propagates a child-test failure;
- sensitive-edit hooks normalize path aliases and symlinks, request human approval for protected control-plane files, hard-block environment secrets/direct lockfile edits, and allow environment templates;
- Kiro is included in commit and protected-branch hook coverage;
- orphan Kiro template JSON is absent.

## Test Requirements

1. Add the failing regression before changing script behavior and confirm the expected RED result.
2. Put every fixture under `mkdtemp()` and register recursive cleanup with `t.after()`.
3. Copy only the scripts needed by the fixture; never write under the real `.agents/` tree.
4. Clear `NODE_TEST_CONTEXT` before recursively invoking `node --test` from a test fixture.
5. Assert exit status plus meaningful stdout/stderr, not `assert.ok(true)` placeholders.
6. Keep tests deterministic and offline; live MCP smoke is a separate explicit operation.
