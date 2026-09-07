import { expect, test } from "@playwright/test";

/**
 * Real authenticated-flow tests. Credentials are created through the public
 * registration boundary so these tests never depend on an implicit demo seed.
 */
test.describe("Authenticated sign-in flow (API-backed)", () => {
  test("invalid credentials surface a typed error and do NOT authenticate", async ({ page }) => {
    await page.goto("/app/auth/sign-in");
    await page.fill("#email", "nobody@example.com");
    await page.fill("#password", "wrong-password");
    await page.click("button[type='submit']");

    await expect(page.locator("[role='alert']")).toBeVisible();
    await expect(page).toHaveURL(/\/auth\/sign-in$/);
  });

  test("a registered credential authenticates after logout", async ({ page }, testInfo) => {
    const email = `sign-in-${Date.now()}-${testInfo.workerIndex}@example.com`;
    const password = "CorrectHorse123!";
    const registration = await page.request.post("/api/v1/users", {
      data: { name: "Sign In User", email, password },
    });
    expect(registration.status()).toBe(201);

    const logout = await page.request.delete("/api/v1/sessions/current");
    expect(logout.status()).toBe(204);

    await page.goto("/app/auth/sign-in");
    await page.fill("#email", email);
    await page.fill("#password", password);

    const sessionResponse = page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/sessions") && response.request().method() === "POST",
    );
    await page.click("button[type='submit']");
    expect((await sessionResponse).status()).toBeLessThan(400);

    await expect(page).toHaveURL(/\/onboarding$/, { timeout: 15_000 });
  });
});
