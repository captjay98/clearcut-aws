import React from "react";
import { Progress, Badge } from "@clearcut/design-system";
import type { Job, RunStatus, ScriptDiffSummary } from "@clearcut/contracts";

export interface RescanProgressProps {
  job: Job;
  summary: ScriptDiffSummary;
}

type BadgeVariant = "neutral" | "primary" | "success" | "warning" | "danger";

// Human-readable, status-accurate labelling for every RunStatus the durable
// job engine can report. The persisted job is the single source of truth, so
// a reload reconstructs this view without any local timer or storage.
const STATUS_META: Record<RunStatus, { label: string; variant: BadgeVariant; terminal: boolean }> = {
  queued: { label: "Queued", variant: "neutral", terminal: false },
  claimed: { label: "Claimed", variant: "primary", terminal: false },
  running: { label: "Running", variant: "primary", terminal: false },
  retry_wait: { label: "Waiting to retry", variant: "warning", terminal: false },
  manual_retry: { label: "Awaiting manual retry", variant: "warning", terminal: false },
  succeeded: { label: "Completed", variant: "success", terminal: true },
  failed: { label: "Failed", variant: "danger", terminal: true },
  cancelled: { label: "Cancelled", variant: "neutral", terminal: true },
};

function resultCount(summary: Record<string, unknown> | null, key: string): number | null {
  if (!summary) return null;
  const value = summary[key];
  return typeof value === "number" ? value : null;
}

export function RescanProgress({ job, summary }: RescanProgressProps) {
  const meta = STATUS_META[job.status] ?? {
    label: job.status,
    variant: "neutral" as BadgeVariant,
    terminal: false,
  };

  const rescanned = resultCount(job.resultSummary, "rescanned");
  const carried = resultCount(job.resultSummary, "carried");

  return (
    <div
      data-testid="rescan-progress"
      role="status"
      aria-live="polite"
      className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg space-y-3"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
            Selective Re-scan Execution
          </h4>
          <p className="text-xs text-slate-500">
            Rescanning {summary.affectedElementCount} affected clearance items •{" "}
            {summary.carriedForwardItemCount} items carried forward by lineage (
            {summary.carriedForwardEvidenceCount} evidence claims preserved)
          </p>
          <p className="text-[11px] text-slate-400 mt-1">
            Stage: <span className="font-mono">{job.stage || "—"}</span>
          </p>
        </div>
        <Badge label={meta.label} variant={meta.variant} />
      </div>

      <Progress
        value={job.progress}
        max={100}
        label="Rescan progress (persisted)"
      />

      {meta.terminal && job.status === "succeeded" && (
        <div
          data-testid="rescan-result-success"
          className="p-3 rounded bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 text-xs text-emerald-700 dark:text-emerald-300"
        >
          <strong>Completed.</strong>{" "}
          {rescanned !== null
            ? `${rescanned} affected item(s) rescanned`
            : `${summary.affectedElementCount} affected item(s) rescanned`}
          {", "}
          {carried !== null
            ? `${carried} carried forward.`
            : `${summary.carriedForwardItemCount} carried forward.`}
        </div>
      )}

      {job.status === "cancelled" && (
        <div
          data-testid="rescan-result-cancelled"
          className="p-3 rounded bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-300"
        >
          This rescan was cancelled by an accountable human. Carried-forward evidence
          is historical and remains unresolved — it is never treated as cleared.
        </div>
      )}

      {job.status === "failed" && job.error && (
        <div
          data-testid="rescan-result-error"
          className="p-3 rounded bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800/60 text-xs text-rose-700 dark:text-rose-300 space-y-1"
        >
          <div>
            <strong>Rescan failed.</strong> {job.error.message}
          </div>
          <div className="font-mono text-[11px] opacity-80">
            code: {job.error.code}
          </div>
          <div>
            {job.canRetry
              ? "This failure can be retried by an accountable human."
              : "This failure is not retryable."}
          </div>
        </div>
      )}
    </div>
  );
}

export default RescanProgress;
