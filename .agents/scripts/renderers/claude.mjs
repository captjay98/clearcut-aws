import fs from 'node:fs'
import path from 'node:path'
import {
  ROOT,
  copySkills,
  hooksForTool,
  readUtf8,
  renderMcpConfig,
  renderGuide,
  resolveModelMap,
  titleCase,
  writeMarkdownSet,
  writeUtf8,
} from './common.mjs'

export const meta = {
  name: 'claude',
  outputDirs: ['.claude/agents', '.claude/commands', '.claude/skills', '.claude/CLAUDE.md', '.claude/settings.json'],
  mcpCapable: true,
}

const HOOK_EVENT_MAP = {
  session_start: 'SessionStart',
  before_tool: 'PreToolUse',
  after_tool: 'PostToolUse',
}

function mapHooks(hooks, { strict }) {
  const warnings = []
  const mapped = {
    SessionStart: [],
    PreToolUse: [],
    PostToolUse: [],
  }

  for (const hook of hooks) {
    const target = HOOK_EVENT_MAP[hook.event]
    if (!target) {
      const message = `claude: unsupported hook event '${hook.event}' for hook '${hook.id}'`
      if (strict) throw new Error(message)
      warnings.push(message)
      continue
    }

    mapped[target].push({
      matcher: hook.matcher,
      hooks: [{ type: 'command', command: hook.command }],
    })
  }

  const compact = {}
  for (const [key, value] of Object.entries(mapped)) {
    if (value.length) compact[key] = value
  }

  return { hooks: compact, warnings }
}

export function renderClaude(canonical, options = {}) {
  const strict = Boolean(options.strict)
  const prettyName = titleCase(options.projectName || 'Project')
  const warnings = []

  // Preserve settings.local.json (user-managed tool permissions)
  const localSettingsPath = path.join(ROOT, '.claude', 'settings.local.json')
  const savedLocalSettings = fs.existsSync(localSettingsPath) ? readUtf8(localSettingsPath) : null

  writeMarkdownSet(canonical.personas, path.join(ROOT, '.claude', 'agents'), { modelMap: resolveModelMap(canonical, 'claude') })
  writeMarkdownSet(canonical.commands, path.join(ROOT, '.claude', 'commands'))
  copySkills(canonical.skills, path.join(ROOT, '.claude', 'skills'))

  if (savedLocalSettings !== null) {
    writeUtf8(localSettingsPath, savedLocalSettings)
  }

  const mapped = mapHooks(hooksForTool(canonical.hooks.hooks, 'claude'), { strict })
  warnings.push(...mapped.warnings)

  const settingsPath = path.join(ROOT, '.claude', 'settings.json')
  let settings = {}
  if (fs.existsSync(settingsPath)) {
    settings = JSON.parse(readUtf8(settingsPath))
  }

  settings.hooks = mapped.hooks

  if (canonical.mcpServers) {
    const mcpServers = renderMcpConfig(canonical.mcpServers, 'claude')
    if (mcpServers) {
      settings.mcpServers = mcpServers
    }
  }

  writeUtf8(settingsPath, JSON.stringify(settings, null, 2) + '\n')

  writeUtf8(
    path.join(ROOT, '.claude', 'CLAUDE.md'),
    renderGuide({
      title: `${prettyName} - Claude Context`,
      subtitle: 'Generated Claude guide for agents, commands, skills, and hooks.',
      toolName: 'Claude Code',
      canonical,
    }),
  )

  return { warnings }
}
