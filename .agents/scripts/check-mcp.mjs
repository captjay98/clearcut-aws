import fs from 'node:fs'
import path from 'node:path'
import { resolveToolchains } from './config.mjs'

const ROOT = process.cwd()

const CONFIGS = [
  {
    id: 'root',
    file: '.mcp.json',
    allowedTopLevel: new Set(['mcpServers']),
    format: 'standard',
  },
  {
    id: 'kiro',
    file: '.kiro/settings/mcp.json',
    allowedTopLevel: new Set(['mcpServers']),
    format: 'standard',
  },
  {
    id: 'gemini',
    file: '.gemini/settings.json',
    allowedTopLevel: new Set([
      'general',
      'model',
      'context',
      'tools',
      'privacy',
      'experimental',
      'mcpServers',
    ]),
    format: 'standard',
  },
  {
    id: 'factory',
    file: '.factory/mcp.json',
    allowedTopLevel: new Set(['mcpServers']),
    format: 'standard',
  },
  {
    id: 'claude',
    file: '.claude/settings.json',
    allowedTopLevel: new Set(['hooks', 'mcpServers']),
    format: 'standard',
  },
  {
    id: 'opencode',
    file: 'opencode.json',
    allowedTopLevel: new Set(['$schema', 'instructions', 'mcp']),
    format: 'opencode',
  },
]

const PINNED = {
  figma: 'figma-developer-mcp@0.6.4',
  filesystem: '@modelcontextprotocol/server-filesystem@2026.1.14',
  postgres: '@modelcontextprotocol/server-postgres@0.6.2',
  neon: '@neondatabase/mcp-server-neon@0.6.5',
  git: 'mcp-server-git==2026.1.14',
}

let hasError = false

function fail(message) {
  hasError = true
  process.stderr.write(`${message}\n`)
}

function hasHardcodedSecret(raw) {
  if (/figd_[A-Za-z0-9_]+/.test(raw)) return true

  const sensitiveEnvPattern =
    /"([A-Z0-9_]*(?:API|TOKEN|SECRET|KEY)[A-Z0-9_]*)"\s*:\s*"([^\"]+)"/g
  for (const match of raw.matchAll(sensitiveEnvPattern)) {
    const value = String(match[2] ?? '').trim()
    if (!value) continue
    if (value.startsWith('${') && value.endsWith('}')) continue
    if (value.toLowerCase() === 'changeme') continue
    return true
  }

  return false
}

function readJson(relativePath) {
  const absolutePath = path.join(ROOT, relativePath)
  if (!fs.existsSync(absolutePath)) {
    fail(`check-mcp: missing file ${relativePath}`)
    return null
  }

  const raw = fs.readFileSync(absolutePath, 'utf8')
  if (hasHardcodedSecret(raw)) {
    fail(`check-mcp: hardcoded secret detected in ${relativePath}`)
  }

  try {
    return { value: JSON.parse(raw), raw, relativePath }
  } catch (error) {
    fail(`check-mcp: invalid json ${relativePath} (${error.message})`)
    return null
  }
}

function assertString(value, label) {
  if (typeof value !== 'string' || !value.trim()) {
    fail(`check-mcp: ${label} must be a non-empty string`)
    return false
  }
  return true
}

function assertStringArray(value, label) {
  if (
    !Array.isArray(value) ||
    value.length === 0 ||
    value.some((item) => typeof item !== 'string')
  ) {
    fail(`check-mcp: ${label} must be a non-empty string array`)
    return false
  }
  return true
}

