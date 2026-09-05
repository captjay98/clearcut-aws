import { api, type Membership } from "@clearcut/contracts";

export interface OrganizationMemberScope {
  orgId: string;
  projectId: string;
}

export function organizationMentionRecipientsQueryOptions({
  orgId,
  projectId,
}: OrganizationMemberScope) {
  return {
    queryKey: ["organization-members", orgId, projectId, "mention-recipients"] as const,
    queryFn: async (): Promise<Membership[]> => {
      const [membersResult, sessionResult] = await Promise.all([
        api.listOrganizationMembers({ params: { orgId } }),
        api.getSessionContext(),
      ]);
      if (!membersResult.ok) throw Object.assign(new Error(membersResult.error.message), membersResult.error);
      if (!sessionResult.ok) throw Object.assign(new Error(sessionResult.error.message), sessionResult.error);

      const actorId = sessionResult.value.userId;
      return membersResult.value.filter((member) => {
        const hasProjectAccess =
          member.role === "owner" ||
          member.role === "admin" ||
          member.projectGrants?.includes(projectId) === true;
        return member.active && member.userId !== actorId && hasProjectAccess;
      });
    },
    staleTime: 30_000,
  };
}
