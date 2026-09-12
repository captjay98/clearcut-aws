import React, { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Job } from "@clearcut/contracts";
import {
  clearanceItemKeys,
  toQueryError,
} from "../../queries/clearanceItems";

const TERMINAL = new Set(["succeeded", "failed", "cancelled", "manual_retry"]);

export interface ResearchProgressProps {
  orgSlug: string;
  projectId: string;
  jobId: string | null;
  entityName?: string;
  onSettled?: (job: Job) => void;
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    queued: "Queued",
    running: "Running",
    planning_queries: "Planning research queries",
    searching_sources: "Searching sources",
    extracting_claims: "Extracting claims",
    evaluating_evidence: "Quality judge reviewing evidence",
    persisting_claims: "Saving cited claims",
    succeeded: "Complete",
    failed: "Failed",
  };
  return labels[stage] ?? stage.replaceAll("_", " ");
}

/**
 * Visible progress for a durable research job (Parallel + judge). Without this
 * the 202 response looks like a no-op for 30–60s.
 */
export function ResearchProgress({
  orgSlug,
  projectId,
  jobId,
  entityName,
  onSettled,
}: ResearchProgressProps) {
  const queryClient = useQueryClient();
  const enabled = Boolean(jobId);

  const jobQuery = useQuery({
    queryKey: ["job", orgSlug, projectId, jobId ?? "none"] as const,
    enabled,
    queryFn: async () => {
      const result = await api.getJob({
        params: { orgId: orgSlug, projectId, jobId: jobId! },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
    refetchInterval: (query) => {
      const job = query.state.data;
      return job && TERMINAL.has(job.status) ? false : 1500;
    },
  });

  const job = jobQuery.data;

  useEffect(() => {
    if (!job || !TERMINAL.has(job.status)) return;
    void queryClient.invalidateQueries({
      queryKey: clearanceItemKeys.detail(orgSlug, projectId, job.target.id),
    });
    void queryClient.invalidateQueries({
      queryKey: clearanceItemKeys.evidence(orgSlug, projectId, job.target.id),
    });
    void queryClient.invalidateQueries({
      queryKey: clearanceItemKeys.list(orgSlug, projectId),
    });
    onSettled?.(job);
  }, [job, orgSlug, projectId, queryClient, onSettled]);

  if (!enabled || !job) return null;

  if (job.status === "succeeded") {
    return (
      <div className="banner is-success" role="status" data-testid="research-progress">
        <span className="banner-icon" aria-hidden="true">
          ✓
        </span>
        <span className="banner-body">
          <strong>Research complete{entityName ? ` for ${entityName}` : ""}</strong>
          <p className="gap-t-1 small">
            {Number(job.resultSummary?.claimCount ?? 0)} cited claim
            {Number(job.resultSummary?.claimCount ?? 0) === 1 ? "" : "s"} ·{" "}
            {Number(job.resultSummary?.snapshotCount ?? 0)} source snapshot
            {Number(job.resultSummary?.snapshotCount ?? 0) === 1 ? "" : "s"} · judge{" "}
            {job.resultSummary?.judgePassed ? "passed" : "needs review"} · score{" "}
            {job.resultSummary?.headlineScore == null
              ? "—"
              : String(job.resultSummary.headlineScore)}
          </p>
        </span>
      </div>
    );
  }

  if (job.status === "failed" || job.status === "cancelled") {
    return (
      <div className="banner is-danger" role="alert" data-testid="research-progress">
        <span className="banner-icon" aria-hidden="true">
          ⚠
        </span>
        <span className="banner-body">
          <strong>
            Research {job.status === "failed" ? "failed" : "cancelled"}
            {entityName ? ` for ${entityName}` : ""}
          </strong>
          <p className="gap-t-1 small">
            {job.error?.message || "The research job did not complete."}
            {job.error?.retryable ? " You can run research again." : ""}
          </p>
        </span>
      </div>
    );
  }

  const progress = Math.round(job.progress ?? 0);
  return (
    <div
      className="banner is-accent"
      role="status"
      aria-live="polite"
      data-testid="research-progress"
      data-research-status={job.status}
    >
      <span className="banner-icon" aria-hidden="true">
        ◐
      </span>
      <span className="banner-body">
        <strong>
          Research running{entityName ? ` for ${entityName}` : ""} — this can take a
          minute
        </strong>
        <p className="gap-t-1 small">
          Persisted stage: <span className="mono">{stageLabel(job.stage)}</span>
          {" · "}
          <span className="mono">{progress}%</span>
          {" · "}
          attempt {job.attemptCount || 1}
        </p>
        <div className="meter gap-t-2" aria-hidden="true">
          <span style={{ width: `${Math.max(progress, 8)}%` }} />
        </div>
      </span>
    </div>
  );
}

export default ResearchProgress;
