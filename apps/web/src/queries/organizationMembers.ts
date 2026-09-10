import { api, type Membership } from "@clearcut/contracts";

export interface OrganizationMemberScope {
  orgId: string;
  projectId: string;
}

/** Roles that may hold a clearance assignment: the reviewing roles plus the
 *  org leadership that implicitly reviews. Editors coordinate rewrites but do
 *  not own review, so they are not offered as assignees. */
const ASSIGNABLE_ROLES: ReadonlySet<Membership["role"]> = new Set([
  "owner",
  "admin",
  "reviewer",
]);

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

/**
 * Members eligible to receive a clearance assignment in this project: active,
 * in an assignable role, and either org leadership or explicitly granted the
 * project. The server re-authorizes every assignment, so this only decides who
 * to *offer* as an assignee.
 */
export function assignableMembersQueryOptions({
  orgId,
  projectId,
}: OrganizationMemberScope) {
  return {
    queryKey: ["organization-members", orgId, projectId, "assignable"] as const,
    queryFn: async (): Promise<Membership[]> => {
      const result = await api.listOrganizationMembers({ params: { orgId } });
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return result.value.filter((member) => {
        const hasProjectAccess =
          member.role === "owner" ||
          member.role === "admin" ||
          member.projectGrants?.includes(projectId) === true;
        return member.active && ASSIGNABLE_ROLES.has(member.role) && hasProjectAccess;
      });
    },
    staleTime: 30_000,
  };
}
