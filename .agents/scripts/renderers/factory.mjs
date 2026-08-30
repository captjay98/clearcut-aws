import path from 'node:path'
import {
  ROOT,
  copySkills,
  hooksForTool,
  renderMcpConfig,
  renderGuide,
  removeIfExists,
  resolveModelMap,
  titleCase,
  writeMarkdownSet,
  writeUtf8,
} from './common.mjs'

export const meta = {
  name: 'factory',
  outputDirs: ['.factory/droids', '.factory/commands', '.factory/skills', '.factory/rules', '.factory/memories.md', '.factory/settings.json', '.factory/mcp.json', '.factory/FACTORY.md'],
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
      const message = `factory: unsupported hook event '${hook.event}' for hook '${hook.id}'`
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

export function renderFactory(canonical, options = {}) {
  const strict = Boolean(options.strict)
  const prettyName = titleCase(options.projectName || 'Project')
  const warnings = []

  writeMarkdownSet(canonical.personas, path.join(ROOT, '.factory', 'droids'), { modelMap: resolveModelMap(canonical, 'factory') })
  writeMarkdownSet(canonical.commands, path.join(ROOT, '.factory', 'commands'))
  copySkills(canonical.skills, path.join(ROOT, '.factory', 'skills'))
  writeMarkdownSet(canonical.rules, path.join(ROOT, '.factory', 'rules'))

  writeUtf8(path.join(ROOT, '.factory', 'memories.md'), canonical.memory)

  const mapped = mapHooks(hooksForTool(canonical.hooks.hooks, 'factory'), { strict })
  warnings.push(...mapped.warnings)
  writeUtf8(
    path.join(ROOT, '.factory', 'settings.json'),
    JSON.stringify({ hooks: mapped.hooks }, null, 2) + '\n',
  )

  removeIfExists(path.join(ROOT, '.factory', 'commands.json'))
  removeIfExists(path.join(ROOT, '.factory', 'hooks.json'))

  writeUtf8(
    path.join(ROOT, '.factory', 'FACTORY.md'),
    renderGuide({
      title: `${prettyName} - Factory Context`,
      subtitle: 'Generated Factory guide for droids, commands, skills, rules, memory, and hooks.',
      toolName: 'Factory CLI',
      canonical,
    }),
  )

  if (canonical.mcpServers) {
    const mcpServers = renderMcpConfig(canonical.mcpServers, 'factory')
    if (mcpServers) {
      writeUtf8(
        path.join(ROOT, '.factory', 'mcp.json'),
        JSON.stringify({ mcpServers }, null, 2) + '\n',
      )
    }
  }

  return { warnings }
}
