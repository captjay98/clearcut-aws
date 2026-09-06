#!/usr/bin/env bun
import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import yaml from "js-yaml";

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

function argumentValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isUnavailable(value) {
  return (
    typeof value !== "string" ||
    value.trim() === "" ||
    /^(?:HEAD|TBD|TODO|placeholder|not-available|not-built|not-deployed|not-recorded-dirty-worktree)$/i.test(
      value.trim(),
    ) ||
    /^<.*>$/.test(value.trim())
  );
}

function hasExactImageDigest(value, service) {
  return new RegExp(`^${service}@sha256:[a-f0-9]{64}$`).test(value ?? "");
}

function collectForbiddenPlaceholders(value, path = "submission") {
  if (Array.isArray(value)) {
    return value.flatMap((entry, index) =>
      collectForbiddenPlaceholders(entry, `${path}[${index}]`),
    );
  }
  if (isRecord(value)) {
    return Object.entries(value).flatMap(([key, entry]) =>
      collectForbiddenPlaceholders(entry, `${path}.${key}`),
    );
  }
  if (
    typeof value === "string" &&
    (/^(?:HEAD|TBD|TODO)$/i.test(value.trim()) ||
      /placeholder/i.test(value) ||
      /^<[^>]+>$/.test(value.trim()))
  ) {
    return [path];
  }
  return [];
}

function validateManifest(document, licenseText, readmeText) {
  const errors = [];
  const submission = document?.submission;
  if (!isRecord(submission)) {
    return ["manifest must contain a submission mapping"];
  }

  const placeholderPaths = collectForbiddenPlaceholders(submission);
  if (placeholderPaths.length > 0) {
    errors.push(
      `manifest contains forbidden placeholder values at: ${placeholderPaths.join(", ")}`,
    );
  }

  if (submission.license !== "MIT" || !licenseText.startsWith("MIT License")) {
    errors.push("submission.license must match the repository MIT LICENSE");
  }
  if (
    !readmeText.includes("MIT License") ||
    readmeText.includes("Apache-2.0")
  ) {
    errors.push("README license must match the repository MIT LICENSE");
  }

  const legalBoundary = submission.legal_boundary ?? "";
  if (
    !/does not provide legal advice/i.test(legalBoundary) ||
    !/final legal clearance/i.test(legalBoundary)
  ) {
    errors.push(
      'submission.legal_boundary must state both "does not provide legal advice" and "final legal clearance"',
    );
  }

  const revision = submission.revision ?? {};
  const exactRevision = /^[a-f0-9]{40}$/.test(revision.git_sha ?? "");
  const explicitUnrecordedRevision =
    submission.verdict === "NO-GO" &&
    revision.git_sha === "not-recorded-dirty-worktree" &&
    revision.clean_tree === false &&
    revision.remote_parity === "not-verified";
  if (!exactRevision && !explicitUnrecordedRevision) {
    errors.push("revision.git_sha must be an exact 40-character commit SHA");
  }

  const adapters = submission.production_adapters ?? {};
  const runtimeProof = submission.runtime_proof ?? {};
  if (
    adapters.monitor_adapter !== "not-enabled" &&
    (adapters.monitor_decision !== "GO" ||
      isUnavailable(runtimeProof.parallel_monitor_id))
  ) {
    errors.push(
      "Parallel Monitor must remain not-enabled without a recorded GO decision and deployed proof",
    );
  }

  if (!Array.isArray(submission.external_blockers)) {
    errors.push("submission.external_blockers must be a list");
  }

  if (submission.verdict === "NO-GO") {
    if (submission.external_blockers?.length === 0) {
      errors.push("NO-GO requires at least one explicit external blocker");
    }
  } else if (submission.verdict === "GO") {
    const imageDigests = submission.image_digests ?? {};
    const hosted = submission.hosted_services ?? {};
    const video = submission.video ?? {};
    const compliance = submission.compliance_correspondence ?? {};
    const goEvidenceIsComplete =
      revision.clean_tree === true &&
      revision.remote_parity === "verified" &&
      hasExactImageDigest(imageDigests.site, "clearcut-site") &&
      hasExactImageDigest(imageDigests.web, "clearcut-web") &&
      hasExactImageDigest(imageDigests.api, "clearcut-api") &&
      [hosted.site, hosted.web, hosted.api].every(
        (value) => typeof value === "string" && /^https:\/\//.test(value),
      ) &&
      !isUnavailable(runtimeProof.gemini_trace_id) &&
      !isUnavailable(runtimeProof.parallel_search_id) &&
      !isUnavailable(runtimeProof.parallel_extract_id) &&
      typeof video.url === "string" &&
      /^https:\/\//.test(video.url) &&
      video.duration_seconds > 0 &&
      video.duration_seconds <= 180 &&
      video.visibility === "public" &&
      compliance.status === "verified" &&
      !isUnavailable(compliance.reference) &&
      submission.external_blockers?.length === 0;

    if (!goEvidenceIsComplete) {
      errors.push(
        "GO requires independently verifiable evidence for every release gate",
      );
    }
  } else {
    errors.push('submission.verdict must be either "GO" or "NO-GO"');
  }

  return errors;
}

function verifyRequiredFiles() {
  let passed = true;
  for (const file of requiredFiles) {
    if (!existsSync(file)) {
      console.error(`❌ Missing required submission file: ${file}`);
      passed = false;
    } else {
      console.log(`✅ Found: ${file}`);
    }
  }
  return passed;
}

console.log("🔍 Verifying ClearCut Submission Integrity...");

if (!verifyRequiredFiles()) {
  process.exit(1);
}

const manifestPath = resolve(
  argumentValue("--manifest") ?? "docs/submission/manifest.yaml",
);
if (!existsSync(manifestPath)) {
  console.error(`❌ Manifest does not exist: ${manifestPath}`);
  process.exit(1);
}

let document;
try {
  document = yaml.load(readFileSync(manifestPath, "utf8"));
} catch (error) {
  console.error(`❌ Manifest YAML is invalid: ${error.message}`);
  process.exit(1);
}

const readmePath = resolve(argumentValue("--readme") ?? "README.md");
if (!existsSync(readmePath)) {
  console.error(`❌ README does not exist: ${readmePath}`);
  process.exit(1);
}

const errors = validateManifest(
  document,
  readFileSync("LICENSE", "utf8"),
  readFileSync(readmePath, "utf8"),
);
if (errors.length > 0) {
  for (const error of errors) {
    console.error(`❌ ${error}`);
  }
  process.exit(1);
}
console.log(
  `✅ Submission manifest is truthful and internally consistent: ${manifestPath}`,
);

try {
  console.log("🔍 Running no-legacy runtime gate...");
  execSync("node scripts/check-no-legacy-runtime.mjs", { stdio: "inherit" });
} catch {
  console.error("❌ No-legacy runtime verification failed.");
  process.exit(1);
}

console.log("🎉 All submission artifacts verified successfully!");
