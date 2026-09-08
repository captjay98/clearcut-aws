import path from "node:path";

import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

/**
 * Durable, provider-free browser proof of the revision + selective-rescan
 * vertical slice.
 *
 * This spec drives the REAL production UI and API boundaries end to end:
 * public registration/organization/project creation, the real upload -> parse ->
 * commit import flow for v1 and the v2 revision, the persisted adjacent diff,
 * the governed confirmation dialog, the durable rescan job, URL-restored
 * progress, and terminal success.
 *
 * It is honest about its boundary. The API composition under Playwright uses
 * in-repo hermetic detection/search/extract/planner/judge doubles (see
 * apps/web/tests/support/e2e_api.py). No Parallel, Gemini, network, or cloud
 * provider is ever called. Every assertion reads the SAME published contracts
 * the production TypeScript client and versions UI consume:
 *   - getScriptVersionDiff -> { data: { beforeVersionId, afterVersionId,
 *     beforeLabel, afterLabel, elements[].changeKind, summary.* } }
 *   - listClearanceItems   -> { data: [{ itemId, versionId, entityName,
 *     status, ... }] }
 *   - getClearanceItem     -> { data: { claims[], snapshots[].url/excerpt/
 *     retrievedAt, decisions[] } }
 *   - listJobs / getJob    -> { data: { jobId, jobType, status, stage } }
 *
 * The deeper element-lineage IDENTITY invariants (lineage_kind == carried
 * forward, predecessor_item_id linkage, carried_forward_confirmation_required,
 * evidence-lineage edges) are NOT exposed over HTTP; they are proven at the
 * repository level by services/api/tests/e2e/test_revision_selective_rescan.py.
 * This browser proof asserts the behavior those invariants produce that IS
 * observable at the HTTP/UI surface. What this proves and does not prove is
 * documented in apps/web/tests/e2e/TESTING.md; it does NOT prove hosted
 * durability, live Parallel quality, paid-provider reliability, or legal
 * clearance.
 */

const PASSWORD = "RevisionRescan123!";
const API_PORT = process.env.CLEARCUT_E2E_API_PORT ?? "28080";

const V1_FIXTURE = path.resolve(process.cwd(), "tests/fixtures/revision-v1.fountain");
const V2_FIXTURE = path.resolve(process.cwd(), "tests/fixtures/revision-v2.fountain");

// Every one of the five change kinds the diff contract can report.
const CHANGE_KINDS = ["unchanged", "moved", "modified", "added", "removed"] as const;
type ChangeKind = (typeof CHANGE_KINDS)[number];

// Hosts that would indicate a real paid-provider / cloud call. The hermetic
// composition must never reach any of these; a single hit fails the proof.
const PAID_PROVIDER_HOST_PATTERN =
  /(parallel\.ai|api\.parallel|googleapis\.com|aiplatform|generativelanguage|vertexai|gemini)/i;

interface Owner {
  context: BrowserContext;
  page: Page;
  orgId: string;
  orgSlug: string;
  projectId: string;
}

async function jsonOk<T>(
  promise: Promise<import("@playwright/test").APIResponse>,
  expected: number,
): Promise<T> {
  const response = await promise;
  if (response.status() !== expected) {
    throw new Error(
      `Expected ${expected} from ${response.url()}, got ${response.status()}: ${await response.text()}`,
    );
  }
  return (await response.json()) as T;
}

/** Register an owner and create an org + project through the public API. */
async function createOwnerWorkspace(browser: Browser, baseURL: string): Promise<Owner> {
  const context = await browser.newContext({ baseURL });
  const unique = crypto.randomUUID();
  const email = `revision-owner-${unique}@example.com`;

  await jsonOk(
    context.request.post("/api/v1/users", {
      data: { name: "Revision Owner", email, password: PASSWORD },
    }),
    201,
  );

  const orgSlug = `revision-${unique.slice(0, 8)}`;
  const org = await jsonOk<{ data: { orgId: string; slug: string } }>(
    context.request.post("/api/v1/organizations", {
      data: { name: "Revision Rescan Studio", slug: orgSlug },
    }),
    201,
  );
  const orgId = org.data.orgId;

  const project = await jsonOk<{ data: { projectId: string } }>(
    context.request.post(`/api/v1/organizations/${orgId}/projects`, {
      data: { title: "Revision Rescan Project" },
    }),
    201,
  );

  return {
    context,
    page: await context.newPage(),
    orgId,
    orgSlug: org.data.slug,
    projectId: project.data.projectId,
  };
}

