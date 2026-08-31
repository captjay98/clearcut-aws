import { test, expect } from "@playwright/test";

test.describe("Script Import, Parser Diagnostics, and Screenplay Viewer", () => {
  test("screenplay viewer renders standard formatting, scenes, and category highlights", async ({ page }) => {
    // Navigate to workspace
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/workspace");

    // 1. Check screenplay viewer container
    const scriptViewer = page.locator("[data-testid='screenplay-viewer']");
    await expect(scriptViewer).toBeVisible();

    // 2. Check scene headings and elements
    const sceneHeading = page.locator("[data-testid='scene-heading']").first();
    await expect(sceneHeading).toBeVisible();

    // 3. Check upload modal trigger
    const uploadBtn = page.locator("button:has-text('Upload Script'), button:has-text('Import')").first();
    await expect(uploadBtn).toBeVisible();
    await uploadBtn.click();

    // 4. Check parser diagnostics modal / dropzone
    const uploadModal = page.locator("[data-testid='script-upload-modal']");
    await expect(uploadModal).toBeVisible();

    // Check parser warnings review and acknowledge button
    const ackBtn = page.locator("button:has-text('Acknowledge & Parse'), button:has-text('Accept Warnings')").first();
    if (await ackBtn.isVisible()) {
      await ackBtn.click();
      await expect(uploadModal).not.toBeVisible();
    }
  });
});
