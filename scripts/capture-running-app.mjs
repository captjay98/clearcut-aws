import { chromium } from "playwright";
import path from "path";

const APP_URL = "http://127.0.0.1:5173";
const OUT_DIR = "/Users/captjay98/.gemini/antigravity/brain/e359994a-e7a2-4bef-9215-4e6a4f23a9fd/screenshots-app";

async function main() {
  console.log(`Connecting to live running app at ${APP_URL}...`);
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  const surfaces = [
    { hash: "#project", name: "01_live_app_project_overview" },
    { hash: "#workspace", name: "02_live_app_workspace_screenplay" },
    { hash: "#items", name: "03_live_app_items_worklist" },
    { hash: "#item", name: "04_live_app_item_detail_claims" },
    { hash: "#versions", name: "05_live_app_script_versions" },
    { hash: "#watch", name: "06_live_app_evidence_watch" },
    { hash: "#report", name: "07_live_app_clearance_report" },
    { hash: "#projects", name: "08_live_app_projects_list" },
    { hash: "#notifications", name: "09_live_app_notifications_inbox" },
    { hash: "#records", name: "10_live_app_records_ledger" },
    { hash: "#trust", name: "11_live_app_ai_trust_rubric" },
    { hash: "#team", name: "12_live_app_team_permissions" },
    { hash: "#settings", name: "13_live_app_settings_retention" },
    { hash: "#new", name: "14_live_app_new_clearance_wizard" },
    { hash: "#auth", name: "15_live_app_sign_in" },
    { hash: "#onboarding", name: "16_live_app_onboarding" },
    { hash: "#invite", name: "17_live_app_invite" },
  ];

  for (const s of surfaces) {
    console.log(`Navigating to ${s.hash} on LIVE RUNNING APP -> ${s.name}...`);
    await page.goto(`${APP_URL}/${s.hash}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(600);

    const outPath = path.join(OUT_DIR, `${s.name}.png`);
    await page.screenshot({ path: outPath, fullPage: false });
    console.log(`📸 Saved live screenshot: ${outPath}`);
  }

  await browser.close();
  console.log("✨ All live running app screenshots captured!");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
