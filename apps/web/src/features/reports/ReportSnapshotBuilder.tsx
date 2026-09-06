import React, { useState } from "react";

const DEFAULT_ATTESTATION =
  "I attest this frozen snapshot is accurate for qualified human review and is not legal advice or final legal clearance.";

export interface ReportSnapshotBuilderProps {
  snapshotId?: string;
  versionLabel?: string;
  contentHash?: string;
  isReleased?: boolean;
  onRelease?: (attestation: string) => Promise<void> | void;
  onCreateSnapshot?: () => Promise<void> | void;
  loading?: boolean;
}

export function ReportSnapshotBuilder({
  snapshotId,
  versionLabel,
  contentHash,
  isReleased = false,
  onRelease,
  onCreateSnapshot,
  loading = false,
}: ReportSnapshotBuilderProps) {
  const [attestation, setAttestation] = useState(DEFAULT_ATTESTATION);
  const [releaseDialogOpen, setReleaseDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleRelease = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!snapshotId || !attestation.trim()) return;

    setSubmitting(true);
    try {
      await onRelease?.(attestation);
      setReleaseDialogOpen(false);
    } catch {
      // The route renders the canonical API error while this dialog remains open.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section
      data-testid="report-snapshot-builder"
      className="space-y-4 rounded-lg border border-slate-800 bg-slate-900 p-5 font-sans shadow-sm"
      aria-labelledby="report-snapshot-heading"
    >
      <div className="flex flex-col gap-3 border-b border-slate-800 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2
            id="report-snapshot-heading"
            className="text-sm font-bold text-white"
          >
            Frozen report snapshot
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            {snapshotId
              ? `Version ${versionLabel ?? "unknown"} is frozen independently from later live changes.`
              : "Create an immutable, version-bound snapshot before accountable release."}
          </p>
        </div>
        <span
          className={`w-fit rounded border px-2.5 py-1 text-xs font-bold uppercase ${
            isReleased
              ? "border-emerald-900 bg-emerald-950 text-emerald-400"
              : "border-amber-900 bg-amber-950 text-amber-400"
          }`}
        >
          {isReleased
            ? "Frozen and released"
            : snapshotId
              ? "Frozen draft"
              : "No snapshot"}
        </span>
      </div>

      <div className="space-y-1 rounded-md border border-slate-800 bg-slate-950 p-3 font-mono text-xs">
        <div className="font-sans text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Binding manifest SHA-256
        </div>
        <div
          data-testid="binding-manifest-hash"
          className="break-all font-bold text-amber-400"
        >
          {contentHash ?? "Unavailable until snapshot generation completes."}
        </div>
      </div>

      <div className="flex flex-wrap justify-end gap-3">
        <button
          type="button"
          onClick={() => void onCreateSnapshot?.()}
          disabled={loading}
          className="rounded bg-slate-800 px-3 py-2 text-xs font-bold text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          Create report snapshot
        </button>
        {!isReleased && (
          <button
            type="button"
            onClick={() => setReleaseDialogOpen(true)}
            disabled={loading || !snapshotId}
            className="rounded bg-amber-600 px-4 py-2 text-xs font-bold text-white shadow hover:bg-amber-700 disabled:opacity-50"
          >
            Review release
          </button>
        )}
      </div>

      {isReleased && (
        <p className="rounded border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-400">
          The release references this frozen snapshot. It does not regenerate or
          change the artifact.
        </p>
      )}

      {releaseDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="release-report-title"
            className="w-full max-w-xl space-y-4 rounded-lg border border-slate-700 bg-slate-900 p-5 shadow-2xl"
          >
            <div>
              <h2
                id="release-report-title"
                className="text-lg font-bold text-white"
              >
                Release this frozen snapshot?
              </h2>
              <p className="mt-2 text-sm text-slate-300">
                Releasing records an accountable human attestation without
                regenerating or changing this snapshot.
              </p>
            </div>
            <form onSubmit={handleRelease} className="space-y-4">
              <div>
                <label
                  htmlFor="report-release-attestation"
                  className="mb-1 block text-xs font-bold text-slate-300"
                >
                  Accountable human attestation
                </label>
                <textarea
                  id="report-release-attestation"
                  autoFocus
                  required
                  minLength={40}
                  maxLength={2000}
                  rows={4}
                  value={attestation}
                  onChange={(event) => setAttestation(event.target.value)}
                  className="w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setReleaseDialogOpen(false)}
                  disabled={submitting}
                  className="rounded bg-slate-800 px-3 py-2 text-xs font-bold text-slate-200 hover:bg-slate-700 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !attestation.trim()}
                  className="rounded bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700 disabled:opacity-50"
                >
                  Release report
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

export default ReportSnapshotBuilder;
