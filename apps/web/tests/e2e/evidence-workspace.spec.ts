import { expect, test } from "@playwright/test";
import {
  createEvidenceWorkspace,
  itemPath,
} from "./support/evidenceWorkspace";

test.describe("Authoritative evidence workspace", () => {
  test("reviewer deep links preserve cited and zero-evidence states without a legal conclusion", async ({
    browser,
  }, testInfo) => {
    const baseURL = String(testInfo.project.use.baseURL);
    const workspace = await createEvidenceWorkspace(browser, baseURL);

    try {
      const page = workspace.reviewer.page;
      await page.goto(itemPath(workspace, workspace.citedItemId));

      await expect(page.getByRole("heading", { level: 1, name: /Vega Camera/ })).toBeVisible();
      await expect(
        page.getByRole("heading", {
          name: "Source Snapshots & Evidence Claims (1)",
        }),
      ).toBeVisible();
      await expect(
        page.getByRole("link", { name: /Deterministic Vega Camera fixture record/ }),
      ).toBeVisible();
      await expect(
        page.getByText(
          "This deterministic fixture record supplies cited context for browser testing only.",
          { exact: true },
        ),
      ).toBeVisible();

      await page.goto(itemPath(workspace, workspace.zeroEvidenceItemId));
      await expect(
        page.getByRole("heading", { level: 1, name: /Northstar Drone/ }),
      ).toBeVisible();
      await expect(
        page.getByText(
          "Zero cited evidence remains unresolved. No fallback evidence has been invented.",
        ),
      ).toBeVisible();
      await expect(
        page.getByText(
          "ClearCut provides sourced findings for qualified human review. It does not provide legal advice or final legal clearance.",
        ),
      ).toBeVisible();
      await expect(page.getByText(/guaranteed legal clearance/i)).toHaveCount(0);
    } finally {
      await workspace.close();
    }
  });
});



test("reviewer decision persists through authoritative refetch and reload", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.reviewer.page;
    await page.goto(itemPath(workspace, workspace.citedItemId));
    const decisionBar = page.getByTestId("decision-action-bar");
    await page.getByText("Accept cited evidence", { exact: true }).click();
    await decisionBar.getByLabel("Accountable rationale").fill(
      "The cited context is attributable and suitable for continued human review.",
    );
    await decisionBar.getByRole("button", { name: "Record Review Decision" }).click();

    await expect(page.getByRole("alert")).toContainText(
      "Evidence-review decision recorded",
    );
    await expect(page.getByText("evidence: accepted", { exact: true })).toBeVisible();
    await expect(
      page.getByText(
        "The cited context is attributable and suitable for continued human review.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(decisionBar.getByLabel("Accountable rationale")).toHaveValue("");

    await page.reload();
    await expect(page.getByText("evidence: accepted", { exact: true })).toBeVisible();
    await expect(
      page.getByText(
        "The cited context is attributable and suitable for continued human review.",
        { exact: true },
      ),
    ).toBeVisible();
  } finally {
    await workspace.close();
  }
});



test("two actors receive a stale conflict without losing the reviewer rationale", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const reviewerPage = workspace.reviewer.page;
    const ownerPage = workspace.owner.page;
    const path = itemPath(workspace, workspace.citedItemId);
    await Promise.all([reviewerPage.goto(path), ownerPage.goto(path)]);

    const reviewerDecisionBar = reviewerPage.getByTestId("decision-action-bar");
    const reviewerRationale =
      "Retain this reviewer rationale when another actor changes the item.";
    await reviewerPage.getByText("Reject cited evidence", { exact: true }).click();
    await reviewerDecisionBar.getByLabel("Accountable rationale").fill(reviewerRationale);

    const ownerDecisionBar = ownerPage.getByTestId("decision-action-bar");
    await ownerPage.getByText("Accept cited evidence", { exact: true }).click();
    await ownerDecisionBar
      .getByLabel("Accountable rationale")
      .fill("Owner records the first authoritative decision.");
    await ownerDecisionBar
      .getByRole("button", { name: "Record Review Decision" })
      .click();
    await expect(ownerPage.getByRole("alert")).toContainText(
      "Evidence-review decision recorded",
    );

    await reviewerDecisionBar
      .getByRole("button", { name: "Record Review Decision" })
      .click();
    await expect(reviewerPage.getByRole("alert")).toContainText(
      "This item changed during review. Your rationale is preserved",
    );
    await expect(
      reviewerDecisionBar.getByLabel("Accountable rationale"),
    ).toHaveValue(reviewerRationale);
    await expect(reviewerPage.getByText("evidence: rejected", { exact: true })).toHaveCount(0);
  } finally {
    await workspace.close();
  }
});



