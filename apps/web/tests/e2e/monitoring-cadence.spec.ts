import { test, expect } from "@playwright/test";

test.describe("Monitoring, Watch Cadence, and Change Detection", () => {
  test("cadence selector, sources inventory, manual check trigger, and signals", async ({ page }) => {
    await page.goto("/app/o/northlight/projects/018f0000-0000-7000-8000-000000000101/watch");

    // 1. Check cadence selector
    const cadenceSelect = page.locator("[data-testid='cadence-selector']");
    await expect(cadenceSelect).toBeVisible();

    // 2. Check monitored sources inventory table
    const sourcesTable = page.locator("[data-testid='monitored-sources-table']");
    await expect(sourcesTable).toBeVisible();

    // 3. Check manual check trigger button
    const triggerBtn = page.locator("button:has-text('Run Immediate Source Check'), button:has-text('Run Check')").first();
    await expect(triggerBtn).toBeVisible();
    await triggerBtn.click();

    // 4. Check change signal cards
    const changeSignals = page.locator("[data-testid='change-signal-card']");
    await expect(changeSignals.first()).toBeVisible();
  });
});