/** Import a screenplay version through the real upload/parse/commit UI. */
async function importVersion(
  page: Page,
  {
    filePath,
    dialogName,
    commitPattern,
  }: {
    filePath: string;
    dialogName: string;
    commitPattern: RegExp;
  },
): Promise<import("@playwright/test").APIResponse> {
  const dialog = page.getByRole("dialog", { name: dialogName });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Screenplay file").setInputFiles(filePath);
  await dialog.getByRole("button", { name: "Upload & Analyze" }).click();

  const diagnostics = page.getByRole("dialog", {
    name: "Parser Diagnostics & Verification",
  });
  await expect(diagnostics).toBeVisible();

  const commitPersisted = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /:commitVersion$/.test(new URL(response.url()).pathname),
  );
  await diagnostics.getByRole("button", { name: commitPattern }).click();
  const committed = await commitPersisted;
  expect(committed.ok()).toBe(true);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  return committed;
}

interface DiffPayload {
  data: {
    beforeVersionId: string | null;
    afterVersionId: string;
    beforeLabel: string | null;
    afterLabel: string;
    elements: {
      changeKind: ChangeKind;
      type: string;
      text: string | null;
      beforeElementId: string | null;
      afterElementId: string | null;
      confidence: string;
    }[];
    summary: {
      unchanged: number;
      moved: number;
      modified: number;
      added: number;
      removed: number;
      affectedElementCount: number;
      carriedForwardItemCount: number;
      carriedForwardEvidenceCount: number;
      providerWorkEstimate: number;
    };
  };
}

interface ClearanceItemListEntry {
  itemId: string;
  versionId: string;
  entityName: string;
  status: string;
  category: string;
}

interface ClearanceItemDetail {
  data: {
    itemId: string;
    entityName: string;
    status: string;
    researchStatus: string;
    claims: { claimId: string; provenanceExcerpt: string }[];
    snapshots: { snapshotId: string; url: string; excerpt: string; retrievedAt: string }[];
    decisions: { recordId: string; kind: string; value: string }[];
  };
}

