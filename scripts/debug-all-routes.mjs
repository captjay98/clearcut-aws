import { chromium } from "playwright";

const routes = [
  "#project", "#workspace", "#items", "#item", "#versions", "#watch", "#report",
  "#projects", "#notifications", "#records", "#trust", "#team", "#settings", "#new",
  "#auth", "#onboarding", "#invite"
];

async function check() {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  page.on("pageerror", (err) => console.error(`[PAGE ERROR on ${page.url()}]:`, err.message));

  for (const r of routes) {
    console.log(`Checking ${r}...`);
    await page.goto(`http://127.0.0.1:5173/${r}`);
    await page.waitForTimeout(500);
  }

  await browser.close();
  console.log("Done checking all routes!");
}

check();
