import { expect, test, type Page, type TestInfo } from "@playwright/test";

const SCRIPT = `Title: Signal Check

EXT. MARKET STREET - DAY

MARA photographs a Coca-Cola sign outside the Apple store.

MARA
This production needs a sourced review.
`;

const SLOW_SCRIPT = `Title: Interrupted Check

EXT. TEST STAGE - DAY

E2E HOLD while a Coca-Cola can sits on the desk.

MARA
Wait for the accountable review.
`;

interface FlowContext {
  orgSlug: string;
  projectId: string;
}

function fakeSucceededJob(jobId: string, jobType: string, scriptVersionId: string) {
  const now = new Date().toISOString();
  return {
    jobId,
    status: "succeeded",
    jobType,
    target: { type: "script_version", id: scriptVersionId },
    canRetry: false,
    progress: 100,
    stage: "succeeded",
    resultSummary: {
      scriptVersionId,
      elementsProcessed: 4,
      candidateCount: 1,
      clearanceItemCount: 1,
      reviewStatus: "unresolved",
    },
    error: null,
    attemptCount: 1,
    attempts: [],
    history: [],
    availableAt: now,
    createdAt: now,
    updatedAt: now,
  };
}

async function createNewClearance(page: Page, testInfo: TestInfo): Promise<FlowContext> {
  const unique = `${Date.now()}-${testInfo.workerIndex}-${testInfo.project.name.replace(/[^a-z0-9]+/gi, "-")}`;
  const organizationName = `Clearance Flow ${unique}`;
  const orgSlug = organizationName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

  await page.goto("/app/auth/sign-up");
  await page.getByLabel("Full Name").fill("Morgan Lee");
  await page.getByLabel("Email Address").fill(`new-clearance-${unique}@example.com`);
  await page.getByLabel("Password").fill("CorrectHorse123!");
  await page.getByRole("button", { name: "Create Account" }).click();

  await page.getByLabel("Organization Name").fill(organizationName);
  await page.getByRole("button", { name: "Create Organization" }).click();
  await page.getByRole("link", { name: "+ New Project" }).click();
  await expect(page.getByRole("heading", { name: "Describe production" })).toBeVisible();
  await page.getByLabel("Project / Screenplay Title").fill("Signal Check");
  await page.getByLabel("Description / Production Notes (Optional)").fill(
    "Pre-clearance evidence gathering for qualified human review.",
  );
  await page.getByLabel("Production Type").selectOption("Feature film");
  await page.getByLabel("Production Stage").selectOption("Pre-production");
  await page.getByLabel("Jurisdiction").fill("California, United States");
  await page.getByLabel("Target Lock Date").fill("2026-10-15");
  await page.getByLabel("Review Brief").fill(
    "Review named products and locations for unresolved evidence needs.",
  );
  await page.getByRole("button", { name: "Save and bring in script" }).click();

  await expect(page).toHaveURL(/\/projects\/new\?[^#]*projectId=/);
  const projectId = new URL(page.url()).searchParams.get("projectId");
  expect(projectId).toBeTruthy();
  await expect(page.getByRole("heading", { name: "Bring in script" })).toBeVisible();
  return { orgSlug, projectId: projectId! };
}

async function commitPastedVersion(page: Page, script: string): Promise<string> {
  await page.getByRole("button", { name: "Bring in script" }).click();
  const dialog = page.getByRole("dialog", { name: "Import Screenplay" });
  await dialog.getByRole("button", { name: "Paste Screenplay Text" }).click();
  await dialog.getByLabel("Screenplay Text Content").fill(script);
  await dialog.getByRole("button", { name: "Upload & Analyze" }).click();
  const diagnostics = page.getByRole("dialog", { name: "Parser Diagnostics & Verification" });
  const commitButton = diagnostics.getByRole("button", {
    name: /Commit Version 1|Accept Warnings & Commit Version 1/,
  });
  await commitButton.click();
  await expect(diagnostics).not.toBeVisible();
  await expect(page).toHaveURL(/versionId=/);
  const versionId = new URL(page.url()).searchParams.get("versionId");
  expect(versionId).toBeTruthy();
  return versionId!;
}

test("persists all three new-clearance steps and renders only authoritative terminal results", async ({
  page,
}, testInfo) => {
  const { orgSlug, projectId } = await createNewClearance(page, testInfo);
  const versionId = await commitPastedVersion(page, SCRIPT);

  const versionResponse = await page.request.get(
    `/api/v1/organizations/${orgSlug}/projects/${projectId}/script-versions/${versionId}`,
  );
  expect(versionResponse.ok()).toBe(true);
  const version = (await versionResponse.json()).data;
  await expect(page.getByTestId("version-scene-count")).toHaveText(String(version.sceneCount));
  await expect(page.getByTestId("version-element-count")).toHaveText(String(version.elementCount));

  await page.reload();
  await expect(page.getByText("Feature film")).toBeVisible();
  await expect(page.getByText("Pre-production")).toBeVisible();
  await expect(page.getByText("California, United States")).toBeVisible();
  await expect(page.getByText("October 15, 2026")).toBeVisible();
  await expect(
    page.getByText("Review named products and locations for unresolved evidence needs."),
  ).toBeVisible();
  await expect(page.getByText("Version 1 is ready for a check.")).toBeVisible();
  await page.getByRole("button", { name: "Check script" }).click();
  await expect(page).toHaveURL(/jobId=/);
  const jobId = new URL(page.url()).searchParams.get("jobId");
  expect(jobId).toBeTruthy();

  await expect(page.getByRole("heading", { name: "Check succeeded" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("Unresolved — human review required")).toBeVisible();
  await expect(
    page.getByText(/Detected unresolved findings are pending evidence research/),
  ).toBeVisible();
  await expect(page.getByText(/These sourced findings/)).toHaveCount(0);

  const jobResponse = await page.request.get(
    `/api/v1/organizations/${orgSlug}/projects/${projectId}/jobs/${jobId}`,
  );
  expect(jobResponse.ok()).toBe(true);
  const job = (await jobResponse.json()).data;
  expect(job.status).toBe("succeeded");
  await expect(page.getByTestId("job-stage")).toHaveAttribute("data-stage", job.stage);
  await expect(page.getByTestId("elements-processed-count")).toHaveText(
    String(job.resultSummary.elementsProcessed),
  );
  await expect(page.getByTestId("candidate-count")).toHaveText(
    String(job.resultSummary.candidateCount),
  );
  await expect(page.getByTestId("clearance-item-count")).toHaveText(
    String(job.resultSummary.clearanceItemCount),
  );

  await expect(page.getByRole("link", { name: "Open persisted screenplay" })).toHaveAttribute(
    "href",
    `/app/o/${orgSlug}/projects/${projectId}/workspace`,
  );
  await expect(page.getByRole("link", { name: "Review detected items" })).toHaveAttribute(
    "href",
    `/app/o/${orgSlug}/projects/${projectId}/items`,
  );
  await expect(page.getByRole("link", { name: "View operation Records" })).toHaveAttribute(
    "href",
    new RegExp(`/app/o/${orgSlug}/records\\?.*projectId=${projectId}`),
  );

  const recordsRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.startsWith("/api/v1/organizations/") && url.pathname.endsWith("/records");
  });
  await page.getByRole("link", { name: "View operation Records" }).click();
  const requestedRecordsUrl = new URL((await recordsRequest).url());
  expect(requestedRecordsUrl.searchParams.get("view")).toBe("operations");
  expect(requestedRecordsUrl.searchParams.get("projectId")).toBe(projectId);
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Check succeeded" })).toBeVisible();

  const itemsResponse = await page.request.get(
    `/api/v1/organizations/${orgSlug}/projects/${projectId}/clearance-items`,
  );
  expect(itemsResponse.ok()).toBe(true);
  const persistedItems = (await itemsResponse.json()).data;
  expect(persistedItems.length).toBeGreaterThan(0);
  await page.getByRole("link", { name: "Review detected items" }).click();
  await expect(page).toHaveURL(`/app/o/${orgSlug}/projects/${projectId}/items`);
  await expect(page.getByRole("heading", { name: "Detected clearance items" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: persistedItems[0].entityName, exact: true }),
  ).toBeVisible();
  const persistedItemRow = page.getByRole("listitem").filter({
    has: page.getByRole("heading", {
      name: persistedItems[0].entityName,
      exact: true,
    }),
  });
  const reviewItemLink = persistedItemRow.getByRole("link", {
    name: "Review item",
  });
  await expect(reviewItemLink).toHaveAttribute(
    "href",
    `/app/o/${orgSlug}/projects/${projectId}/items/${persistedItems[0].itemId}`,
  );
  await page.goBack();

  await page.getByRole("link", { name: "Open persisted screenplay" }).click();
  await expect(page).toHaveURL(`/app/o/${orgSlug}/projects/${projectId}/workspace`);
  await expect(page.getByText("EXT. MARKET STREET - DAY")).toBeVisible();
});

test("cancel sends the governed API command and never exposes terminal counts as complete", async ({
  page,
}, testInfo) => {
  await createNewClearance(page, testInfo);
  await commitPastedVersion(page, SLOW_SCRIPT);

  await page.getByRole("button", { name: "Check script" }).click();
  await expect(page.getByRole("progressbar", { name: "Persisted check progress" })).toBeVisible();
  await expect(
    page.getByRole("listitem").filter({ hasText: "Check script" }),
  ).not.toContainText("✓");
  await page.reload();
  await expect(page.getByRole("button", { name: "Cancel check" })).toBeVisible();
  const cancelRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith(":cancel"),
  );
  await page.getByRole("button", { name: "Cancel check" }).click();
  await cancelRequest;

  await expect(page.getByRole("heading", { name: "Check cancelled" })).toBeVisible();
  await expect(page.getByTestId("terminal-result-counts")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Review detected items" })).toHaveCount(0);
  const retryRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith(":retry"),
  );
  await page.getByRole("button", { name: "Retry check" }).click();
  await retryRequest;
  await expect(page.getByText("Attempt 1 — cancelled")).toBeVisible();
  await expect(page.getByText("Cancellation requested")).toBeVisible();
  await expect(page.getByText("Retry requested")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Check queued|Checking script|Check succeeded/ })).toBeVisible();
});

