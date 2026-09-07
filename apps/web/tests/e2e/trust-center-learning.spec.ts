import { expect, test } from "@playwright/test";
import { createEvidenceWorkspace } from "./support/evidenceWorkspace";

test("trust center reports the honest unavailable evaluation boundary", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.owner.page;
    await page.goto(`/app/o/${workspace.orgId}/trust`);

    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Trust Center & Evaluation Rubric",
      }),
    ).toBeVisible();
    await expect(page.getByRole("status")).toContainText(
      "The Trust evaluation capability is not available until a project run has persisted its deterministic and judge evaluations.",
    );
    await expect(page.getByRole("status")).toContainText(
      "No score or policy status is inferred in the meantime.",
    );
    await expect(page.getByTestId("rubric-visualizer")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /promote candidate/i }),
    ).toHaveCount(0);
  } finally {
    await workspace.close();
  }
});
