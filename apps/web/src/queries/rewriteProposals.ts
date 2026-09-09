import { queryOptions } from "@tanstack/react-query";
import { api, type ApiError, type RewriteProposal } from "@clearcut/contracts";

/**
 * Reads for the governed rewrite-proposal history of one clearance item.
 *
 * The history is server state, not session state: a proposal raised by one
 * person has to survive that person's reload and be visible to the different
 * accountable person who decides on it, because maker-checker is the whole
 * point of the feature. Everything here therefore goes through the generated
 * `listRewriteProposals` operation; no URL is assembled by hand.
 */

export interface RewriteProposalScope {
  orgId: string;
  projectId: string;
  itemId: string;
}

type RewriteListClient = Pick<typeof api, "listRewriteProposals">;
type ViewerIdentityClient = Pick<typeof api, "getSessionContext">;

export const rewriteProposalKeys = {
  /** Tenant + project + item scoped, so no cached entry can cross a boundary. */
  list: (orgId: string, projectId: string, itemId: string) =>
    ["rewrite-proposals", orgId, projectId, itemId] as const,
  /**
   * Namespaced under this feature deliberately. The viewer identity is only
   * needed here to keep a proposer from being offered approval of their own
   * proposal, and a feature-local key cannot collide with another surface's
   * session cache entry.
   */
  viewer: () => ["rewrite-proposals", "viewer-identity"] as const,
};

function toQueryError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

export async function loadRewriteProposals(
  scope: RewriteProposalScope,
  client: RewriteListClient = api,
): Promise<RewriteProposal[]> {
  const result = await client.listRewriteProposals({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
    },
  });
  if (!result.ok) throw toQueryError(result.error);
  return result.value;
}

/**
 * The authenticated user's id, or null when the session carries none.
 *
 * This is a convenience input to the UI only. The server enforces maker-checker
 * on every approval regardless of what this returns.
 */
export async function loadRewriteViewerId(
  client: ViewerIdentityClient = api,
): Promise<string | null> {
  const result = await client.getSessionContext();
  if (!result.ok) throw toQueryError(result.error);
  return result.value.userId ?? null;
}

export function rewriteProposalsQueryOptions(
  scope: RewriteProposalScope,
  client: RewriteListClient = api,
) {
  return queryOptions({
    queryKey: rewriteProposalKeys.list(scope.orgId, scope.projectId, scope.itemId),
    queryFn: () => loadRewriteProposals(scope, client),
  });
}

export function rewriteViewerQueryOptions(client: ViewerIdentityClient = api) {
  return queryOptions({
    queryKey: rewriteProposalKeys.viewer(),
    queryFn: () => loadRewriteViewerId(client),
    staleTime: 60_000,
  });
}
