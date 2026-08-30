#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

const HUMAN_ONLY_PATHS = [
  '.agents/profile.toml',
  '.agents/local.profile.toml',
  '.agents/permissions.json',
  '.agents/models.toml',
  '.agents/lock.json',
  '.agents/hooks',
  '.agents/mcp',
  '.agents/rules',
  '.agents/steering',
  '.agents/kiro',
]
const ENV_EXAMPLE_NAMES = new Set(['.env.example', '.env.sample', '.env.template'])
const LOCKFILE_NAMES = new Set([
  'bun.lock',
  'bun.lockb',
  'npm-shrinkwrap.json',
  'package-lock.json',
  'pnpm-lock.yaml',
  'yarn.lock',
])

function block(message) {
  process.stderr.write(`sensitive-edit-adapter: ${message}\n`)
  process.exit(2)
}

function requestApproval(relativePath) {
  const reason = `Human approval required for protected agent control-plane path: ${relativePath}`
  process.stdout.write(`${JSON.stringify({
    hookSpecificOutput: {
      permissionDecision: 'ask',
      permissionDecisionReason: reason,
    },
  })}\n`)
}

function record(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    block(`${label} must be a JSON object`)
  }
  return value
}

function resolveThroughSymlinks(absolutePath) {
  let existingPath = absolutePath
  const missingParts = []

  while (!fs.existsSync(existingPath)) {
    const parent = path.dirname(existingPath)
    if (parent === existingPath) break
    missingParts.unshift(path.basename(existingPath))
    existingPath = parent
  }

  const resolvedBase = fs.existsSync(existingPath)
    ? fs.realpathSync(existingPath)
    : existingPath
  return path.join(resolvedBase, ...missingParts)
}

function normalizePath(value) {
  const raw = String(value ?? '').trim()
  if (!raw) return ''

  const lexicalAbsolute = path.isAbsolute(raw) ? raw : path.resolve(process.cwd(), raw)
  const absolute = resolveThroughSymlinks(lexicalAbsolute)
  const relative = path.relative(process.cwd(), absolute).replace(/\\/g, '/')
  if (relative === '' || relative.startsWith('../') || relative === '..') return absolute.replace(/\\/g, '/')
  return relative.replace(/^\.\//, '')
}

function isHumanOnly(relativePath) {
  return HUMAN_ONLY_PATHS.some((protectedPath) =>
    relativePath === protectedPath || relativePath.startsWith(`${protectedPath}/`),
  )
}

function isEnvironmentSecret(relativePath) {
  const name = path.posix.basename(relativePath)
  return name.startsWith('.env') && !ENV_EXAMPLE_NAMES.has(name)
}

function isLockfile(relativePath) {
  return LOCKFILE_NAMES.has(path.posix.basename(relativePath))
}

function extractPath(payload) {
  const toolInput = payload.toolInput ?? payload.tool_input ?? payload.input ?? payload
  const input = record(toolInput, 'tool input')
  return input.path ?? input.file_path ?? input.filePath ?? payload.path ?? payload.file_path ?? payload.filePath ?? process.env.TOOL_INPUT_FILE_PATH ?? ''
}

function main() {
  let payload
  try {
    const raw = fs.readFileSync(0, 'utf8').trim()
    payload = record(raw ? JSON.parse(raw) : {}, 'event payload')
  } catch (error) {
    block(`invalid event JSON (${error.message})`)
  }

  const normalized = normalizePath(extractPath(payload))
  if (!normalized) block('edit path is required')
  if (isEnvironmentSecret(normalized)) block(`environment secret path is protected: ${normalized}`)
  if (isLockfile(normalized)) block(`lockfile must be updated by its package manager: ${normalized}`)
  if (isHumanOnly(normalized)) requestApproval(normalized)
}

try {
  main()
} catch (error) {
  block(`internal failure (${error.message})`)
}