function validateStandardServerShape(serverName, serverConfig, cfg) {
  if (
    !serverConfig ||
    typeof serverConfig !== 'object' ||
    Array.isArray(serverConfig)
  ) {
    fail(`check-mcp: ${cfg.id}.${serverName} must be an object`)
    return null
  }

  const allowedKeys = new Set([
    'command',
    'args',
    'env',
    'disabled',
    'autoApprove',
    'timeout',
  ])
  for (const key of Object.keys(serverConfig)) {
    if (!allowedKeys.has(key)) {
      fail(
        `check-mcp: ${cfg.id}.${serverName} contains unsupported key '${key}'`,
      )
    }
  }

  if (!assertString(serverConfig.command, `${cfg.id}.${serverName}.command`))
    return null
  if (!assertStringArray(serverConfig.args, `${cfg.id}.${serverName}.args`))
    return null

  if (serverConfig.env !== undefined) {
    if (
      !serverConfig.env ||
      typeof serverConfig.env !== 'object' ||
      Array.isArray(serverConfig.env)
    ) {
      fail(`check-mcp: ${cfg.id}.${serverName}.env must be an object`)
    } else {
      for (const [key, value] of Object.entries(serverConfig.env)) {
        if (typeof value !== 'string') {
          fail(`check-mcp: ${cfg.id}.${serverName}.env.${key} must be a string`)
        }
      }
    }
  }

  if (
    serverConfig.disabled !== undefined &&
    typeof serverConfig.disabled !== 'boolean'
  ) {
    fail(`check-mcp: ${cfg.id}.${serverName}.disabled must be boolean`)
  }

  if (
    serverConfig.timeout !== undefined &&
    !Number.isFinite(serverConfig.timeout)
  ) {
    fail(`check-mcp: ${cfg.id}.${serverName}.timeout must be numeric`)
  }

  if (serverConfig.autoApprove !== undefined) {
    if (
      !Array.isArray(serverConfig.autoApprove) ||
      serverConfig.autoApprove.some((value) => typeof value !== 'string')
    ) {
      fail(
        `check-mcp: ${cfg.id}.${serverName}.autoApprove must be a string array`,
      )
    }
  }

  return {
    command: serverConfig.command,
    args: serverConfig.args,
    env: serverConfig.env ?? {},
    disabled: serverConfig.disabled ?? false,
  }
}

function validateOpenCodeServerShape(serverName, serverConfig, cfg) {
  if (
    !serverConfig ||
    typeof serverConfig !== 'object' ||
    Array.isArray(serverConfig)
  ) {
    fail(`check-mcp: ${cfg.id}.${serverName} must be an object`)
    return null
  }

  const allowedKeys = new Set([
    'type',
    'command',
    'enabled',
    'environment',
    'cwd',
    'timeout',
  ])
  for (const key of Object.keys(serverConfig)) {
    if (!allowedKeys.has(key)) {
      fail(
        `check-mcp: ${cfg.id}.${serverName} contains unsupported key '${key}'`,
      )
    }
  }

  if (
    !Array.isArray(serverConfig.command) ||
    serverConfig.command.length === 0 ||
    serverConfig.command.some((value) => typeof value !== 'string')
  ) {
    fail(`check-mcp: ${cfg.id}.${serverName}.command must be a non-empty string array`)
    return null
  }

  if (
    serverConfig.environment !== undefined &&
    (!serverConfig.environment ||
      typeof serverConfig.environment !== 'object' ||
      Array.isArray(serverConfig.environment))
  ) {
    fail(`check-mcp: ${cfg.id}.${serverName}.environment must be an object`)
  }

  if (
    serverConfig.environment &&
    typeof serverConfig.environment === 'object' &&
    !Array.isArray(serverConfig.environment)
  ) {
    for (const [key, value] of Object.entries(serverConfig.environment)) {
      if (typeof value !== 'string') {
        fail(`check-mcp: ${cfg.id}.${serverName}.environment.${key} must be a string`)
      }
    }
  }

  if (
    serverConfig.enabled !== undefined &&
    typeof serverConfig.enabled !== 'boolean'
  ) {
    fail(`check-mcp: ${cfg.id}.${serverName}.enabled must be boolean`)
  }

  return {
    command: serverConfig.command[0],
    args: serverConfig.command.slice(1),
    env: serverConfig.environment ?? {},
    disabled: serverConfig.enabled === false,
  }
}

function assertBunxPinned(serverName, serverConfig, cfgId, pinnedPackage) {
  if (serverConfig.command !== 'bunx') {
    fail(`check-mcp: ${cfgId}.${serverName}.command must be bunx`)
  }
  if (serverConfig.args?.[0] !== pinnedPackage) {
    fail(`check-mcp: ${cfgId}.${serverName}.args[0] must be '${pinnedPackage}'`)
  }
}

