#!/usr/bin/env bun
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { GENERATED_FILE_TARGETS } from './renderers/common.mjs'

const root = process.cwd()
const tempContainer = fs.mkdtempSync(path.join(os.tmpdir(), 'agents-generated-check-'))
const tempRoot = path.join(tempContainer, path.basename(root))
fs.mkdirSync(tempRoot)

function hashFile(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex')
}

function collectFiles(base) {
  const files = new Map()

  function visit(current) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) visit(full)
      else files.set(path.relative(base, full).replace(/\\/g, '/'), hashFile(full))
    }
  }

  for (const target of GENERATED_FILE_TARGETS) {
    const full = path.join(base, target)
    if (!fs.existsSync(full)) continue
    const stat = fs.lstatSync(full)
    if (stat.isDirectory()) visit(full)
    else files.set(target.replace(/\\/g, '/'), hashFile(full))
  }

  return files
}

function isProjectOwnedExtra(relativePath) {
  if (!/^\.kiro\/hooks\/[^/]+\.json$/.test(relativePath)) return false
  try {
    const parsed = JSON.parse(fs.readFileSync(path.join(root, relativePath), 'utf8'))
    const generated = parsed.hooks?.some((hook) =>
      String(hook?.action?.command ?? '').includes('.agents/scripts/kiro-hook-adapter.mjs'),
    )
    return !generated
  } catch {
    return true
  }
}

try {
  fs.cpSync(path.join(root, '.agents'), path.join(tempRoot, '.agents'), {
    recursive: true,
    filter(source) {
      return path.basename(source) !== 'render-manifest.json'
    },
  })

  for (const name of ['package.json', 'bun.lock', 'bun.lockb']) {
    const source = path.join(root, name)
    if (fs.existsSync(source)) fs.copyFileSync(source, path.join(tempRoot, name))
  }

  const build = spawnSync(process.execPath, ['.agents/scripts/build.mjs'], {
    cwd: tempRoot,
    encoding: 'utf8',
    env: process.env,
  })
  if (build.status !== 0) {
    process.stderr.write(build.stderr || build.stdout || 'generated check build failed\n')
    process.exit(1)
  }

  const expected = collectFiles(tempRoot)
  const actual = collectFiles(root)
  const drift = []

  for (const [relativePath, expectedHash] of expected) {
    const actualHash = actual.get(relativePath)
    if (!actualHash) drift.push(`missing: ${relativePath}`)
    else if (actualHash !== expectedHash) drift.push(`changed: ${relativePath}`)
  }
  for (const relativePath of actual.keys()) {
    if (!expected.has(relativePath) && !isProjectOwnedExtra(relativePath)) {
      drift.push(`stale: ${relativePath}`)
    }
  }

  if (drift.length) {
    process.stderr.write('agents-check-generated: generated outputs are stale\n')
    for (const entry of drift) process.stderr.write(`  ${entry}\n`)
    process.stderr.write('run: bun .agents/scripts/build.mjs\n')
    process.exit(1)
  }

  process.stdout.write('agents-check-generated: ok\n')
} finally {
  fs.rmSync(tempContainer, { recursive: true, force: true })
}
