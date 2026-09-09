import { queryOptions } from "@tanstack/react-query";
import { api, type Project } from "@clearcut/contracts";

type ProjectListClient = Pick<typeof api, "listProjects">;

export const organizationProjectKeys = {
  list: (orgId: string) => ["organization-projects", orgId] as const,
};

/**
 * The projects the caller can actually see in this organization.
 *
 * Project-scoped surfaces reached through an organization-scoped route (Trust is
 * the one) resolve their scope from this list rather than guessing an id. An
 * empty list is a real answer — "there is nothing to scope to" — not a failure.
 */
export function organizationProjectsQueryOptions(
  orgId: string,
  client: ProjectListClient = api,
) {
  return queryOptions({
    queryKey: organizationProjectKeys.list(orgId),
    queryFn: async (): Promise<Project[]> => {
      const result = await client.listProjects({ params: { orgId } });
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return result.value ?? [];
    },
  });
}

/**
 * Resolve which project a project-scoped read should use.
 *
 * The rules, in order:
 *  - an explicitly requested id is honoured only when the caller can see it, so
 *    a hand-edited URL cannot make the surface claim scope it does not have;
 *  - a single visible project resolves automatically, and the caller is told
 *    which one it is;
 *  - two or more resolve to nothing, because picking one silently would present
 *    one project's evaluation as if it were the organization's.
 */
export interface ProjectScopeResolution {
  projectId: string | null;
  /** True when the id came from the URL rather than from being the only option. */
  requested: boolean;
  /** True when the requested id is not among the projects the caller can see. */
  requestedButNotVisible: boolean;
  /** True when a choice is needed because more than one project is visible. */
  needsChoice: boolean;
}

export function resolveProjectScope(
  projects: readonly Project[],
  requestedProjectId: string | undefined,
): ProjectScopeResolution {
  if (requestedProjectId) {
    const visible = projects.some((project) => project.projectId === requestedProjectId);
    return {
      projectId: visible ? requestedProjectId : null,
      requested: true,
      requestedButNotVisible: !visible,
      needsChoice: !visible && projects.length > 0,
    };
  }
  if (projects.length === 1) {
    return {
      projectId: projects[0].projectId,
      requested: false,
      requestedButNotVisible: false,
      needsChoice: false,
    };
  }
  return {
    projectId: null,
    requested: false,
    requestedButNotVisible: false,
    needsChoice: projects.length > 1,
  };
}
