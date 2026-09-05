import type { APIResponse, Browser, BrowserContext, Page } from "@playwright/test";

const PASSWORD = "Task11Browser123!";

export interface EvidenceActor {
  context: BrowserContext;
  page: Page;
  email: string;
  userId: string;
  membershipId?: string;
}

export interface EvidenceWorkspace {
  owner: EvidenceActor;
  reviewer: EvidenceActor;
  editor: EvidenceActor;
  orgId: string;
  orgSlug: string;
  projectId: string;
  citedItemId: string;
  zeroEvidenceItemId: string;
  close: () => Promise<void>;
}

interface RegistrationData {
  data: {
    userId: string;
  };
}

interface OrganizationData {
  data: {
    orgId: string;
    slug: string;
  };
}

interface ProjectData {
  data: {
    projectId: string;
  };
}

interface InvitationData {
  data: {
    token: string;
  };
}

interface InvitationAcceptanceData {
  data: {
    membershipId: string;
  };
}

interface EvidenceFixtureData {
  data: {
    citedItemId: string;
    zeroEvidenceItemId: string;
  };
}

async function responseJson<T>(response: APIResponse, expectedStatus: number): Promise<T> {
  if (response.status() !== expectedStatus) {
    throw new Error(
      `Expected ${expectedStatus} from ${response.url()}, ` +
        `received ${response.status()}: ${await response.text()}`,
    );
  }
  return (await response.json()) as T;
}

async function registerActor(
  browser: Browser,
  baseURL: string,
  label: string,
): Promise<EvidenceActor> {
  const context = await browser.newContext({ baseURL });
  const email = `${label}-${crypto.randomUUID()}@example.com`;
  const registration = await context.request.post("/api/v1/users", {
    data: {
      name: `Task 11 ${label}`,
      email,
      password: PASSWORD,
    },
  });
  const payload = await responseJson<RegistrationData>(registration, 201);
  return {
    context,
    page: await context.newPage(),
    email,
    userId: payload.data.userId,
  };
}

async function inviteActor(
  browser: Browser,
  baseURL: string,
  owner: EvidenceActor,
  orgId: string,
  projectId: string,
  role: "reviewer" | "editor",
): Promise<EvidenceActor> {
  const email = `${role}-${crypto.randomUUID()}@example.com`;
  const invitation = await owner.context.request.post(
    `/api/v1/organizations/${orgId}/invitations`,
    { data: { email, role } },
  );
  const invitationPayload = await responseJson<InvitationData>(invitation, 201);

  const context = await browser.newContext({ baseURL });
  const registration = await context.request.post("/api/v1/users", {
    data: {
      name: `Task 11 ${role}`,
      email,
      password: PASSWORD,
    },
  });
  const registrationPayload = await responseJson<RegistrationData>(registration, 201);
  const acceptance = await context.request.post(
    `/api/v1/invitations/${invitationPayload.data.token}:accept`,
  );
  const acceptancePayload = await responseJson<InvitationAcceptanceData>(acceptance, 200);

  const grant = await owner.context.request.post(
    `/api/v1/organizations/${orgId}/memberships/${acceptancePayload.data.membershipId}:changeProjectGrant`,
    { data: { projectIds: [projectId] } },
  );
  await responseJson(grant, 200);

  return {
    context,
    page: await context.newPage(),
    email,
    userId: registrationPayload.data.userId,
    membershipId: acceptancePayload.data.membershipId,
  };
}

export async function createEvidenceWorkspace(
  browser: Browser,
  baseURL: string,
): Promise<EvidenceWorkspace> {
  const owner = await registerActor(browser, baseURL, "owner");
  const orgSlug = `task-11-${crypto.randomUUID()}`;
  const organization = await owner.context.request.post("/api/v1/organizations", {
    data: {
      name: "Task 11 Evidence Studio",
      slug: orgSlug,
    },
  });
  const organizationPayload = await responseJson<OrganizationData>(organization, 201);
  const orgId = organizationPayload.data.orgId;

  const project = await owner.context.request.post(
    `/api/v1/organizations/${orgId}/projects`,
    { data: { title: "Task 11 Evidence Workspace" } },
  );
  const projectPayload = await responseJson<ProjectData>(project, 201);
  const projectId = projectPayload.data.projectId;

  const apiPort = process.env.CLEARCUT_E2E_API_PORT ?? "28080";
  const evidenceFixture = await owner.context.request.post(
    `http://127.0.0.1:${apiPort}/e2e/organizations/${orgId}/projects/${projectId}/evidence-fixture`,
    { headers: { origin: baseURL } },
  );
  const fixturePayload = await responseJson<EvidenceFixtureData>(evidenceFixture, 201);

  const reviewer = await inviteActor(
    browser,
    baseURL,
    owner,
    orgId,
    projectId,
    "reviewer",
  );
  const editor = await inviteActor(
    browser,
    baseURL,
    owner,
    orgId,
    projectId,
    "editor",
  );

  return {
    owner,
    reviewer,
    editor,
    orgId,
    orgSlug: organizationPayload.data.slug,
    projectId,
    citedItemId: fixturePayload.data.citedItemId,
    zeroEvidenceItemId: fixturePayload.data.zeroEvidenceItemId,
    close: async () => {
      await Promise.allSettled([
        owner.context.close(),
        reviewer.context.close(),
        editor.context.close(),
      ]);
    },
  };
}

export function itemPath(
  workspace: EvidenceWorkspace,
  itemId: string,
): string {
  return `/o/${workspace.orgId}/projects/${workspace.projectId}/items/${itemId}`;
}