test("rejects a persisted job that is not the selected version's detection check", async ({
  page,
}, testInfo) => {
  const { projectId } = await createNewClearance(page, testInfo);
  const versionId = await commitPastedVersion(page, SCRIPT);
  const fakeJobId = "01999999-9999-7999-8999-999999999999";
  let job = fakeSucceededJob(fakeJobId, "research", versionId);

  await page.route("**/script-versions/*:detect", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ data: job, meta: { requestId: "e2e-job-identity" } }),
    });
  });
  await page.route(`**/jobs/${fakeJobId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: job, meta: { requestId: "e2e-job-read" } }),
    });
  });

  await page.getByRole("button", { name: "Check script" }).click();
  await expect(page.getByRole("heading", { name: "Check unavailable" })).toBeVisible();
  await expect(page.getByText("This operation is not a script detection check.")).toBeVisible();

  const wrongVersionId = "01999999-9999-7999-8999-999999999998";
  job = {
    ...fakeSucceededJob(fakeJobId, "detection", wrongVersionId),
    status: "queued",
    progress: 0,
    stage: "queued",
    resultSummary: null,
  };
  await page.reload();
  await expect(page.getByRole("heading", { name: "Check unavailable" })).toBeVisible();
  await expect(page.getByText("This check belongs to a different persisted script version.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel check" })).toHaveCount(0);

  job = { ...job, status: "running", progress: 40, stage: "detecting_candidates" };
  await page.reload();
  await expect(page.getByRole("heading", { name: "Check unavailable" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel check" })).toHaveCount(0);
  await expect(page.getByRole("progressbar")).toHaveCount(0);

  job = fakeSucceededJob(fakeJobId, "detection", wrongVersionId);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Check unavailable" })).toBeVisible();
  await expect(page.getByText("This check belongs to a different persisted script version.")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`projectId=${projectId}.*versionId=${versionId}.*jobId=${fakeJobId}`));
});

test("renders interrupted and failed persisted states and retries through the API", async ({
  page,
}, testInfo) => {
  await createNewClearance(page, testInfo);
  const versionId = await commitPastedVersion(page, SCRIPT);
  const fakeJobId = "01999999-9999-7999-8999-999999999997";
  let job = {
    ...fakeSucceededJob(fakeJobId, "detection", versionId),
    status: "manual_retry",
    canRetry: true,
    progress: 0,
    stage: "interrupted",
    resultSummary: null,
    error: {
      code: "interrupted",
      message: "The local operation was interrupted.",
      retryable: true,
    },
  };

  await page.route("**/script-versions/*:detect", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ data: job, meta: { requestId: "e2e-manual-retry" } }),
    });
  });
  await page.route(`**/jobs/${fakeJobId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: job, meta: { requestId: "e2e-job-state" } }),
    });
  });
  await page.route(`**/jobs/${fakeJobId}:retry`, async (route) => {
    job = { ...job, status: "queued", stage: "queued", error: null };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: job, meta: { requestId: "e2e-retry" } }),
    });
  });

  await page.getByRole("button", { name: "Check script" }).click();
  await expect(page.getByRole("heading", { name: "Check interrupted" })).toBeVisible();
  await expect(page.getByText("Manual retry required after an interrupted local operation.")).toBeVisible();
  const retryRequest = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith(":retry"),
  );
  await page.getByRole("button", { name: "Retry check" }).click();
  await retryRequest;
  await expect(page.getByRole("heading", { name: "Check queued" })).toBeVisible();

  job = {
    ...job,
    status: "failed",
    stage: "failed",
    error: { code: "judge_rejected", message: "The persisted check failed.", retryable: false },
  };
  await page.reload();
  await expect(page.getByRole("heading", { name: "Check failed" })).toBeVisible();
  await expect(page.getByText("The persisted check failed.")).toBeVisible();
  await expect(page.getByTestId("terminal-result-counts")).toHaveCount(0);
});

