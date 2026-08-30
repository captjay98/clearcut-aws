# ClearCut Agent Consumer Tooling

These scripts run from the ClearCut repository and treat `.agents/` as the canonical source of agent configuration. Generated `.kiro/`, `.claude/`, `.gemini/`, `.factory/`, `.opencode/`, and root guide files are consumer output; do not edit them by hand.

## Supported commands

| Script | Purpose |
| --- | --- |
| `build.mjs` | Render enabled toolchains, hooks, MCP configuration, `AGENTS.md`, and the render manifest. `AGENTS_STRICT=1` enables hard renderer policy. |
| `check-generated.mjs` | Build in an isolated temporary directory and compare generated output without mutating the repository. |
| `check-mcp.mjs` | Validate canonical MCP declarations and enabled toolchain MCP output, including pinned provider versions and secret placeholders. |
| `check-package-managers.mjs` | Check actionable agent surfaces for disallowed npm/yarn installs and unpinned npx executors while ignoring vendored skills, generated copies, tests, and this checker. |
| `config.mjs` | Parse profiles, resolve enabled toolchains, and load policy configuration. |
| `kiro-hook-adapter.mjs` | Translate Kiro hook JSON input into canonical hook environment variables and fail closed on malformed input. |
| `lint.mjs` | Validate canonical frontmatter, schemas, hooks, profiles, executable headings, and overlay policy. |
| `mcp-smoke.mjs` | Run configured MCP stdio commands for enabled toolchains only. It skips when canonical MCP servers are empty. |
| `signoff.mjs` | Run strict generated-output, lint, verify, package-manager, MCP, and consumer test gates. It intentionally does not run network-dependent MCP smoke. |
| `sensitive-edit-adapter.mjs` | Normalize edit path aliases, resolve symlinks, request explicit Kiro approval for human-only `.agents` control-plane paths, and hard-block real environment secret files or direct lockfile edits. `.env.example`, `.env.sample`, and `.env.template` remain editable. |
| `toolchains.mjs` | Discover renderer metadata and output locations. |
| `verify.mjs` | Verify generated parity, manifests, hook coverage, stale artifacts, and retained references. |
| `verify-kiro.mjs` | Validate Kiro hook documents and expected generated names. |

Renderer modules live in `renderers/`: `claude.mjs`, `common.mjs`, `factory.mjs`, `gemini.mjs`, `kiro.mjs`, `opencode.mjs`, and `pi.mjs`.

## Tests

Use Node's built-in test runner; tests create temporary consumer repositories and never write to tracked files:

```bash
node --test .agents/scripts/test/*.test.mjs
```

The same consumer tests run as part of signoff. Run the full local gate with:

```bash
node .agents/scripts/signoff.mjs
```

For a strict authoring check before signoff:

```bash
AGENTS_STRICT=1 node .agents/scripts/build.mjs
AGENTS_STRICT=1 node .agents/scripts/lint.mjs
AGENTS_STRICT=1 node .agents/scripts/verify.mjs
```

## Consumer workflow

1. Edit canonical `.agents/` content and scripts.
2. Run the Node test command above; a failing test should identify the missing behavior.
3. Run `node .agents/scripts/signoff.mjs` before delivering changes.
4. Regenerate toolchain output separately when the coordinator requests it; this repository does not keep generated output as the source of truth.

The hooks provide an additional translation and fail-closed boundary, but user-level Kiro permissions remain the enforcement layer for generated Kiro agents. Do not narrow the intentional Kiro renderer contract of `tools: ["@builtin"]` and `includeMcpJson: true`.
