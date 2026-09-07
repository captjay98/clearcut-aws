import { expect, test } from "@playwright/test";
import { createEvidenceWorkspace } from "./support/evidenceWorkspace";

test("versions show the persisted revision and honest diff-lineage boundary", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.owner.page;
    await page.goto(
      `/app/o/${workspace.orgId}/projects/${workspace.projectId}/versions`,
    );

    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Script Versions, Diffing & Lineage",
      }),
    ).toBeVisible();
    await expect(page.getByText("Recorded Script Versions (1)")).toBeVisible();
    await expect(page.getByText("Version 1", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Active Revision", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "Script diff and item-lineage views are unavailable until persisted comparison data exists.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(page.getByTestId("script-diff-viewer")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /rescan/i })).toHaveCount(0);
  } finally {
    await workspace.close();
  }
});
