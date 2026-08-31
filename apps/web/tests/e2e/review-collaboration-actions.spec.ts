import { test, expect } from "@playwright/test";

test.describe("Review Actions, Comments, Rewrites, and Referrals", () => {
  test("decision recording, comments thread, rewrite proposal, and referrals", async ({ page }) => {
    await page.goto("/o/northlight/projects/018f0000-0000-7000-8000-000000000101/items/018f0000-0000-7000-8000-000000001101");

    // 1. Check decision recorder
    const rationaleInput = page.locator("textarea#rationale");
    await expect(rationaleInput).toBeVisible();

    const commitDecisionBtn = page.locator("button:has-text('Commit Governed Decision')");
    await expect(commitDecisionBtn).toBeVisible();

    // 2. Check comments thread section
    const commentInput = page.locator("[data-testid='comment-input']");
    await expect(commentInput).toBeVisible();

    const postCommentBtn = page.locator("[data-testid='post-comment-btn']");
    await expect(postCommentBtn).toBeVisible();

    // 3. Check rewrite proposals section
    const rewriteSection = page.locator("[data-testid='rewrite-proposals-section']");
    await expect(rewriteSection).toBeVisible();

    // 4. Check referral section / modal
    const referralSection = page.locator("[data-testid='referral-section']");
    await expect(referralSection).toBeVisible();
  });
});
