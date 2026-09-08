import type { QueryClient } from "@tanstack/react-query";
import { api, type Job } from "@clearcut/contracts";
import { scriptVersionKeys } from "../queries/scriptVersions";

export interface StartSelectiveRescanScope {
  orgSlug: string;
  projectId: string;
  versionId: string;
  queryClient: QueryClient;
}

/** A fresh, accountable idempotency key for a single human-triggered command. */
function freshIdempotencyKey(): string {
  const cryptoObj = globalThis.crypto;
  if (cryptoObj && typeof cryptoObj.randomUUID === "function") {
    return cryptoObj.randomUUID();
  }
  // Deterministic fallback for environments without WebCrypto; still unique.
  return `rescan-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function unwrap(result: { ok: true; value: Job } | { ok: false; error: { message: string } }): Job {
  if (!result.ok) {
    throw Object.assign(new Error(result.error.message), result.error);
  }
  return result.value;
}

/**
 * Selective rescan is a governed write, so:
 *  - each invocation carries a freshly minted Idempotency-Key (accountable, one
 *    key per human trigger — never reused across attempts);
 *  - it never auto-retries (retry: false), matching the governed-write invariant;
 *  - on success the returned Job is seeded into the exact job query cache so the
 *    progress view resolves immediately without waiting for the first poll, and
 *    the version list, predecessor diff and job entries are invalidated.
 */
export function startSelectiveRescanMutationOptions({
  orgSlug,
  projectId,
  versionId,
  queryClient,
}: StartSelectiveRescanScope) {
  return {
    mutationKey: [
      ...scriptVersionKeys.all(orgSlug, projectId),
      "selective-rescan",
      versionId,
    ] as const,
    retry: false as const,
    mutationFn: async (): Promise<Job> =>
      unwrap(
        await api.startSelectiveRescan({
          params: { orgId: orgSlug, projectId, versionId },
          headers: { "Idempotency-Key": freshIdempotencyKey() },
        }),
      ),
    onSuccess: (job: Job) => {
      queryClient.setQueryData(
        scriptVersionKeys.job(orgSlug, projectId, job.jobId),
        job,
      );
      void queryClient.invalidateQueries({
        queryKey: scriptVersionKeys.list(orgSlug, projectId),
      });
      void queryClient.invalidateQueries({
        queryKey: scriptVersionKeys.diff(orgSlug, projectId, versionId),
      });
      void queryClient.invalidateQueries({
        queryKey: scriptVersionKeys.job(orgSlug, projectId, job.jobId),
      });
    },
  };
}
