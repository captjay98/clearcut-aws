#!/usr/bin/env node
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const ROOT = join(__dirname, "..");
const WEB_SRC = join(ROOT, "apps", "web", "src");

console.log("🔍 Checking for legacy runtime and forbidden architectural patterns...");

const violations = [];

// 1. Assert runtime.js does not exist
const legacyRuntime = join(WEB_SRC, "runtime.js");
if (existsSync(legacyRuntime)) {
  violations.push(`apps/web/src/runtime.js exists: legacy runtime file must be deleted.`);
}

// 2. Recursively scan apps/web/src
function scanDir(dir) {
  if (!existsSync(dir)) return;
  const entries = readdirSync(dir);
  for (const entry of entries) {
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      scanDir(fullPath);
    } else if (/\.(ts|tsx|js|jsx)$/.test(entry)) {
      const content = readFileSync(fullPath, "utf-8");
      const relPath = relative(ROOT, fullPath);

      if (content.includes("runtime.js")) {
        violations.push(`${relPath}: references 'runtime.js'`);
      }
      if (content.includes("window.location.hash")) {
        violations.push(`${relPath}: uses 'window.location.hash' (hash routing prohibited)`);
      }
      if (content.includes("tests/fixtures")) {
        violations.push(`${relPath}: imports test fixtures in production source`);
      }
      if (content.includes("clearcut-flow-state")) {
        violations.push(`${relPath}: references 'clearcut-flow-state' (domain local storage prohibited)`);
      }

      // Check for direct fetch() calls outside generated transport/api client directories
      // Allowlist: apps/web/src/api/, apps/web/src/integrations/api/, packages/contracts/generated/
      const isTransportFile = relPath.includes("apps/web/src/api/") || relPath.includes("apps/web/src/integrations/api/");
      if (!isTransportFile && /\bfetch\s*\(/.test(content)) {
        violations.push(`${relPath}: direct 'fetch()' call found; all network calls must use generated client`);
      }
    }
  }
}

if (existsSync(WEB_SRC)) {
  scanDir(WEB_SRC);
}

if (violations.length > 0) {
  console.error("❌ Legacy runtime or boundary violations found:");
  for (const v of violations) {
    console.error(`  - ${v}`);
  }
  process.exit(1);
}

console.log("✅ No legacy runtime or architecture boundary violations detected.");
process.exit(0);
