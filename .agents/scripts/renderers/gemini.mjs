import fs from 'node:fs'
import path from 'node:path'
import {
  ROOT,
  hooksForTool,
  readUtf8,
  removeIfExists,
  renderMcpConfig,
  renderGeminiCommandToml,
  renderGuide,
  resetDir,
  resolveModel,
  titleCase,
  writeMarkdownSet,
  writeUtf8,
} from './common.mjs'

export const meta = {
  name: 'gemini',
  outputDirs: ['.gemini/agents', '.gemini/commands', '.gemini/GEMINI.md', '.gemini/hooks.json', '.gemini/settings.json'],
  mcpCapable: true,
}

const HOOK_EVENT_MAP = {
  session_start: 'sessionStart',
  before_tool: 'preToolCall',
  after_tool: 'postToolCall',
  session_end: 'sessionEnd',
}

function mapHooks(hooks, { strict }) {
  const warnings = []
  const mapped = {
    sessionStart: [],
    preToolCall: [],
    postToolCall: [],
    sessionEnd: [],
  }

  for (const hook of hooks) {
    const target = HOOK_EVENT_MAP[hook.event]
    if (!target) {
      const message = `gemini: unsupported hook event '${hook.event}' for hook '${hook.id}'`
      if (strict) throw new Error(message)
      warnings.push(message)
      continue
    }

    mapped[target].push({ matcher: hook.matcher, command: hook.command })
  }

  const compact = {}
  for (const [key, value] of Object.entries(mapped)) {
    if (value.length) compact[key] = value
  }

  return { hooks: compact, warnings }
}

function toGeminiFrontmatter(persona, canonical) {
  const fm = persona.frontmatter || {}
  const gemini = { name: persona.id, description: String(fm.description || '') }
  gemini.kind = 'local'
  // tools must be an array of tool name strings
  if (fm.tools && typeof fm.tools === 'object' && !Array.isArray(fm.tools)) {
    gemini.tools = Object.keys(fm.tools).filter(k => fm.tools[k])
  } else if (Array.isArray(fm.tools)) {
    gemini.tools = fm.tools
  } else {
    gemini.tools = ['*']
  }
  const model = resolveModel(canonical, persona.id, 'gemini', fm.model)
  if (model) gemini.model = model
  // Rebuild markdown with Gemini-compatible frontmatter
  const yamlLines = Object.entries(gemini).map(([k, v]) => {
    if (Array.isArray(v)) return `${k}:\n${v.map(i => `  - "${i}"`).join('\n')}`
    return `${k}: ${v}`
  })
  return `---\n${yamlLines.join('\n')}\n---\n${persona.body || ''}`
}

export function renderGemini(canonical, options = {}) {
  const strict = Boolean(options.strict)
  const prettyName = titleCase(options.projectName || 'Project')
  const warnings = []

  const agentDir = path.join(ROOT, '.gemini', 'agents')
  resetDir(agentDir)
  for (const persona of canonical.personas) {
    writeUtf8(path.join(agentDir, `${persona.id}.md`), toGeminiFrontmatter(persona, canonical))
  }

  const commandDir = path.join(ROOT, '.gemini', 'commands')
  resetDir(commandDir)
  for (const command of canonical.commands) {
    const description = String(command.description || command.frontmatter.description || '')
    writeUtf8(
      path.join(commandDir, `${command.id}.toml`),
      renderGeminiCommandToml({ description, prompt: command.raw }),
    )
  }

  removeIfExists(path.join(ROOT, '.gemini', 'skills'))

  const mapped = mapHooks(hooksForTool(canonical.hooks.hooks, 'gemini'), { strict })
  warnings.push(...mapped.warnings)

  writeUtf8(
    path.join(ROOT, '.gemini', 'hooks.json'),
    JSON.stringify({ hooks: mapped.hooks }, null, 2) + '\n',
  )

  writeUtf8(
    path.join(ROOT, '.gemini', 'GEMINI.md'),
    renderGuide({
      title: `${prettyName} - Gemini Context`,
      subtitle: 'Generated Gemini guide for agents, commands, skills, and hooks.',
      toolName: 'Gemini CLI',
      canonical,
    }),
  )

  if (canonical.mcpServers) {
    const mcpServers = renderMcpConfig(canonical.mcpServers, 'gemini')
    if (mcpServers) {
      const settingsPath = path.join(ROOT, '.gemini', 'settings.json')
      let settings = {}
      if (fs.existsSync(settingsPath)) {
        settings = JSON.parse(readUtf8(settingsPath))
      }
      settings.experimental = { subagents: true, ...(settings.experimental ?? {}) }
      settings.mcpServers = mcpServers
      writeUtf8(settingsPath, JSON.stringify(settings, null, 2) + '\n')
    }
  }

  return { warnings }
}
