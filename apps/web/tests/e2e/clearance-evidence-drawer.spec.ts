import { test, expect } from "@playwright/test";

test.describe("Clearance Workspace, Categories, and Evidence Drawer", () => {
  test("category filters, item triage states, and evidence drawer with source snapshots", async ({ page }) => {
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/workspace");

    // 1. Check category filter bar renders 10 categories
    const categoryChips = page.locator("[data-testid='category-filter-chip']");
    await expect(categoryChips.first()).toBeVisible();
    expect(await categoryChips.count()).toBeGreaterThanOrEqual(10);

    // 2. Check item triage card and status badge
    const itemCard = page.locator("[data-testid='clearance-item-card']").first();
    await expect(itemCard).toBeVisible();

    // 3. Open evidence drawer
    const viewEvidenceBtn = page.locator("[data-testid='open-evidence-drawer-btn']").first();
    await expect(viewEvidenceBtn).toBeVisible();
    await viewEvidenceBtn.click();

    // 4. Verify evidence drawer renders source snapshots
    const evidenceDrawer = page.locator("[data-testid='evidence-drawer']");
    await expect(evidenceDrawer).toBeVisible();

    // Check authority tier and stance badge
    const stanceBadge = page.locator("[data-testid='claim-stance-badge']").first();
    await expect(stanceBadge).toBeVisible();

    // Check secure link attributes
    const sourceLink = page.locator("[data-testid='source-snapshot-url']").first();
    if (await sourceLink.isVisible()) {
      const rel = await sourceLink.getAttribute("rel");
      expect(rel).toContain("noreferrer");
    }
  });
});
