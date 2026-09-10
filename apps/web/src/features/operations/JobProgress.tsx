import React, { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api, type ApiError, type Job, type RunStatus } from "@clearcut/contracts";
import { Badge } from "../../components/ds";

const TERMINAL_STATUSES = new Set<RunStatus>([
  "succeeded",
  "failed",
  "manual_retry",
  "cancelled",
]);
const CANCELLABLE_STATUSES = new Set<RunStatus>([
  "queued",
  "claimed",
  "running",
  "retry_wait",
  "manual_retry",
]);

interface JobProgressProps {
  orgSlug: string;
  projectId: string;
  jobId: string;
  expectedVersionId: string;
  onJobChange?: (job: Job) => void;
}

function toQueryError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

function isExpectedDetectionJob(job: Job, expectedVersionId: string): boolean {
  return (
    job.jobType === "detection" &&
    job.target.type === "script_version" &&
    job.target.id === expectedVersionId
  );
}

function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    queued: "Queued",
    running: "Running",
    reading_persisted_elements: "Reading persisted elements",
    detecting_candidates: "Detecting candidates",
    evaluating_findings: "Evaluating findings",
    persisting_unresolved_findings: "Persisting unresolved findings",
    finalizing_detected_findings: "Finalizing detected findings",
    succeeded: "Complete",
    failed: "Failed",
    interrupted: "Interrupted",
    cancelled: "Cancelled",
  };
  return labels[stage] ?? stage.replaceAll("_", " ");
}

/** Persisted stage readout, shared by every state of this view. */
function StageLine({ stage }: { stage: string }) {
  return (
    <p className="small muted gap-t-1">
      Persisted stage:{" "}
      <span className="mono" data-testid="job-stage" data-stage={stage}>
        {stageLabel(stage)}
      </span>
    </p>
  );
}

