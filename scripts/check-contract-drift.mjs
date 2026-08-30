#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import { execSync } from 'node:child_process'
import { load } from 'js-yaml'

const root = process.cwd()
const openapiPath = path.join(root, 'packages', 'contracts', 'openapi.yaml')
const tsPath = path.join(root, 'packages', 'contracts', 'generated', 'typescript', 'index.ts')
const pyPath = path.join(root, 'packages', 'contracts', 'generated', 'python', '__init__.py')

console.log('--- Checking ClearCut Contract Integrity & Drift ---')

// 1. Validate OpenAPI file exists and parses
if (!fs.existsSync(openapiPath)) {
  console.error(`❌ openapi.yaml not found at ${openapiPath}`)
  process.exit(1)
}

try {
  const content = fs.readFileSync(openapiPath, 'utf-8')
  const spec = load(content)
  if (!spec || typeof spec !== 'object' || !spec.openapi) {
    throw new Error('Invalid OpenAPI structure')
  }
  console.log(`✅ openapi.yaml is valid OpenAPI ${spec.openapi} specification.`)
} catch (err) {
  console.error(`❌ Failed to parse openapi.yaml: ${err.message}`)
  process.exit(1)
}

// 2. Check generated files exist and have headers
for (const filePath of [tsPath, pyPath]) {
  if (!fs.existsSync(filePath)) {
    console.error(`❌ Generated client file missing: ${filePath}`)
    process.exit(1)
  }
  const content = fs.readFileSync(filePath, 'utf-8')
  if (!content.includes('AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY')) {
    console.error(`❌ Missing auto-generated header in ${filePath}`)
    process.exit(1)
  }
}
console.log('✅ Generated client headers verified.')

// 3. Check drift by re-running generator
const tsBefore = fs.readFileSync(tsPath, 'utf-8')
const pyBefore = fs.readFileSync(pyPath, 'utf-8')

execSync('bun scripts/generate-clients.mjs', { stdio: 'inherit' })

const tsAfter = fs.readFileSync(tsPath, 'utf-8')
const pyAfter = fs.readFileSync(pyPath, 'utf-8')

if (tsBefore !== tsAfter || pyBefore !== pyAfter) {
  console.error('❌ Contract drift detected! Generated clients were out of sync with openapi.yaml.')
  process.exit(1)
}

console.log('✅ Zero contract drift verified.')