function validatePinnedVersions(cfgId, servers) {
  if (servers.figma) {
    if (servers.figma.command !== 'bash') {
      fail(`check-mcp: ${cfgId}.figma.command must be bash`)
    }
    if (servers.figma.args?.[0] !== '-lc') {
      fail(`check-mcp: ${cfgId}.figma.args[0] must be -lc`)
    }
    const script = String(servers.figma.args?.[1] ?? '')
    if (!script.includes(PINNED.figma)) {
      fail(`check-mcp: ${cfgId}.figma must pin ${PINNED.figma}`)
    }
    if (!script.includes('FIGMA_API_KEY')) {
      fail(`check-mcp: ${cfgId}.figma must read FIGMA_API_KEY`)
    }
    if (script.includes('figd_')) {
      fail(`check-mcp: ${cfgId}.figma script contains hardcoded figma key`)
    }
  }

  if (servers.filesystem) {
    assertBunxPinned('filesystem', servers.filesystem, cfgId, PINNED.filesystem)
    if (servers.filesystem.args?.[1] !== ROOT) {
      fail(`check-mcp: ${cfgId}.filesystem.args[1] must be ${ROOT}`)
    }
  }

  if (servers.postgres) {
    assertBunxPinned('postgres', servers.postgres, cfgId, PINNED.postgres)
    const connection = String(servers.postgres.args?.[1] ?? '')
    if (!connection.startsWith('postgresql://')) {
      fail(
        `check-mcp: ${cfgId}.postgres must pass postgresql:// connection string as args[1]`,
      )
    }
  }

  if (servers.git) {
    if (servers.git.command !== 'uvx') {
      fail(`check-mcp: ${cfgId}.git.command must be uvx`)
    }
    const fromIndex = servers.git.args?.indexOf('--from') ?? -1
    if (fromIndex < 0 || servers.git.args[fromIndex + 1] !== PINNED.git) {
      fail(`check-mcp: ${cfgId}.git must pin '${PINNED.git}' via --from`)
    }
    const repositoryIndex = servers.git.args?.indexOf('--repository') ?? -1
    if (repositoryIndex < 0 || servers.git.args[repositoryIndex + 1] !== ROOT) {
      fail(`check-mcp: ${cfgId}.git must set --repository ${ROOT}`)
    }
  }

  if (servers['laravel-boost']) {
    if (servers['laravel-boost'].command !== 'php') {
      fail(`check-mcp: ${cfgId}.laravel-boost.command must be php`)
    }
    if (servers['laravel-boost'].args?.[0] !== './backend/artisan') {
      fail(`check-mcp: ${cfgId}.laravel-boost.args[0] must be ./backend/artisan`)
    }
    if (servers['laravel-boost'].args?.[1] !== 'boost:mcp') {
      fail(`check-mcp: ${cfgId}.laravel-boost.args[1] must be boost:mcp`)
    }
  }

  if (servers.neon) {
    assertBunxPinned('neon', servers.neon, cfgId, PINNED.neon)
    if (servers.neon.args?.[1] !== 'start') {
      fail(`check-mcp: ${cfgId}.neon.args[1] must be 'start'`)
    }
    if (servers.neon.args?.[2] !== '${NEON_API_KEY}') {
      fail(`check-mcp: ${cfgId}.neon.args[2] must be '\${NEON_API_KEY}'`)
    }
  }
}

function validateConfigObject(cfg, parsed) {
  const topLevelKeys = Object.keys(parsed.value)
  for (const key of topLevelKeys) {
    if (!cfg.allowedTopLevel.has(key)) {
      fail(`check-mcp: ${cfg.id} has unsupported top-level key '${key}'`)
    }
  }

  const rawServers =
    cfg.format === 'opencode' ? parsed.value.mcp : parsed.value.mcpServers
  if (!rawServers || typeof rawServers !== 'object' || Array.isArray(rawServers)) {
    fail(`check-mcp: ${cfg.id} missing object ${cfg.format === 'opencode' ? 'mcp' : 'mcpServers'}`)
    return null
  }

  const normalized = {}
  for (const [serverName, serverConfig] of Object.entries(rawServers)) {
    normalized[serverName] =
      cfg.format === 'opencode'
        ? validateOpenCodeServerShape(serverName, serverConfig, cfg)
        : validateStandardServerShape(serverName, serverConfig, cfg)
  }

  validatePinnedVersions(cfg.id, normalized)
  return new Set(Object.keys(normalized))
}

