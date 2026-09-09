import { expect, test } from "@playwright/test";
import { createEvidenceWorkspace } from "./support/evidenceWorkspace";

/**
 * The workspace has exactly one project and no persisted evaluation, so this
 * exercises both honest boundaries at once: the project scope resolves to the
 * single visible project and names it, and the graded-run region reports that
 * nothing has been graded rather than showing a score.
 */
test("trust center resolves one visible project and reports the ungraded boundary", async ({
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

    // The project is resolved, not fabricated, and it is named on screen.
    const scope = page.getByTestId("trust-project-scope");
    await expect(scope).toContainText("Task 11 Evidence Workspace");
    await expect(scope).toContainText("the only project you can see");

    // No evaluation has been persisted, so nothing is scored and nothing is
    // inferred. This replaces the earlier "capability not available" assertion:
    // the capability is wired now, and it is the record that is empty.
    await expect(
      page.getByRole("heading", { name: "No run has been graded yet" }),
    ).toBeVisible();
    await expect(page.getByText(/no deterministic or judge evaluation/i)).toContainText(
      "None is inferred in the meantime.",
    );

    // No rubric, no score ring, and no fabricated headline number.
    await expect(page.getByTestId("rubric-visualizer")).toHaveCount(0);
    await expect(page.getByTestId("trust-score-ring")).toHaveCount(0);
    await expect(page.getByTestId("trust-score-summary")).toHaveCount(0);

    // The human-only boundary is stated on the surface regardless of scope.
    await expect(
      page.getByText("Some things only a person may change"),
    ).toBeVisible();
  } finally {
    await workspace.close();
  }
});

test("trust center offers no learning-stage action without a candidate", async ({
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
      page.getByRole("heading", { name: "No learning candidate raised yet" }),
    ).toBeVisible();
    await expect(page.getByTestId("learning-candidate-card")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /adopt it/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /revert/i })).toHaveCount(0);
  } finally {
    await workspace.close();
  }
});
