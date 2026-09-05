import { defineConfig, devices } from "@playwright/test";

const runId = `${process.pid}-${Date.now()}`;
const apiDatabaseUrl = `sqlite+aiosqlite:////tmp/clearcut-playwright-${runId}.db`;
const apiStoragePath = `/tmp/clearcut-playwright-storage-${runId}`;
const reuseExistingServers = process.env.CLEARCUT_E2E_REUSE_SERVERS === "true";
const apiPort = Number(process.env.CLEARCUT_E2E_API_PORT ?? 28_080);
const webPort = Number(process.env.CLEARCUT_E2E_WEB_PORT ?? 29_000);
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: "html",
  use: {
    baseURL: webUrl,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium-desktop-1440",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "firefox-desktop-1024",
      use: { ...devices["Desktop Firefox"], viewport: { width: 1024, height: 768 } },
    },
    {
      name: "webkit-tablet-768",
      use: { ...devices["Desktop Safari"], viewport: { width: 768, height: 1024 } },
    },
    {
      name: "mobile-375",
      use: { ...devices["iPhone 13"], viewport: { width: 375, height: 667 } },
    },
  ],
  webServer: [
    {
      command:
        "uv --directory ../.. run python -c \"import asyncio; from clearcut.init_db import init_and_seed_db; asyncio.run(init_and_seed_db(seed_if_empty=False))\" && " +
        `uv --directory ../.. run uvicorn e2e_api:app --app-dir apps/web/tests/support --host 127.0.0.1 --port ${apiPort}`,
      url: `${apiUrl}/healthz`,
      reuseExistingServer: reuseExistingServers,
      timeout: 120_000,
      env: {
        ...process.env,
        DATABASE_URL: apiDatabaseUrl,
        CLEARCUT_STORAGE_PATH: apiStoragePath,
        CLEARCUT_SEED_DEMO: "false",
        CLEARCUT_JOB_DISPATCH_MODE: "local",
        CLEARCUT_API_WORKERS: "1",
      },
    },
    {
      command: `pnpm dev --host 127.0.0.1 --port ${webPort}`,
      url: webUrl,
      reuseExistingServer: reuseExistingServers,
      timeout: 120_000,
      env: {
        ...process.env,
        CLEARCUT_API_PROXY_TARGET: apiUrl,
      },
    },
  ],
});