function setsEqual(left, right) {
  if (left.size !== right.size) return false
  for (const item of left) {
    if (!right.has(item)) return false
  }
  return true
}

function readCanonicalExpectedServers() {
  const canonicalPath = path.join(ROOT, '.agents', 'mcp', 'servers.json')
  if (!fs.existsSync(canonicalPath)) {
    fail('check-mcp: missing canonical .agents/mcp/servers.json')
    return null
  }

  let parsed
  try {
    parsed = JSON.parse(fs.readFileSync(canonicalPath, 'utf8'))
  } catch (error) {
    fail(`check-mcp: invalid json .agents/mcp/servers.json (${error.message})`)
    return null
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    fail('check-mcp: .agents/mcp/servers.json must be an object')
    return null
  }

  if (!parsed.servers || typeof parsed.servers !== 'object' || Array.isArray(parsed.servers)) {
    fail('check-mcp: .agents/mcp/servers.json must contain object key "servers"')
    return null
  }

  return new Set(Object.keys(parsed.servers))
}

function enabledConfigs() {
  const resolution = resolveToolchains({
    includeLocalOverride: false,
    requireProfileInCi: true,
  })
  const enabled = resolution.enabledSet
  const byId = new Map(CONFIGS.map((cfg) => [cfg.id, cfg]))

  const out = []
  for (const toolchain of ['claude', 'gemini', 'kiro', 'factory', 'opencode']) {
    if (enabled.has(toolchain) && byId.has(toolchain)) {
      out.push(byId.get(toolchain))
    }
  }

  const rootCfg = byId.get('root')
  if (rootCfg) {
    const rootPath = path.join(ROOT, rootCfg.file)
    if (fs.existsSync(rootPath)) out.unshift(rootCfg)
  }

  return out
}

function main() {
  const expectedServers = readCanonicalExpectedServers()
  if (!expectedServers) {
    process.exitCode = 1
    return
  }

  if (expectedServers.size === 0) {
    process.stdout.write('agents-check-mcp: skipped (no canonical MCP servers configured)\n')
    return
  }

  const activeConfigs = enabledConfigs()
  if (activeConfigs.length === 0) {
    process.stdout.write('agents-check-mcp: skipped (no mcp-capable toolchains enabled)\n')
    return
  }

  const parsedById = new Map()

  for (const cfg of activeConfigs) {
    const parsed = readJson(cfg.file)
    if (!parsed) continue
    parsedById.set(cfg.id, { cfg, parsed })
  }

  if (parsedById.size !== activeConfigs.length) {
    process.exitCode = 1
    return
  }

  const referenceConfig = parsedById.values().next().value
  const referenceServers = validateConfigObject(
    referenceConfig.cfg,
    referenceConfig.parsed,
  )
  if (!referenceServers) {
    process.exitCode = 1
    return
  }

  if (!setsEqual(referenceServers, expectedServers)) {
    const expectedNames = [...expectedServers].sort().join(', ')
    const actualNames = [...referenceServers].sort().join(', ')
    fail(
      `check-mcp: server set mismatch expected=[${expectedNames}] actual=[${actualNames}]`,
    )
  }

  for (const { cfg, parsed } of parsedById.values()) {
    const current = validateConfigObject(cfg, parsed)
    if (!current) continue
    if (!setsEqual(referenceServers, current)) {
      const refNames = [...referenceServers].sort().join(', ')
      const currentNames = [...current].sort().join(', ')
      fail(
        `check-mcp: server-set drift in ${cfg.id}. expected=[${refNames}] actual=[${currentNames}]`,
      )
    }
  }

  if (hasError) {
    process.exitCode = 1
    return
  }

  process.stdout.write('agents-check-mcp: ok\n')
}

main()
