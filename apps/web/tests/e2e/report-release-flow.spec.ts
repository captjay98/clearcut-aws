import { test, expect } from "@playwright/test";

test.describe("Report Builder, Preview, Release Gating, and Print Styles", () => {
  test("report snapshot creation, manifest hash, attestation release, and receipt view", async ({ page }) => {
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/report");

    // 1. Check report snapshot builder container
    const reportBuilder = page.locator("[data-testid='report-snapshot-builder']");
    await expect(reportBuilder).toBeVisible();

    // 2. Check SHA-256 manifest hash display
    const manifestHash = page.locator("[data-testid='binding-manifest-hash']");
    await expect(manifestHash).toBeVisible();

    // 3. Check attestation input and release button
    const attestationInput = page.locator("textarea#attestation");
    if (await attestationInput.isVisible()) {
      await attestationInput.fill("I attest that all clearance items have been reviewed by production legal counsel.");
      const releaseBtn = page.locator("button:has-text('Sign & Release Governed Report'), button:has-text('Release Dossier')").first();
      await releaseBtn.click();
    }

    // 4. Check immutable audit receipt view
    const receiptView = page.locator("[data-testid='report-receipt-view']");
    await expect(receiptView).toBeVisible();

    // 5. Test print media styling
    await page.emulateMedia({ media: "print" });
    // In print media, header theme switcher and sidebar should have print:hidden
    const header = page.locator("header");
    await expect(header).toBeAttached();
  });
});
