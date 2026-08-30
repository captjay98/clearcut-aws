import fs from 'node:fs'
import path from 'node:path'
import { walkFiles } from './renderers/common.mjs'

const ROOT = process.cwd()
const ACTIONABLE_TARGETS = [
  '.agents/commands',
  '.agents/personas',
  '.agents/rules',
  '.agents/steering',
  '.agents/hooks',
  '.agents/scripts',
  'AGENTS.md',
]
const TEXT_EXTENSIONS = new Set([
  '.md',
  '.json',
  '.toml',
  '.yaml',
  '.yml',
  '.ts',
  '.js',
  '.mjs',
  '.txt',
])
const EXCLUDED_PREFIXES = [
  '.agents/scripts/test/',
  '.agents/scripts/check-package-managers.mjs',
  '.agents/scripts/README.md',
]
const INSTALL_COMMAND = /\b(?:npm|yarn)\s+(?:install|i|ci|add|init|update|remove|uninstall)\b/i
const NPX_COMMAND = /\bnpx\s+(.+)$/i

let hasError = false

function fail(message) {
  hasError = true
  process.stderr.write(`${message}\n`)
}

function isTextFile(filePath) {
  return TEXT_EXTENSIONS.has(path.extname(filePath).toLowerCase())
}

function isExcluded(relativePath) {
  const normalized = relativePath.replace(/\\/g, '/')
  return EXCLUDED_PREFIXES.some((prefix) =>
    normalized === prefix.replace(/\/$/, '') || normalized.startsWith(prefix),
  )
}

const EXACT_VERSION = /^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/

function packageTokenHasExactVersion(packageToken) {
  const atIndex = packageToken.lastIndexOf('@')
  const slashIndex = packageToken.indexOf('/')
  if (atIndex <= slashIndex || atIndex === packageToken.length - 1) return false
  return EXACT_VERSION.test(packageToken.slice(atIndex + 1))
}

function npxPackageIsPinned(argumentsText) {
  const tokens = argumentsText.trim().split(/\s+/).filter(Boolean)
  const explicitPackages = []

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]
    if (token === '--package' || token === '-p') {
      if (tokens[index + 1]) explicitPackages.push(tokens[index + 1])
      index += 1
      continue
    }
    if (token.startsWith('--package=')) {
      explicitPackages.push(token.slice('--package='.length))
    }
  }

  if (explicitPackages.length > 0) {
    return explicitPackages.every(packageTokenHasExactVersion)
  }

  const packageToken = tokens.find((token) => !token.startsWith('-'))
  return packageToken ? packageTokenHasExactVersion(packageToken) : false
}

function scanFile(filePath) {
  if (!isTextFile(filePath)) return

  const relativePath = path.relative(ROOT, filePath).replace(/\\/g, '/')
  if (isExcluded(relativePath)) return

  const lines = fs.readFileSync(filePath, 'utf8').split('\n')
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    if (INSTALL_COMMAND.test(line)) {
      const match = line.match(/\b(?:npm|yarn)\s+(?:install|i|ci|add|init|update|remove|uninstall)\b/i)
      fail(`check-package-managers: disallowed package-manager install '${match?.[0] ?? 'command'}' in ${relativePath}:${index + 1}`)
    }

    const npxMatch = line.match(NPX_COMMAND)
    if (npxMatch && !npxPackageIsPinned(npxMatch[1])) {
      fail(`check-package-managers: unpinned npx executor in ${relativePath}:${index + 1}`)
    }
  }
}

function main() {
  for (const target of ACTIONABLE_TARGETS) {
    const fullPath = path.join(ROOT, target)
    if (!fs.existsSync(fullPath)) continue

    const stat = fs.lstatSync(fullPath)
    if (stat.isDirectory()) {
      for (const filePath of walkFiles(fullPath)) scanFile(filePath)
    } else {
      scanFile(fullPath)
    }
  }

  if (hasError) {
    process.exitCode = 1
    return
  }
  process.stdout.write('agents-check-package-managers: ok\n')
}

main()
