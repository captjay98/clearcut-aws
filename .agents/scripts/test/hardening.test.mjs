import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import {
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { test } from 'node:test'

const SCRIPTS_SOURCE = join(import.meta.dirname, '..')
const REPO_ROOT = join(SCRIPTS_SOURCE, '..', '..')

function createTempDir(t, prefix = 'agents-consumer-') {
  const root = mkdtempSync(join(tmpdir(), prefix))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  return root
}

function write(root, relativePath, content) {
  const target = join(root, relativePath)
  mkdirSync(dirname(target), { recursive: true })
  writeFileSync(target, content)
}

function copyConsumerScripts(root) {
  cpSync(SCRIPTS_SOURCE, join(root, '.agents', 'scripts'), {
    recursive: true,
    filter(source) {
      return !source.includes(`${join('scripts', 'test')}`)
    },
  })
}

function createConsumer(t, { mcpServers = {}, hooks = null } = {}) {
  const root = createTempDir(t)
  copyConsumerScripts(root)
  write(root, '.agents/profile.toml', `version = 1

[selection]
toolchains_allowed = ["kiro"]
toolchains_default_enabled = ["kiro"]
stacks = []
commands_include = []
commands_exclude = []
skills_include = []
skills_exclude = []

[policy]
mcp_base = []
override_mode = "narrowing_only"
disabled_output_behavior = "prune"
`)
  write(root, '.agents/personas/explorer.md', `---
description: Read-only explorer
mode: subagent
model: inherit
---
# Explorer
`)
  write(root, '.agents/commands/keep.md', `---
description: Keep command
---
# Keep
`)
  write(root, '.agents/skills/keep/SKILL.md', `---
name: keep
description: Keep skill
---
# Keep
`)
  write(root, '.agents/rules/guide.md', '# Rule\n')
  write(root, '.agents/steering/guide.md', '# Guide\n')
  write(root, '.agents/mcp/servers.json', JSON.stringify({ version: 1, servers: mcpServers }, null, 2) + '\n')
  write(root, '.agents/hooks/hooks.json', JSON.stringify({
    version: 1,
    hooks: hooks ?? [
      {
        id: 'session-start-reminder',
        event: 'session_start',
        matcher: '.*',
        command: 'exit 0',
        tools: ['kiro'],
      },
      {
        id: 'block-sensitive-edits',
        event: 'before_tool',
        matcher: 'Edit|Write',
        command: 'node .agents/scripts/sensitive-edit-adapter.mjs',
        tools: ['kiro'],
      },
    ],
  }, null, 2) + '\n')
  write(root, '.agents/models.toml', '[models.explorer]\nkiro = "test/model"\n')
  return root
}

function runScript(root, script, args = [], env = {}, input = undefined) {
  const childEnv = { ...process.env, ...env }
  delete childEnv.NODE_TEST_CONTEXT
  return spawnSync(process.execPath, [`.agents/scripts/${script}`, ...args], {
    cwd: root,
    encoding: 'utf8',
    env: childEnv,
    input,
  })
}

function runBuild(root, env = {}) {
  return runScript(root, 'build.mjs', [], { AGENTS_STRICT: '1', ...env })
}

function readFrontmatterArray(markdown, key) {
  const line = markdown.split('\n').find((candidate) => candidate.startsWith(`${key}: `))
  assert.ok(line, `missing ${key} frontmatter`)
  return JSON.parse(line.slice(key.length + 2))
}

test('consumer build preserves Kiro autonomy tools and removes stale root MCP output', (t) => {
  const root = createConsumer(t, {
    mcpServers: {
      local: { command: 'node', args: ['-e', 'setTimeout(() => {}, 1000)'] },
    },
  })

  const first = runBuild(root)
  assert.equal(first.status, 0, first.stderr || first.stdout)
  const agent = readFileSync(join(root, '.kiro/agents/explorer.md'), 'utf8')
  assert.deepEqual(readFrontmatterArray(agent, 'tools'), ['@builtin'])
  assert.match(agent, /^includeMcpJson: true$/m)
  assert.equal(existsSync(join(root, '.mcp.json')), true)

  write(root, '.agents/mcp/servers.json', JSON.stringify({ version: 1, servers: {} }) + '\n')
  const second = runBuild(root)
  assert.equal(second.status, 0, second.stderr || second.stdout)
  assert.equal(existsSync(join(root, '.mcp.json')), false)
})

test('MCP smoke inspects only enabled toolchains and skips without canonical servers', (t) => {
  const root = createConsumer(t)
  write(root, '.kiro/settings/mcp.json', '{"mcpServers":{"unexpected":{}}}\n')

  const skipped = runScript(root, 'mcp-smoke.mjs')
  assert.equal(skipped.status, 0, skipped.stderr || skipped.stdout)
  assert.match(skipped.stdout, /skipped \(no canonical MCP servers configured\)/)

  rmSync(join(root, '.agents/mcp/servers.json'))
  const missingCanonical = runScript(root, 'mcp-smoke.mjs')
  assert.notEqual(missingCanonical.status, 0)
  assert.match(missingCanonical.stderr, /missing canonical MCP config/)

  write(root, '.agents/mcp/servers.json', JSON.stringify({
    version: 1,
    servers: { local: { command: process.execPath, args: ['-e', 'setTimeout(() => {}, 20000)'] } },
  }) + '\n')
  write(root, '.kiro/settings/mcp.json', JSON.stringify({
    mcpServers: { local: { command: process.execPath, args: ['-e', 'setTimeout(() => {}, 20000)'] } },
  }) + '\n')
  const active = runScript(root, 'mcp-smoke.mjs', [], { MCP_SMOKE_TIMEOUT_MS: '50' })
  assert.equal(active.status, 0, active.stderr || active.stdout)
  assert.match(active.stdout, /summary pass=1 fail=0 unique=1/)

  write(root, '.agents/local.profile.toml', 'version = 1\n\n[selection]\ndisable_toolchains = ["kiro"]\n')
  rmSync(join(root, '.kiro'), { recursive: true, force: true })
  const locallyDisabled = runScript(root, 'mcp-smoke.mjs')
  assert.equal(locallyDisabled.status, 0, locallyDisabled.stderr || locallyDisabled.stdout)
  assert.match(locallyDisabled.stdout, /summary pass=0 fail=0 unique=0/)
})

test('package-manager policy allows pnpm, rejects install alternatives and unpinned npx, and skips skills/generated copies', (t) => {
  const root = createConsumer(t)
  write(root, '.agents/commands/workflow.md', `---\ndescription: Workflow\n---\npnpm install\npnpm test\nnpx package@1.2.3 test\nnpx @scope/package@2.3.4 test\nnpx --package helper@3.4.5 helper\n`)
  write(root, '.agents/skills/vendor/SKILL.md', '# Vendor examples\nnpm install\nnpx playwright init\n')
  write(root, '.kiro/skills/vendor/SKILL.md', '# Generated copy\nyarn install\n')
  const allowed = runScript(root, 'check-package-managers.mjs')
  assert.equal(allowed.status, 0, allowed.stderr || allowed.stdout)

  write(root, '.agents/commands/workflow.md', `---\ndescription: Workflow\n---\nnpm install\nyarn add package\nnpx playwright test\nnpx package@latest test\nnpx package@^1.2.3 test\n`)
  write(root, '.agents/scripts/unsafe.mjs', 'const command = "npx unsafe@* run"\n')
  const rejected = runScript(root, 'check-package-managers.mjs')
  assert.notEqual(rejected.status, 0)
  assert.match(rejected.stderr, /npm install/)
  assert.match(rejected.stderr, /yarn add/)
  assert.match(rejected.stderr, /unpinned npx executor/)
  assert.match(rejected.stderr, /unsafe\.mjs/)
})

test('signoff runs real node tests and package policy with strict mode, and fails broken tests', (t) => {
  const root = createTempDir(t, 'agents-signoff-')
  mkdirSync(join(root, '.agents/scripts/test'), { recursive: true })
  cpSync(join(SCRIPTS_SOURCE, 'signoff.mjs'), join(root, '.agents/scripts/signoff.mjs'))
  const calls = []
  for (const name of ['check-generated', 'lint', 'verify', 'check-mcp', 'check-package-managers']) {
    write(root, `.agents/scripts/${name}.mjs`, `import { appendFileSync } from 'node:fs'\nappendFileSync(${JSON.stringify(join(root, 'calls.log'))}, ${JSON.stringify(name + ':' )} + (process.env.AGENTS_STRICT || 'unset') + '\\n')\n`)
  }
  write(root, '.agents/scripts/test/consumer.test.mjs', `import { test } from 'node:test'\ntest('passes', () => {})\n`)

  const passing = runScript(root, 'signoff.mjs')
  assert.equal(passing.status, 0, passing.stderr || passing.stdout)
  assert.match(readFileSync(join(root, 'calls.log'), 'utf8'), /check-package-managers:1/)
  assert.match(passing.stdout, /node --test/)

  const failingRoot = createTempDir(t, 'agents-signoff-failing-')
  mkdirSync(join(failingRoot, '.agents/scripts/test'), { recursive: true })
  cpSync(join(SCRIPTS_SOURCE, 'signoff.mjs'), join(failingRoot, '.agents/scripts/signoff.mjs'))
  for (const name of ['check-generated', 'lint', 'verify', 'check-mcp', 'check-package-managers']) {
    write(failingRoot, `.agents/scripts/${name}.mjs`, '')
  }
  write(failingRoot, '.agents/scripts/test/nested/consumer.test.mjs', `import { test } from 'node:test'\ntest('fails', () => { throw new Error('broken consumer') })\n`)
  const failing = runScript(failingRoot, 'signoff.mjs')
  assert.notEqual(
    failing.status,
    0,
    `signoff unexpectedly passed\nstdout:\n${failing.stdout}\nstderr:\n${failing.stderr}`,
  )
  assert.match(`${failing.stdout}\n${failing.stderr}`, /broken consumer/)
})

test('Kiro hook adapter normalizes path aliases, asks for approval on human-only control-plane edits, and hard-blocks secrets and lockfiles', (t) => {
  const root = createConsumer(t)
  const missingPath = runScript(root, 'kiro-hook-adapter.mjs', ['block-sensitive-edits'], {}, JSON.stringify({ toolInput: {} }))
  assert.equal(missingPath.status, 2, missingPath.stderr || missingPath.stdout)

  const approval = runScript(root, 'kiro-hook-adapter.mjs', ['block-sensitive-edits'], {}, JSON.stringify({ toolInput: { path: '.agents/hooks/hooks.json' } }))
  assert.equal(approval.status, 0, approval.stderr || approval.stdout)
  assert.match(approval.stdout, /"permissionDecision":"ask"/)

  symlinkSync(join(root, '.agents/hooks/hooks.json'), join(root, 'hooks-alias.json'))
  const symlinkApproval = runScript(root, 'kiro-hook-adapter.mjs', ['block-sensitive-edits'], {}, JSON.stringify({ toolInput: { path: 'hooks-alias.json' } }))
  assert.equal(symlinkApproval.status, 0, symlinkApproval.stderr || symlinkApproval.stdout)
  assert.match(symlinkApproval.stdout, /"permissionDecision":"ask"/)

  const secret = runScript(root, 'kiro-hook-adapter.mjs', ['block-sensitive-edits'], {}, JSON.stringify({ toolInput: { filePath: '.env.local' } }))
  assert.equal(secret.status, 2, secret.stderr || secret.stdout)

  const lockfile = runScript(root, 'kiro-hook-adapter.mjs', ['block-sensitive-edits'], {}, JSON.stringify({ toolInput: { filePath: 'pnpm-lock.yaml' } }))
  assert.equal(lockfile.status, 2, lockfile.stderr || lockfile.stdout)

  const allowed = runScript(root, 'kiro-hook-adapter.mjs', ['block-sensitive-edits'], {}, JSON.stringify({ toolInput: { filePath: '.env.example' } }))
  assert.equal(allowed.status, 0, allowed.stderr || allowed.stdout)
})

test('canonical commit and protected-branch hooks include Kiro coverage', () => {
  const hooks = JSON.parse(readFileSync(join(REPO_ROOT, '.agents/hooks/hooks.json'), 'utf8')).hooks
  for (const id of ['enforce-conventional-commit', 'protect-main-branch']) {
    const hook = hooks.find((candidate) => candidate.id === id)
    assert.ok(hook)
    assert.ok(hook.tools.includes('kiro'))
  }
})

test('orphan Kiro template JSON configuration is not retained', () => {
  const templateDir = join(REPO_ROOT, '.agents/kiro/templates')
  const jsonFiles = readdirSync(templateDir).filter((name) => name.endsWith('.json'))
  assert.deepEqual(jsonFiles, [])
})
