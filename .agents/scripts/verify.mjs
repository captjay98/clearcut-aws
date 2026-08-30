import fs from 'node:fs'
import path from 'node:path'
import {
  ROOT,
  GENERATED_FILE_TARGETS,
  AGENTS_ROOT,
  hashString,
  hooksForTool,
  loadCanonical,
  parseHooks,
  readUtf8,
  relativeFromRoot,
  walkFiles,
} from './renderers/common.mjs'
import { resolveToolchains } from './config.mjs'
import { TOOLCHAIN_OUTPUTS } from './toolchains.mjs'
import {
  expectedKiroAgentFiles,
  expectedKiroAutomatedHookFiles,
  validateKiroHookDocument,
} from './verify-kiro.mjs'

let hasError = false

function fail(message) {
  hasError = true
  process.stderr.write(`${message}\n`)
}

function assertExists(filePath) {
  if (!fs.existsSync(filePath)) {
    fail(`verify: missing -> ${relativeFromRoot(filePath)}`)
    return false
  }
  return true
}

function listFilesWithExt(dir, ext) {
  if (!fs.existsSync(dir)) return []
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(ext))
    .map((entry) => entry.name)
    .sort()
}

function listDirectoryEntries(dir) {
  if (!fs.existsSync(dir)) return []
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() || entry.isSymbolicLink())
    .map((entry) => entry.name)
    .sort()
}

function verifyExactFileSet(dir, expectedNames, label) {
  if (!assertExists(dir)) return
  const actual = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort()

  const expected = [...expectedNames].sort()

  for (const name of expected) {
    if (!actual.includes(name)) {
      fail(`verify: missing generated file ${label}/${name}`)
    }
  }
  for (const name of actual) {
    if (!expected.includes(name)) {
      fail(`verify: stale generated file ${label}/${name}`)
    }
  }
}

function verifyExactFileSetFiltered(dir, expectedNames, label, predicate) {
  if (!assertExists(dir)) return
  const actual = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && predicate(entry.name))
    .map((entry) => entry.name)
    .sort()

  const expected = [...expectedNames].sort()

  for (const name of expected) {
    if (!actual.includes(name)) {
      fail(`verify: missing generated file ${label}/${name}`)
    }
  }
  // Filtered sets may also contain project-owned files (notably Kiro hooks).
  // The renderer removes only stale files it can identify as generated.
}
function verifyExactDirSet(dir, expectedNames, label) {
  if (!assertExists(dir)) return
  const actual = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() || entry.isSymbolicLink())
    .map((entry) => entry.name)
    .sort()

  const expected = [...expectedNames].sort()
  for (const name of expected) {
    if (!actual.includes(name)) {
      fail(`verify: missing generated directory ${label}/${name}`)
    }
  }
  for (const name of actual) {
    if (!expected.includes(name)) {
      fail(`verify: stale generated directory ${label}/${name}`)
    }
  }
}

function verifyPathAbsent(target, label) {
  if (fs.existsSync(target)) {
    fail(`verify: disabled toolchain output must be absent -> ${label}`)
  }
}

function ensureNoIncludeTokens(dir) {
  if (!fs.existsSync(dir)) return
  for (const filePath of walkFiles(dir)) {
    const content = readUtf8(filePath)
    if (content.includes('{{include:')) {
      fail(`verify: unresolved include token -> ${relativeFromRoot(filePath)}`)
    }
  }
}

