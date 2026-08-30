import fs from 'node:fs'
import path from 'node:path'
import { AGENTS_ROOT } from './renderers/common.mjs'
import { TOOLCHAINS } from './toolchains.mjs'

const PROFILE_PATH = path.join(AGENTS_ROOT, 'profile.toml')
const LOCAL_PROFILE_PATH = path.join(AGENTS_ROOT, 'local.profile.toml')
const LOCK_PATH = path.join(AGENTS_ROOT, 'lock.json')
const DRIFT_POLICY_PATH = path.join(AGENTS_ROOT, 'drift-policy.toml')

function parseTomlValue(raw) {
  const value = raw.trim()
  if (!value) return ''

  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1)
  }

  if (value === 'true') return true
  if (value === 'false') return false

  if (/^-?\d+$/.test(value)) return Number(value)

  if (value.startsWith('[') && value.endsWith(']')) {
    const inner = value.slice(1, -1).trim()
    if (!inner) return []

    const parts = []
    let buf = ''
    let inQuote = false
    let quoteChar = ''
    for (let i = 0; i < inner.length; i += 1) {
      const ch = inner[i]
      if ((ch === '"' || ch === "'") && (!inQuote || ch === quoteChar)) {
        if (!inQuote) {
          inQuote = true
          quoteChar = ch
        } else {
          inQuote = false
          quoteChar = ''
        }
        buf += ch
        continue
      }
      if (ch === ',' && !inQuote) {
        parts.push(buf.trim())
        buf = ''
        continue
      }
      buf += ch
    }
    if (buf.trim()) parts.push(buf.trim())

    return parts.map((part) => parseTomlValue(part))
  }

  return value
}

function isArrayClosed(value) {
  let depth = 0
  let inQuote = false
  let quoteChar = ''
  for (const ch of value) {
    if ((ch === '"' || ch === "'") && (!inQuote || ch === quoteChar)) {
      inQuote = !inQuote
      quoteChar = inQuote ? ch : ''
      continue
    }
    if (inQuote) continue
    if (ch === '[') depth += 1
    if (ch === ']') depth -= 1
  }
  return depth === 0 && value.trim().endsWith(']')
}

