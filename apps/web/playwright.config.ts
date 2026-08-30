import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: "http://localhost:3000",
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
      use: { ...devices["iPhone 13"] },
    },
  ],
});