test("shows a truthful unavailable state when detection cannot be started", async ({ page }, testInfo) => {
  await createNewClearance(page, testInfo);
  await commitPastedVersion(page, SCRIPT);

  await page.route("**/script-versions/*:detect", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "capability_unavailable",
          message: "Detection runtime is not configured for this environment.",
          requestId: "e2e-unavailable",
          retryable: true,
        },
      }),
    });
  });

  await page.getByRole("button", { name: "Check script" }).click();
  await expect(page.getByRole("heading", { name: "Check unavailable" })).toBeVisible();
  await expect(page.getByText("Detection runtime is not configured for this environment.")).toBeVisible();
  await expect(page.getByTestId("terminal-result-counts")).toHaveCount(0);
});



test("items route shows persisted empty and error states without redirecting", async ({
  page,
}, testInfo) => {
  const { orgSlug, projectId } = await createNewClearance(page, testInfo);
  await page.goto(`/app/o/${orgSlug}/projects/${projectId}/items`);
  await expect(page).toHaveURL(`/app/o/${orgSlug}/projects/${projectId}/items`);
  await expect(page.getByRole("heading", { name: "Detected clearance items" })).toBeVisible();
  await expect(page.getByText("No detected clearance items yet.")).toBeVisible();

  await page.route(`**/projects/${projectId}/clearance-items`, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "capability_unavailable",
          message: "Persisted clearance items are temporarily unavailable.",
          requestId: "items-unavailable",
          retryable: true,
        },
      }),
    });
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Clearance items unavailable" })).toBeVisible();
  await expect(
    page.getByText("Persisted clearance items are temporarily unavailable."),
  ).toBeVisible();
});



