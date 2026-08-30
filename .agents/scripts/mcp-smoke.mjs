import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { resolveToolchains } from './config.mjs'

const ROOT = process.cwd()
const TIMEOUT_MS = Number(process.env.MCP_SMOKE_TIMEOUT_MS ?? 10000)
const FAIL_FAST = process.env.MCP_SMOKE_FAIL_FAST === '1'
const SKIP_SERVERS = new Set(
  String(process.env.MCP_SMOKE_SKIP ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean),
)

const CONFIGS = [
  { id: 'root', file: '.mcp.json', format: 'standard' },
  { id: 'kiro', file: '.kiro/settings/mcp.json', format: 'standard' },
  { id: 'gemini', file: '.gemini/settings.json', format: 'standard' },
  { id: 'factory', file: '.factory/mcp.json', format: 'standard' },
  { id: 'claude', file: '.claude/settings.json', format: 'standard' },
  { id: 'opencode', file: 'opencode.json', format: 'opencode' },
]

function getServers(parsed, cfg) {
  if (cfg.format === 'standard') return parsed.mcpServers
  if (cfg.format === 'opencode') return parsed.mcp
  return null
}

function parseServerSpec(spec, cfg) {
  if (!spec || typeof spec !== 'object') return null

  if (cfg.format === 'opencode') {
    if (spec.enabled === false) return null

    let command = ''
    let args = []

    if (Array.isArray(spec.command) && spec.command.length > 0) {
      command = String(spec.command[0])
      args = spec.command.slice(1).map((part) => String(part))
    } else if (typeof spec.command === 'string') {
      command = spec.command
      args = Array.isArray(spec.args) ? spec.args.map((part) => String(part)) : []
    }

    if (!command) return null
    const env = spec.environment && typeof spec.environment === 'object'
      ? spec.environment
      : {}

    return { command, args, env }
  }

  if (typeof spec.command !== 'string') return null
  return {
    command: spec.command,
    args: Array.isArray(spec.args) ? spec.args : [],
    env: spec.env && typeof spec.env === 'object' ? spec.env : {},
  }
}

function resolveEnvTemplate(value) {
  if (typeof value !== 'string') return value
  return value.replace(/\$\{([A-Z0-9_]+)\}/g, (_, key) =>
    process.env[key] ?? `\${${key}}`,
  )
}

function resolveServerSpec(entry) {
  const args = Array.isArray(entry.args)
    ? entry.args.map((value) => resolveEnvTemplate(String(value)))
    : []

  const env = {}
  for (const [key, value] of Object.entries(entry.env ?? {})) {
    env[key] = resolveEnvTemplate(String(value))
  }

  return {
    ...entry,
    command: resolveEnvTemplate(String(entry.command)),
    args,
    env,
    displayCommand: String(entry.command),
    displayArgs: Array.isArray(entry.args) ? entry.args.map((value) => String(value)) : [],
  }
}

function loadCanonicalServerNames() {
  const canonicalPath = path.join(ROOT, '.agents/mcp/servers.json')
  if (!fs.existsSync(canonicalPath)) {
    throw new Error('missing canonical MCP config .agents/mcp/servers.json')
  }

  let parsed
  try {
    parsed = JSON.parse(fs.readFileSync(canonicalPath, 'utf8'))
  } catch (error) {
    throw new Error(`invalid canonical MCP config (${error.message})`)
  }

  const servers = parsed?.servers
  if (!servers || typeof servers !== 'object' || Array.isArray(servers)) {
    throw new Error('canonical MCP config must contain object key "servers"')
  }
  return Object.keys(servers)
}

function enabledToolchains() {
  return resolveToolchains({
    requireProfileInCi: true,
  }).enabledSet
}

function loadConfigs() {
  const enabled = enabledToolchains()
  const entries = []

  for (const cfg of CONFIGS) {
    if (cfg.id !== 'root' && !enabled.has(cfg.id)) continue

    const absolutePath = path.join(ROOT, cfg.file)
    if (!fs.existsSync(absolutePath)) {
      if (cfg.id === 'root') continue
      throw new Error(`missing config file ${cfg.file}`)
    }

    const parsed = JSON.parse(fs.readFileSync(absolutePath, 'utf8'))
    const servers = getServers(parsed, cfg)
    if (!servers || typeof servers !== 'object' || Array.isArray(servers)) {
      throw new Error(`invalid MCP server map in ${cfg.file}`)
    }

    for (const [server, spec] of Object.entries(servers)) {
      if (SKIP_SERVERS.has(server)) continue
      const parsedSpec = parseServerSpec(spec, cfg)
      if (!parsedSpec) continue
      entries.push(
        resolveServerSpec({
          config: cfg.file,
          server,
          command: parsedSpec.command,
          args: parsedSpec.args,
          env: parsedSpec.env,
        }),
      )
    }
  }

  return entries
}

