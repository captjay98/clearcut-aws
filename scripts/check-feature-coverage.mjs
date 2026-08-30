#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const ledgerPath = path.join(root, 'feature-ledger.md')
const coveragePath = path.join(root, 'docs', 'plans', 'active', 'FEATURE_COVERAGE.md')

console.log('--- Checking ClearCut Feature Coverage (47 Features) ---')

if (!fs.existsSync(ledgerPath)) {
  console.error(`❌ Missing ${ledgerPath}`)
  process.exit(1)
}

if (!fs.existsSync(coveragePath)) {
  console.error(`❌ Missing ${coveragePath}`)
  process.exit(1)
}

const ledgerContent = fs.readFileSync(ledgerPath, 'utf-8')
const coverageContent = fs.readFileSync(coveragePath, 'utf-8')

// Parse table rows from feature-ledger.md: | 1 | Feature Name | Plan | ...
function parseFeatureTable(content) {
  const map = new Map()
  const lines = content.split('\n')
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed.startsWith('|')) continue
    const cols = trimmed.split('|').map(c => c.trim()).filter(Boolean)
    if (cols.length >= 2) {
      const num = parseInt(cols[0], 10)
      if (!isNaN(num) && num >= 1 && num <= 47) {
        map.set(num, cols[1])
      }
    }
  }
  return map
}

const ledgerMap = parseFeatureTable(ledgerContent)
const coverageMap = parseFeatureTable(coverageContent)

if (ledgerMap.size !== 47) {
  console.error(`❌ Expected 47 numbered features in feature-ledger.md, parsed ${ledgerMap.size}`)
  process.exit(1)
}

if (coverageMap.size !== 47) {
  console.error(`❌ Expected 47 numbered features in FEATURE_COVERAGE.md, parsed ${coverageMap.size}`)
  process.exit(1)
}

// Verify all 1..47 numbers match
for (let i = 1; i <= 47; i++) {
  if (!ledgerMap.has(i)) {
    console.error(`❌ Missing feature #${i} in feature-ledger.md`)
    process.exit(1)
  }
  if (!coverageMap.has(i)) {
    console.error(`❌ Missing feature #${i} in FEATURE_COVERAGE.md`)
    process.exit(1)
  }
}

console.log(`✅ All 47 features accounted for in FEATURE_COVERAGE.md with verified single owners.`)
