import type { QueryClient } from "@tanstack/react-query";
import { api, type ApiError, type RewriteProposal } from "@clearcut/contracts";
import { clearanceItemKeys } from "../queries/clearanceItems";
import {
  rewriteProposalKeys,
  type RewriteProposalScope,
} from "../queries/rewriteProposals";

/**
 * Governed rewrite-lifecycle commands: propose, approve, reject, withdraw.
 *
 * Nothing is applied locally. Each command returns the server's own projection
 * of the proposal, and success is only reported once the server has confirmed
 * it. The authoritative history is then refetched rather than patched, so what
 * the card shows after an action is what is persisted.
 */

export type RewriteTransition = "approve" | "reject" | "withdraw";

export interface ProposeRewriteInput {
  proposedText: string;
  rationale?: string;
}

export interface RewriteTransitionInput {
  proposalId: string;
  transition: RewriteTransition;
}

type ProposeClient = Pick<typeof api, "proposeRewrite">;
type TransitionClient = Pick<
  typeof api,
  "approveRewrite" | "rejectRewrite" | "withdrawRewrite"
>;

function toCommandError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

export async function executeProposeRewrite(
  scope: RewriteProposalScope,
  input: ProposeRewriteInput,
  client: ProposeClient = api,
): Promise<RewriteProposal> {
  const proposedText = input.proposedText.trim();
  const rationale = input.rationale?.trim();
  const result = await client.proposeRewrite({
    params: {
      orgId: scope.orgId,
      projectId: scope.projectId,
      itemId: scope.itemId,
    },
    body: {
      proposedText,
      ...(rationale ? { rationale } : {}),
    },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeRewriteTransition(
  scope: RewriteProposalScope,
  input: RewriteTransitionInput,
  client: TransitionClient = api,
): Promise<RewriteProposal> {
  const params = {
    orgId: scope.orgId,
    projectId: scope.projectId,
    proposalId: input.proposalId,
  };
  const result =
    input.transition === "approve"
      ? await client.approveRewrite({ params })
      : input.transition === "reject"
        ? await client.rejectRewrite({ params })
        : await client.withdrawRewrite({ params });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

/**
 * Refetch every read a rewrite command can change.
 *
 * The proposal history obviously changes. A lifecycle move also advances the
 * item's governed version, so the item detail and the flag list would otherwise
 * keep showing a version that can no longer be used as an expected version.
 */
async function invalidateRewriteState(
  queryClient: QueryClient,
  scope: RewriteProposalScope,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: rewriteProposalKeys.list(scope.orgId, scope.projectId, scope.itemId),
    exact: true,
  });
  await queryClient.invalidateQueries({
    queryKey: clearanceItemKeys.detail(scope.orgId, scope.projectId, scope.itemId),
    exact: true,
  });
  await queryClient.invalidateQueries({
    queryKey: clearanceItemKeys.list(scope.orgId, scope.projectId),
  });
  await queryClient.invalidateQueries({ queryKey: ["records", scope.orgId] });
}

export function proposeRewriteMutationOptions(
  scope: RewriteProposalScope,
  queryClient: QueryClient,
  client: ProposeClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: ProposeRewriteInput) =>
      executeProposeRewrite(scope, input, client),
    onSuccess: () => invalidateRewriteState(queryClient, scope),
  };
}

export function rewriteTransitionMutationOptions(
  scope: RewriteProposalScope,
  queryClient: QueryClient,
  client: TransitionClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (input: RewriteTransitionInput) =>
      executeRewriteTransition(scope, input, client),
    onSuccess: () => invalidateRewriteState(queryClient, scope),
  };
}
