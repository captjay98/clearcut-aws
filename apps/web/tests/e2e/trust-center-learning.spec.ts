import { test, expect } from "@playwright/test";

test.describe("Trust Center, Evaluation Rubric, and Learning Gates", () => {
  test("10-dimension rubric visualizer, protected configs, and candidate gates", async ({ page }) => {
    await page.goto("/o/northlight/trust");

    // 1. Check 10-dimension rubric visualizer
    const rubricVisualizer = page.locator("[data-testid='rubric-visualizer']");
    await expect(rubricVisualizer).toBeVisible();

    const dimensionCards = page.locator("[data-testid='rubric-dimension-card']");
    expect(await dimensionCards.count()).toBe(10);

    // 2. Check protected configurations card
    const protectedConfigCard = page.locator("[data-testid='protected-config-card']");
    await expect(protectedConfigCard).toBeVisible();

    // 3. Check learning candidates table
    const candidatesTable = page.locator("[data-testid='learning-candidates-table']");
    await expect(candidatesTable).toBeVisible();

    // 4. Check promote / rollback gate button
    const promoteBtn = page.locator("button:has-text('Promote Candidate')").first();
    if (await promoteBtn.isVisible()) {
      await promoteBtn.click();
    }
  });
});
