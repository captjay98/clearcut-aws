import path from 'node:path'
import {
  ROOT,
  parseFrontmatter,
  resolveModel,
  resetDir,
  titleCase,
  writeUtf8,
} from './common.mjs'

export const meta = {
  name: 'pi',
  outputDirs: ['.pi/agents', '.pi/prompts'],
  mcpCapable: false,
}

// Frontmatter fields that pi-subagents understands.
const SUPPORTED_FIELDS = new Set([
  'description',
  'display_name',
  'thinking',
  'max_turns',
  'tools',
  'extensions',
  'exclude_extensions',
  'skills',
  'memory',
  'disallowed_tools',
  'isolation',
  'inherit_context',
  'run_in_background',
  'isolated',
  'enabled',
  'persist_session',
  'output_transcript',
  'session_dir',
  'prompt_mode',
])

function normalizeFrontmatterValue(value) {
  const trimmed = String(value ?? '').trim()
  if (trimmed === 'true') return true
  if (trimmed === 'false') return false
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1)
  }
  return trimmed
}

function parsePersonaFrontmatter(raw) {
  const parsed = parseFrontmatter(raw)
  const fm = parsed.frontmatter || {}
  const body = parsed.body || ''

  // parseFrontmatter skips nested object lines; parse the raw block ourselves
  // so we can convert the `tools:` object into a pi-subagents list.
  const blockMatch = raw.match(/^---\n([\s\S]*?)\n---\n/)
  if (!blockMatch) return { fm, body }

  const enhanced = { ...fm }
  const lines = blockMatch[1].split('\n')
  let currentKey = null

  for (const line of lines) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue

    if (/^\s/.test(line)) {
      if (currentKey === 'tools') {
        const m = line.match(/^\s+(\w+):\s*(.+)$/)
        if (m) {
          enhanced.tools = enhanced.tools || {}
          enhanced.tools[m[1]] = normalizeFrontmatterValue(m[2]) === true
        }
      }
      continue
    }

    const idx = line.indexOf(':')
    if (idx === -1) continue

    const key = line.slice(0, idx).trim()
    const value = line.slice(idx + 1).trim()
    if (value === '') {
      currentKey = key
      continue
    }

    currentKey = null
    enhanced[key] = normalizeFrontmatterValue(value)
  }

  return { fm: enhanced, body }
}

function serializeFrontmatter(frontmatter) {
  const lines = ['---']

  function formatKey(key) {
    if (key === '*' || /[:#]/.test(key)) return `"${key}"`
    return key
  }

  function write(key, value, indent = '') {
    if (value === undefined || value === null || value === '') return

    if (Array.isArray(value)) {
      if (value.length === 0) return
      lines.push(`${indent}${formatKey(key)}:`)
      for (const item of value) lines.push(`${indent}  - ${item}`)
    } else if (typeof value === 'object') {
      const entries = Object.entries(value)
      if (entries.length === 0) return
      lines.push(`${indent}${formatKey(key)}:`)
      for (const [k, v] of entries) {
        write(k, v, indent + '  ')
      }
    } else if (typeof value === 'boolean') {
      lines.push(`${indent}${formatKey(key)}: ${value}`)
    } else {
      lines.push(`${indent}${formatKey(key)}: ${value}`)
    }
  }

  for (const [key, value] of Object.entries(frontmatter)) {
    write(key, value)
  }

  lines.push('---')
  return lines.join('\n')
}

function toPiAgent(persona, canonical) {
  const { fm, body } = parsePersonaFrontmatter(persona.raw)

  const out = {}

  if (fm.description) {
    out.description = String(fm.description)
  }
  out.display_name = String(fm.display_name || titleCase(persona.id))

  const model = resolveModel(canonical, persona.id, 'pi', fm.model)
  if (model) {
    out.model = model
  }

  const thinking = fm.thinking || canonical?.models?.[persona.id]?.thinking
  if (thinking) out.thinking = String(thinking)

  if (canonical?.permissions?.agents?.[persona.id]) {
    out.permission = canonical.permissions.agents[persona.id]
  }
  if (fm.max_turns !== undefined && fm.max_turns !== '') {
    const n = Number(fm.max_turns)
    if (!Number.isNaN(n)) out.max_turns = n
  }

  if (fm.tools && typeof fm.tools === 'object') {
    const enabled = Array.isArray(fm.tools)
      ? fm.tools.filter((t) => typeof t === 'string')
      : Object.entries(fm.tools)
          .filter(([, v]) => v === true)
          .map(([k]) => k)
    if (enabled.length) {
      out.tools = enabled.join(', ')
    }
  } else if (typeof fm.tools === 'string' && fm.tools.trim() !== '') {
    out.tools = fm.tools.trim()
  }

  if (fm.skills) {
    out.skills = Array.isArray(fm.skills) ? fm.skills.join(', ') : String(fm.skills)
  }

  for (const key of SUPPORTED_FIELDS) {
    if (out[key] !== undefined) continue
    const val = fm[key]
    if (val === undefined || val === null || val === '') continue
    if (typeof val === 'boolean') {
      out[key] = val
    } else {
      out[key] = String(val)
    }
  }

  return `${serializeFrontmatter(out)}\n${body}`
}

function toPiPrompt(command) {
  const { frontmatter, body } = parseFrontmatter(command.raw)
  const out = {}
  if (frontmatter.description) out.description = String(frontmatter.description)
  if (frontmatter.argument_hint) out.argument_hint = String(frontmatter.argument_hint)
  if (Object.keys(out).length === 0) out.description = titleCase(command.id)

  return `${serializeFrontmatter(out)}\n${body}`
}

export function renderPi(canonical) {
  const warnings = []
  const agentDir = path.join(ROOT, '.pi', 'agents')
  resetDir(agentDir)

  for (const persona of canonical.personas) {
    writeUtf8(path.join(agentDir, `${persona.id}.md`), toPiAgent(persona, canonical))
  }

  const promptDir = path.join(ROOT, '.pi', 'prompts')
  resetDir(promptDir)

  for (const command of canonical.commands ?? []) {
    writeUtf8(path.join(promptDir, `${command.id}.md`), toPiPrompt(command))
  }

  return { warnings }
}
