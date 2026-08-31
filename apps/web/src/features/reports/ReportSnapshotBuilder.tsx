import React, { useState } from "react";

export interface ReportSnapshotBuilderProps {
  snapshotId?: string;
  versionLabel?: string;
  contentHash?: string;
  isReleased?: boolean;
  onRelease?: (attestation: string) => void;
  onCreateSnapshot?: () => void;
  loading?: boolean;
}

export function ReportSnapshotBuilder({
  snapshotId = "snap-001",
  versionLabel = "v2 (Blue Revision)",
  contentHash = "8f49a88cd72b9a714e8248c8715873918f49a88cd72b9a714e8248c871587391",
  isReleased = false,
  onRelease,
  onCreateSnapshot,
  loading = false,
}: ReportSnapshotBuilderProps) {
  const [attestation, setAttestation] = useState(
    "I attest that all clearance items have been reviewed and approved in accordance with production legal guidelines."
  );
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!attestation.trim()) return;
    setSubmitting(true);
    onRelease?.(attestation);
    setSubmitting(false);
  };

  return (
    <div
      data-testid="report-snapshot-builder"
      className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4 font-sans shadow-sm"
    >
      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
        <div>
          <h3 className="text-sm font-bold text-white">Pre-Clearance Dossier Snapshot Builder</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Cryptographically bound to screenplay revision {versionLabel}.
          </p>
        </div>

        <span
          className={`text-xs px-2.5 py-1 rounded font-bold uppercase ${
            isReleased
              ? "bg-emerald-950 text-emerald-400 border border-emerald-900"
              : "bg-amber-950 text-amber-400 border border-amber-900"
          }`}
        >
          {isReleased ? "Locked & Released" : "Draft Snapshot"}
        </span>
      </div>

      {/* SHA-256 Manifest Hash Box */}
      <div className="p-3 bg-slate-950 border border-slate-800 rounded-md font-mono text-xs space-y-1">
        <div className="text-[10px] text-slate-500 font-sans font-bold uppercase tracking-wider">
          SHA-256 Binding Manifest Hash:
        </div>
        <div data-testid="binding-manifest-hash" className="text-amber-400 font-bold break-all">
          {contentHash}
        </div>
      </div>

      {!isReleased ? (
        <form onSubmit={handleSubmit} className="space-y-3 pt-2">
          <div>
            <label htmlFor="attestation" className="block text-xs font-bold text-slate-300 mb-1">
              Accountable Human Reviewer Attestation (Required for Release)
            </label>
            <textarea
              id="attestation"
              required
              rows={2}
              value={attestation}
              onChange={(e) => setAttestation(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
              placeholder="I attest that I have reviewed all sourced evidence claims..."
            />
          </div>

          <div className="flex items-center justify-end space-x-3">
            <button
              type="button"
              onClick={onCreateSnapshot}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded"
            >
              Recompute Manifest
            </button>
            <button
              type="submit"
              disabled={submitting || !attestation.trim()}
              className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              Sign & Release Governed Report
            </button>
          </div>
        </form>
      ) : (
        <div className="text-xs text-slate-400 p-3 bg-slate-950/60 rounded border border-slate-800 flex items-center space-x-2">
          <span className="text-emerald-400">🔒</span>
          <span>Dossier is signed and immutable. All claims and decisions committed to audit database.</span>
        </div>
      )}
    </div>
  );
}

export default ReportSnapshotBuilder;
