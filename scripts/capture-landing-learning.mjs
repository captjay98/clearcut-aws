import { chromium } from "playwright";
import { join } from "path";

const APP_DIR = "/Users/captjay98/.gemini/antigravity/brain/e359994a-e7a2-4bef-9215-4e6a4f23a9fd/screenshots-landing";

const SURFACES = [
  { hash: "#marketing", name: "01_marketing_landing_main" },
  { hash: "#marketing-a", name: "02_marketing_landing_polished_oss" },
  { hash: "#marketing-b", name: "03_marketing_landing_dev_first" },
  { hash: "#marketing-c", name: "04_marketing_landing_hybrid" },
  { hash: "#features", name: "05_features_matrix" },
  { hash: "#docs", name: "06_documentation_and_contracts" },
  { hash: "#trust", name: "07_ai_trust_and_learning_governance" },
];

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  console.log("Capturing landing and learning surfaces from http://127.0.0.1:5173...");

  for (const s of SURFACES) {
    const url = `http://127.0.0.1:5173/${s.hash}`;
    console.log(`Navigating to ${url} -> ${s.name}...`);
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForTimeout(600);

    const outPath = join(APP_DIR, `${s.name}.png`);
    await page.screenshot({ path: outPath, fullPage: false });
    console.log(`📸 Saved screenshot: ${outPath}`);
  }

  // Also capture full-page version of main marketing landing
  await page.goto("http://127.0.0.1:5173/#marketing", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(APP_DIR, "01_marketing_landing_fullpage.png"), fullPage: true });

  await browser.close();
  console.log("✨ All landing & learning screenshots captured!");
}

main().catch((err) => {
  console.error("Capture failed:", err);
  process.exit(1);
});
