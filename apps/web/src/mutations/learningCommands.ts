import type { QueryClient } from "@tanstack/react-query";
import { api, type ApiError } from "@clearcut/contracts";
import { trustKeys } from "../queries/trust";

type PromoteClient = Pick<typeof api, "promoteLearningCandidate">;
type RollbackClient = Pick<typeof api, "rollbackLearningCandidate">;

export interface LearningStageResult {
  candidateId: string;
  stage: string;
}

function toCommandError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

export async function executePromoteLearningCandidate(
  orgId: string,
  candidateId: string,
  client: PromoteClient = api,
): Promise<LearningStageResult> {
  const result = await client.promoteLearningCandidate({
    params: { orgId, candidateId },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

export async function executeRollbackLearningCandidate(
  orgId: string,
  candidateId: string,
  client: RollbackClient = api,
): Promise<LearningStageResult> {
  const result = await client.rollbackLearningCandidate({
    params: { orgId, candidateId },
  });
  if (!result.ok) throw toCommandError(result.error);
  return result.value;
}

async function invalidateLearningState(
  queryClient: QueryClient,
  orgId: string,
): Promise<void> {
  await queryClient.invalidateQueries({
    queryKey: trustKeys.learningCandidates(orgId),
  });
  // Promotion and rollback are governed actions; both write to the ledger.
  await queryClient.invalidateQueries({ queryKey: ["records", orgId] });
}

/**
 * Advancing or reverting a learning candidate is a governed, human-triggered
 * action: never auto-retried, and the returned stage is not assumed — the
 * candidate list is refetched so the surface shows the persisted stage.
 */
export function promoteLearningCandidateMutationOptions(
  orgId: string,
  queryClient: QueryClient,
  client: PromoteClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (candidateId: string) =>
      executePromoteLearningCandidate(orgId, candidateId, client),
    onSuccess: () => invalidateLearningState(queryClient, orgId),
  };
}

export function rollbackLearningCandidateMutationOptions(
  orgId: string,
  queryClient: QueryClient,
  client: RollbackClient = api,
) {
  return {
    retry: false as const,
    mutationFn: (candidateId: string) =>
      executeRollbackLearningCandidate(orgId, candidateId, client),
    onSuccess: () => invalidateLearningState(queryClient, orgId),
  };
}
