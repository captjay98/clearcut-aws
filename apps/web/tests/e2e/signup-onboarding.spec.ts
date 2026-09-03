import { expect, test } from "@playwright/test";

test("signup persists through onboarding and workspace reload", async ({ page }, testInfo) => {
  const unique = `${Date.now()}-${testInfo.project.name.replace(/[^a-z0-9]+/gi, "-")}`;
  const email = `signup-${unique}@example.com`;
  const organizationName = `Northstar ${unique}`;
  const organizationSlug = organizationName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

  await page.goto("/auth/sign-in");
  await page.getByRole("link", { name: "Create an account" }).click();

  await expect(page).toHaveURL(/\/auth\/sign-up$/);
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();

  await page.getByLabel("Full Name").fill("Casey Morgan");
  await page.getByLabel("Email Address").fill(email);
  await page.getByLabel("Password").fill("CorrectHorse123!");
  await page.getByRole("button", { name: "Create Account" }).click();

  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByRole("heading", { name: "Create Workspace" })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: "Create Workspace" })).toBeVisible();

  await page.getByLabel("Organization Name").fill(organizationName);
  await expect(page.getByLabel("Workspace URL Identifier")).toHaveValue(organizationSlug);
  await page.getByRole("button", { name: "Create Organization" }).click();

  await expect(page).toHaveURL(new RegExp(`/o/${organizationSlug}/projects/?$`));
  await expect(page.getByRole("heading", { name: "Clearance Projects", exact: true })).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(new RegExp(`/o/${organizationSlug}/projects/?$`));
  await expect(page.getByRole("heading", { name: "Clearance Projects", exact: true })).toBeVisible();

  const sessionContext = await page.evaluate(async () => {
    const response = await fetch("/api/v1/session-context");
    return response.json();
  });
  expect(sessionContext.data.authenticated).toBe(true);
  expect(sessionContext.data.email).toBe(email);
});
