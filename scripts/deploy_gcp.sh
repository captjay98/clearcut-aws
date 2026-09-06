#!/usr/bin/env bash
# Legacy direct deployment entry point retained only to fail closed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"

cat >&2 <<EOF
Deployment is blocked while submission readiness is NO-GO.

No cloud authentication, project creation, API enablement, IAM mutation, build,
database creation, or deployment was attempted.

Review:
  $ROOT/docs/submission/manifest.yaml
  $ROOT/infra/gcp/README.md
  $ROOT/.github/workflows/migrate.yml
  $ROOT/.github/workflows/deploy.yml

Only the protected, keyless, digest-pinned workflows may be used after every
external blocker is closed and accountable human approval is recorded.
EOF

exit 1
