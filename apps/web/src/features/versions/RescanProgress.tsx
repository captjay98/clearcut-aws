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
    <article className="card" data-testid="rescan-progress" role="status" aria-live="polite">
      <div className="card-head">
        <div>
          <h3>Selective re-scan execution</h3>
          <p className="small">
            Rescanning {summary.affectedElementCount} affected clearance items ·{" "}
            {summary.carriedForwardItemCount} items carried forward by lineage (
            {summary.carriedForwardEvidenceCount} evidence claims preserved)
          </p>
          <p className="small muted gap-t-1">
            Stage: <span className="mono">{job.stage || "—"}</span>
          </p>
        </div>
        <Badge label={meta.label} variant={meta.variant} />
      </div>

      <Progress value={job.progress} max={100} label="Rescan progress (persisted)" />

      {meta.terminal && job.status === "succeeded" && (
        <div className="banner is-success gap-t-4" data-testid="rescan-result-success">
          <span className="banner-icon" aria-hidden="true">
            ✓
          </span>
          <div className="banner-body">
            <p>
              <strong>Completed.</strong>{" "}
              {rescanned !== null
                ? `${rescanned} affected item(s) rescanned`
                : `${summary.affectedElementCount} affected item(s) rescanned`}
              {", "}
              {carried !== null
                ? `${carried} carried forward.`
                : `${summary.carriedForwardItemCount} carried forward.`}
            </p>
          </div>
        </div>
      )}

      {job.status === "cancelled" && (
        <div className="banner gap-t-4" data-testid="rescan-result-cancelled">
          <span className="banner-icon" aria-hidden="true">
            ○
          </span>
          <div className="banner-body">
            <p>
              This rescan was cancelled by an accountable human. Carried-forward evidence is
              historical and remains unresolved — it is never treated as cleared.
            </p>
          </div>
        </div>
      )}

      {job.status === "failed" && job.error && (
        <div className="banner is-danger gap-t-4" data-testid="rescan-result-error">
          <span className="banner-icon" aria-hidden="true">
            ⚠
          </span>
          <div className="banner-body">
            <strong>Rescan failed.</strong>
            <p>{job.error.message}</p>
            <p className="mono small gap-t-1">code: {job.error.code}</p>
            <p className="small gap-t-1">
              {job.canRetry
                ? "This failure can be retried by an accountable human."
                : "This failure is not retryable."}
            </p>
          </div>
        </div>
      )}
    </article>
  );
}

export default RescanProgress;
