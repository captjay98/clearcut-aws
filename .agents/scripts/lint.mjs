import fs from 'node:fs'
import path from 'node:path'
import {
  AGENTS_ROOT,
  listDirectories,
  listMarkdownFiles,
  loadCanonical,
  parseFrontmatter,
  parseHooks,
  readUtf8,
  relativeFromRoot,
  walkFiles,
} from './renderers/common.mjs'
import { loadDriftPolicy, validateProfileAndPolicy } from './config.mjs'

let hasError = false
let warningCount = 0

function isTemplateId(value) {
  return String(value || '').startsWith('_')
}

function isTemplateMarkdownFile(filePath) {
  return path.basename(filePath).startsWith('_')
}

function error(message) {
  hasError = true
  process.stderr.write(`${message}\n`)
}

function warn(message) {
  warningCount += 1
  process.stdout.write(`warn: ${message}\n`)
}

function requireFrontmatter(filePath, requiredKeys) {
  const parsed = parseFrontmatter(readUtf8(filePath))
  if (!parsed.hasFrontmatter) {
    error(`lint: missing frontmatter -> ${relativeFromRoot(filePath)}`)
    return
  }

  for (const key of requiredKeys) {
    const value = parsed.frontmatter[key]
    if (value === undefined || String(value).trim() === '') {
      error(`lint: missing required frontmatter key '${key}' -> ${relativeFromRoot(filePath)}`)
    }
  }
}

function findPatternMatches(filePath, regex) {
  const content = readUtf8(filePath)
  const lines = content.split('\n')
  const matches = []

  for (let index = 0; index < lines.length; index += 1) {
    if (regex.test(lines[index])) {
      matches.push(index + 1)
    }
  }

  return matches
}

function lintHooks() {
  const allowedEvents = new Set(['session_start', 'before_tool', 'after_tool', 'prompt_submit', 'session_end'])
  const allowedTools = new Set(['claude', 'gemini', 'kiro', 'factory', 'opencode'])
  const hooks = parseHooks().hooks

  for (const hook of hooks) {
    if (!hook.id) error(`lint: hook missing id -> ${JSON.stringify(hook)}`)
    if (!allowedEvents.has(hook.event)) {
      error(`lint: invalid hook event '${hook.event}' for hook '${hook.id}'`)
    }
    if (!hook.matcher || !hook.command) {
      error(`lint: hook must include matcher and command -> ${hook.id}`)
    }
    if (!Array.isArray(hook.tools) || hook.tools.length === 0) {
      error(`lint: hook.tools must be a non-empty array -> ${hook.id}`)
      continue
    }
    for (const tool of hook.tools) {
      if (!allowedTools.has(tool)) {
        error(`lint: invalid hook tool '${tool}' for hook '${hook.id}'`)
      }
    }
  }
}

function lintSchemas() {
  const schemaDir = path.join(AGENTS_ROOT, 'schema')
  const schemaFiles = [
    'persona.schema.json',
    'command.schema.json',
    'skill.schema.json',
    'hook.schema.json',
  ]

  for (const name of schemaFiles) {
    const fullPath = path.join(schemaDir, name)
    if (!fs.existsSync(fullPath)) {
      error(`lint: missing schema file -> ${relativeFromRoot(fullPath)}`)
      continue
    }

    try {
      JSON.parse(readUtf8(fullPath))
    } catch (parseError) {
      error(`lint: invalid JSON schema -> ${relativeFromRoot(fullPath)} (${parseError.message})`)
    }
  }
}

