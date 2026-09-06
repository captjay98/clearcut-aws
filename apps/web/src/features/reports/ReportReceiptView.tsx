import React from "react";

export interface ReportReceiptViewProps {
  releaseId: string;
  releasedBy: string;
  releasedAt: string;
  manifestHash: string;
  attestation: string;
  downloadUrl: string;
}

export function ReportReceiptView({
  releaseId,
  releasedBy,
  releasedAt,
  manifestHash,
  attestation,
  downloadUrl,
}: ReportReceiptViewProps) {
  return (
    <section
      data-testid="report-receipt-view"
      className="space-y-4 rounded-lg border border-emerald-900 bg-slate-900 p-5 font-sans shadow-sm"
      aria-labelledby="report-receipt-heading"
    >
      <div className="flex flex-col gap-3 border-b border-slate-800 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2
            id="report-receipt-heading"
            className="text-sm font-bold text-white"
          >
            Report release receipt
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Server-persisted projection of the accountable release transaction.
          </p>
        </div>
        <a
          href={downloadUrl}
          className="w-fit rounded bg-emerald-700 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-400"
        >
          Download released HTML
        </a>
      </div>

      <dl className="grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
        <div className="rounded border border-slate-800 bg-slate-950 p-3">
          <dt className="font-bold uppercase text-slate-500">
            Release identifier
          </dt>
          <dd className="mt-1 break-all font-mono text-slate-200">
            Release ID: <span data-testid="release-id">{releaseId}</span>
          </dd>
        </div>
        <div className="rounded border border-slate-800 bg-slate-950 p-3">
          <dt className="font-bold uppercase text-slate-500">
            Accountable reviewer
          </dt>
          <dd className="mt-1 break-all font-mono text-slate-200">
            {releasedBy}
          </dd>
        </div>
        <div className="rounded border border-slate-800 bg-slate-950 p-3">
          <dt className="font-bold uppercase text-slate-500">Released at</dt>
          <dd className="mt-1 text-slate-200">
            {new Date(releasedAt).toLocaleString()}
          </dd>
        </div>
        <div className="rounded border border-slate-800 bg-slate-950 p-3">
          <dt className="font-bold uppercase text-slate-500">Frozen binding</dt>
          <dd className="mt-1 break-all font-mono text-slate-200">
            Binding manifest SHA-256: {manifestHash}
          </dd>
        </div>
      </dl>

      <div className="space-y-1 rounded border border-slate-800 bg-slate-950 p-3 text-xs">
        <div className="font-bold uppercase text-slate-500">
          Release attestation
        </div>
        <p className="text-slate-300">{attestation}</p>
      </div>
      <p className="text-xs text-slate-400">
        ClearCut provides sourced findings for qualified human review. It does
        not provide legal advice or final legal clearance.
      </p>
    </section>
  );
}

export default ReportReceiptView;
