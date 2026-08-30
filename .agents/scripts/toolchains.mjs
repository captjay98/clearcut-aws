import fs from 'node:fs'
import path from 'node:path'
import { ROOT } from './renderers/common.mjs'

const renderersDir = path.join(import.meta.dirname, 'renderers')

// Auto-discover renderers by scanning for .mjs files with a `meta` export
const rendererFiles = fs.readdirSync(renderersDir)
  .filter(f => f.endsWith('.mjs') && f !== 'common.mjs')
  .sort()

const loaded = await Promise.all(
  rendererFiles.map(f => import(path.join(renderersDir, f)))
)

export const renderers = loaded
  .filter(mod => mod.meta?.name)
  .map(mod => {
    // Find the render function: renderClaude, renderGemini, etc. or just render
    const renderFnName = `render${mod.meta.name[0].toUpperCase()}${mod.meta.name.slice(1)}`
    const render = mod[renderFnName] || mod.render
    return { meta: mod.meta, render }
  })

export const TOOLCHAINS = renderers.map(r => r.meta.name)
export const MCP_CAPABLE_TOOLCHAINS = renderers.filter(r => r.meta.mcpCapable).map(r => r.meta.name)
export const TOOLCHAIN_OUTPUTS = Object.fromEntries(renderers.map(r => [r.meta.name, r.meta.outputDirs]))

export const MCP_CONFIG_BY_TOOLCHAIN = {
  kiro: {
    id: 'kiro',
    file: '.kiro/settings/mcp.json',
    allowedTopLevel: new Set(['mcpServers']),
  },
  gemini: {
    id: 'gemini',
    file: '.gemini/settings.json',
    allowedTopLevel: new Set([
      'general', 'model', 'context', 'tools', 'privacy', 'experimental', 'mcpServers',
    ]),
  },
  factory: {
    id: 'factory',
    file: '.factory/mcp.json',
    allowedTopLevel: new Set(['mcpServers']),
  },
  claude: {
    id: 'claude',
    file: '.claude/settings.json',
    allowedTopLevel: new Set(['hooks', 'mcpServers']),
  },
}

export function absoluteOutputs(toolchain) {
  return (TOOLCHAIN_OUTPUTS[toolchain] ?? []).map((relativePath) => path.join(ROOT, relativePath))
}