function AttemptHistory({ job }: { job: Job }) {
  if (job.attempts.length === 0) return null;
  return (
    <div className="source-card gap-t-4">
      <h4>Attempt history</h4>
      <ul className="small muted gap-t-2">
        {job.attempts.map((attempt) => (
          <li key={attempt.number}>
            Attempt {attempt.number} — {attempt.status}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LifecycleHistory({ job }: { job: Job }) {
  if (job.history.length === 0) return null;
  const labels = {
    cancelled: "Cancellation requested",
    retry_requested: "Retry requested",
  } as const;
  return (
    <div className="source-card gap-t-4">
      <h4>Governed lifecycle history</h4>
      <ul className="small muted gap-t-2">
        {job.history.map((event, index) => (
          <li key={`${event.occurredAt}-${index}`}>{labels[event.action]}</li>
        ))}
      </ul>
    </div>
  );
}

function persistedNumber(summary: Record<string, unknown>, key: string): number | null {
  const value = summary[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function headingForStatus(status: RunStatus): string {
  if (status === "queued") return "Check queued";
  if (status === "claimed" || status === "running") return "Checking script";
  if (status === "retry_wait") return "Check waiting to retry";
  if (status === "failed") return "Check failed";
  if (status === "manual_retry") return "Check interrupted";
  if (status === "cancelled") return "Check cancelled";
  return "Check succeeded";
}

/** A refusal to show a check that is not the one asked for. */
function Unavailable({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <section className="card card-accent" role="alert">
      <h3>Check unavailable</h3>
      <p className="small gap-t-2">{message}</p>
      {onRetry && (
        <div className="cluster gap-t-4">
          <button className="button button-secondary button-sm" type="button" onClick={onRetry}>
            Try loading again
          </button>
        </div>
      )}
    </section>
  );
}

export function JobProgress({
  orgSlug,
  projectId,
  jobId,
  expectedVersionId,
  onJobChange,
}: JobProgressProps) {
  const queryClient = useQueryClient();
  const queryKey = ["job", orgSlug, projectId, jobId] as const;
  const jobQuery = useQuery({
    queryKey,
    queryFn: async () => {
      const result = await api.getJob({
        params: { orgId: orgSlug, projectId, jobId },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
    refetchInterval: (query) => {
      const job = query.state.data;
      if (job && !isExpectedDetectionJob(job, expectedVersionId)) return false;
      return job && TERMINAL_STATUSES.has(job.status) ? false : 750;
    },
  });

  useEffect(() => {
    if (jobQuery.data) onJobChange?.(jobQuery.data);
  }, [jobQuery.data, onJobChange]);

  const cancelMutation = useMutation({
    mutationFn: async () => {
      const result = await api.cancelJob({
        params: { orgId: orgSlug, projectId, jobId },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
    onSuccess: (job) => {
      queryClient.setQueryData(queryKey, job);
    },
  });

  const retryMutation = useMutation({
    mutationFn: async () => {
      const result = await api.retryJob({
        params: { orgId: orgSlug, projectId, jobId },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
    onSuccess: (job) => {
      queryClient.setQueryData(queryKey, job);
    },
  });

  if (jobQuery.isPending) {
    return (
      <section className="card" aria-live="polite">
        <h3>Loading check status</h3>
        <p className="small muted gap-t-2">Reading the persisted operation record…</p>
      </section>
    );
  }

  if (jobQuery.isError || !jobQuery.data) {
    return (
      <Unavailable
        message={jobQuery.error?.message ?? "The persisted operation could not be loaded."}
        onRetry={() => void jobQuery.refetch()}
      />
    );
  }

  const job = jobQuery.data;
  if (job.jobType !== "detection") {
    return <Unavailable message="This operation is not a script detection check." />;
  }
  if (job.target.type !== "script_version" || job.target.id !== expectedVersionId) {
    return <Unavailable message="This check belongs to a different persisted script version." />;
  }

  const isTerminal = TERMINAL_STATUSES.has(job.status);
  const mutationError = cancelMutation.error ?? retryMutation.error;

  if (job.status === "succeeded") {
    const summary = job.resultSummary;
    const elementsProcessed = summary ? persistedNumber(summary, "elementsProcessed") : null;
    const candidateCount = summary ? persistedNumber(summary, "candidateCount") : null;
    const clearanceItemCount = summary ? persistedNumber(summary, "clearanceItemCount") : null;
    const hasTerminalCounts =
      elementsProcessed !== null && candidateCount !== null && clearanceItemCount !== null;
    const reviewStatus = summary?.reviewStatus;

    return (
      <section className="card card-accent" aria-live="polite">
        <div className="cluster-between">
          <div>
            <h3>Check succeeded</h3>
            <StageLine stage={job.stage} />
          </div>
          <Badge tone="is-success">Complete</Badge>
        </div>

        {hasTerminalCounts ? (
          <div className="grid grid-3 gap-t-4" data-testid="terminal-result-counts">
            <div className="stat">
              <span className="stat-label">Elements processed</span>
              <span className="stat-value" data-testid="elements-processed-count">
                {elementsProcessed}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Candidates detected</span>
              <span className="stat-value" data-testid="candidate-count">
                {candidateCount}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Clearance items</span>
              <span className="stat-value" data-testid="clearance-item-count">
                {clearanceItemCount}
              </span>
            </div>
          </div>
        ) : (
          <div className="banner is-warning gap-t-4" role="status">
            <span className="banner-icon" aria-hidden="true">
              ⚠
            </span>
            <div className="banner-body">
              <p>The check succeeded, but its persisted terminal count summary is unavailable.</p>
            </div>
          </div>
        )}

        {reviewStatus === "unresolved" ? (
          <div className="banner is-warning gap-t-4">
            <span className="banner-icon" aria-hidden="true">
              ⚠
            </span>
            <div className="banner-body">
              <strong>Unresolved — human review required</strong>
              <p>
                Detected unresolved findings are pending evidence research and qualified human
                review; they are not legal advice or a clearance decision.
              </p>
            </div>
          </div>
        ) : typeof reviewStatus === "string" ? (
          <p className="small muted gap-t-4">Persisted review status: {reviewStatus}</p>
        ) : (
          <p className="small muted gap-t-4">
            No review disposition was inferred from the completed check.
          </p>
        )}

        <AttemptHistory job={job} />
        <LifecycleHistory job={job} />

        <div className="cluster gap-t-4">
          <Link
            className="button button-primary"
            to="/o/$orgSlug/projects/$projectId/workspace"
            params={{ orgSlug, projectId }}
          >
            Open persisted screenplay
          </Link>
          <Link
            className="button button-secondary"
            to="/o/$orgSlug/projects/$projectId/items"
            params={{ orgSlug, projectId }}
            search={{ sort: "severity", dir: "desc", group: "none" }}
          >
            Review detected items
          </Link>
          <Link
            className="button button-secondary"
            to="/o/$orgSlug/records"
            params={{ orgSlug }}
            search={{ view: "operations", projectId }}
          >
            View operation Records
          </Link>
        </div>
      </section>
    );
  }

  if (job.status === "failed" || job.status === "manual_retry" || job.status === "cancelled") {
    return (
      <section className="card card-accent" aria-live="polite">
        <div className="cluster-between">
          <div>
            <h3>{headingForStatus(job.status)}</h3>
            <StageLine stage={job.stage} />
          </div>
          <Badge tone={job.status === "cancelled" ? "" : "is-danger"}>
            {job.status === "cancelled" ? "Cancelled" : "Needs attention"}
          </Badge>
        </div>

        {job.status === "manual_retry" && (
          <p className="small gap-t-3">
            Manual retry required after an interrupted local operation.
          </p>
        )}
        {job.error && <p className="small gap-t-3">{job.error.message}</p>}

        {job.canRetry && (
          <div className="cluster gap-t-4">
            <button
              className="button button-primary"
              type="button"
              onClick={() => retryMutation.mutate()}
              disabled={retryMutation.isPending}
            >
              {retryMutation.isPending ? "Retrying…" : "Retry check"}
            </button>
          </div>
        )}

        <AttemptHistory job={job} />
        <LifecycleHistory job={job} />
        {mutationError && (
          <p className="small gap-t-3" role="alert">
            {mutationError.message}
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="card">
      <div className="cluster-between">
        <div role="status" aria-live="polite">
          <h3>{headingForStatus(job.status)}</h3>
          <StageLine stage={job.stage} />
        </div>
        <span className="spinner" aria-label="Check in progress" />
      </div>

      <div className="gap-t-4">
        <div className="cluster-between gap-b-3">
          <span className="small muted">Persisted progress</span>
          <span className="mono">{job.progress}%</span>
        </div>
        <div className="progress">
          <span
            role="progressbar"
            aria-label="Persisted check progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={job.progress}
            style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }}
          />
        </div>
      </div>

      {!isTerminal && CANCELLABLE_STATUSES.has(job.status) && (
        <div className="cluster gap-t-4">
          <button
            className="button button-secondary"
            type="button"
            onClick={() => cancelMutation.mutate()}
            disabled={cancelMutation.isPending}
          >
            {cancelMutation.isPending ? "Cancelling…" : "Cancel check"}
          </button>
        </div>
      )}

      <AttemptHistory job={job} />
      <LifecycleHistory job={job} />
      {mutationError && (
        <p className="small gap-t-3" role="alert">
          {mutationError.message}
        </p>
      )}
    </section>
  );
}

export default JobProgress;
