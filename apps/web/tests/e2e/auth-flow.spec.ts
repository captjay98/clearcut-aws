import { test, expect } from "@playwright/test";

/**
 * Real authenticated-flow test. Unlike the visibility smoke specs, this one:
 *  - drives the actual sign-in form,
 *  - exercises the real POST /api/v1/sessions via the generated client,
 *  - asserts an authenticated outcome (navigation away from /auth/sign-in),
 *  - and asserts the failure path surfaces a typed error rather than a fake success.
 *
 * Requires the API running with the seeded demo credentials
 * (jamie@northlight.example / password123, seeded in clearcut.main lifespan).
 */
test.describe("Authenticated sign-in flow (API-backed)", () => {
  test("invalid credentials surface a typed error and do NOT authenticate", async ({ page }) => {
    await page.goto("/auth/sign-in");
    await page.fill("#email", "nobody@example.com");
    await page.fill("#password", "wrong-password");
    await page.click("button[type='submit']");

    // Error alert must appear; user must remain on the sign-in surface.
    await expect(page.locator("[role='alert']")).toBeVisible();
    await expect(page).toHaveURL(/\/auth\/sign-in$/);
  });

  test("valid demo credentials authenticate and leave the sign-in surface", async ({ page }) => {
    await page.goto("/auth/sign-in");
    await page.fill("#email", "jamie@northlight.example");
    await page.fill("#password", "password123");

    // Assert the real session call actually happens and succeeds.
    const sessionResp = page.waitForResponse(
      (r) => r.url().includes("/api/v1/sessions") && r.request().method() === "POST",
    );
    await page.click("button[type='submit']");
    const resp = await sessionResp;
    expect(resp.status()).toBeLessThan(400);

    // Authenticated outcome: navigated away from the sign-in route.
    await expect(page).not.toHaveURL(/\/auth\/sign-in$/, { timeout: 15_000 });
  });
});
