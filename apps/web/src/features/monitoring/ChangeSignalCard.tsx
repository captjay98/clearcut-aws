import React from "react";
import { Badge, Card } from "../../components/ds";

export interface ChangeSignal {
  id: string;
  sourceTitle: string;
  detectedAt: string;
  signalType: string;
  summary: string;
  previousSnippet: string;
  currentSnippet: string;
  status: "unreviewed" | "reviewed" | "dismissed";
}

export interface ChangeSignalCardProps {
  signals?: ChangeSignal[];
  /** Records a human review of a signal. Absent until the write is available. */
  onReview?: (signalId: string) => void;
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
export function ChangeSignalCard({ signals = [], onReview }: ChangeSignalCardProps) {
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
            <Card key={signal.id} testId="change-signal-card">
              <div className="cluster-between">
                <div className="min-w-0">
                  <div className="cluster">
                    <strong className="small">{signal.sourceTitle}</strong>
                    <Badge tone="is-warning">{signal.signalType}</Badge>
                  </div>
                  <p className="small muted gap-t-1">{signal.summary}</p>
                </div>
                <Badge tone={signal.status === "reviewed" ? "is-success" : "is-danger"}>
                  {signal.status}
                </Badge>
              </div>

              <div className="diff gap-t-4">
                <section>
                  <span className="field-label">Snapshot at capture</span>
                  <p className="diff-text">
                    <del>{signal.previousSnippet}</del>
                  </p>
                </section>
                <section>
                  <span className="field-label">Current state</span>
                  <p className="diff-text">
                    <ins>{signal.currentSnippet}</ins>
                  </p>
                </section>
              </div>

              <div className="cluster-between gap-t-4">
                <span className="mono small muted">
                  Detected {new Date(signal.detectedAt).toLocaleString()}
                </span>
                {signal.status === "unreviewed" && onReview && (
                  <button
                    className="button button-primary button-sm"
                    type="button"
                    onClick={() => onReview(signal.id)}
                  >
                    Mark Reviewed
                  </button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}

export default ChangeSignalCard;
