#!/usr/bin/env node
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()

function checkCommand(cmd, regex, name) {
  try {
    const output = execSync(cmd, { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
    const match = output.match(regex)
    if (!match) {
      console.error(`❌ ${name} version check failed: "${output}" did not match ${regex}`)
      process.exit(1)
    }
    console.log(`✅ ${name} verified: ${match[0]}`)
  } catch (err) {
    console.error(`❌ ${name} command (${cmd}) failed: ${err.message}`)
    process.exit(1)
  }
}

console.log('--- Checking ClearCut Workspace Toolchains ---')

// 1. Check pnpm
checkCommand('pnpm --version', /^(9|10)\.\d+\.\d+/, 'pnpm')

// 2. Check uv
checkCommand('uv --version', /^uv \d+\.\d+\.\d+/, 'uv')

// 3. Check node
checkCommand('node --version', /^v(20|22|24|26)\.\d+\.\d+/, 'node')

// 4. Check bun
checkCommand('bun --version', /^\d+\.\d+\.\d+/, 'bun')

// 5. Verify single lockfile rule
const bannedLocks = ['package-lock.json', 'yarn.lock', 'poetry.lock', 'Pipfile.lock']
for (const lock of bannedLocks) {
  if (fs.existsSync(path.join(root, lock))) {
    console.error(`❌ Found forbidden lockfile: ${lock}`)
    process.exit(1)
  }
}

console.log('✅ All package manager and toolchain assertions passed.')
