import { api } from "@clearcut/contracts";

type NavigateTo = (options: {
  to: "/organizations" | "/onboarding" | "/o/$orgSlug/projects";
  params?: { orgSlug: string };
}) => unknown;

/**
 * After sign-in/sign-up/invite: multi-org accounts choose a workspace; single
 * org accounts go straight to their default; no org goes to onboarding.
 */
export async function navigateAfterAuthentication(navigate: NavigateTo): Promise<void> {
  const orgs = await api.listOrganizations();
  if (orgs.ok && orgs.value.length > 1) {
    await navigate({ to: "/organizations" });
    return;
  }
  const entryRes = await api.resolveOrganizationEntry();
  if (entryRes.ok && entryRes.value?.defaultOrgSlug) {
    await navigate({
      to: "/o/$orgSlug/projects",
      params: { orgSlug: entryRes.value.defaultOrgSlug },
    });
    return;
  }
  await navigate({ to: "/onboarding" });
}
