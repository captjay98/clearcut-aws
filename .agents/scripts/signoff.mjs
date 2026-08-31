import { readdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import path from 'node:path'

const ROOT = process.cwd()
const NODE = 'node'
const STRICT_ENV = { ...process.env, AGENTS_STRICT: '1' }

function collectTestFiles(directory) {
  const files = []
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      files.push(...collectTestFiles(fullPath))
    } else if (entry.isFile() && entry.name.endsWith('.test.mjs')) {
      files.push(path.relative(ROOT, fullPath))
    }
  }
  return files
}

function run(scriptPath) {
  const result = spawnSync(
    NODE,
    [path.join('.agents', 'scripts', scriptPath)],
    {
      cwd: ROOT,
      env: STRICT_ENV,
      stdio: 'inherit',
    },
  )
  if (result.status !== 0) process.exit(result.status ?? 1)
}

function runConsumerTests() {
  const testDir = path.join(ROOT, '.agents', 'scripts', 'test')
  const testFiles = collectTestFiles(testDir).sort()

  if (testFiles.length === 0) {
    process.stderr.write('agents-signoff: no consumer tests found\n')
    process.exit(1)
  }

  process.stdout.write(`agents-signoff: node --test ${testFiles.join(' ')}\n`)
  const result = spawnSync(NODE, ['--test', ...testFiles], {
    cwd: ROOT,
    env: STRICT_ENV,
    stdio: 'inherit',
  })
  if (result.status !== 0) process.exit(result.status ?? 1)
}

run('check-generated.mjs')
run('lint.mjs')
run('verify.mjs')
run('check-package-managers.mjs')
run('check-mcp.mjs')
runConsumerTests()
process.stdout.write('agents-signoff: ok\n')
