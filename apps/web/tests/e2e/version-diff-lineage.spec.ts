import { test, expect } from "@playwright/test";

test.describe("Version Diffing, Rescan Triggers, and Lineage Views", () => {
  test("version diff viewer, rescan trigger, and item lineage trace", async ({ page }) => {
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/versions");

    // 1. Check version diff viewer container
    const diffViewer = page.locator("[data-testid='script-diff-viewer']");
    await expect(diffViewer).toBeVisible();

    // 2. Check added, modified, removed item categorization
    const diffSummary = page.locator("[data-testid='diff-summary-card']");
    await expect(diffSummary).toBeVisible();

    // 3. Check rescan trigger button
    const rescanBtn = page.locator("button:has-text('Trigger Rescan'), button:has-text('Rescan Revision')").first();
    await expect(rescanBtn).toBeVisible();
    await rescanBtn.click();

    // 4. Check item lineage history drawer/section
    const lineageSection = page.locator("[data-testid='item-lineage-section']");
    await expect(lineageSection).toBeVisible();
  });
});
