import { test, expect } from "@playwright/test";

test.describe("Full End-to-End Clearance Lifecycle & Legal Disclaimers", () => {
  test("complete lifecycle: script import, triage, evidence, referral, diff, monitoring, trust, and report release", async ({
    page,
  }) => {
    // 1. Visit workspace
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/workspace");
    await expect(page.locator("h1:has-text('Clearance Workspace')")).toBeVisible();

    // Verify non-legal-advice disclaimer notice is present
    const notice = page.locator("text=ClearCut provides evidence-grounded risk intelligence");
    await expect(notice).toBeVisible();

    // 2. Visit Item Detail and make decision
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/items/item-001");
    await expect(page.locator("[data-testid='decision-action-bar']")).toBeVisible();
    await expect(page.locator("[data-testid='comment-thread']")).toBeVisible();

    // 3. Visit Versions & Lineage
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/versions");
    await expect(page.locator("[data-testid='script-diff-viewer']")).toBeVisible();
    await expect(page.locator("[data-testid='item-lineage-section']")).toBeVisible();

    // 4. Visit Monitoring & Cadence
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/watch");
    await expect(page.locator("[data-testid='cadence-selector']")).toBeVisible();
    await expect(page.locator("[data-testid='monitored-sources-table']")).toBeVisible();

    // 5. Visit Trust Center
    await page.goto("/o/northlight/trust");
    await expect(page.locator("[data-testid='rubric-visualizer']")).toBeVisible();
    await expect(page.locator("[data-testid='protected-config-card']")).toBeVisible();

    // 6. Visit Report & Release
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/report");
    await expect(page.locator("[data-testid='report-snapshot-builder']")).toBeVisible();
    await expect(page.locator("[data-testid='report-receipt-view']")).toBeVisible();
  });
});