function verifyCounts(canonical, enabledSet) {
  const personaCount = canonical.personas.length
  const subagentCount = canonical.personas.filter((persona) => persona.mode === 'subagent').length
  const commandCount = canonical.commands.length
  const skillCount = canonical.skills.length

  const parity = []
  if (enabledSet.has('claude')) {
    parity.push(['.claude/agents', listFilesWithExt(path.join(ROOT, '.claude', 'agents'), '.md').length, personaCount])
    parity.push(['.claude/commands', listFilesWithExt(path.join(ROOT, '.claude', 'commands'), '.md').length, commandCount])
    parity.push(['.claude/skills', listDirectoryEntries(path.join(ROOT, '.claude', 'skills')).length, skillCount])
  }
  if (enabledSet.has('gemini')) {
    parity.push(['.gemini/agents', listFilesWithExt(path.join(ROOT, '.gemini', 'agents'), '.md').length, personaCount])
    parity.push(['.gemini/commands', listFilesWithExt(path.join(ROOT, '.gemini', 'commands'), '.toml').length, commandCount])
  }
  if (enabledSet.has('opencode')) {
    parity.push(['.opencode/agents', listFilesWithExt(path.join(ROOT, '.opencode', 'agents'), '.md').length, personaCount])
    parity.push(['.opencode/commands', listFilesWithExt(path.join(ROOT, '.opencode', 'commands'), '.md').length, commandCount])
    parity.push(['.opencode/skills', listDirectoryEntries(path.join(ROOT, '.opencode', 'skills')).length, skillCount])
  }
  if (enabledSet.has('factory')) {
    parity.push(['.factory/droids', listFilesWithExt(path.join(ROOT, '.factory', 'droids'), '.md').length, personaCount])
    parity.push(['.factory/commands', listFilesWithExt(path.join(ROOT, '.factory', 'commands'), '.md').length, commandCount])
    parity.push(['.factory/skills', listDirectoryEntries(path.join(ROOT, '.factory', 'skills')).length, skillCount])
  }
  if (enabledSet.has('kiro')) {
    parity.push(['.kiro/prompts', listFilesWithExt(path.join(ROOT, '.kiro', 'prompts'), '.md').length, commandCount])
    parity.push(['.kiro/skills', listDirectoryEntries(path.join(ROOT, '.kiro', 'skills')).length, skillCount])
    parity.push(['.kiro/agents', listFilesWithExt(path.join(ROOT, '.kiro', 'agents'), '.md').length, subagentCount])
  }

  for (const [label, actual, expected] of parity) {
    if (actual !== expected) {
      fail(`verify: count mismatch ${label} actual=${actual} expected=${expected}`)
    }
  }
}

function verifyHookConfigShape(filePath, allowedKeys) {
  if (!assertExists(filePath)) return
  let parsed
  try {
    parsed = JSON.parse(readUtf8(filePath))
  } catch (error) {
    fail(`verify: invalid json ${relativeFromRoot(filePath)} (${error.message})`)
    return
  }

  const hooks = parsed.hooks
  if (!hooks || typeof hooks !== 'object') {
    fail(`verify: hooks object missing in ${relativeFromRoot(filePath)}`)
    return
  }

  for (const key of Object.keys(hooks)) {
    if (!allowedKeys.has(key)) {
      fail(`verify: invalid hook key '${key}' in ${relativeFromRoot(filePath)}`)
    }
    if (!Array.isArray(hooks[key])) {
      fail(`verify: hook bucket '${key}' must be array in ${relativeFromRoot(filePath)}`)
    }
  }
}

function verifyKiroV3Hooks(canonical) {
  const hooksDir = path.join(ROOT, '.kiro', 'hooks')
  const expectedFiles = expectedKiroAutomatedHookFiles(canonical.hooks.hooks)

  verifyExactFileSetFiltered(
    hooksDir,
    expectedFiles,
    '.kiro/hooks',
    (name) => name.endsWith('.json'),
  )

  for (const name of expectedFiles) {
    const filePath = path.join(hooksDir, name)
    if (!fs.existsSync(filePath)) continue

    let parsed
    try {
      parsed = JSON.parse(readUtf8(filePath))
    } catch (error) {
      fail(`verify: invalid json ${relativeFromRoot(filePath)} (${error.message})`)
      continue
    }

    for (const error of validateKiroHookDocument(parsed)) {
      fail(`verify: invalid Kiro hook ${relativeFromRoot(filePath)} (${error})`)
    }
  }
}

