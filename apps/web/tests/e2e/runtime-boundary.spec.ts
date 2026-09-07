import { test, expect } from "@playwright/test";

test.describe("Runtime and Architecture Boundary", () => {
  test("root renders React application, no hash routes, no legacy localStorage", async ({ page }) => {
    await page.goto("/app/");

    // 1. Verify React root marker is present
    const root = page.locator("[data-clearcut-app='react']").first();
    await expect(root).toBeVisible();

    // 2. Check URL is not using hash routing
    expect(page.url()).not.toContain("#");

    // 3. Assert no legacy storage keys exist
    const storageKeys = await page.evaluate(() => Object.keys(localStorage));
    expect(storageKeys).not.toContain("clearcut-flow-state");
    expect(storageKeys).not.toContain("clearcut-flow-state-v2");

    // 4. Navigate to a typed route under the workspace base
    await page.goto("/app/auth/sign-in");
    await expect(page).toHaveURL(/\/app\/auth\/sign-in$/);
    expect(page.url()).not.toContain("#");

    // 5. Refresh typed route and verify it remains without hash routing or legacy storage
    await page.reload();
    await expect(page).toHaveURL(/\/app\/auth\/sign-in$/);
    expect(page.url()).not.toContain("#");

    const refreshedStorageKeys = await page.evaluate(() => Object.keys(localStorage));
    expect(refreshedStorageKeys).not.toContain("clearcut-flow-state");
    expect(refreshedStorageKeys).not.toContain("clearcut-flow-state-v2");
  });
});
