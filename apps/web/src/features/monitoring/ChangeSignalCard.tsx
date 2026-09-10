import React, { useState } from "react";
import type { MonitoringChange } from "@clearcut/contracts";
import { Badge, Card } from "../../components/ds";

/** The governed decision recorded against a monitoring change delta. */
export type MonitoringReviewDecision = "accepted" | "rejected" | "escalated";

export interface ChangeSignalCardProps {
  signals?: MonitoringChange[];
  /**
   * Records a human review of a change signal. The reviewId is the delta's
   * review handle expected by reviewMonitoringChange. Absent until the write is
   * wired; when absent the action controls are withheld rather than shown inert.
   */
  onReview?: (
    reviewId: string,
    decision: MonitoringReviewDecision,
    rationale?: string,
  ) => Promise<void> | void;
  /** True while a review is in flight, so controls disable rather than double-fire. */
  reviewing?: boolean;
}

function signalTone(signalType: MonitoringChange["signalType"]) {
  if (signalType === "material") return "is-danger" as const;
  if (signalType === "unavailable") return "is-warning" as const;
  return "" as const;
}

/**
 * A single reviewable change with its own rationale draft.
 *
 * The keep / reopen / refer labels are the domain vocabulary the mock uses; the
 * recorded decision enum is accepted / rejected / escalated. A change signal
 * never re-decides an item — it is surfaced for a human call.
 */
function ChangeSignalRow({
  signal,
  onReview,
  reviewing = false,
}: {
  signal: MonitoringChange;
  onReview?: ChangeSignalCardProps["onReview"];
  reviewing?: boolean;
}) {
  const [rationale, setRationale] = useState("");

  const submit = (decision: MonitoringReviewDecision) => {
    if (!onReview || reviewing) return;
    const note = rationale.trim();
    void onReview(signal.reviewId, decision, note ? note : undefined);
  };

  return (
    <Card testId="change-signal-card">
      <div className="cluster-between">
        <div className="min-w-0">
          <div className="cluster">
            <strong className="small">{signal.changeKind}</strong>
            <Badge tone={signalTone(signal.signalType)}>{signal.signalType}</Badge>
          </div>
          <p className="small muted gap-t-1">{signal.changeSummary}</p>
        </div>
      </div>

      {(signal.priorExcerpt || signal.currentExcerpt) && (
        <div className="diff gap-t-4">
          <section>
            <span className="field-label">Snapshot at capture</span>
            <p className="diff-text">
              <del>{signal.priorExcerpt ?? "—"}</del>
            </p>
          </section>
          <section>
            <span className="field-label">Current state</span>
            <p className="diff-text">
              <ins>{signal.currentExcerpt ?? "—"}</ins>
            </p>
          </section>
        </div>
      )}

      <div className="cluster-between gap-t-4">
        <span className="mono small muted">
          Detected {new Date(signal.detectedAt).toLocaleString()}
        </span>
      </div>

      {onReview && (
        <>
          <label className="field gap-t-4" htmlFor={`monitoring-rationale-${signal.reviewId}`}>
            <span className="field-label">Rationale (optional)</span>
            <textarea
              id={`monitoring-rationale-${signal.reviewId}`}
              rows={2}
              value={rationale}
              disabled={reviewing}
              onChange={(event) => setRationale(event.target.value)}
              placeholder="Why this change is kept, reopened, or referred…"
            />
          </label>

          <div className="cluster gap-t-4" style={{ justifyContent: "flex-end" }}>
            <button
              className="button button-quiet button-sm"
              type="button"
              disabled={reviewing}
              onClick={() => submit("escalated")}
            >
              Refer
            </button>
            <button
              className="button button-secondary button-sm"
              type="button"
              disabled={reviewing}
              onClick={() => submit("rejected")}
            >
              Reopen
            </button>
            <button
              className="button button-primary button-sm"
              type="button"
              disabled={reviewing}
              onClick={() => submit("accepted")}
            >
              Keep
            </button>
          </div>
        </>
      )}
    </Card>
  );
}

/**
 * Attributable changes detected in a cited source since it was captured.
 *
 * This component previously invented a signal when given none: a specific
 * pending USPTO application, "VEGA LENS", with serial number 98765432, labelled
 * as triggered by Parallel Monitor. That is a fabricated factual claim about a
 * real registry, presented as monitoring output while no monitoring had run, and
 * its "Mark Reviewed" button changed only local state. Both are removed.
 *
 * A change signal never re-decides an item. It is surfaced for a human call.
 */
export function ChangeSignalCard({ signals = [], onReview, reviewing = false }: ChangeSignalCardProps) {
  return (
    <section className="section">
      <div className="section-head">
        <div>
          <h2>Source change signals ({signals.length})</h2>
          <p>
            A detected change is shown for a human call. It never re-decides an item and never
            marks evidence cleared.
          </p>
        </div>
      </div>

      {signals.length === 0 ? (
        // Keeps the surface addressable while reporting absence rather than
        // manufacturing an alert.
        <Card className="card-quiet" testId="change-signal-card">
          <div className="empty-state">
            <span className="empty-icon" aria-hidden="true">
              ○
            </span>
            <h3>No source changes recorded</h3>
            <p>
              No attributable change has been detected for this project's cited sources. Signals
              appear here only after a monitoring run persists one.
            </p>
          </div>
        </Card>
      ) : (
        <div className="stack">
          {signals.map((signal) => (
            <ChangeSignalRow
              key={signal.reviewId}
              signal={signal}
              onReview={onReview}
              reviewing={reviewing}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default ChangeSignalCard;
