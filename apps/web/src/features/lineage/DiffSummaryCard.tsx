import React, { useState } from "react";

export interface DiffSummaryCardProps {
  addedCount?: number;
  modifiedCount?: number;
  removedCount?: number;
  onTriggerRescan?: () => void;
}

export function DiffSummaryCard({
  addedCount = 2,
  modifiedCount = 1,
  removedCount = 1,
  onTriggerRescan,
}: DiffSummaryCardProps) {
  const [rescanStatus, setRescanStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleRescan = () => {
    setLoading(true);
    setRescanStatus("Running targeted Parallel re-scan on affected items...");
    setTimeout(() => {
      setLoading(false);
      setRescanStatus("Targeted re-scan completed. All affected item states updated.");
      onTriggerRescan?.();
    }, 400);
  };

  return (
    <div
      data-testid="diff-summary-card"
      className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4 font-sans shadow-sm"
    >
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-white">Revision Diff & Item Impact Summary</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Clearance state recalculation across script revision changes.
          </p>
        </div>

        <button
          type="button"
          onClick={handleRescan}
          disabled={loading}
          className="px-3.5 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded-md shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
        >
          {loading ? "Rescanning..." : "Trigger Rescan"}
        </button>
      </div>

      {rescanStatus && (
        <div role="status" className="p-3 bg-emerald-950/40 border border-emerald-900 text-emerald-400 text-xs rounded">
          {rescanStatus}
        </div>
      )}

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="p-3 bg-emerald-950/20 border border-emerald-900/40 rounded-lg">
          <div className="text-[11px] text-emerald-400 font-bold uppercase">Added Items</div>
          <div className="text-xl font-bold text-emerald-300 mt-1">+{addedCount}</div>
        </div>

        <div className="p-3 bg-amber-950/20 border border-amber-900/40 rounded-lg">
          <div className="text-[11px] text-amber-400 font-bold uppercase">Modified Items</div>
          <div className="text-xl font-bold text-amber-300 mt-1">~{modifiedCount}</div>
        </div>

        <div className="p-3 bg-red-950/20 border border-red-900/40 rounded-lg">
          <div className="text-[11px] text-red-400 font-bold uppercase">Removed / Cleared</div>
          <div className="text-xl font-bold text-red-300 mt-1">-{removedCount}</div>
        </div>
      </div>
    </div>
  );
}

export default DiffSummaryCard;
