#!/usr/bin/env bun
import { readFileSync, existsSync } from "node:fs";

console.log("🔍 Verifying ClearCut Submission Integrity...");

const requiredFiles = [
  "docs/submission/manifest.yaml",
  "docs/submission/demo-script.md",
  "docs/submission/devpost-copy.md",
  "docs/submission/limitations.md",
  "demo/original-screenplay/the_last_reel.fountain",
  "demo/runbook.md",
  "LICENSE",
  "README.md",
];

let allPassed = true;

for (const file of requiredFiles) {
  if (!existsSync(file)) {
    console.error(`❌ Missing required submission file: ${file}`);
    allPassed = false;
  } else {
    console.log(`✅ Found: ${file}`);
  }
}

if (!allPassed) {
  process.exit(1);
}

const { execSync } = await import("node:child_process");
try {
  console.log("🔍 Running no-legacy runtime gate...");
  execSync("node scripts/check-no-legacy-runtime.mjs", { stdio: "inherit" });
} catch (err) {
  console.error("❌ No-legacy runtime verification failed.");
  process.exit(1);
}

console.log("🎉 All submission artifacts verified successfully!");
