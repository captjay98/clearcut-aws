#!/usr/bin/env bun
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'

function block(message) {
  process.stderr.write(`kiro-hook-adapter: ${message}\n`)
  process.exit(2)
}

function requireRecord(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    block(`${label} must be a JSON object`)
  }
  return value
}

function main() {
  const hookId = process.argv[2]
  if (!hookId) block('hook id is required')

  let payload
  try {
    const input = fs.readFileSync(0, 'utf8').trim()
    payload = requireRecord(input ? JSON.parse(input) : {}, 'event payload')
  } catch (error) {
    block(`invalid event JSON (${error.message})`)
  }

  const hooksPath = path.join(process.cwd(), '.agents', 'hooks', 'hooks.json')
  let hooksDocument
  try {
    hooksDocument = requireRecord(JSON.parse(fs.readFileSync(hooksPath, 'utf8')), 'hooks document')
  } catch (error) {
    block(`cannot read canonical hooks (${error.message})`)
  }
  if (!Array.isArray(hooksDocument.hooks)) block('canonical hooks must contain hooks[]')

  const hook = hooksDocument.hooks.find((candidate) => candidate?.id === hookId)
  if (!hook || typeof hook.command !== 'string' || !hook.command.trim()) {
    block(`unknown or invalid hook '${hookId}'`)
  }

  const rawToolInput = payload.toolInput ?? payload.tool_input ?? payload.input ?? {}
  const toolInput = requireRecord(rawToolInput, 'tool input')
  const command = String(toolInput.command ?? payload.command ?? '')
  const filePath = String(
    toolInput.path ??
    toolInput.file_path ??
    toolInput.filePath ??
    payload.path ??
    payload.file_path ??
    payload.filePath ??
    '',
  )
  const normalized = JSON.stringify({
    ...payload,
    tool_input: {
      ...toolInput,
      command,
      file_path: filePath,
    },
  }) + '\n'

  const result = spawnSync('/bin/sh', ['-c', hook.command], {
    cwd: process.cwd(),
    encoding: 'utf8',
    env: {
      ...process.env,
      TOOL_INPUT_COMMAND: command,
      TOOL_INPUT_FILE_PATH: filePath,
    },
    input: normalized,
  })
  if (result.error) block(`hook execution failed (${result.error.message})`)

  if (result.stdout) process.stdout.write(result.stdout)
  if (result.stderr) process.stderr.write(result.stderr)
  process.exit(result.status === 0 ? 0 : 2)
}

try {
  main()
} catch (error) {
  block(`internal failure (${error.message})`)
}
