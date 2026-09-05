import { expect, test } from "@playwright/test";
import { createEvidenceWorkspace, itemPath } from "./support/evidenceWorkspace";

test("authenticated owner reaches current governed collaboration surfaces", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.owner.page;
    await page.goto(itemPath(workspace, workspace.citedItemId));

    await expect(page.locator("textarea#rationale")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Record Review Decision" }),
    ).toBeVisible();
    await expect(page.getByTestId("comment-input")).toBeVisible();
    await expect(page.getByTestId("post-comment-btn")).toBeVisible();
    await expect(page.getByTestId("rewrite-proposals-section")).toBeVisible();
    await expect(page.getByTestId("referral-section")).toBeVisible();
    await expect(
      page.getByText(
        "ClearCut provides sourced findings for qualified human review. It does not provide legal advice or final legal clearance.",
        { exact: true },
      ),
    ).toBeVisible();
  } finally {
    await workspace.close();
  }
});
