import { queryOptions } from "@tanstack/react-query";
import {
  api,
  type LearningCandidate,
  type TrustEvaluation,
} from "@clearcut/contracts";

type EvaluationListClient = Pick<typeof api, "listTrustEvaluations">;
type EvaluationDetailClient = Pick<typeof api, "getTrustEvaluation">;
type LearningCandidateClient = Pick<typeof api, "listLearningCandidates">;

export interface TrustProjectScope {
  orgId: string;
  projectId: string;
  /** Narrows the list to one research/detection run when supplied. */
  jobId?: string;
}

export const trustKeys = {
  evaluations: (orgId: string, projectId: string, jobId?: string) =>
    ["trust-evaluations", orgId, projectId, jobId ?? "all"] as const,
  evaluation: (orgId: string, projectId: string, evaluationId: string) =>
    ["trust-evaluations", orgId, projectId, "detail", evaluationId] as const,
  learningCandidates: (orgId: string) => ["learning-candidates", orgId] as const,
};

/**
 * Trust evaluations are project-scoped: the endpoint carries both the org and the
 * project predicate. An empty array with 200 is the honest "no run has been
 * graded yet" answer and is returned as an empty list, never as an error and
 * never padded with a placeholder evaluation.
 */
export function trustEvaluationsQueryOptions(
  scope: TrustProjectScope,
  client: EvaluationListClient = api,
) {
  return queryOptions({
    queryKey: trustKeys.evaluations(scope.orgId, scope.projectId, scope.jobId),
    queryFn: async (): Promise<TrustEvaluation[]> => {
      const result = await client.listTrustEvaluations({
        params: { orgId: scope.orgId, projectId: scope.projectId },
        ...(scope.jobId ? { query: { jobId: scope.jobId } } : {}),
      });
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return result.value ?? [];
    },
  });
}

export function trustEvaluationQueryOptions(
  scope: TrustProjectScope & { evaluationId: string },
  client: EvaluationDetailClient = api,
) {
  return queryOptions({
    queryKey: trustKeys.evaluation(scope.orgId, scope.projectId, scope.evaluationId),
    queryFn: async (): Promise<TrustEvaluation> => {
      const result = await client.getTrustEvaluation({
        params: {
          orgId: scope.orgId,
          projectId: scope.projectId,
          evaluationId: scope.evaluationId,
        },
      });
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return result.value;
    },
  });
}

/** Learning candidates are organization-scoped, unlike the evaluations above. */
export function learningCandidatesQueryOptions(
  orgId: string,
  client: LearningCandidateClient = api,
) {
  return queryOptions({
    queryKey: trustKeys.learningCandidates(orgId),
    queryFn: async (): Promise<LearningCandidate[]> => {
      const result = await client.listLearningCandidates({ params: { orgId } });
      if (!result.ok) throw Object.assign(new Error(result.error.message), result.error);
      return result.value ?? [];
    },
  });
}

/**
 * The evaluation a reader means by "the latest one".
 *
 * Ordering is by persistence time descending, which is the only ordering the
 * payload supports. Returns null for an empty list rather than a synthesised
 * evaluation.
 */
export function latestEvaluation(
  evaluations: readonly TrustEvaluation[],
): TrustEvaluation | null {
  if (evaluations.length === 0) return null;
  return [...evaluations].sort(
    (left, right) =>
      new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime(),
  )[0];
}
