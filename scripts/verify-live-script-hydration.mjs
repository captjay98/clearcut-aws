import { chromium } from "playwright";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const scriptRequests = [];
  page.on("request", (req) => {
    if (req.url().includes("/script")) {
      scriptRequests.push({ url: req.url(), method: req.method() });
    }
  });

  const consoleLogs = [];
  page.on("console", (msg) => {
    if (msg.text().includes("[ClearCut")) {
      consoleLogs.push(msg.text());
    }
  });

  console.log("Navigating to live workspace at http://127.0.0.1:5173/#workspace...");
  await page.goto("http://127.0.0.1:5173/#workspace", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);

  console.log("\n--- Script Endpoint Requests Captured ---");
  scriptRequests.forEach((req) => console.log(`📡 [${req.method}] ${req.url}`));

  console.log("\n--- Console Logs Captured ---");
  consoleLogs.forEach((log) => console.log(`📝 ${log}`));

  // Check that the script stage rendered the scene headings from PostgreSQL
  const sceneHeader = await page.locator("text=INT. VELEZ CAMERA SHOP — DUSK").first();
  const isVisible = await sceneHeader.isVisible();
  console.log(`\nScene Heading 'INT. VELEZ CAMERA SHOP — DUSK' visible: ${isVisible}`);

  await browser.close();
}

main().catch((err) => {
  console.error("Verification failed:", err);
  process.exit(1);
});
