import { expect, test } from "@playwright/test";
import { createEvidenceWorkspace, itemPath } from "./support/evidenceWorkspace";

test.describe("Evidence authorization and access", () => {
  test("denied editor actions expose focusable server-derived explanations", async ({
    browser,
  }, testInfo) => {
    const workspace = await createEvidenceWorkspace(
      browser,
      String(testInfo.project.use.baseURL),
    );

    try {
      const page = workspace.editor.page;
      await page.goto(itemPath(workspace, workspace.citedItemId));

      const decisionExplanation = page.getByText(
        "Record a human evidence-review decision; this is not legal clearance.",
        { exact: true },
      );
      await expect(decisionExplanation).toBeVisible();
      await decisionExplanation.focus();
      await expect(decisionExplanation).toBeFocused();
      const decisionRadios = page
        .getByTestId("decision-action-bar")
        .getByRole("radio");
      await expect(decisionRadios).toHaveCount(3);
      for (const radio of await decisionRadios.all()) {
        await expect(radio).toBeDisabled();
      }

      const dispositionExplanation = page.getByText(
        "Record a pre-clearance workflow disposition.",
        { exact: true },
      );
      await expect(dispositionExplanation).toBeVisible();
      await dispositionExplanation.focus();
      await expect(dispositionExplanation).toBeFocused();
      const governance = page.getByRole("region", {
        name: "Item governance controls",
      });
      await expect(
        governance.getByLabel("Disposition", { exact: true }),
      ).toBeDisabled();
      await expect(
        governance.getByRole("button", { name: "Save Disposition" }),
      ).toBeDisabled();
      await expect(
        governance.getByRole("button", { name: "Save Assignment" }),
      ).toBeEnabled();

      const referralExplanation = page.getByText(
        "Refer unresolved evidence to an authorized specialist.",
        { exact: true },
      );
      await expect(referralExplanation).toBeVisible();
      await referralExplanation.focus();
      await expect(referralExplanation).toBeFocused();
      await expect(
        page.getByTestId("referral-section").getByRole("button", {
          name: "Send Formal Referral",
        }),
      ).toBeDisabled();
    } finally {
      await workspace.close();
    }
  });
});

test("unknown and foreign item identities have neutral deep-link parity", async ({
  browser,
}, testInfo) => {
  const baseURL = String(testInfo.project.use.baseURL);
  const owned = await createEvidenceWorkspace(browser, baseURL);
  const foreign = await createEvidenceWorkspace(browser, baseURL);

  try {
    const page = owned.owner.page;
    await page.goto(itemPath(owned, crypto.randomUUID()));
    const unknownMessage = await page.getByRole("alert").innerText();

    await page.goto(itemPath(owned, foreign.citedItemId));
    const foreignMessage = await page.getByRole("alert").innerText();

    expect(foreignMessage).toBe(unknownMessage);
    expect(foreignMessage).not.toContain("Vega Camera");
    expect(foreignMessage).not.toContain(foreign.orgId);
  } finally {
    await Promise.allSettled([owned.close(), foreign.close()]);
  }
});

test("zero evidence remains unresolved and exposes no source link", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.reviewer.page;
    await page.goto(itemPath(workspace, workspace.zeroEvidenceItemId));

    await expect(
      page.getByText(
        "Zero cited evidence remains unresolved. No fallback evidence has been invented.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      page.getByText(
        "ClearCut provides sourced findings for qualified human review. It does not provide legal advice or final legal clearance.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "Source Snapshots & Evidence Claims (0)",
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /fixture record/ }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("radio", { name: /Further review required/ }),
    ).toBeChecked();
  } finally {
    await workspace.close();
  }
});

test("evidence drawer supports keyboard operation and restores trigger focus", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.owner.page;
    await page.goto(
      `/app/o/${workspace.orgId}/projects/${workspace.projectId}/workspace`,
    );
    // Below 901px the three workspace panes cannot share the viewport, so the
    // flag pane sits behind a pane switcher. Select it when that switcher is
    // on screen; on wider viewports the pane is already laid out.
    const flagPaneTab = page
      .getByRole("group", { name: "Workspace view" })
      .getByRole("button", { name: "Evidence" });
    if (await flagPaneTab.isVisible()) {
      await flagPaneTab.click();
    }

    const citedCard = page
      .getByTestId("clearance-item-card")
      .filter({ hasText: "Vega Camera" });
    const openButton = citedCard.getByTestId("open-evidence-drawer-btn");
    await expect(openButton).toBeVisible();
    await openButton.focus();
    await page.keyboard.press("Enter");

    const drawer = page.getByRole("dialog", { name: /Vega Camera evidence/ });
    await expect(drawer).toBeVisible();
    const closeButton = drawer.getByRole("button", {
      name: "Close evidence drawer",
    });
    const reviewLink = drawer.getByRole("link", { name: "Review Item →" });
    await expect(closeButton).toBeFocused();

    await page.keyboard.press("Shift+Tab");
    await expect(reviewLink).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(closeButton).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(drawer).toHaveCount(0);
    await expect(openButton).toBeFocused();
  } finally {
    await workspace.close();
  }
});

test("item detail preserves legal boundary and governance at the configured viewport", async ({
  browser,
}, testInfo) => {
  const workspace = await createEvidenceWorkspace(
    browser,
    String(testInfo.project.use.baseURL),
  );

  try {
    const page = workspace.reviewer.page;
    await page.goto(itemPath(workspace, workspace.citedItemId));

    await expect(
      page.getByRole("heading", { name: /^Vega Camera/ }),
    ).toBeVisible();
    await expect(
      page.getByText(
        "ClearCut provides sourced findings for qualified human review. It does not provide legal advice or final legal clearance.",
        { exact: true },
      ),
    ).toBeVisible();

    const governance = page.getByRole("region", {
      name: "Item governance controls",
    });
    await expect(governance).toBeVisible();
    const assignmentButton = governance.getByRole("button", {
      name: "Save Assignment",
    });
    await expect(assignmentButton).toBeEnabled();
    await assignmentButton.focus();
    await expect(assignmentButton).toBeFocused();

    const viewportWidths = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(viewportWidths.scrollWidth).toBeLessThanOrEqual(
      viewportWidths.clientWidth,
    );
  } finally {
    await workspace.close();
  }
});