test.describe("durable revision selective rescan", () => {
  test("imports v1, revises to v2, and runs a durable provider-free rescan", async ({
    browser,
  }, testInfo) => {
    // This is a full end-to-end journey: public registration, two real
    // upload/parse/commit imports, a persisted diff, and a durable rescan job
    // that must reach a terminal state. Give it headroom well beyond the
    // per-assertion waits so a slow-but-healthy run is never a false failure.
    testInfo.setTimeout(180_000);
    const baseURL = String(testInfo.project.use.baseURL);
    const owner = await createOwnerWorkspace(browser, baseURL);
    const { page, orgId, orgSlug, projectId } = owner;

    // Fail the proof if any browser request reaches a real paid provider/cloud.
    // This guards BROWSER egress only; it cannot observe server->provider calls.
    // The actual provider-freedom is structural: the API composition wires
    // in-repo hermetic detection/search/extract/planner doubles (see
    // apps/web/tests/support/e2e_api.py), so no provider code path is reachable.
    const paidProviderHits: string[] = [];
    page.on("request", (request) => {
      if (PAID_PROVIDER_HOST_PATTERN.test(request.url())) {
        paidProviderHits.push(request.url());
      }
    });

    try {
      // --- Import v1 through the real versions-page import flow. ---
      await page.goto(`/app/o/${orgSlug}/projects/${projectId}/versions`);
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: "Script Versions, Diffing & Lineage",
        }),
      ).toBeVisible();
      await expect(page.getByText("Recorded Script Versions (0)")).toBeVisible();

      await page.getByRole("button", { name: "Import Revision" }).click();
      const commitV1 = await importVersion(page, {
        filePath: V1_FIXTURE,
        dialogName: "Import Revision",
        commitPattern: /Commit Revision/,
      });
      const v1VersionId = ((await commitV1.json()) as { data: { versionId: string } }).data
        .versionId;

      // Reload so the persisted version list is the source of truth.
      await page.goto(`/app/o/${orgSlug}/projects/${projectId}/versions`);
      await expect(page.getByText("Recorded Script Versions (1)")).toBeVisible();
      await expect(page.getByText("Version 1", { exact: true })).toBeVisible();
      await expect(page.getByText("Latest Revision", { exact: true })).toBeVisible();

      // --- Attach cited predecessor evidence + a historical decision to a
      // carryable v1 item through the schema-hidden authenticated fixture. ---
      const fixture = await jsonOk<{
        data: {
          citedItemId: string;
          versionId: string;
          sourceUrl: string;
          sourceExcerpt: string;
          retrievedAt: string;
        };
      }>(
        owner.context.request.post(
          `http://127.0.0.1:${API_PORT}/e2e/organizations/${orgId}/projects/${projectId}/predecessor-evidence-fixture`,
          { headers: { origin: baseURL } },
        ),
        201,
      );
      expect(fixture.data.versionId).toBe(v1VersionId);
      expect(fixture.data.sourceUrl).toContain("register.example");

      // The predecessor cited item exposes its ORIGINAL provenance and a
      // historical governed decision BEFORE the rescan runs. This is the
      // baseline the carried-forward assertions compare against.
      const predecessorBefore = await jsonOk<ClearanceItemDetail>(
        owner.context.request.get(
          `/api/v1/organizations/${orgId}/projects/${projectId}/clearance-items/${fixture.data.citedItemId}`,
        ),
        200,
      );
      expect(predecessorBefore.data.snapshots.map((s) => s.url)).toContain(
        fixture.data.sourceUrl,
      );
      expect(predecessorBefore.data.snapshots.map((s) => s.excerpt)).toContain(
        fixture.data.sourceExcerpt,
      );
      expect(predecessorBefore.data.decisions.length).toBeGreaterThan(0);
      const historicalDecisionId = predecessorBefore.data.decisions[0].recordId;

      // --- Upload v2 through the versions-page revision modal. ---
      await page.goto(`/app/o/${orgSlug}/projects/${projectId}/versions`);
      await page.getByRole("button", { name: "Import Revision" }).click();
      const commitV2 = await importVersion(page, {
        filePath: V2_FIXTURE,
        dialogName: "Import Revision",
        commitPattern: /Commit Revision/,
      });
      const v2VersionId = ((await commitV2.json()) as { data: { versionId: string } }).data
        .versionId;

      // The timeline shows both persisted versions with the newest selected.
      await page.goto(
        `/app/o/${orgSlug}/projects/${projectId}/versions?versionId=${v2VersionId}`,
      );
      await expect(page.getByText("Recorded Script Versions (2)")).toBeVisible();
      await expect(page.getByText("Version 1", { exact: true })).toBeVisible();
      await expect(page.getByText("Version 2", { exact: true })).toBeVisible();

      // --- The persisted diff exposes all five change kinds with impact counts
      // sourced from the published contract (data.elements + data.summary). ---
      const diffPayload = await jsonOk<DiffPayload>(
        owner.context.request.get(
          `/api/v1/organizations/${orgId}/projects/${projectId}/script-versions/${v2VersionId}/diff`,
        ),
        200,
      );
      expect(diffPayload.data.beforeVersionId).toBe(v1VersionId);
      expect(diffPayload.data.afterVersionId).toBe(v2VersionId);
      const apiChangeKinds = new Set(
        diffPayload.data.elements.map((element) => element.changeKind),
      );
      expect(apiChangeKinds).toEqual(new Set(CHANGE_KINDS));

      // Per-kind element counts (what the diff viewer's filter chips render).
      const countByKind = (kind: ChangeKind) =>
        diffPayload.data.elements.filter((element) => element.changeKind === kind).length;
      for (const kind of CHANGE_KINDS) {
        expect(countByKind(kind)).toBeGreaterThan(0);
      }
      // The summary impact counts are the authoritative aggregate.
      expect(diffPayload.data.summary.modified).toBe(countByKind("modified"));
      expect(diffPayload.data.summary.added).toBe(countByKind("added"));
      expect(diffPayload.data.summary.removed).toBe(countByKind("removed"));
      expect(diffPayload.data.summary.affectedElementCount).toBe(
        diffPayload.data.summary.modified + diffPayload.data.summary.added,
      );
      expect(diffPayload.data.summary.affectedElementCount).toBeGreaterThan(0);

      // The rendered diff viewer shows every change-kind filter with the same
      // element counts, sourced from the API response the UI consumes.
      const diffViewer = page.getByTestId("script-diff-viewer");
      await expect(diffViewer).toBeVisible();
      await expect(
        diffViewer.getByRole("button", { name: `All (${diffPayload.data.elements.length})` }),
      ).toBeVisible();
      for (const kind of CHANGE_KINDS) {
        const label = kind.charAt(0).toUpperCase() + kind.slice(1);
        await expect(
          diffViewer.getByRole("button", { name: `${label} (${countByKind(kind)})` }),
        ).toBeVisible();
      }
      // The added Nike line is an added row; the removed Ferrari line is a
      // removed row. Each fixture line is unique, so filter to the exact row.
      await expect(
        diffViewer
          .locator('[data-testid="diff-row"][data-change-kind="added"]')
          .filter({ hasText: "Nike" }),
      ).toHaveCount(1);
      await expect(
        diffViewer
          .locator('[data-testid="diff-row"][data-change-kind="removed"]')
          .filter({ hasText: "Ferrari" }),
      ).toHaveCount(1);

      // --- Open the confirmation dialog and explicitly start the rescan.
      // A selective rescan is a governed, provider-spending action; it must
      // never auto-start. The confirm button is the sole trigger. ---
      await page.getByRole("button", { name: /selective re-?scan/i }).click();
      const confirmDialog = page.getByRole("dialog", { name: "Confirm Selective Re-scan" });
      await expect(confirmDialog).toBeVisible();

      const startResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          /:startSelectiveRescan$/.test(new URL(response.url()).pathname),
      );
      await confirmDialog.getByRole("button", { name: "Confirm & Start Re-scan" }).click();
      const startResponse = await startResponsePromise;
      expect(startResponse.status()).toBe(202);
      // The governed write carries a fresh accountable Idempotency-Key.
      const startRequestHeaders = startResponse.request().headers();
      expect(startRequestHeaders["idempotency-key"]).toBeTruthy();
      const rescanJobId = ((await startResponse.json()) as { data: { jobId: string } }).data
        .jobId;
      expect(rescanJobId).toBeTruthy();

      // The URL now carries the persisted rescanJobId.
      await expect(page).toHaveURL(new RegExp(`rescanJobId=${rescanJobId}`));

      // --- Reload and prove the URL restores the SAME persisted job/progress
      // without restarting it (a reload must issue no new start POST). ---
      let restartAttempted = false;
      await page.route("**/*:startSelectiveRescan", (route) => {
        restartAttempted = true;
        return route.continue();
      });
      await page.reload();
      await expect(page.getByTestId("rescan-progress")).toBeVisible();
      expect(restartAttempted).toBe(false);

      // --- Wait for durable terminal success. ---
      const success = page.getByTestId("rescan-result-success");
      await expect(success).toBeVisible({ timeout: 60_000 });
      await expect(success).toContainText("Completed.");

      // The persisted job reached succeeded through the durable job engine.
      const jobRecord = await jsonOk<{
        data: { status: string; stage: string | null; jobType: string };
      }>(
        owner.context.request.get(
          `/api/v1/organizations/${orgId}/projects/${projectId}/jobs/${rescanJobId}`,
        ),
        200,
      );
      expect(jobRecord.data.status).toBe("succeeded");
      expect(jobRecord.data.jobType).toBe("selective_rescan");

      // --- Drain the enqueued detection/research CHILD jobs.
      // The parent selective_rescan job only ENQUEUES durable detection/research
      // children (it never blocks on them), and the local composition runs no
      // queue-draining worker — in the hosted target a durable dispatcher
      // (Cloud Tasks) would pull them. This schema-hidden, hermetic, org+project
      // scoped fixture runs exactly the children the rescan already enqueued
      // through the SAME provider-free doubles, mirroring the repository-level
      // drain in test_revision_selective_rescan.py. It invents no work; it only
      // executes the durable jobs already queued, so the affected items reach a
      // real, provider-free terminal research state. ---
      const drain = await jsonOk<{
        data: { drainedCount: number; outcomes: { jobType: string; status: string }[] };
      }>(
        owner.context.request.post(
          `http://127.0.0.1:${API_PORT}/e2e/organizations/${orgId}/projects/${projectId}/drain-child-jobs`,
          { headers: { origin: baseURL } },
        ),
        200,
      );
      // Every enqueued detection/research child settled at a terminal success
      // through hermetic doubles (jobs already terminal report their persisted
      // status), and at least one research child (the affected items' research)
      // was among them.
      expect(drain.data.drainedCount).toBeGreaterThan(0);
      expect(drain.data.outcomes.every((o) => o.status === "succeeded")).toBe(true);
      expect(
        drain.data.outcomes.some((o) => o.jobType === "research"),
      ).toBe(true);

      // --- Result state sourced from the published clearance-item contracts. ---
      const items = await jsonOk<{ data: ClearanceItemListEntry[] }>(
        owner.context.request.get(
          `/api/v1/organizations/${orgId}/projects/${projectId}/clearance-items`,
        ),
        200,
      );
      const v2Items = items.data.filter((item) => item.versionId === v2VersionId);

      // The MODIFIED (Rolex -> iPhone) and ADDED (Nike) passages were detected
      // as fresh v2 clearance items by the real detection path.
      const iphoneItem = v2Items.find(
        (item) => item.entityName.toLowerCase() === "iphone",
      );
      const nikeItem = v2Items.find((item) => item.entityName.toLowerCase() === "nike");
      expect(iphoneItem, "modified iPhone item detected on v2").toBeTruthy();
      expect(nikeItem, "added Nike item detected on v2").toBeTruthy();

      // Both affected items were RESEARCHED through the real research job
      // (hermetic Search/Extract), reaching a completed research status.
      for (const affected of [iphoneItem!, nikeItem!]) {
        const detail = await jsonOk<ClearanceItemDetail>(
          owner.context.request.get(
            `/api/v1/organizations/${orgId}/projects/${projectId}/clearance-items/${affected.itemId}`,
          ),
          200,
        );
        expect(detail.data.researchStatus).toBe("completed");
      }

      // The REMOVED Ferrari passage never resurfaces as a v2 item and its v1
      // item is not carried onto v2.
      expect(
        v2Items.find((item) => item.entityName.toLowerCase() === "ferrari"),
      ).toBeUndefined();

      // --- The predecessor cited item still references its ORIGINAL provenance
      // (same URL, excerpt, and retrieval time — carried evidence is never
      // re-fetched or re-cleared), and its prior governed decision stays
      // HISTORICAL and unchanged: the rescan mutates neither. This is the
      // observable behavior the carried-forward lineage invariants produce. ---
      const predecessorAfter = await jsonOk<ClearanceItemDetail>(
        owner.context.request.get(
          `/api/v1/organizations/${orgId}/projects/${projectId}/clearance-items/${fixture.data.citedItemId}`,
        ),
        200,
      );
      expect(predecessorAfter.data.snapshots.map((s) => s.url)).toContain(
        fixture.data.sourceUrl,
      );
      expect(predecessorAfter.data.snapshots.map((s) => s.excerpt)).toContain(
        fixture.data.sourceExcerpt,
      );
      expect(predecessorAfter.data.snapshots.map((s) => s.retrievedAt)).toContain(
        predecessorBefore.data.snapshots.find((s) => s.url === fixture.data.sourceUrl)!
          .retrievedAt,
      );
      // The predecessor's own status is untouched by the rescan.
      expect(predecessorAfter.data.status).toBe(predecessorBefore.data.status);
      // The prior decision is unchanged (same record, same value) after rescan.
      const decisionAfter = predecessorAfter.data.decisions.find(
        (decision) => decision.recordId === historicalDecisionId,
      );
      expect(decisionAfter, "historical predecessor decision preserved").toBeTruthy();
      expect(decisionAfter!.value).toBe(predecessorBefore.data.decisions[0].value);

      // --- Revisit the persisted job and prove no duplicate provider work and
      // no second revision: a fresh navigation to the persisted job issues no
      // new start POST, the timeline still shows exactly two versions, and only
      // one selective_rescan job was ever created. ---
      await page.goto(
        `/app/o/${orgSlug}/projects/${projectId}/versions?versionId=${v2VersionId}&rescanJobId=${rescanJobId}`,
      );
      await expect(page.getByTestId("rescan-result-success")).toBeVisible({
        timeout: 30_000,
      });
      expect(restartAttempted).toBe(false);

      const versions = await jsonOk<{ data: { versionId: string }[] }>(
        owner.context.request.get(
          `/api/v1/organizations/${orgId}/projects/${projectId}/script-versions`,
        ),
        200,
      );
      expect(versions.data.length).toBe(2);

      const jobs = await jsonOk<{ data: { jobId: string; jobType: string }[] }>(
        owner.context.request.get(
          `/api/v1/organizations/${orgId}/projects/${projectId}/jobs`,
        ),
        200,
      );
      const rescanJobs = jobs.data.filter((job) => job.jobType === "selective_rescan");
      expect(rescanJobs.length).toBe(1);
      expect(rescanJobs[0].jobId).toBe(rescanJobId);

      // No paid provider was ever contacted from the browser.
      expect(paidProviderHits).toEqual([]);
    } finally {
      await owner.context.close();
    }
  });
});
