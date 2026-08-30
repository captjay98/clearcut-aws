import { chromium } from "playwright";

async function test() {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  page.on("console", (msg) => console.log(`[BROWSER CONSOLE ${msg.type()}]:`, msg.text()));
  page.on("pageerror", (err) => console.error("[BROWSER PAGE ERROR]:", err));

  console.log("Navigating to http://127.0.0.1:5173/#workspace...");
  await page.goto("http://127.0.0.1:5173/#workspace");
  await page.waitForTimeout(1000);

  await browser.close();
}

test();
