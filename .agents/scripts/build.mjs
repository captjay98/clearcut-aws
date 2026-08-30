import fs from 'node:fs'
import path from 'node:path'
import {
  AGENTS_ROOT,
  GENERATED_FILE_TARGETS,
  ROOT,
  hashString,
  loadCanonical,
  removeIfExists,
  relativeFromRoot,
  renderMcpConfig,
  renderGuide,
  resolveProjectName,
  titleCase,
  walkFiles,
  writeManifest,
  writeUtf8,
} from './renderers/common.mjs'
import { resolveToolchains } from './config.mjs'
import { renderers, TOOLCHAINS, absoluteOutputs } from './toolchains.mjs'
const rendererByToolchain = Object.fromEntries(renderers.map(r => [r.meta.name, r.render]))

function generateRootAgentsMd(canonical, enabledToolchains) {
  const steeringIndex = canonical.steering
    .map((doc) => `- [${doc.id}](.agents/steering/${doc.id}.md)`)
    .join('\n')

  const projectName = resolveProjectName()
  const title = `AI Agent Guide for ${projectName.charAt(0).toUpperCase() + projectName.slice(1)}`

  return `${renderGuide({
    title,
    subtitle:
      'Generated root guide for the unified multi-tool system. Canonical source of truth is .agents/.',
    toolName: `Enabled Toolchains: ${enabledToolchains.length ? enabledToolchains.join(', ') : '(none)'}`,
    canonical,
  })}\n## Canonical Roots\n\n- Personas: \`.agents/personas\`\n- Commands: \`.agents/commands\`\n- Skills: \`.agents/skills\`\n- Hooks: \`.agents/hooks/hooks.json\`\n- Rules: \`.agents/rules\`\n- Steering: \`.agents/steering\`\n- Memory: \`.agents/memory/project-memory.md\`\n\n## Steering Index\n\n${steeringIndex || '- (none)'}\n`
}

function collectGeneratedFiles() {
  const targets = GENERATED_FILE_TARGETS

  const files = []
  for (const target of targets) {
    const fullPath = path.join(ROOT, target)
    if (!fs.existsSync(fullPath)) continue
    const stat = fs.lstatSync(fullPath)

    if (stat.isDirectory()) {
      files.push(...walkFiles(fullPath))
      continue
    }

    files.push(fullPath)
  }

  return files
    .map((filePath) => ({
      path: relativeFromRoot(filePath),
      sha256: hashString(fs.readFileSync(filePath)),
    }))
    .sort((a, b) => a.path.localeCompare(b.path))
}

function main() {
  const strict = process.env.AGENTS_STRICT === '1'
  const resolution = resolveToolchains({
    includeLocalOverride: true,
    requireProfileInCi: true,
  })
  const enabledSet = resolution.enabledSet
  const enabledToolchains = resolution.enabled
  const canonical = loadCanonical(resolution.profile)
  const projectName = resolveProjectName()

  const warnings = []

  for (const toolchain of TOOLCHAINS) {
    if (enabledSet.has(toolchain)) {
      const renderer = rendererByToolchain[toolchain]
      warnings.push(...renderer(canonical, { strict, projectName, profile: resolution.profile }).warnings)
      continue
    }

    for (const outputPath of absoluteOutputs(toolchain)) {
      removeIfExists(outputPath)
    }
  }

  const hasDefinedServers = canonical.mcpServers?.servers && Object.keys(canonical.mcpServers.servers).length > 0
  if (hasDefinedServers) {
    const shouldRenderMcp =
      enabledSet.has('kiro') ||
      enabledSet.has('gemini') ||
      enabledSet.has('factory') ||
      enabledSet.has('claude') ||
      enabledSet.has('opencode')
    if (shouldRenderMcp) {
      const mcpServers = renderMcpConfig(canonical.mcpServers, 'kiro')
      if (mcpServers) {
        writeUtf8(path.join(ROOT, '.mcp.json'), JSON.stringify({ mcpServers }, null, 2) + '\n')
      }
    } else {
      removeIfExists(path.join(ROOT, '.mcp.json'))
    }
  } else {
    removeIfExists(path.join(ROOT, '.mcp.json'))
  }

  writeUtf8(path.join(ROOT, 'AGENTS.md'), generateRootAgentsMd(canonical, enabledToolchains))

  // Load previous manifest for change detection
  const manifestPath = path.join(AGENTS_ROOT, 'render-manifest.json')
  let previousFiles = new Map()
  if (fs.existsSync(manifestPath)) {
    try {
      const prev = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
      for (const f of prev.generatedFiles ?? []) previousFiles.set(f.path, f.sha256)
    } catch {}
  }

  const generatedFiles = collectGeneratedFiles()

  // Diff against previous
  const currentFiles = new Map(generatedFiles.map((f) => [f.path, f.sha256]))
  const added = generatedFiles.filter((f) => !previousFiles.has(f.path))
  const removed = [...previousFiles.keys()].filter((p) => !currentFiles.has(p))
  const changed = generatedFiles.filter((f) => previousFiles.has(f.path) && previousFiles.get(f.path) !== f.sha256)

  writeManifest({
    version: 2,
    strict,
    enabledToolchains,
    counts: {
      personas: canonical.personas.length,
      subagents: canonical.personas.filter((item) => item.mode === 'subagent').length,
      commands: canonical.commands.length,
      skills: canonical.skills.length,
      rules: canonical.rules.length,
      steering: canonical.steering.length,
      hooks: canonical.hooks.hooks.length,
    },
    generatedFiles,
  })

  // Print summary
  const total = added.length + changed.length + removed.length
  if (warnings.length) {
    process.stdout.write(`agents-build: completed with ${warnings.length} warning(s)\n`)
    for (const warning of warnings) {
      process.stdout.write(`warn: ${warning}\n`)
    }
  }

  if (total === 0) {
    process.stdout.write('agents-build: done (no changes)\n')
  } else {
    process.stdout.write(`agents-build: done — ${added.length} added, ${changed.length} changed, ${removed.length} removed\n`)
    for (const f of added) process.stdout.write(`  + ${f.path}\n`)
    for (const f of changed) process.stdout.write(`  ~ ${f.path}\n`)
    for (const p of removed) process.stdout.write(`  - ${p}\n`)
  }

  process.stdout.write('\ntip: for rapid iteration while authoring, use:\n  watchexec -w .agents -- bun .agents/scripts/build.mjs\n')
}

main()
