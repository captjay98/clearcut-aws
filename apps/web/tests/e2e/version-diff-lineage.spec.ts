import { expect, test } from "@playwright/test";
import { createEvidenceWorkspace } from "./support/evidenceWorkspace";

/**
 * A project with a single committed version has no persisted predecessor
 * comparison, so the versions page must present that honestly: the sole version
 * is the latest revision, and the diff/lineage surface reports that no adjacent
 * diff exists rather than fabricating an empty diff or offering a rescan. This
 * asserts the CURRENT production copy (see
 * apps/web/src/routes/o/$orgSlug/projects/$projectId/versions.tsx and
 * VersionDiffViewer), replacing the stale "Active Revision" / "…unavailable
 * until persisted comparison data exists" assertions.
 */
test("a first version shows the latest-revision badge and the honest no-predecessor diff boundary", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.owner.page;
    await page.goto(
      `/app/o/${workspace.orgSlug}/projects/${workspace.projectId}/versions`,
    );

    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Script Versions, Diffing & Lineage",
      }),
    ).toBeVisible();

    // Exactly one committed version exists, labelled as the latest revision.
    await expect(page.getByText("Recorded Script Versions (1)")).toBeVisible();
    await expect(page.getByText("Version 1", { exact: true })).toBeVisible();
    await expect(
      page.getByText("Latest Revision", { exact: true }),
    ).toBeVisible();

    // With no persisted adjacent diff for this single committed version, the
    // diff surface states the honest boundary and neither renders a diff viewer
    // nor offers a governed rescan trigger. The evidence-fixture version has no
    // recorded predecessor comparison, so the API reports no adjacent diff.
    await expect(
      page.getByRole("alert").filter({
        hasText: "No adjacent diff exists for this script version.",
      }),
    ).toBeVisible();
    await expect(page.getByTestId("script-diff-viewer")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /re-?scan/i })).toHaveCount(0);
  } finally {
    await workspace.close();
  }
});