function lintCanonicalSpec(canonical) {
  const idPattern = /^[a-z0-9-]+$/
  const toSlug = (value) =>
    value
      .toLowerCase()
      .replace(/&/g, ' and ')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')

  const seenPersonaIds = new Set()
  for (const persona of canonical.personas) {
    if (isTemplateId(persona.id)) continue
    if (!idPattern.test(persona.id)) {
      error(`lint: invalid persona id '${persona.id}' (must be kebab-case)`)
    }
    if (seenPersonaIds.has(persona.id)) {
      error(`lint: duplicate persona id '${persona.id}'`)
    }
    seenPersonaIds.add(persona.id)

    if (!persona.description.trim()) {
      error(`lint: persona '${persona.id}' missing description`)
    }
    if (!['agent', 'subagent'].includes(persona.mode)) {
      error(`lint: persona '${persona.id}' has invalid mode '${persona.mode}'`)
    }
    if (!persona.model.trim()) {
      error(`lint: persona '${persona.id}' missing model`)
    }
  }

  const seenCommandIds = new Set()
  for (const command of canonical.commands) {
    if (isTemplateId(command.id)) continue
    if (!idPattern.test(command.id)) {
      error(`lint: invalid command id '${command.id}' (must be kebab-case)`)
    }
    if (seenCommandIds.has(command.id)) {
      error(`lint: duplicate command id '${command.id}'`)
    }
    seenCommandIds.add(command.id)

    if (!command.description.trim()) {
      error(`lint: command '${command.id}' missing description`)
    }
    if (!command.raw.trim()) {
      error(`lint: command '${command.id}' is empty`)
    }
  }

  const seenSkillIds = new Set()
  for (const skill of canonical.skills) {
    if (isTemplateId(skill.id)) continue
    if (!idPattern.test(skill.id)) {
      error(`lint: invalid skill id '${skill.id}' (must be kebab-case)`)
    }
    if (seenSkillIds.has(skill.id)) {
      error(`lint: duplicate skill id '${skill.id}'`)
    }
    seenSkillIds.add(skill.id)

    if (!skill.hasEntrypoint) {
      error(`lint: skill '${skill.id}' missing SKILL.md entrypoint`)
      continue
    }

    const declaredName = String(skill.frontmatter.name ?? '').trim()
    if (!declaredName) {
      error(`lint: skill '${skill.id}' missing frontmatter name`)
    } else {
      const normalized = toSlug(declaredName)
      if (normalized !== skill.id) {
        error(
          `lint: skill '${skill.id}' frontmatter name '${declaredName}' is not canonically mappable to directory id`,
        )
      }
    }

    if (!String(skill.frontmatter.description ?? '').trim()) {
      error(`lint: skill '${skill.id}' missing frontmatter description`)
    }
  }
}

function hasHeading(content, heading) {
  return new RegExp(`^${heading.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}\\s*$`, 'm').test(content)
}

function lintExecutableTemplates(commandsDir, skillsDir, strictLevel) {
  if (strictLevel !== 'hard') {
    return
  }

  const commandHeadings = [
    '## Inputs Required',
    '## Preconditions',
    '## Steps',
    '## Verification',
    '## Rollback/Fallback',
    '## Output Contract',
  ]
  const skillHeadings = [
    '## Purpose',
    '## Inputs Required',
    '## Preconditions',
    '## Workflow',
    '## Commands To Run',
    '## Verification',
    '## Output Contract',
    '## Guardrails',
  ]

  for (const filePath of listMarkdownFiles(commandsDir)) {
    if (isTemplateMarkdownFile(filePath)) continue
    const content = readUtf8(filePath)
    for (const heading of commandHeadings) {
      if (!hasHeading(content, heading)) {
        const message = `lint: command missing executable heading '${heading}' -> ${relativeFromRoot(filePath)}`
        if (strictLevel === 'hard') error(message)
        else warn(message)
      }
    }
  }

  for (const skillDirName of listDirectories(skillsDir)) {
    if (isTemplateId(skillDirName)) continue
    const entrypoint = path.join(skillsDir, skillDirName, 'SKILL.md')
    if (!fs.existsSync(entrypoint)) continue
    const content = readUtf8(entrypoint)
    for (const heading of skillHeadings) {
      if (!hasHeading(content, heading)) {
        const message = `lint: skill missing executable heading '${heading}' -> ${relativeFromRoot(entrypoint)}`
        if (strictLevel === 'hard') error(message)
        else warn(message)
      }
    }
  }
}

function lintOverlayContract(personasDir, commandsDir, skillsDir, rulesDir, steeringDir, strictLevel) {
  const required = ['core_ref', 'core_version', 'overlay_mode']
  const scan = []
  scan.push(...listMarkdownFiles(personasDir))
  scan.push(...listMarkdownFiles(commandsDir))
  scan.push(...listMarkdownFiles(rulesDir))
  scan.push(...listMarkdownFiles(steeringDir))
  for (const skillDirName of listDirectories(skillsDir)) {
    if (isTemplateId(skillDirName)) continue
    const entrypoint = path.join(skillsDir, skillDirName, 'SKILL.md')
    if (fs.existsSync(entrypoint)) scan.push(entrypoint)
  }

  for (const filePath of scan) {
    if (isTemplateMarkdownFile(filePath)) continue
    const parsed = parseFrontmatter(readUtf8(filePath))
    if (!parsed.hasFrontmatter) continue

    const hasAnyOverlayMetadata = required.some((key) => String(parsed.frontmatter[key] ?? '').trim())
    if (strictLevel !== 'hard' && !hasAnyOverlayMetadata) {
      continue
    }

    for (const key of required) {
      const value = String(parsed.frontmatter[key] ?? '').trim()
      if (!value) {
        const message = `lint: overlay frontmatter key '${key}' missing -> ${relativeFromRoot(filePath)}`
        if (strictLevel === 'hard') error(message)
        else warn(message)
      }
    }
    const overlayMode = String(parsed.frontmatter.overlay_mode ?? '').trim()
    if (overlayMode && !['append', 'replace'].includes(overlayMode)) {
      const message = `lint: overlay_mode must be append|replace -> ${relativeFromRoot(filePath)}`
      if (strictLevel === 'hard') error(message)
      else warn(message)
    }
    if (overlayMode === 'replace') {
      const driftReason = String(parsed.frontmatter.drift_reason ?? '').trim()
      if (!driftReason) {
        const message = `lint: drift_reason required when overlay_mode=replace -> ${relativeFromRoot(filePath)}`
        if (strictLevel === 'hard') error(message)
        else warn(message)
      }
    }
  }
}