export function parseToml(text) {
  const out = {}
  let sectionPath = []

  const lines = String(text).split(/\r?\n/)
  let i = 0
  while (i < lines.length) {
    const original = lines[i]
    const noComment = original.replace(/\s+#.*$/, '')
    const line = noComment.trim()
    i += 1
    if (!line) continue

    if (line.startsWith('[') && line.endsWith(']')) {
      sectionPath = line.slice(1, -1).trim().split('.').map((part) => part.trim()).filter(Boolean)
      let ptr = out
      for (const key of sectionPath) {
        if (!ptr[key] || typeof ptr[key] !== 'object' || Array.isArray(ptr[key])) {
          ptr[key] = {}
        }
        ptr = ptr[key]
      }
      continue
    }

    const idx = line.indexOf('=')
    if (idx < 0) continue
    const key = line.slice(0, idx).trim()
    let rawValue = line.slice(idx + 1)

    if (rawValue.trimStart().startsWith('[') && !isArrayClosed(rawValue)) {
      while (i < lines.length) {
        const nextOriginal = lines[i]
        const nextNoComment = nextOriginal.replace(/\s+#.*$/, '')
        const nextLine = nextNoComment.trim()
        i += 1
        if (!nextLine) continue
        rawValue += ' ' + nextLine
        if (isArrayClosed(rawValue)) break
      }
    }

    let ptr = out
    for (const part of sectionPath) {
      if (!ptr[part] || typeof ptr[part] !== 'object' || Array.isArray(ptr[part])) {
        ptr[part] = {}
      }
      ptr = ptr[part]
    }

    ptr[key] = parseTomlValue(rawValue)
  }

  return out
}

function isCi() {
  const value = String(process.env.CI ?? '').trim().toLowerCase()
  return value === '1' || value === 'true'
}

function defaultProfile() {
  return {
    version: 1,
    hub: {
      source: '',
      version: '',
    },
    selection: {
      toolchains_allowed: [...TOOLCHAINS],
      toolchains_default_enabled: [],
      packs: [],
      stacks: [],
      commands_include: [],
      commands_exclude: [],
      skills_include: [],
      skills_exclude: [],
    },
    policy: {
      mcp_base: [],
      db_owner_agent: '',
      edge_owner_agent: '',
      override_mode: 'narrowing_only',
      disabled_output_behavior: 'prune',
    },
  }
}

function mergeDefaults(base) {
  const defaults = defaultProfile()
  return {
    ...defaults,
    ...base,
    hub: {
      ...defaults.hub,
      ...(base.hub ?? {}),
    },
    selection: {
      ...defaults.selection,
      ...(base.selection ?? {}),
    },
    policy: {
      ...defaults.policy,
      ...(base.policy ?? {}),
    },
  }
}

export function loadProfile(options = {}) {
  const { requireInCi = true } = options
  const profileExists = fs.existsSync(PROFILE_PATH)

  if (!profileExists) {
    if (requireInCi && isCi()) {
      throw new Error('agents config missing: .agents/profile.toml is required in CI. Run agents init.')
    }

    return {
      path: PROFILE_PATH,
      exists: false,
      profile: defaultProfile(),
      usedDefaultProfile: true,
    }
  }

  const parsed = parseToml(fs.readFileSync(PROFILE_PATH, 'utf8'))
  return {
    path: PROFILE_PATH,
    exists: true,
    profile: mergeDefaults(parsed),
    usedDefaultProfile: false,
  }
}

export function loadLocalProfile() {
  if (!fs.existsSync(LOCAL_PROFILE_PATH)) {
    return {
      path: LOCAL_PROFILE_PATH,
      exists: false,
      profile: { version: 1, selection: { disable_toolchains: [] } },
    }
  }

  const parsed = parseToml(fs.readFileSync(LOCAL_PROFILE_PATH, 'utf8'))
  return {
    path: LOCAL_PROFILE_PATH,
    exists: true,
    profile: {
      version: Number(parsed.version ?? 1),
      selection: {
        disable_toolchains: Array.isArray(parsed.selection?.disable_toolchains)
          ? parsed.selection.disable_toolchains.map((value) => String(value))
          : [],
      },
    },
  }
}

export function resolveToolchains(options = {}) {
  const {
    includeLocalOverride = !isCi(),
    requireProfileInCi = true,
  } = options

  const { profile, usedDefaultProfile } = loadProfile({ requireInCi: requireProfileInCi })

  const allowed = Array.isArray(profile.selection.toolchains_allowed)
    ? profile.selection.toolchains_allowed.map((value) => String(value))
    : [...TOOLCHAINS]

  const defaultEnabled = Array.isArray(profile.selection.toolchains_default_enabled)
    ? profile.selection.toolchains_default_enabled.map((value) => String(value))
    : []

  const unknownAllowed = allowed.filter((value) => !TOOLCHAINS.includes(value))
  if (unknownAllowed.length) {
    throw new Error(`profile invalid: unsupported toolchains_allowed: ${unknownAllowed.join(', ')}`)
  }

  const unknownDefault = defaultEnabled.filter((value) => !TOOLCHAINS.includes(value))
  if (unknownDefault.length) {
    throw new Error(`profile invalid: unsupported toolchains_default_enabled: ${unknownDefault.join(', ')}`)
  }

  const allowedSet = new Set(allowed)
  let enabled = defaultEnabled.filter((value) => allowedSet.has(value))

  let localDisabled = []
  if (includeLocalOverride) {
    const local = loadLocalProfile()
    localDisabled = local.profile.selection.disable_toolchains ?? []
    const unknownLocal = localDisabled.filter((value) => !TOOLCHAINS.includes(value))
    if (unknownLocal.length) {
      throw new Error(`local profile invalid: unsupported disable_toolchains: ${unknownLocal.join(', ')}`)
    }

    const widening = localDisabled.filter((value) => !allowedSet.has(value))
    if (widening.length) {
      throw new Error(`local profile invalid: disable_toolchains contains disallowed values: ${widening.join(', ')}`)
    }

    const localDisabledSet = new Set(localDisabled)
    enabled = enabled.filter((value) => !localDisabledSet.has(value))
  }

  return {
    profile,
    allowed,
    enabled,
    enabledSet: new Set(enabled),
    defaultEnabled,
    localDisabled,
    usedDefaultProfile,
    includeLocalOverride,
    ci: isCi(),
  }
}

export function loadLock() {
  if (!fs.existsSync(LOCK_PATH)) {
    return { exists: false, path: LOCK_PATH, lock: null }
  }

  try {
    return {
      exists: true,
      path: LOCK_PATH,
      lock: JSON.parse(fs.readFileSync(LOCK_PATH, 'utf8')),
    }
  } catch (error) {
    throw new Error(`invalid lock file .agents/lock.json (${error.message})`)
  }
}

export function loadDriftPolicy() {
  if (!fs.existsSync(DRIFT_POLICY_PATH)) {
    return {
      exists: false,
      path: DRIFT_POLICY_PATH,
      policy: {
        version: 1,
        mode: 'warn',
        harden_after: 'migration_complete',
      },
    }
  }

  const parsed = parseToml(fs.readFileSync(DRIFT_POLICY_PATH, 'utf8'))
  return {
    exists: true,
    path: DRIFT_POLICY_PATH,
    policy: {
      version: Number(parsed.version ?? 1),
      mode: String(parsed.mode ?? 'warn'),
      harden_after: String(parsed.harden_after ?? 'migration_complete'),
    },
  }
}

export function validateProfileAndPolicy() {
  const issues = []

  let resolved
  try {
    resolved = resolveToolchains({ includeLocalOverride: false, requireProfileInCi: true })
  } catch (error) {
    issues.push({ level: 'error', message: error.message })
    return issues
  }

  if (!resolved.profile.version) {
    issues.push({ level: 'error', message: '.agents/profile.toml must include version' })
  }

  const selectionLists = [
    'packs',
    'stacks',
    'commands_include',
    'commands_exclude',
    'skills_include',
    'skills_exclude',
  ]
  for (const key of selectionLists) {
    if (!Array.isArray(resolved.profile.selection[key])) {
      issues.push({ level: 'error', message: `.agents/profile.toml selection.${key} must be an array` })
    }
  }

  const policy = loadDriftPolicy().policy
  if (!['warn', 'hard'].includes(policy.mode)) {
    issues.push({ level: 'error', message: '.agents/drift-policy.toml mode must be warn|hard' })
  }

  const lock = loadLock()
  if (!lock.exists) {
    issues.push({ level: 'warn', message: '.agents/lock.json missing (run agents sync)' })
  }

  return issues
}

export function profilePaths() {
  return {
    profilePath: PROFILE_PATH,
    localProfilePath: LOCAL_PROFILE_PATH,
    lockPath: LOCK_PATH,
    driftPolicyPath: DRIFT_POLICY_PATH,
  }
}
