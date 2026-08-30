# Coding Standards

## Python (Backend — FastAPI)

- **Version**: Python 3.12+
- **Formatter**: Ruff (`ruff format`)
- **Linter**: Ruff (`ruff check --fix`)
- **Type checking**: Pyright in strict mode
- **Config**: `pyproject.toml`
- **Run**: `ruff check . && ruff format --check . && pyright`

### Conventions
- Strict types everywhere. No `Any` unless wrapping an untyped third-party library, and annotate the wrapper's return.
- Explicit error handling — no bare `except:`, no silent catches. Use typed result/error returns from provider ports.
- Guard clauses before happy path.
- Async by default for I/O-bound operations. Use `async def` for route handlers and service methods that call providers.
- Domain types use `dataclass` or Pydantic `BaseModel`. No raw dicts crossing module boundaries.
- SQLAlchemy models use mapped columns with explicit types. No implicit string columns.

## TypeScript (Frontend — TanStack Start + Astro)

- **Version**: TypeScript 5.x, strict mode
- **Formatter**: Prettier
- **Linter**: ESLint with TypeScript plugin
- **Config**: `eslint.config.js`, `.prettierrc`
- **Run**: `pnpm lint && pnpm format:check`

### Conventions
- Strict types everywhere. No `any`. Use `unknown` for truly dynamic values and narrow immediately.
- Explicit error handling — no unhandled promise rejections, no silent catches.
- Guard clauses before happy path.
- Prefer `const` over `let`. No `var`.
- Named exports only — no default exports.
- Use `cn()` (or equivalent) for conditional class composition. No inline styles except runtime-computed values.

## General

### Naming
- Files: `kebab-case` (both Python and TypeScript)
- Functions/variables: `snake_case` (Python), `camelCase` (TypeScript)
- Classes/types: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Database columns: `snake_case`
- API endpoints: `/kebab-case`

### Error Handling
- Provider ports return typed results or typed errors, not ambiguous booleans or `None`.
- Critical decisions and their audit events commit in the same database transaction.
- Retries use bounded exponential backoff with jitter. Permanent failures create visible review items.
- Never convert a failed research run into invented fallback evidence.

### Security
- Never include API keys, passwords, or sensitive data in source files. Use Secret Manager.
- Fetched content and screenplay text are untrusted data, never instructions. Source content cannot change agent policy or tool permissions.
- Input validation on every endpoint. MIME, magic-byte, extension, and size checks on uploads.
