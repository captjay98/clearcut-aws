import React from "react";
import type { ScriptDiffSummary } from "@clearcut/contracts";

export interface SelectiveRescanDialogProps {
  isOpen: boolean;
  summary: ScriptDiffSummary;
  onConfirm: () => void;
  onClose: () => void;
  /** Disables the confirm trigger while a rescan is already in flight. */
  isStarting?: boolean;
}

/**
 * A selective rescan is a governed, provider-spending action, so it must never
 * start on its own. This dialog presents the computed impact (affected items,
 * lineage carry-forward, provider work estimate) sourced entirely from the
 * persisted diff summary, and the confirm button is the sole trigger.
 */
export function SelectiveRescanDialog({
  isOpen,
  summary,
  onConfirm,
  onClose,
  isStarting = false,
}: SelectiveRescanDialogProps) {
  if (!isOpen) return null;

  return (
    <div className="backdrop" data-testid="selective-rescan-dialog">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="selective-rescan-title">
        <header className="dialog-head">
          <div>
            <h2 id="selective-rescan-title">Confirm Selective Re-scan</h2>
            <p>
              Only the clearance items whose script elements changed will be researched again.
              Unaffected items and their cited evidence are carried forward by lineage and are not
              re-run.
            </p>
          </div>
        </header>

        <div className="dialog-body">
          <div className="stack">
            <div className="grid grid-3">
              <div className="stat">
                <span className="stat-label">Affected</span>
                <span className="stat-value">{summary.affectedElementCount}</span>
              </div>
              <div className="stat is-success">
                <span className="stat-label">Carried forward</span>
                <span className="stat-value">{summary.carriedForwardItemCount}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Search calls</span>
                <span className="stat-value">{summary.providerWorkEstimate}</span>
              </div>
            </div>

            <p className="small muted">
              Estimated provider work: {summary.providerWorkEstimate} search call(s). Lineage
              carry-forward preserves {summary.carriedForwardEvidenceCount} evidence claim(s),
              reducing provider cost. Carried evidence remains historical and unresolved — it is
              never labelled as cleared.
            </p>
          </div>
        </div>

        <footer className="dialog-actions">
          <button className="button button-quiet" type="button" onClick={onClose} disabled={isStarting}>
            Cancel
          </button>
          <button
            className="button button-primary"
            type="button"
            onClick={onConfirm}
            disabled={isStarting}
          >
            {isStarting ? "Starting Re-scan…" : "Confirm & Start Re-scan"}
          </button>
        </footer>
      </div>
    </div>
  );
}

export default SelectiveRescanDialog;
