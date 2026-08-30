import fs from 'node:fs'
import path from 'node:path'
import {
  ROOT,
  copySkills,
  ensureDir,
  hooksForTool,
  removeIfExists,
  renderMcpConfig,
  resetDir,
  resolveModel,
  titleCase,
  writeMarkdownSet,
  writeUtf8,
} from './common.mjs'

export const meta = {
  name: 'kiro',
  outputDirs: [
    '.kiro/agents',
    '.kiro/prompts',
    '.kiro/skills',
    '.kiro/steering',
    '.kiro/hooks',
    '.kiro/settings/hooks.json',
    '.kiro/settings/mcp.json',
    '.kiro/README.md',
  ],
  mcpCapable: true,
}

const HOOK_EVENT_MAP = {
  session_start: 'SessionStart',
  before_tool: 'PreToolUse',
  after_tool: 'PostToolUse',
  prompt_submit: 'UserPromptSubmit',
  session_end: 'Stop',
}

const KIRO_MATCHER_MAP = new Map([
  ['Bash', 'execute_bash'],
  ['Edit|Write', 'str_replace|fs_write'],
  ['Read', 'read_file'],
])

export function renderKiroAgentMarkdown(persona, { tools, resources, model }) {
  const description = persona.description || ''
  const body = String(persona.body ?? persona.raw ?? '').trim()

  const frontmatter = [
    '---',
    `name: ${persona.id}`,
    `description: ${JSON.stringify(description)}`,
    `tools: ${JSON.stringify(tools)}`,
    `model: ${model}`,
    `includeMcpJson: true`,
    `resources: ${JSON.stringify(resources)}`,
    '---',
    '',
  ].join('\n')

  return `${frontmatter}${body}\n`
}

function renderKiroManualHook(command, projectName) {
  const description = command.frontmatter?.description || `${projectName} ${command.id} workflow`
  const prompt = String(command.body ?? command.raw ?? '').trim()
  const hook = {
    name: command.id,
    description,
    when: { type: 'userTriggered' },
    then: { type: 'askAgent', prompt },
  }
  return JSON.stringify(hook, null, 2) + '\n'
}

function mapKiroMatcher(matcher) {
  return KIRO_MATCHER_MAP.get(matcher) ?? matcher
}

function assertSafeHookId(id, seen) {
  if (typeof id !== 'string' || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) {
    throw new Error(`kiro: unsafe hook id '${String(id)}'`)
  }
  if (seen.has(id)) throw new Error(`kiro: duplicate hook id '${id}'`)
  seen.add(id)
}

function mapHooksV3(hooks, { strict }) {
  const warnings = []
  const files = []
  const seen = new Set()

  for (const hook of hooks) {
    assertSafeHookId(hook.id, seen)
    const trigger = HOOK_EVENT_MAP[hook.event]
    if (!trigger) {
      const message = `kiro: unsupported hook event '${hook.event}' for hook '${hook.id}'`
      if (strict) throw new Error(message)
      warnings.push(message)
      continue
    }

    const entry = {
      name: hook.id,
      trigger,
      action: {
        type: 'command',
        command: `bun .agents/scripts/kiro-hook-adapter.mjs ${JSON.stringify(hook.id)}`,
      },
    }

    if (trigger === 'PreToolUse' || trigger === 'PostToolUse') {
      if (hook.matcher) entry.matcher = mapKiroMatcher(hook.matcher)
    }

    files.push({
      id: hook.id,
      content: JSON.stringify({ version: 'v1', hooks: [entry] }, null, 2) + '\n',
    })
  }

  return { files, warnings }
}

function allowsWholeCategory(value) {
  if (value === undefined) return true
  return typeof value === 'string' && value.toLowerCase() === 'allow'
}

