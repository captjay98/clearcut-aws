# Normalized Static Route Reservation Design

## Problem

The public static catch-all classifies its raw route parameter before file resolution repeatedly percent-decodes it. Encoded aliases can therefore bypass reserved `api` and `healthz` checks and serve colliding files from the public site distribution.

## Decision

Introduce one canonical path boundary for static delivery. It will percent-decode once, reject malformed or residual percent escapes and unsafe separators, reject NUL, absolute paths, and `.` or `..` segments, and produce one `PurePosixPath`. Namespace classification and filesystem resolution will consume that same object without decoding again.

The first canonical segment `api` is reserved, covering product API, FastAPI docs, OpenAPI, and ReDoc routes. The exact canonical root path `healthz` is reserved. Root `/docs` remains an authored public route because the framework documentation contract is `/api/docs`.

## Error Behavior

Reserved canonical aliases must not enter public static resolution. Existing route ordering continues to handle real API/docs/health endpoints. Unknown or encoded reserved aliases return JSON not-found behavior rather than static HTML or files. Ambiguous paths that retain percent escapes after the single decode pass are rejected instead of being decoded repeatedly.

## Security Invariants

The existing resolved-path containment and symlink checks remain authoritative. Canonicalization continues to reject traversal, backslashes, NULs, absolute paths, and dot segments. Asset, workspace, and public resolvers all receive an already canonical relative path, preventing classification and resolution from interpreting different path identities.

## TDD and Validation

First add reserved-name fixture files and regression requests for literal, singly encoded, and multiply encoded `api` and `healthz` aliases; verify the new cases fail before implementation. Then make the smallest static-delivery change and run same-origin tests, mounted operation/contract tests, site tests/build, web build and focused runtime E2E, Ruff/format checks, and diff checks. No cloud, provider, network, Terraform, or protected-path access is required.
