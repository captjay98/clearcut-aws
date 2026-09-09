import { expect, test, type Page } from "@playwright/test";
import { createEvidenceWorkspace, itemPath } from "./support/evidenceWorkspace";

/**
 * The rewrite lifecycle across two independent authenticated browser contexts.
 *
 * The regression these tests exist for: the proposal history used to live in
 * React state, so it vanished on reload and the second accountable actor never
 * saw a proposal at all. Every assertion below is against the persisted history
 * served by `listRewriteProposals`.
 */

const PROPOSED_TEXT =
  "A borrowed field camera rests beside a covered prototype drone.";
const PROPOSED_RATIONALE =
  "Removing the named product avoids an unresolved trademark question.";

function rewriteSection(page: Page) {
  return page.getByTestId("rewrite-proposals-section");
}

interface ProposalResponse {
  data: { proposalId: string };
}

test("a proposal survives the proposer's reload and reaches a second accountable actor", async ({
  browser,
}, testInfo) => {
  const baseURL = String(testInfo.project.use.baseURL);
  const workspace = await createEvidenceWorkspace(browser, baseURL);

  try {
    // Owner holds rewrite:propose; reviewer holds rewrite:approve. Two separate
    // contexts means two separate sessions, not two tabs of one actor.
    const proposerPage = workspace.owner.page;
    const reviewerPage = workspace.reviewer.page;
    const path = itemPath(workspace, workspace.citedItemId);

    await proposerPage.goto(path);
    const proposerSection = rewriteSection(proposerPage);
    await expect(
      proposerSection.getByText("No rewrite proposals recorded", { exact: true }),
    ).toBeVisible();
    // The card must not promise work the server does not do.
    await expect(proposerSection).toContainText(
      "it creates no script version and starts no research",
    );

    await proposerSection
      .getByLabel("Proposed replacement text")
      .fill(PROPOSED_TEXT);
    await proposerSection.getByLabel("Rationale").fill(PROPOSED_RATIONALE);
    const proposeResponse = proposerPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(":proposeRewrite"),
    );
    await proposerSection.getByRole("button", { name: "Submit Proposal" }).click();
    const created = await proposeResponse;
    expect(created.status()).toBe(201);
    const proposalId = ((await created.json()) as ProposalResponse).data.proposalId;

    await expect(
      proposerSection.getByText(PROPOSED_TEXT, { exact: true }),
    ).toBeVisible();
    await expect(
      proposerSection.getByText(PROPOSED_RATIONALE, { exact: true }),
    ).toBeVisible();
    await expect(proposerSection.getByText("Proposed", { exact: true })).toBeVisible();
    await expect(
      proposerSection.getByText(workspace.owner.email, { exact: false }),
    ).toBeVisible();
    await expect(
      proposerSection.getByLabel("Proposed replacement text"),
    ).toHaveValue("");

    // The core regression: the history is server state, so it is still there
    // after the proposer's own reload.
    await proposerPage.reload();
    const reloadedSection = rewriteSection(proposerPage);
    await expect(reloadedSection.getByText(PROPOSED_TEXT, { exact: true })).toBeVisible();
    await expect(
      reloadedSection.getByText(PROPOSED_RATIONALE, { exact: true }),
    ).toBeVisible();
    await expect(reloadedSection.getByText("Proposed", { exact: true })).toBeVisible();

    // Maker-checker: the proposer is never offered approval of their own work,
    // and may only retract it.
    await expect(
      reloadedSection.getByRole("button", { name: "Approve Rewrite" }),
    ).toHaveCount(0);
    await expect(
      reloadedSection.getByRole("button", { name: "Withdraw Proposal" }),
    ).toBeVisible();
    await expect(reloadedSection).toContainText(
      "a different accountable reviewer has to decide on it",
    );

    // Hiding the button is a convenience. The server is the control, so ask it
    // directly: an owner holds rewrite:approve and is still refused.
    const selfApproval = await workspace.owner.context.request.post(
      `/api/v1/organizations/${workspace.orgId}/projects/${workspace.projectId}` +
        `/rewrite-proposals/${proposalId}:approve`,
    );
    expect(selfApproval.status()).toBe(403);

    // The second actor, in a separate authenticated context, retrieves the same
    // persisted proposal.
    await reviewerPage.goto(path);
    const reviewerSection = rewriteSection(reviewerPage);
    await expect(reviewerSection.getByText(PROPOSED_TEXT, { exact: true })).toBeVisible();
    await expect(
      reviewerSection.getByText(PROPOSED_RATIONALE, { exact: true }),
    ).toBeVisible();
    await expect(reviewerSection.getByText("Proposed", { exact: true })).toBeVisible();
    await expect(
      reviewerSection.getByRole("button", { name: "Withdraw Proposal" }),
    ).toHaveCount(0);

    const approvalResponse = reviewerPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" && response.url().endsWith(":approve"),
    );
    await reviewerSection.getByRole("button", { name: "Approve Rewrite" }).click();
    expect((await approvalResponse).status()).toBe(200);

    await expect(reviewerSection.getByText("Approved", { exact: true })).toBeVisible();
    // Approval creates no version and starts no research, so nothing may claim
    // it did.
    await expect(reviewerSection).toContainText(
      "No successor version is bound to this approval",
    );
    await expect(reviewerPage.getByText(/version created/i)).toHaveCount(0);
    await expect(
      reviewerSection.getByRole("link", { name: /resulting script version/ }),
    ).toHaveCount(0);
    await expect(
      reviewerSection.getByRole("button", { name: "Approve Rewrite" }),
    ).toHaveCount(0);

    // Both actors see the same persisted outcome after their own reloads.
    await Promise.all([proposerPage.reload(), reviewerPage.reload()]);
    await expect(
      rewriteSection(proposerPage).getByText("Approved", { exact: true }),
    ).toBeVisible();
    await expect(
      rewriteSection(reviewerPage).getByText("Approved", { exact: true }),
    ).toBeVisible();
    await expect(
      rewriteSection(proposerPage).getByText(PROPOSED_TEXT, { exact: true }),
    ).toBeVisible();
  } finally {
    await workspace.close();
  }
});

