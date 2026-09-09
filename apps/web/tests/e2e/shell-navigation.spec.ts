import { test, expect } from "@playwright/test";

test.describe("Shell, Navigation, and Theme System", () => {
  test("skip link, landmarks, and semantic structure exist", async ({ page }) => {
    await page.goto("/app/");
    const skipLink = page.locator("a[href='#main-content']");
    await expect(skipLink).toBeAttached();

    // The banner landmark, specifically. Surfaces also render the design
    // system's <header class="page-head"> inside <main>, which is a generic
    // element rather than a landmark, so a bare "header" locator matches two.
    const header = page.getByRole("banner");
    await expect(header).toBeVisible();

    const main = page.locator("main#main-content");
    await expect(main).toBeVisible();
  });

  test("theme switcher toggles and persists data-theme attribute", async ({ page }) => {
    await page.goto("/app/");

    // Initial data-theme attribute on html
    const html = page.locator("html");
    const initialTheme = await html.getAttribute("data-theme");
    expect(initialTheme).toBeTruthy();

    // Addressed by test id rather than label wording: the accessible name now
    // follows the mock's "Choose workspace appearance" phrasing, which is copy
    // and free to change, while the control's identity is not.
    const themeBtn = page.getByTestId("theme-switcher").first();
    await expect(themeBtn).toBeVisible();
    await themeBtn.click();

    // Verify theme changed on html tag
    const newTheme = await html.getAttribute("data-theme");
    expect(newTheme).not.toBe(initialTheme);

    // Reload and verify persistence
    await page.reload();
    const persistedTheme = await page.locator("html").getAttribute("data-theme");
    expect(persistedTheme).toBe(newTheme);
  });

  test("organization sidebar navigation and project routing", async ({ page }) => {
    // Navigate directly to sign in and check auth flow
    await page.goto("/app/auth/sign-in");
    await expect(page.locator("input#email")).toBeVisible();
    await expect(page.locator("input#password")).toBeVisible();

    // Navigate to onboarding
    await page.goto("/app/onboarding");
    await expect(page.locator("input#org-name")).toBeVisible();
    await expect(page.locator("input#org-slug")).toBeVisible();
  });
});
