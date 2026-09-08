import { queryOptions } from "@tanstack/react-query";
import {
  api,
  type Job,
  type RunStatus,
  type ScriptVersion,
  type ScriptVersionDiff,
} from "@clearcut/contracts";

/**
 * Tenant + project scoped query keys for the versions workflow.
 *
 * Every read in this feature is scoped by the authenticated organization slug
 * and project id, so a cached entry from one project can never leak into
 * another. The keys are plain string arrays so they serialize deterministically
 * for cache lookups and invalidation.
 */
export const scriptVersionKeys = {
  all: (orgSlug: string, projectId: string): readonly string[] => [
    "org",
    orgSlug,
    "project",
    projectId,
    "script-versions",
  ],
  list: (orgSlug: string, projectId: string): readonly string[] => [
    ...scriptVersionKeys.all(orgSlug, projectId),
    "list",
  ],
  diff: (orgSlug: string, projectId: string, versionId: string): readonly string[] => [
    ...scriptVersionKeys.all(orgSlug, projectId),
    "diff",
    versionId,
  ],
  job: (orgSlug: string, projectId: string, jobId: string): readonly string[] => [
    "org",
    orgSlug,
    "project",
    projectId,
    "job",
    jobId,
  ],
};

const TERMINAL_RUN_STATUSES: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "succeeded",
  "failed",
  "cancelled",
]);

/** A run is terminal once it can no longer transition on its own. */
export function isTerminalRunStatus(status: RunStatus): boolean {
  return TERMINAL_RUN_STATUSES.has(status);
}

/** Poll cadence for a job that is still making progress. */
export const JOB_POLL_INTERVAL_MS = 2_000;

export interface VersionScope {
  orgSlug: string;
  projectId: string;
}

export interface VersionDiffScope extends VersionScope {
  versionId: string;
}

export interface JobScope extends VersionScope {
  jobId: string;
}

function unwrap<T>(result: { ok: true; value: T } | { ok: false; error: { message: string } }): T {
  if (!result.ok) {
    // Surface a typed failure to TanStack Query so its own retry policy can
    // classify it. The generated client already returns typed ApiError objects.
    throw Object.assign(new Error(result.error.message), result.error);
  }
  return result.value;
}

export function listProjectVersionsQueryOptions({ orgSlug, projectId }: VersionScope) {
  return queryOptions<ScriptVersion[]>({
    queryKey: scriptVersionKeys.list(orgSlug, projectId),
    queryFn: async () =>
      unwrap(
        await api.listProjectVersions({ params: { orgId: orgSlug, projectId } }),
      ),
  });
}

export function scriptVersionDiffQueryOptions({
  orgSlug,
  projectId,
  versionId,
}: VersionDiffScope) {
  return queryOptions<ScriptVersionDiff>({
    queryKey: scriptVersionKeys.diff(orgSlug, projectId, versionId),
    queryFn: async () =>
      unwrap(
        await api.getScriptVersionDiff({
          params: { orgId: orgSlug, projectId, versionId },
        }),
      ),
  });
}

/**
 * Job status/progress query. Reload-safe: the persisted job is the sole source
 * of truth, so a fresh page load reconstructs progress purely from getJob.
 * Polling runs only while the run is nonterminal and stops the moment it
 * reaches succeeded/failed/cancelled.
 */
export function jobQueryOptions({ orgSlug, projectId, jobId }: JobScope) {
  return queryOptions<Job>({
    queryKey: scriptVersionKeys.job(orgSlug, projectId, jobId),
    queryFn: async () =>
      unwrap(await api.getJob({ params: { orgId: orgSlug, projectId, jobId } })),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && isTerminalRunStatus(status)) return false;
      return JOB_POLL_INTERVAL_MS;
    },
  });
}