function main() {
  const canonical = loadCanonical()
  const personasDir = path.join(AGENTS_ROOT, 'personas')
  const commandsDir = path.join(AGENTS_ROOT, 'commands')
  const skillsDir = path.join(AGENTS_ROOT, 'skills')
  const rulesDir = path.join(AGENTS_ROOT, 'rules')
  const steeringDir = path.join(AGENTS_ROOT, 'steering')
  const driftMode = loadDriftPolicy().policy.mode === 'hard' ? 'hard' : 'warn'

  for (const filePath of listMarkdownFiles(personasDir)) {
    if (isTemplateMarkdownFile(filePath)) continue
    requireFrontmatter(filePath, ['description', 'model'])
  }

  for (const filePath of listMarkdownFiles(commandsDir)) {
    if (isTemplateMarkdownFile(filePath)) continue
    requireFrontmatter(filePath, ['description'])
  }

  for (const skillDirName of listDirectories(skillsDir)) {
    if (isTemplateId(skillDirName)) continue
    const entrypoint = path.join(skillsDir, skillDirName, 'SKILL.md')
    if (!fs.existsSync(entrypoint)) {
      error(`lint: missing skill entrypoint -> ${relativeFromRoot(entrypoint)}`)
      continue
    }
    requireFrontmatter(entrypoint, ['name', 'description'])
  }

  const bannedSnippet = /const\s+\{\s*db\s*\}\s*=\s*await\s+import\('~\/lib\/db'\)/
  const bannedSkillBoilerplate = [
    /Confirm scope and success criteria for the task\./,
    /Identify authoritative files and existing patterns first\./,
    /Propose minimal, testable changes aligned with project architecture\./,
    /Verify with targeted checks and summarize evidence\./,
  ]
  const scanDirs = [personasDir, commandsDir, skillsDir, steeringDir]

  for (const dir of scanDirs) {
    const files = walkFiles(dir).filter((filePath) => filePath.endsWith('.md'))

    for (const filePath of files) {
      const matches = findPatternMatches(filePath, bannedSnippet)
      for (const line of matches) {
        error(`lint: banned legacy db import snippet -> ${relativeFromRoot(filePath)}:${line}`)
      }
    }
  }

  for (const skillDirName of listDirectories(skillsDir)) {
    if (isTemplateId(skillDirName)) continue
    const entrypoint = path.join(skillsDir, skillDirName, 'SKILL.md')
    if (!fs.existsSync(entrypoint)) continue

    for (const pattern of bannedSkillBoilerplate) {
      const matches = findPatternMatches(entrypoint, pattern)
      for (const line of matches) {
        error(`lint: banned boilerplate skill content -> ${relativeFromRoot(entrypoint)}:${line}`)
      }
    }
  }

  // Fix 6: Detect unfilled placeholders in non-template files
  if (driftMode === 'hard') {
    const placeholderRe = /<!--\s*PROJECT:/
    for (const dir of scanDirs) {
      for (const filePath of walkFiles(dir).filter((f) => f.endsWith('.md') && !f.includes('_TEMPLATE'))) {
        for (const line of findPatternMatches(filePath, placeholderRe)) {
          error(`lint: unfilled placeholder -> ${relativeFromRoot(filePath)}:${line}`)
        }
      }
    }
  }

  lintCanonicalSpec(canonical)
  lintSchemas()
  lintHooks()
  lintExecutableTemplates(commandsDir, skillsDir, driftMode)
  lintOverlayContract(personasDir, commandsDir, skillsDir, rulesDir, steeringDir, driftMode)

  for (const issue of validateProfileAndPolicy()) {
    if (issue.level === 'error') error(`lint: ${issue.message}`)
    else warn(`lint: ${issue.message}`)
  }

  if (hasError) {
    process.exitCode = 1
    return
  }

  if (warningCount > 0) {
    process.stdout.write(`agents-lint: ok with ${warningCount} warning(s)\n`)
    return
  }

  process.stdout.write('agents-lint: ok\n')
}

main()