function comboKey(entry) {
  const env = Object.entries(entry.env)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${value}`)
    .join(';')
  return `${entry.command}\n${entry.args.join('\n')}\n${env}`
}

function classifyFailure(out, err) {
  const text = `${out}\n${err}`.toLowerCase()
  if (
    /\b404\b|not found|command not found|missing figma_api_key|please provide a database url|could not open input file|no such file|unknown option/i.test(
      text,
    )
  ) {
    return 'runtime error'
  }
  return 'exited early'
}

function runOne(entry) {
  return new Promise((resolve) => {
    const child = spawn(entry.command, entry.args, {
      cwd: ROOT,
      env: { ...process.env, ...entry.env },
      stdio: ['pipe', 'pipe', 'pipe'],
    })

    let out = ''
    let err = ''
    let timedOut = false
    let settled = false

    child.stdout.on('data', (chunk) => {
      if (out.length < 3000) out += String(chunk)
    })
    child.stderr.on('data', (chunk) => {
      if (err.length < 3000) err += String(chunk)
    })

    const finish = (result) => {
      if (settled) return
      settled = true
      resolve({ ...result, out: out.trim(), err: err.trim() })
    }

    child.on('error', (error) => {
      finish({ pass: false, reason: `spawn error: ${String(error)}` })
    })

    child.on('exit', (code, signal) => {
      if (settled) return

      const text = `${out}\n${err}`.toLowerCase()
      if (timedOut) {
        finish({ pass: true, reason: 'started (terminated after timeout)' })
        return
      }
      if (text.includes('running on stdio')) {
        finish({ pass: true, reason: 'started on stdio' })
        return
      }

      const failureKind = classifyFailure(out, err)
      finish({
        pass: false,
        reason: `${failureKind} (code=${code ?? 'null'}, signal=${signal ?? 'none'})`,
      })
    })

    setTimeout(() => {
      if (settled) return
      timedOut = true
      try {
        child.kill('SIGTERM')
      } catch {}
      setTimeout(() => {
        if (!settled) {
          try {
            child.kill('SIGKILL')
          } catch {}
        }
      }, 1000)
    }, TIMEOUT_MS)
  })
}

async function main() {
  const canonicalServers = loadCanonicalServerNames()
  if (canonicalServers.length === 0) {
    process.stdout.write('mcp-smoke: skipped (no canonical MCP servers configured)\n')
    return
  }

  const entries = loadConfigs()
  const combos = new Map()

  for (const entry of entries) {
    const key = comboKey(entry)
    if (!combos.has(key)) combos.set(key, { ...entry, refs: [] })
    combos.get(key).refs.push(`${entry.server}@${entry.config}`)
  }

  let passCount = 0
  let failCount = 0

  for (const combo of combos.values()) {
    const result = await runOne(combo)
    if (result.pass) {
      passCount += 1
      process.stdout.write(
        `mcp-smoke: pass ${combo.displayCommand} ${combo.displayArgs.join(' ')} :: ${result.reason}\n`,
      )
      continue
    }

    failCount += 1
    process.stderr.write(
      `mcp-smoke: fail ${combo.displayCommand} ${combo.displayArgs.join(' ')} :: ${result.reason}\n`,
    )
    const preview = (result.err || result.out || '')
      .split('\n')
      .slice(0, 3)
      .join(' | ')
    if (preview) process.stderr.write(`mcp-smoke: output ${preview}\n`)
    process.stderr.write(`mcp-smoke: used by ${combo.refs.join(', ')}\n`)

    if (FAIL_FAST) {
      process.exitCode = 1
      return
    }
  }

  process.stdout.write(
    `mcp-smoke: summary pass=${passCount} fail=${failCount} unique=${combos.size}\n`,
  )
  if (failCount > 0) process.exitCode = 1
}

main()
