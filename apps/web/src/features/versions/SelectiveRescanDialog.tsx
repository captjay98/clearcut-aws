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
    <div
      className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4"
      data-testid="selective-rescan-dialog"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="selective-rescan-title"
        className="w-full max-w-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-2xl overflow-hidden"
      >
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800">
          <h2
            id="selective-rescan-title"
            className="text-base font-bold text-slate-900 dark:text-white"
          >
            Confirm Selective Re-scan
          </h2>
        </div>

        <div className="p-5 space-y-4 text-xs text-slate-600 dark:text-slate-300">
          <p>
            Only the clearance items whose script elements changed will be
            researched again. Unaffected items and their cited evidence are
            carried forward by lineage and are not re-run.
          </p>

          <dl className="grid grid-cols-3 gap-2 text-center">
            <div className="p-3 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
              <dt className="text-[10px] uppercase tracking-wide text-slate-400">Affected</dt>
              <dd className="text-base font-bold text-amber-600 dark:text-amber-400">
                {summary.affectedElementCount}
              </dd>
            </div>
            <div className="p-3 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
              <dt className="text-[10px] uppercase tracking-wide text-slate-400">Carried forward</dt>
              <dd className="text-base font-bold text-emerald-600 dark:text-emerald-400">
                {summary.carriedForwardItemCount}
              </dd>
            </div>
            <div className="p-3 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
              <dt className="text-[10px] uppercase tracking-wide text-slate-400">Search calls</dt>
              <dd className="text-base font-bold text-slate-900 dark:text-white">
                {summary.providerWorkEstimate}
              </dd>
            </div>
          </dl>

          <p className="text-[11px] text-slate-500">
            Estimated provider work: {summary.providerWorkEstimate} search call(s).
            Lineage carry-forward preserves {summary.carriedForwardEvidenceCount}{" "}
            evidence claim(s), reducing provider cost. Carried evidence remains
            historical and unresolved — it is never labelled as cleared.
          </p>
        </div>

        <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-800 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isStarting}
            className="px-4 py-2 text-slate-500 hover:text-slate-900 dark:hover:text-white disabled:opacity-50 font-medium text-xs"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isStarting}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded shadow"
          >
            {isStarting ? "Starting Re-scan…" : "Confirm & Start Re-scan"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SelectiveRescanDialog;
