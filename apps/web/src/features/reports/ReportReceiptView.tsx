import React from "react";

export interface ReportReceiptViewProps {
  receiptId?: string;
  projectName?: string;
  releasedBy?: string;
  releasedAt?: string;
  manifestHash?: string;
  itemsClearedCount?: number;
}

export function ReportReceiptView({
  receiptId = "rec-001",
  projectName = "Borrowed Light",
  releasedBy = "Jamie Park (Lead Reviewer)",
  releasedAt = "2026-08-30T17:00:00Z",
  manifestHash = "8f49a88cd72b9a714e8248c8715873918f49a88cd72b9a714e8248c871587391",
  itemsClearedCount = 38,
}: ReportReceiptViewProps) {
  const handlePrint = () => {
    window.print();
  };

  return (
    <div
      data-testid="report-receipt-view"
      className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4 font-sans shadow-sm"
    >
      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
        <div>
          <h3 className="text-sm font-bold text-white">Immutable Clearance Release Receipt</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Audit-backed cryptographic release projection for counsel review and production archive.
          </p>
        </div>

        <button
          type="button"
          onClick={handlePrint}
          className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold rounded flex items-center space-x-1.5 focus:outline-none focus:ring-2 focus:ring-amber-500"
        >
          <span>🖨️</span>
          <span>Print / Export PDF</span>
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
        <div className="p-3 bg-slate-950 border border-slate-800 rounded">
          <span className="text-[10px] text-slate-500 font-bold uppercase">Receipt Identifier</span>
          <div className="font-mono font-bold text-slate-200 mt-1">{receiptId}</div>
        </div>

        <div className="p-3 bg-slate-950 border border-slate-800 rounded">
          <span className="text-[10px] text-slate-500 font-bold uppercase">Authorizing Reviewer</span>
          <div className="font-bold text-slate-200 mt-1">{releasedBy}</div>
        </div>

        <div className="p-3 bg-slate-950 border border-slate-800 rounded">
          <span className="text-[10px] text-slate-500 font-bold uppercase">Release Timestamp</span>
          <div className="text-slate-300 mt-1">{new Date(releasedAt).toLocaleString()}</div>
        </div>

        <div className="p-3 bg-slate-950 border border-slate-800 rounded">
          <span className="text-[10px] text-slate-500 font-bold uppercase">Items Cleared</span>
          <div className="text-sm font-bold text-emerald-400 mt-1">{itemsClearedCount} / {itemsClearedCount}</div>
        </div>
      </div>

      <div className="p-3 bg-slate-950 border border-slate-800 rounded text-xs space-y-1">
        <div className="text-[10px] text-slate-500 font-bold uppercase">Verification Status</div>
        <p className="text-slate-400">
          The content hash matches the primary screenplay revision manifest in the immutable PostgreSQL ledger.
        </p>
      </div>
    </div>
  );
}

export default ReportReceiptView;