test("renders persisted detection stages and stops polling at terminal state", async ({
  page,
}, testInfo) => {
  await createNewClearance(page, testInfo);
  const versionId = await commitPastedVersion(page, SCRIPT);
  const jobId = "01999999-9999-7999-8999-999999999996";
  const base = fakeSucceededJob(jobId, "detection", versionId);
  const states = [
    { ...base, status: "running", progress: 5, stage: "reading_persisted_elements", resultSummary: null },
    { ...base, status: "running", progress: 40, stage: "detecting_candidates", resultSummary: null },
    { ...base, status: "running", progress: 85, stage: "evaluating_findings", resultSummary: null },
    base,
  ];
  let reads = 0;

  await page.route("**/script-versions/*:detect", async (route) => {
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ data: states[0], meta: { requestId: "stage-start" } }),
    });
  });
  await page.route(`**/jobs/${jobId}`, async (route) => {
    const state = states[Math.min(reads, states.length - 1)];
    reads += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: state, meta: { requestId: `stage-${reads}` } }),
    });
  });

  await page.getByRole("button", { name: "Check script" }).click();
  await expect(page.getByTestId("job-stage")).toHaveText("Reading persisted elements");
  await expect(page.getByTestId("job-stage")).toHaveText("Detecting candidates");
  await expect(page.getByTestId("job-stage")).toHaveText("Evaluating findings");
  await expect(page.getByRole("heading", { name: "Check succeeded" })).toBeVisible();

  const readsAtTerminal = reads;
  await page.waitForTimeout(1_600);
  expect(reads).toBe(readsAtTerminal);
});
