import { spawnSync } from 'node:child_process'
import path from 'node:path'

const ROOT = process.cwd()
const BUN = process.execPath

const command = process.argv[2]
const args = process.argv.slice(3)

const map = {
  build: 'build.mjs',
  lint: 'lint.mjs',
  verify: 'verify.mjs',
  signoff: 'signoff.mjs',
  'check-mcp': 'check-mcp.mjs',
}

if (!command || !map[command]) {
  process.stderr.write('usage: bun .agents/scripts/agents.mjs <build|lint|verify|signoff|check-mcp>\n')
  process.exit(1)
}

const result = spawnSync(
  BUN,
  [path.join('.agents', 'scripts', map[command]), ...args],
  {
    cwd: ROOT,
    env: process.env,
    stdio: 'inherit',
  },
)

process.exit(result.status ?? 0)
