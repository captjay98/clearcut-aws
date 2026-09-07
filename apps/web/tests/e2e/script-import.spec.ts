import path from "node:path";

import { expect, test } from "@playwright/test";

test("imports, acknowledges, commits, and reloads the original screenplay", async ({ page }, testInfo) => {
  const unique = `${Date.now()}-${testInfo.project.name.replace(/[^a-z0-9]+/gi, "-")}`;
  const organizationName = `Signal Studio ${unique}`;
  const organizationSlug = organizationName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const scriptPath = path.resolve(
    process.cwd(),
    "../../demo/original-screenplay/clearcut_test.fountain",
  );

  await page.goto("/app/auth/sign-up");
  await page.getByLabel("Full Name").fill("Jordan Reyes");
  await page.getByLabel("Email Address").fill(`script-import-${unique}@example.com`);
  await page.getByLabel("Password").fill("CorrectHorse123!");
  await page.getByRole("button", { name: "Create Account" }).click();

  await page.getByLabel("Organization Name").fill(organizationName);
  await page.getByRole("button", { name: "Create Organization" }).click();
  await expect(page).toHaveURL(new RegExp(`/o/${organizationSlug}/projects/?$`));

  await page.getByRole("link", { name: "+ New Project" }).click();
  await page.getByLabel("Project / Screenplay Title").fill("Signal Fires Import");
  const projectCreated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/v1\/organizations\/[^/]+\/projects$/.test(new URL(response.url()).pathname),
  );
  await page.getByRole("button", { name: "Save and bring in script" }).click();
  const createResponse = await projectCreated;
  expect(createResponse.ok()).toBe(true);
  expect(createResponse.request().postDataJSON()).toEqual({
    title: "Signal Fires Import",
    description: null,
    productionType: null,
    productionStage: null,
    jurisdiction: null,
    targetLockDate: null,
    reviewBrief: null,
  });
  expect((await createResponse.json()).data).toMatchObject({
    title: "Signal Fires Import",
    description: null,
    productionType: null,
    productionStage: null,
    jurisdiction: null,
    targetLockDate: null,
    reviewBrief: null,
  });
  await expect(page).toHaveURL(/\/projects\/new\?[^#]*projectId=/);
  const projectId = new URL(page.url()).searchParams.get("projectId");
  expect(projectId).toBeTruthy();

  await page.getByRole("button", { name: "Bring in script" }).click();
  let dialog = page.getByRole("dialog", { name: "Import Screenplay" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close import dialog" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Bring in script" })).toBeFocused();

  await page.getByRole("button", { name: "Bring in script" }).click();
  dialog = page.getByRole("dialog", { name: "Import Screenplay" });
  await dialog.getByLabel("Screenplay file").setInputFiles(scriptPath);

  let releaseUploadRequest!: () => void;
  let markUploadRequestStarted!: () => void;
  const uploadRequestStarted = new Promise<void>((resolve) => {
    markUploadRequestStarted = resolve;
  });
  await page.route("**/upload-capabilities", async (route) => {
    markUploadRequestStarted();
    await new Promise<void>((resolve) => {
      releaseUploadRequest = resolve;
    });
    await route.continue();
  });

  await dialog.getByRole("button", { name: "Upload & Analyze" }).click();
  await uploadRequestStarted;
  await expect(dialog.getByRole("button", { name: "Uploading & Parsing..." })).toBeDisabled();
  await expect(dialog).toBeFocused();

  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Tab");
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);

  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);

  releaseUploadRequest();

  await expect(page.getByRole("dialog", { name: "Parser Diagnostics & Verification" })).toBeVisible();
  await expect(page.getByText("7", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Possible scene heading is missing a period after INT or EXT."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Accept Warnings & Commit Version 1" }).click();

  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByRole("heading", { name: "Check script" })).toBeFocused();
  await page.goto(`/app/o/${organizationSlug}/projects/${projectId}/workspace`);
  const viewer = page.getByTestId("screenplay-viewer");
  await expect(viewer.getByText("Signal Fires", { exact: true })).toBeVisible();
  await expect(viewer.getByText("v1", { exact: true })).toBeVisible();
  await expect(viewer.getByText("EXT. GRIFFITH OBSERVATORY - PRE-DAWN")).toBeVisible();
  await expect(viewer.getByText("EXT. ROOFTOP - DAWN")).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("screenplay-viewer").getByText("Signal Fires", { exact: true })).toBeVisible();
  await expect(page.getByText("EXT. ROOFTOP - DAWN")).toBeVisible();
  await expect(page.getByText("Borrowed Light", { exact: true })).toHaveCount(0);
});