function resolveKiroTools(canonical, profile, personaId) {
  // Always grant all built-in tools. Safety is controlled by permissions.yaml,
  // not by restricting the tools array. This gives agents full autonomy while
  // the deny-overrides permission system governs what actions require prompting.
  const tools = ['@builtin']

  // Append explicit MCP server references so agents see project-specific
  // servers even when includeMcpJson is not set.
  const mcpNames = [
    ...(Array.isArray(profile?.policy?.mcp_base) ? profile.policy.mcp_base : []),
    ...(Array.isArray(profile?.policy?.mcp_agents?.[personaId])
      ? profile.policy.mcp_agents[personaId]
      : []),
  ]
  for (const name of new Set(mcpNames.map(String).filter(Boolean))) {
    const server = canonical.mcpServers?.servers?.[name]
    if (server?.disabled === true) continue
    tools.push(`@${name}`)
  }

  return tools
}

function cleanupGeneratedHooks(hooksDir, expectedNames) {
  for (const entry of fs.readdirSync(hooksDir)) {
    if (expectedNames.has(entry)) continue
    const target = path.join(hooksDir, entry)

    if (entry.endsWith('.kiro.hook')) {
      fs.rmSync(target, { force: true })
      continue
    }

    if (!entry.endsWith('.json')) continue
    try {
      const parsed = JSON.parse(fs.readFileSync(target, 'utf8'))
      const generated = parsed.hooks?.some((hook) =>
        String(hook?.action?.command ?? '').includes('.agents/scripts/kiro-hook-adapter.mjs'),
      )
      if (generated) fs.rmSync(target, { force: true })
    } catch {
      // Unknown or invalid JSON is project-owned; verification can report it
      // separately without the renderer deleting user data.
    }
  }
}

export function renderKiro(canonical, options = {}) {
  const strict = Boolean(options.strict)
  const projectName = options.projectName || 'Project'
  const prettyName = titleCase(projectName)
  const profile = options.profile || null
  const warnings = []

  const subagents = canonical.personas.filter((persona) => persona.mode === 'subagent')
  const agentDir = path.join(ROOT, '.kiro', 'agents')
  resetDir(agentDir)

  for (const persona of subagents) {
    const tools = resolveKiroTools(canonical, profile, persona.id)
    const resources = ['file://AGENTS.md', 'skill://.kiro/skills/**/SKILL.md']
    const model = resolveModel(canonical, persona.id, 'kiro', persona.model) || 'auto'

    writeUtf8(
      path.join(agentDir, `${persona.id}.md`),
      renderKiroAgentMarkdown(persona, { tools, resources, model }),
    )
  }

  writeMarkdownSet(canonical.commands, path.join(ROOT, '.kiro', 'prompts'))
  copySkills(canonical.skills, path.join(ROOT, '.kiro', 'skills'))
  writeMarkdownSet(canonical.steering, path.join(ROOT, '.kiro', 'steering'))

  const hooksDir = path.join(ROOT, '.kiro', 'hooks')
  ensureDir(hooksDir)
  const mapped = mapHooksV3(hooksForTool(canonical.hooks.hooks, 'kiro'), { strict })
  warnings.push(...mapped.warnings)

  const expectedHookNames = new Set([
    ...canonical.commands.map((command) => `${command.id}.kiro.hook`),
    ...mapped.files.map(({ id }) => `${id}.json`),
  ])
  cleanupGeneratedHooks(hooksDir, expectedHookNames)

  for (const command of canonical.commands) {
    writeUtf8(path.join(hooksDir, `${command.id}.kiro.hook`), renderKiroManualHook(command, prettyName))
  }
  for (const { id, content } of mapped.files) {
    writeUtf8(path.join(hooksDir, `${id}.json`), content)
  }

  removeIfExists(path.join(ROOT, '.kiro', 'settings', 'hooks.json'))
  removeIfExists(path.join(ROOT, '.kiro', 'README.md'))

  const mcpPath = path.join(ROOT, '.kiro', 'settings', 'mcp.json')
  const hasDefinedServers = canonical.mcpServers?.servers && Object.keys(canonical.mcpServers.servers).length > 0
  if (hasDefinedServers) {
    const mcpServers = renderMcpConfig(canonical.mcpServers, 'kiro')
    if (mcpServers) {
      writeUtf8(mcpPath, JSON.stringify({ mcpServers }, null, 2) + '\n')
    }
  } else {
    removeIfExists(mcpPath)
  }

  return { warnings }
}