function verifyTemplateReferences() {
  const templateDir = path.join(AGENTS_ROOT, 'kiro', 'templates')
  if (!fs.existsSync(templateDir)) return

  const templateFiles = fs
    .readdirSync(templateDir)
    .filter((name) => name.endsWith('.json'))
    .sort()

  const walkStrings = (value, strings) => {
    if (typeof value === 'string') {
      strings.push(value)
      return
    }
    if (Array.isArray(value)) {
      for (const item of value) walkStrings(item, strings)
      return
    }
    if (value && typeof value === 'object') {
      for (const nested of Object.values(value)) walkStrings(nested, strings)
    }
  }

  for (const name of templateFiles) {
    const fullPath = path.join(templateDir, name)
    const parsed = JSON.parse(readUtf8(fullPath))
    const strings = []
    walkStrings(parsed, strings)

    for (const raw of strings) {
      if (raw.startsWith('skill://')) {
        const relative = raw.slice('skill://'.length).replace(/^\.\//, '')
        const target = path.join(ROOT, relative)
        if (!fs.existsSync(target)) {
          fail(`verify: missing skill reference '${raw}' in ${relativeFromRoot(fullPath)}`)
        }
      }

      if (raw.startsWith('file://')) {
        const ref = raw.slice('file://'.length)
        if (ref.startsWith('http://') || ref.startsWith('https://')) continue
        if (ref.startsWith('./') || ref.startsWith('../')) continue

        const target = path.join(ROOT, ref)
        if (!fs.existsSync(target)) {
          fail(`verify: missing file reference '${raw}' in ${relativeFromRoot(fullPath)}`)
        }
      }
    }
  }
}

function collectGeneratedFiles() {
  const targets = GENERATED_FILE_TARGETS

  const out = []
  for (const target of targets) {
    const fullPath = path.join(ROOT, target)
    if (!fs.existsSync(fullPath)) continue

    const stat = fs.lstatSync(fullPath)
    if (stat.isDirectory()) {
      out.push(...walkFiles(fullPath))
      continue
    }
    out.push(fullPath)
  }

  return out
    .map((filePath) => ({
      path: relativeFromRoot(filePath),
      sha256: hashString(fs.readFileSync(filePath)),
    }))
    .sort((a, b) => a.path.localeCompare(b.path))
}

function verifyManifest() {
  const manifestPath = path.join(AGENTS_ROOT, 'render-manifest.json')
  if (!assertExists(manifestPath)) return

  let manifest
  try {
    manifest = JSON.parse(readUtf8(manifestPath))
  } catch (error) {
    fail(`verify: invalid manifest json (${error.message})`)
    return
  }

  if (!Array.isArray(manifest.generatedFiles)) {
    fail('verify: manifest.generatedFiles must be an array')
    return
  }

  const expected = manifest.generatedFiles
  const actual = collectGeneratedFiles()

  if (expected.length !== actual.length) {
    fail(`verify: manifest file count mismatch expected=${expected.length} actual=${actual.length}`)
    return
  }

  for (let index = 0; index < expected.length; index += 1) {
    const a = expected[index]
    const b = actual[index]

    if (a.path !== b.path || a.sha256 !== b.sha256) {
      fail(`verify: manifest hash mismatch -> expected ${a.path}:${a.sha256} actual ${b.path}:${b.sha256}`)
      return
    }
  }
}

function verifyOpenCodeRegistration(enabledSet) {
  if (!enabledSet.has('opencode')) return

  const legacyConfigPath = path.join(ROOT, '.opencode', 'opencode.json')
  if (fs.existsSync(legacyConfigPath)) {
    fail('verify: legacy .opencode/opencode.json must not exist (OpenCode config belongs at project root)')
  }

  const configPath = path.join(ROOT, 'opencode.json')
  if (!assertExists(configPath)) return

  let parsed
  try {
    parsed = JSON.parse(readUtf8(configPath))
  } catch (error) {
    fail(`verify: invalid opencode config json (${error.message})`)
    return
  }

  if (parsed.$schema !== 'https://opencode.ai/config.json') {
    fail('verify: opencode.json must include $schema=https://opencode.ai/config.json')
  }

  const instructions = parsed.instructions
  if (
    !Array.isArray(instructions) ||
    !instructions.includes('AGENTS.md')
  ) {
    fail('verify: opencode.json must include AGENTS.md in instructions')
  }

  assertExists(path.join(ROOT, '.opencode', 'plugins', 'hooks.generated.ts'))
  assertExists(path.join(ROOT, '.opencode', 'RULES.md'))
}

function verifyNoLegacyFactoryArtifacts() {
  const legacy = [
    path.join(ROOT, '.factory', 'commands.json'),
    path.join(ROOT, '.factory', 'hooks.json'),
  ]

  for (const filePath of legacy) {
    if (fs.existsSync(filePath)) {
      fail(`verify: legacy factory artifact must not exist -> ${relativeFromRoot(filePath)}`)
    }
  }
}

function verifyCanonicalHooksCoverage() {
  const hooks = parseHooks().hooks
  const requiredEvents = new Set(['session_start', 'before_tool'])
  const seen = new Set(hooks.map((hook) => hook.event))

  for (const event of requiredEvents) {
    if (!seen.has(event)) {
      fail(`verify: canonical hooks missing required event '${event}'`)
    }
  }

  const requiredByTool = {
    claude: ['session_start', 'before_tool'],
    gemini: ['session_start', 'before_tool'],
    kiro: ['session_start', 'before_tool'],
    factory: ['session_start', 'before_tool'],
    opencode: ['session_start', 'before_tool'],
  }

  for (const [tool, expectedEvents] of Object.entries(requiredByTool)) {
    const toolHooks = hooksForTool(hooks, tool)
    if (toolHooks.length === 0) {
      fail(`verify: canonical hooks contain no hooks for tool '${tool}'`)
      continue
    }

    const toolEventSet = new Set(toolHooks.map((hook) => hook.event))
    for (const event of expectedEvents) {
      if (!toolEventSet.has(event)) {
        fail(`verify: canonical hooks missing '${event}' coverage for tool '${tool}'`)
      }
    }
  }
}

function verifyNoStaleGeneratedArtifacts(canonical, enabledSet) {
  const personaFiles = canonical.personas.map((persona) => `${persona.id}.md`)
  const subagentFiles = expectedKiroAgentFiles(canonical.personas)
  const commandMarkdownFiles = canonical.commands.map((command) => `${command.id}.md`)
  const commandTomlFiles = canonical.commands.map((command) => `${command.id}.toml`)
  const kiroHookFiles = canonical.commands.map((command) => `${command.id}.kiro.hook`)
  const skillDirs = canonical.skills.map((skill) => skill.id)
  const steeringFiles = canonical.steering.map((doc) => `${doc.id}.md`)

  if (enabledSet.has('claude')) {
    verifyExactFileSet(path.join(ROOT, '.claude', 'agents'), personaFiles, '.claude/agents')
    verifyExactFileSet(path.join(ROOT, '.claude', 'commands'), commandMarkdownFiles, '.claude/commands')
    verifyExactDirSet(path.join(ROOT, '.claude', 'skills'), skillDirs, '.claude/skills')
  }

  if (enabledSet.has('gemini')) {
    verifyExactFileSet(path.join(ROOT, '.gemini', 'agents'), personaFiles, '.gemini/agents')
    verifyExactFileSet(path.join(ROOT, '.gemini', 'commands'), commandTomlFiles, '.gemini/commands')
  }

  if (enabledSet.has('opencode')) {
    verifyExactFileSet(path.join(ROOT, '.opencode', 'agents'), personaFiles, '.opencode/agents')
    verifyExactFileSet(path.join(ROOT, '.opencode', 'commands'), commandMarkdownFiles, '.opencode/commands')
    verifyExactDirSet(path.join(ROOT, '.opencode', 'skills'), skillDirs, '.opencode/skills')
    verifyExactFileSet(path.join(ROOT, '.opencode', 'plugins'), ['hooks.generated.ts'], '.opencode/plugins')
  }

  if (enabledSet.has('factory')) {
    verifyExactFileSet(path.join(ROOT, '.factory', 'droids'), personaFiles, '.factory/droids')
    verifyExactFileSet(path.join(ROOT, '.factory', 'commands'), commandMarkdownFiles, '.factory/commands')
    verifyExactDirSet(path.join(ROOT, '.factory', 'skills'), skillDirs, '.factory/skills')
  }

  if (enabledSet.has('kiro')) {
    verifyExactFileSet(path.join(ROOT, '.kiro', 'prompts'), commandMarkdownFiles, '.kiro/prompts')
    verifyExactFileSet(
      path.join(ROOT, '.kiro', 'agents'),
      subagentFiles,
      '.kiro/agents',
    )
    verifyExactFileSet(path.join(ROOT, '.kiro', 'steering'), steeringFiles, '.kiro/steering')
    verifyExactFileSetFiltered(
      path.join(ROOT, '.kiro', 'hooks'),
      kiroHookFiles,
      '.kiro/hooks',
      (name) => name.endsWith('.kiro.hook'),
    )
    verifyExactDirSet(path.join(ROOT, '.kiro', 'skills'), skillDirs, '.kiro/skills')
  }

  for (const [toolchain, relativePaths] of Object.entries(TOOLCHAIN_OUTPUTS)) {
    if (enabledSet.has(toolchain)) continue
    for (const relativePath of relativePaths) {
      verifyPathAbsent(path.join(ROOT, relativePath), relativePath)
    }
  }
}

function main() {
  const resolution = resolveToolchains({
    includeLocalOverride: true,
    requireProfileInCi: true,
  })
  const enabledSet = resolution.enabledSet
  const canonical = loadCanonical(resolution.profile)

  verifyCounts(canonical, enabledSet)

  if (enabledSet.has('claude')) ensureNoIncludeTokens(path.join(ROOT, '.claude', 'agents'))
  if (enabledSet.has('gemini')) ensureNoIncludeTokens(path.join(ROOT, '.gemini', 'agents'))
  if (enabledSet.has('opencode')) ensureNoIncludeTokens(path.join(ROOT, '.opencode', 'agents'))
  if (enabledSet.has('factory')) ensureNoIncludeTokens(path.join(ROOT, '.factory', 'droids'))

  if (enabledSet.has('claude')) {
    verifyHookConfigShape(path.join(ROOT, '.claude', 'settings.json'), new Set(['SessionStart', 'PreToolUse', 'PostToolUse']))
  }
  if (enabledSet.has('gemini')) {
    verifyHookConfigShape(path.join(ROOT, '.gemini', 'hooks.json'), new Set(['sessionStart', 'preToolCall', 'postToolCall', 'sessionEnd']))
  }
  if (enabledSet.has('kiro')) {
    verifyKiroV3Hooks(canonical)
    verifyPathAbsent(
      path.join(ROOT, '.kiro', 'settings', 'hooks.json'),
      '.kiro/settings/hooks.json',
    )
  }
  if (enabledSet.has('factory')) {
    verifyHookConfigShape(path.join(ROOT, '.factory', 'settings.json'), new Set(['SessionStart', 'PreToolUse', 'PostToolUse']))
  }

  verifyNoLegacyFactoryArtifacts()
  verifyNoStaleGeneratedArtifacts(canonical, enabledSet)
  verifyOpenCodeRegistration(enabledSet)
  verifyCanonicalHooksCoverage()
  verifyManifest()

  if (hasError) {
    process.exitCode = 1
    return
  }

  process.stdout.write('agents-verify: ok\n')
}

main()
