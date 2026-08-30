import { chromium } from "playwright";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const networkRequests = [];
  page.on("request", (req) => {
    if (req.url().includes(":8000/api/v1/")) {
      networkRequests.push({ url: req.url(), method: req.method() });
    }
  });

  const consoleLogs = [];
  page.on("console", (msg) => {
    if (msg.text().includes("[ClearCut")) {
      consoleLogs.push(msg.text());
    }
  });

  console.log("Navigating to live app at http://127.0.0.1:5173/#project...");
  await page.goto("http://127.0.0.1:5173/#project", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);

  console.log("Navigating to #items...");
  await page.goto("http://127.0.0.1:5173/#items", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  console.log("Navigating to #watch...");
  await page.goto("http://127.0.0.1:5173/#watch", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  console.log("Navigating to #records...");
  await page.goto("http://127.0.0.1:5173/#records", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  console.log("Navigating to #trust...");
  await page.goto("http://127.0.0.1:5173/#trust", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  console.log("\n--- Network Requests Captured ---");
  networkRequests.forEach((req) => console.log(`📡 [${req.method}] ${req.url}`));

  console.log("\n--- Console Logs Captured ---");
  consoleLogs.forEach((log) => console.log(`📝 ${log}`));

  await browser.close();
}

main().catch((err) => {
  console.error("Verification failed:", err);
  process.exit(1);
});
