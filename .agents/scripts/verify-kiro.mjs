const KIRO_V3_TRIGGERS = new Set([
  'PreToolUse',
  'PostToolUse',
  'SessionStart',
  'Stop',
  'UserPromptSubmit',
  'PreTaskExec',
  'PostTaskExec',
  'PostFileCreate',
  'PostFileSave',
  'PostFileDelete',
])

export function expectedKiroAgentFiles(personas) {
  return personas
    .filter((persona) => persona.mode === 'subagent')
    .map((persona) => `${persona.id}.md`)
    .sort()
}

export function expectedKiroAutomatedHookFiles(hooks) {
  return hooks
    .filter((hook) => Array.isArray(hook.tools) && hook.tools.includes('kiro'))
    .map((hook) => `${hook.id}.json`)
    .sort()
}

export function validateKiroHookDocument(document) {
  const errors = []

  if (!document || typeof document !== 'object' || Array.isArray(document)) {
    return ['document must be an object']
  }
  if (document.version !== 'v1') {
    errors.push('version must be v1')
  }
  if (!Array.isArray(document.hooks)) {
    errors.push('hooks must be an array')
    return errors
  }

  for (const [index, hook] of document.hooks.entries()) {
    const prefix = `hooks[${index}]`
    if (!hook || typeof hook !== 'object' || Array.isArray(hook)) {
      errors.push(`${prefix} must be an object`)
      continue
    }
    if (typeof hook.name !== 'string' || !hook.name) {
      errors.push(`${prefix}.name must be a non-empty string`)
    }
    if (!KIRO_V3_TRIGGERS.has(hook.trigger)) {
      errors.push(`${prefix}.trigger is invalid`)
    }
    if (hook.matcher !== undefined && typeof hook.matcher !== 'string') {
      errors.push(`${prefix}.matcher must be a string`)
    }

    const action = hook.action
    if (!action || typeof action !== 'object' || Array.isArray(action)) {
      errors.push(`${prefix}.action must be an object`)
      continue
    }
    if (action.type === 'command') {
      if (typeof action.command !== 'string' || !action.command) {
        errors.push(`${prefix}.action.command must be a non-empty string`)
      }
    } else if (action.type === 'agent') {
      if (typeof action.prompt !== 'string' || !action.prompt) {
        errors.push(`${prefix}.action.prompt must be a non-empty string`)
      }
    } else {
      errors.push(`${prefix}.action.type must be command or agent`)
    }
  }

  return errors
}
