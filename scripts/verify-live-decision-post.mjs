import { chromium } from "playwright";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  let postRequest = null;
  page.on("request", (req) => {
    if (req.url().includes("/decisions") && req.method() === "POST") {
      postRequest = { url: req.url(), method: req.method(), postData: req.postData() };
    }
  });

  const consoleLogs = [];
  page.on("console", (msg) => {
    if (msg.text().includes("[ClearCut Live API")) {
      consoleLogs.push(msg.text());
    }
  });

  console.log("Navigating to live item detail page at http://127.0.0.1:5173/#item?id=CC-101...");
  await page.goto("http://127.0.0.1:5173/#item?id=CC-101", { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  console.log("Clicking 'Verify this source' button...");
  const verifyBtn = page.locator('button[data-action="evidence-dialog"][data-decision="accepted"]');
  if (await verifyBtn.isVisible()) {
    await verifyBtn.click();
    await page.waitForTimeout(400);

    const confirmBtn = page.locator('button[data-action="confirm-evidence"]');
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
      await page.waitForTimeout(600);
    }
  }

  console.log("\n--- POST Request Captured ---");
  console.log(postRequest);

  console.log("\n--- Console Logs Captured ---");
  consoleLogs.forEach((l) => console.log("📝", l));

  await browser.close();
}

main().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
