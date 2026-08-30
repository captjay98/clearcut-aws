import { chromium } from "playwright";
import http from "http";
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "/Users/captjay98/.gemini/antigravity/brain/e359994a-e7a2-4bef-9215-4e6a4f23a9fd/screenshots";
const FLOW_DIR = path.resolve("misc/clearcut-flow");

// Simple static server
const server = http.createServer((req, res) => {
  let reqPath = req.url.split("?")[0];
  if (reqPath === "/") reqPath = "/index.html";
  const filePath = path.join(FLOW_DIR, reqPath);

  if (fs.existsSync(filePath)) {
    const ext = path.extname(filePath);
    const contentType =
      ext === ".html" ? "text/html" :
      ext === ".js" ? "text/javascript" :
      ext === ".css" ? "text/css" :
      ext === ".svg" ? "image/svg+xml" : "application/octet-stream";
    res.writeHead(200, { "Content-Type": contentType });
    fs.createReadStream(filePath).pipe(res);
  } else {
    res.writeHead(404);
    res.end();
  }
});

server.listen(4173, async () => {
  console.log("Local server running at http://localhost:4173");

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  const surfaces = [
    { hash: "#marketing", name: "01_marketing_landing" },
    { hash: "#features", name: "02_features_overview" },
    { hash: "#docs", name: "03_documentation" },
    { hash: "#auth", name: "04_sign_in" },
    { hash: "#onboarding", name: "05_onboarding_organization" },
    { hash: "#projects", name: "06_projects_list" },
    { hash: "#new", name: "07_screenplay_ingestion_wizard" },
    { hash: "#project", name: "08_project_overview_breakdown" },
    { hash: "#workspace", name: "09_split_screenplay_workspace" },
    { hash: "#items", name: "10_clearance_item_worklist" },
    { hash: "#item", name: "11_item_detail_cited_claims" },
    { hash: "#versions", name: "12_script_revisions_diff_viewer" },
    { hash: "#watch", name: "13_evidence_watch_cadence" },
    { hash: "#report", name: "14_pre_clearance_dossier_report" },
    { hash: "#team", name: "15_team_permissions" },
    { hash: "#settings", name: "16_settings_retention_deletion" },
    { hash: "#trust", name: "17_ai_trust_10_rubric" },
    { hash: "#records", name: "18_audit_ledger_tool_calls" },
    { hash: "#invite", name: "19_invitation_resolution" },
  ];

  for (const s of surfaces) {
    console.log(`Navigating to ${s.hash} -> ${s.name}...`);
    await page.goto(`http://localhost:4173/${s.hash}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(400);

    const outPath = path.join(ARTIFACT_DIR, `${s.name}.png`);
    await page.screenshot({ path: outPath, fullPage: false });
    console.log(`📸 Saved screenshot: ${outPath}`);
  }

  await browser.close();
  server.close();
  console.log("✨ All surface screenshots captured successfully!");
  process.exit(0);
});