test("assignment and disposition persist as authoritative item state", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.reviewer.page;
    await page.goto(itemPath(workspace, workspace.citedItemId));
    const governance = page.getByRole("region", { name: "Item governance controls" });

    await governance.getByLabel("Assignee member ID").fill(workspace.editor.userId);
    const assignmentResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().includes(workspace.citedItemId),
    );
    await governance.getByRole("button", { name: "Save Assignment" }).click();
    expect((await assignmentResponse).status()).toBe(200);

    await governance.getByLabel("Disposition", { exact: true }).selectOption("deferred");
    await governance
      .getByLabel("Disposition rationale")
      .fill("Keep this evidence state open for qualified specialist review.");
    const dispositionResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().includes(workspace.citedItemId),
    );
    await governance.getByRole("button", { name: "Save Disposition" }).click();
    expect((await dispositionResponse).status()).toBe(200);

    await page.reload();
    await expect(governance.getByLabel("Assignee member ID")).toHaveValue(
      workspace.editor.userId,
    );
    await expect(
      governance.getByLabel("Disposition", { exact: true }),
    ).toHaveValue("deferred");
    await expect(page.getByText("disposition: deferred", { exact: true })).toBeVisible();
    await expect(
      page.getByText(
        "Keep this evidence state open for qualified specialist review.",
        { exact: true },
      ),
    ).toBeVisible();
  } finally {
    await workspace.close();
  }
});



test("a referral is acknowledged by a different accountable actor", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const ownerPage = workspace.owner.page;
    await ownerPage.goto(itemPath(workspace, workspace.citedItemId));
    const ownerReferral = ownerPage.getByTestId("referral-section");
    await ownerReferral.getByLabel("Refer To Specialist Role").selectOption("reviewer");
    await ownerReferral
      .getByLabel("Referral question")
      .fill("Does the cited context require assigned reviewer follow-up?");
    await ownerReferral
      .getByLabel("Accountable rationale")
      .fill("The active project reviewer should assess the unresolved source context.");
    const referralResponse = ownerPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().includes(workspace.citedItemId),
    );
    await ownerReferral
      .getByRole("button", { name: "Send Formal Referral" })
      .click();
    expect((await referralResponse).status()).toBe(201);
    await expect(
      ownerReferral.getByText(
        "Does the cited context require assigned reviewer follow-up?",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(ownerReferral.getByText("submitted", { exact: true })).toBeVisible();

    const reviewerPage = workspace.reviewer.page;
    await reviewerPage.goto(itemPath(workspace, workspace.citedItemId));
    const reviewerReferral = reviewerPage.getByTestId("referral-section");
    await reviewerReferral
      .getByLabel("Referral response")
      .fill("Acknowledged for reviewer follow-up.");
    await reviewerReferral
      .getByLabel("Acknowledgement rationale")
      .fill("The assigned reviewer accepts responsibility for this unresolved issue.");
    const acknowledgementResponse = reviewerPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().includes(workspace.citedItemId),
    );
    await reviewerReferral
      .getByRole("button", { name: "Acknowledge Referral" })
      .click();
    expect((await acknowledgementResponse).status()).toBe(200);

    await expect(
      reviewerReferral.getByText("acknowledged", { exact: true }),
    ).toBeVisible();
    await reviewerPage.reload();
    await expect(
      reviewerPage
        .getByTestId("referral-section")
        .getByText("acknowledged", { exact: true }),
    ).toBeVisible();
  } finally {
    await workspace.close();
  }
});



test("authorized mentions persist across comment, reply, and revision history", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.editor.page;
    await page.goto(itemPath(workspace, workspace.citedItemId));
    const thread = page.getByTestId("comment-thread");

    await thread
      .getByLabel("Mention team members for new comment")
      .selectOption(workspace.reviewer.userId);
    await thread
      .getByTestId("comment-input")
      .fill("Reviewer, please inspect this cited source context.");
    const commentResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith("/comments"),
    );
    await thread.getByTestId("post-comment-btn").click();
    expect((await commentResponse).status()).toBe(201);

    await expect(
      thread.getByText("Reviewer, please inspect this cited source context.", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      thread.getByText(`Mention recipients: ${workspace.reviewer.userId}`, {
        exact: true,
      }),
    ).toBeVisible();

    const rootComment = thread.locator("article").filter({
      hasText: "Reviewer, please inspect this cited source context.",
    });
    const replyInput = rootComment.getByRole("textbox", {
      name: /Reply to comment/,
    });
    await replyInput.fill("The source is attributable, but the item remains unresolved.");
    const replyResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(":reply"),
    );
    await rootComment.getByRole("button", { name: "Post Reply" }).click();
    expect((await replyResponse).status()).toBe(201);
    await expect(
      thread.getByText(
        "The source is attributable, but the item remains unresolved.",
        { exact: true },
      ),
    ).toBeVisible();

    const refreshedRootComment = thread.locator("article").filter({
      hasText: "Reviewer, please inspect this cited source context.",
    });
    const revisionInput = refreshedRootComment.getByRole("textbox", {
      name: /Revise comment/,
    });
    await revisionInput.fill(
      "Reviewer, please inspect this cited source context before disposition.",
    );
    const revisionResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(":revise"),
    );
    await refreshedRootComment
      .getByRole("button", { name: "Save Revision" })
      .click();
    expect((await revisionResponse).status()).toBe(200);

    await expect(
      thread.getByText(
        "Reviewer, please inspect this cited source context before disposition.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(refreshedRootComment.getByText("Revision 1", { exact: false })).toBeVisible();
    await expect(refreshedRootComment.getByText("Revision 2", { exact: false })).toBeVisible();
  } finally {
    await workspace.close();
  }
});
