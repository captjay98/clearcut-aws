import React, { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api, type ApiError, type Job, type RunStatus } from "@clearcut/contracts";

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

function AttemptHistory({ job }: { job: Job }) {
  if (job.attempts.length === 0) return null;
  return (
    <div className="mt-4 rounded border border-slate-800 bg-slate-950/40 p-3">
      <h4 className="text-xs font-bold text-slate-200">Attempt history</h4>
      <ul className="mt-2 space-y-1 text-xs text-slate-400">
        {job.attempts.map((attempt) => (
          <li key={attempt.number}>Attempt {attempt.number} — {attempt.status}</li>
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
    <div className="mt-4 rounded border border-slate-800 bg-slate-950/40 p-3">
      <h4 className="text-xs font-bold text-slate-200">Governed lifecycle history</h4>
      <ul className="mt-2 space-y-1 text-xs text-slate-400">
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
      <section aria-live="polite" className="rounded-lg border border-slate-800 bg-slate-900 p-5">
        <h3 className="text-base font-bold text-white">Loading check status</h3>
        <p className="mt-2 text-xs text-slate-400">Reading the persisted operation record…</p>
      </section>
    );
  }

  if (jobQuery.isError || !jobQuery.data) {
    return (
      <section role="alert" className="rounded-lg border border-rose-900 bg-rose-950/40 p-5">
        <h3 className="text-base font-bold text-rose-200">Check unavailable</h3>
        <p className="mt-2 text-xs text-rose-300">
          {jobQuery.error?.message ?? "The persisted operation could not be loaded."}
        </p>
        <button
          type="button"
          onClick={() => void jobQuery.refetch()}
          className="mt-4 rounded border border-rose-700 px-3 py-2 text-xs font-bold text-rose-100"
        >
          Try loading again
        </button>
      </section>
    );
  }

  const job = jobQuery.data;
  if (job.jobType !== "detection") {
    return (
      <section role="alert" className="rounded-lg border border-rose-900 bg-rose-950/40 p-5">
        <h3 className="text-base font-bold text-rose-200">Check unavailable</h3>
        <p className="mt-2 text-xs text-rose-300">This operation is not a script detection check.</p>
      </section>
    );
  }
  if (
    job.target.type !== "script_version" ||
    job.target.id !== expectedVersionId
  ) {
    return (
      <section role="alert" className="rounded-lg border border-rose-900 bg-rose-950/40 p-5">
        <h3 className="text-base font-bold text-rose-200">Check unavailable</h3>
        <p className="mt-2 text-xs text-rose-300">
          This check belongs to a different persisted script version.
        </p>
      </section>
    );
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
      <section aria-live="polite" className="space-y-4 rounded-lg border border-emerald-900 bg-emerald-950/20 p-5">
        <div>
          <h3 className="text-base font-bold text-emerald-200">Check succeeded</h3>
          <p className="mt-1 text-xs text-slate-400">
            Persisted stage: <span data-testid="job-stage" data-stage={job.stage}>{stageLabel(job.stage)}</span>
          </p>
        </div>

        {hasTerminalCounts ? (
          <dl data-testid="terminal-result-counts" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded border border-slate-800 bg-slate-950/50 p-3">
              <dt className="text-[11px] text-slate-400">Elements processed</dt>
              <dd data-testid="elements-processed-count" className="text-lg font-bold text-white">
                {elementsProcessed}
              </dd>
            </div>
            <div className="rounded border border-slate-800 bg-slate-950/50 p-3">
              <dt className="text-[11px] text-slate-400">Candidates detected</dt>
              <dd data-testid="candidate-count" className="text-lg font-bold text-white">
                {candidateCount}
              </dd>
            </div>
            <div className="rounded border border-slate-800 bg-slate-950/50 p-3">
              <dt className="text-[11px] text-slate-400">Clearance items</dt>
              <dd data-testid="clearance-item-count" className="text-lg font-bold text-white">
                {clearanceItemCount}
              </dd>
            </div>
          </dl>
        ) : (
          <div role="status" className="rounded border border-amber-800 bg-amber-950/30 p-3 text-xs text-amber-200">
            The check succeeded, but its persisted terminal count summary is unavailable.
          </div>
        )}

        {reviewStatus === "unresolved" ? (
          <div className="rounded border border-amber-800 bg-amber-950/30 p-3 text-xs text-amber-100">
            <strong>Unresolved — human review required</strong>
            <p className="mt-1 text-amber-200">
              Detected unresolved findings are pending evidence research and qualified human review; they are not legal advice or a clearance decision.
            </p>
          </div>
        ) : typeof reviewStatus === "string" ? (
          <p className="text-xs text-slate-400">Persisted review status: {reviewStatus}</p>
        ) : (
          <p className="text-xs text-slate-400">No review disposition was inferred from the completed check.</p>
        )}

        <AttemptHistory job={job} />
        <LifecycleHistory job={job} />

        <div className="flex flex-wrap gap-2">
          <Link
            to="/o/$orgSlug/projects/$projectId/workspace"
            params={{ orgSlug, projectId }}
            className="rounded bg-amber-600 px-3 py-2 text-xs font-bold text-white hover:bg-amber-700"
          >
            Open persisted screenplay
          </Link>
          <Link
            to="/o/$orgSlug/projects/$projectId/items"
            params={{ orgSlug, projectId }}
            className="rounded border border-slate-700 px-3 py-2 text-xs font-bold text-slate-200 hover:border-slate-500"
          >
            Review detected items
          </Link>
          <Link
            to="/o/$orgSlug/records"
            params={{ orgSlug }}
            search={{ view: "operations", projectId }}
            className="rounded border border-slate-700 px-3 py-2 text-xs font-bold text-slate-200 hover:border-slate-500"
          >
            View operation Records
          </Link>
        </div>
      </section>
    );
  }

  if (job.status === "failed" || job.status === "manual_retry" || job.status === "cancelled") {
    const tone = job.status === "cancelled" ? "slate" : "rose";
    const canRetry = job.canRetry;
    return (
      <section
        aria-live="polite"
        className={`rounded-lg border p-5 ${
          tone === "rose"
            ? "border-rose-900 bg-rose-950/40"
            : "border-slate-700 bg-slate-900"
        }`}
      >
        <h3 className="text-base font-bold text-white">{headingForStatus(job.status)}</h3>
        <p className="mt-1 text-xs text-slate-400">
          Persisted stage: <span data-testid="job-stage" data-stage={job.stage}>{stageLabel(job.stage)}</span>
        </p>
        {job.status === "manual_retry" && (
          <p className="mt-3 text-xs text-amber-200">Manual retry required after an interrupted local operation.</p>
        )}
        {job.error && <p className="mt-3 text-xs text-rose-200">{job.error.message}</p>}
        {canRetry && (
          <button
            type="button"
            onClick={() => retryMutation.mutate()}
            disabled={retryMutation.isPending}
            className="mt-4 rounded bg-amber-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
          >
            {retryMutation.isPending ? "Retrying…" : "Retry check"}
          </button>
        )}
        <AttemptHistory job={job} />
        <LifecycleHistory job={job} />
        {mutationError && <p role="alert" className="mt-3 text-xs text-rose-300">{mutationError.message}</p>}
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between gap-4">
        <div role="status" aria-live="polite">
          <h3 className="text-base font-bold text-white">{headingForStatus(job.status)}</h3>
          <p className="mt-1 text-xs text-slate-400">
            Persisted stage: <span data-testid="job-stage" data-stage={job.stage}>{stageLabel(job.stage)}</span>
          </p>
        </div>
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-slate-700 border-t-amber-500" aria-label="Check in progress" />
      </div>
      <div className="mt-4">
        <div className="mb-1 flex justify-between text-[11px] text-slate-400">
          <span>Persisted progress</span>
          <span>{job.progress}%</span>
        </div>
        <div
          role="progressbar"
          aria-label="Persisted check progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={job.progress}
          className="h-2 w-full overflow-hidden rounded bg-slate-800"
          style={{ height: "0.5rem" }}
        >
          <div className="h-full bg-amber-500" style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} />
        </div>
      </div>
      {!isTerminal && CANCELLABLE_STATUSES.has(job.status) && (
        <button
          type="button"
          onClick={() => cancelMutation.mutate()}
          disabled={cancelMutation.isPending}
          className="mt-4 rounded border border-slate-600 px-3 py-2 text-xs font-bold text-slate-200 disabled:opacity-50"
        >
          {cancelMutation.isPending ? "Cancelling…" : "Cancel check"}
        </button>
      )}
      <AttemptHistory job={job} />
      <LifecycleHistory job={job} />
      {mutationError && <p role="alert" className="mt-3 text-xs text-rose-300">{mutationError.message}</p>}
    </section>
  );
}

export default JobProgress;