test("a failed proposal request preserves the typed rewrite", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.owner.page;
    await page.goto(itemPath(workspace, workspace.citedItemId));
    const section = rewriteSection(page);

    // Fail only the write. The history read stays intact, so the failure is a
    // failure of this command rather than of the surface.
    const isProposeWrite = (url: URL) => url.pathname.endsWith(":proposeRewrite");
    await page.route(isProposeWrite, (route) => route.abort("connectionfailed"));

    await section.getByLabel("Proposed replacement text").fill(PROPOSED_TEXT);
    await section.getByLabel("Rationale").fill(PROPOSED_RATIONALE);
    await section.getByRole("button", { name: "Submit Proposal" }).click();

    await expect(page.getByRole("alert")).toContainText(
      "The rewrite proposal was not recorded",
    );
    await expect(section.getByLabel("Proposed replacement text")).toHaveValue(
      PROPOSED_TEXT,
    );
    await expect(section.getByLabel("Rationale")).toHaveValue(PROPOSED_RATIONALE);
    // Nothing was recorded, so the history must not show an invented proposal.
    await expect(
      section.getByText("No rewrite proposals recorded", { exact: true }),
    ).toBeVisible();

    // The preserved text is still submittable once the network recovers.
    await page.unroute(isProposeWrite);
    const retry = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(":proposeRewrite"),
    );
    await section.getByRole("button", { name: "Submit Proposal" }).click();
    expect((await retry).status()).toBe(201);
    await expect(section.getByText(PROPOSED_TEXT, { exact: true })).toBeVisible();
  } finally {
    await workspace.close();
  }
});

test("the rewrite card is operable from the keyboard by both actors", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const proposerPage = workspace.owner.page;
    const path = itemPath(workspace, workspace.citedItemId);
    await proposerPage.goto(path);
    const proposerSection = rewriteSection(proposerPage);

    const proposedInput = proposerSection.getByLabel("Proposed replacement text");
    const rationaleInput = proposerSection.getByLabel("Rationale");
    const submitButton = proposerSection.getByRole("button", {
      name: "Submit Proposal",
    });

    await proposedInput.focus();
    await expect(proposedInput).toBeFocused();
    await proposerPage.keyboard.type(PROPOSED_TEXT);
    await proposerPage.keyboard.press("Tab");
    await expect(rationaleInput).toBeFocused();
    await proposerPage.keyboard.type(PROPOSED_RATIONALE);
    await proposerPage.keyboard.press("Tab");
    await expect(submitButton).toBeFocused();

    const proposeResponse = proposerPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(":proposeRewrite"),
    );
    await proposerPage.keyboard.press("Enter");
    expect((await proposeResponse).status()).toBe(201);
    await expect(
      proposerSection.getByText(PROPOSED_TEXT, { exact: true }),
    ).toBeVisible();

    const reviewerPage = workspace.reviewer.page;
    await reviewerPage.goto(path);
    const reviewerSection = rewriteSection(reviewerPage);
    const approveButton = reviewerSection.getByRole("button", {
      name: "Approve Rewrite",
    });
    await approveButton.focus();
    await expect(approveButton).toBeFocused();
    const approvalResponse = reviewerPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" && response.url().endsWith(":approve"),
    );
    await reviewerPage.keyboard.press("Enter");
    expect((await approvalResponse).status()).toBe(200);
    await expect(reviewerSection.getByText("Approved", { exact: true })).toBeVisible();
  } finally {
    await workspace.close();
  }
});
