import { expect, test } from "@playwright/test";
import { createEvidenceWorkspace } from "./support/evidenceWorkspace";

function reportPath(orgId: string, projectId: string): string {
  return `/app/o/${orgId}/projects/${projectId}/report`;
}

test.describe("Immutable clearance report release", () => {
  test("generates, releases, downloads, and reloads one frozen report", async ({
    browser,
  }, testInfo) => {
    const workspace = await createEvidenceWorkspace(
      browser,
      String(testInfo.project.use.baseURL),
    );

    try {
      const page = workspace.owner.page;
      await page.goto(reportPath(workspace.orgId, workspace.projectId));

      await expect(
        page.getByRole("heading", { level: 1, name: "Clearance report" }),
      ).toBeVisible();
      await expect(
        page.getByText("Total items: 2", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText(
          "ClearCut provides sourced findings for qualified human review. It does not provide legal advice or final legal clearance.",
          { exact: true },
        ),
      ).toBeVisible();
      await expect(page.getByText(/dossier/i)).toHaveCount(0);
      await expect(page.getByText(/approved/i)).toHaveCount(0);
      await expect(page.getByText(/cleared/i)).toHaveCount(0);

      await page
        .getByRole("button", { name: "Create report snapshot" })
        .click();
      await expect(page.getByRole("alert")).toContainText(
        "A frozen, version-bound report snapshot was created",
      );
      const manifestHash = page.getByTestId("binding-manifest-hash");
      await expect(manifestHash).toHaveText(/^[0-9a-f]{64}$/);

      await page.getByRole("button", { name: "Review release" }).click();
      const dialog = page.getByRole("dialog", {
        name: "Release this frozen snapshot?",
      });
      await expect(dialog).toBeVisible();
      await expect(
        dialog.getByText(
          "Releasing records an accountable human attestation without regenerating or changing this snapshot.",
          { exact: true },
        ),
      ).toBeVisible();
      await expect(
        dialog.getByLabel("Accountable human attestation"),
      ).toContainText("not legal advice or final legal clearance");
      await dialog.getByRole("button", { name: "Release report" }).click();

      const receipt = page.getByTestId("report-receipt-view");
      await expect(receipt).toBeVisible();
      await expect(
        receipt.getByText("Report release receipt", { exact: true }),
      ).toBeVisible();
      await expect(receipt.getByText(/Release ID:/)).toBeVisible();
      await expect(
        receipt.getByText(/Binding manifest SHA-256:/),
      ).toContainText(await manifestHash.textContent());
      const download = receipt.getByRole("link", {
        name: "Download released HTML",
      });
      await expect(download).toBeVisible();
      const downloadUrl = await download.getAttribute("href");
      expect(downloadUrl).toBeTruthy();

      const artifact = await workspace.owner.context.request.get(
        String(downloadUrl),
      );
      expect(artifact.status()).toBe(200);
      expect(artifact.headers()["content-type"]).toContain("text/html");
      expect(artifact.headers()["content-disposition"]).toContain(
        "clearcut-report-",
      );
      const frozenHtml = await artifact.text();
      expect(frozenHtml).toContain("Vega Camera");
      expect(frozenHtml).toContain("Northstar Drone");
      expect(frozenHtml).toContain("Zero cited evidence remains unresolved");
      expect(frozenHtml).toContain(
        "does not provide legal advice or final legal clearance",
      );

      const releaseId = await receipt.getByTestId("release-id").textContent();
      await page.reload();
      await expect(page.getByTestId("report-receipt-view")).toBeVisible();
      await expect(page.getByTestId("release-id")).toHaveText(
        String(releaseId),
      );
      await expect(page.getByTestId("binding-manifest-hash")).toHaveText(
        String(await manifestHash.textContent()),
      );
      await expect(
        page.getByRole("link", { name: "Download released HTML" }),
      ).toHaveAttribute("href", String(downloadUrl));
    } finally {
      await workspace.close();
    }
  });
});
