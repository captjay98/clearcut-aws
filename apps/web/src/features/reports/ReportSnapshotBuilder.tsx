import React, { useState } from "react";
import { Badge, Card } from "../../components/ds";

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
      className="section"
      data-testid="report-snapshot-builder"
      aria-labelledby="report-snapshot-heading"
    >
      <div className="section-head">
        <div>
          <h2 id="report-snapshot-heading">Frozen report snapshot</h2>
          <p>
            {snapshotId
              ? `Version ${versionLabel ?? "unknown"} is frozen independently from later live changes.`
              : "Create an immutable, version-bound snapshot before accountable release."}
          </p>
        </div>
        <div className="cluster">
          <Badge tone={isReleased ? "is-success" : snapshotId ? "is-warning" : ""}>
            {isReleased ? "Frozen and released" : snapshotId ? "Frozen draft" : "No snapshot"}
          </Badge>
        </div>
      </div>

      <Card>
        <span className="field-label">Binding manifest SHA-256</span>
        <p className="mono gap-t-2" data-testid="binding-manifest-hash">
          {contentHash ?? "Unavailable until snapshot generation completes."}
        </p>

        {isReleased && (
          <p className="small muted gap-t-4">
            The release references this frozen snapshot. It does not regenerate or change the
            artifact.
          </p>
        )}

        <div className="cluster gap-t-5" style={{ justifyContent: "flex-end" }}>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => void onCreateSnapshot?.()}
            disabled={loading}
          >
            Create report snapshot
          </button>
          {!isReleased && (
            <button
              className="button button-primary"
              type="button"
              onClick={() => setReleaseDialogOpen(true)}
              disabled={loading || !snapshotId}
            >
              Review release
            </button>
          )}
        </div>
      </Card>

      {releaseDialogOpen && (
        <div className="backdrop">
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="release-report-title"
          >
            <header className="dialog-head">
              <div>
                <h2 id="release-report-title">Release this frozen snapshot?</h2>
                <p>
                  Releasing records an accountable human attestation without regenerating or
                  changing this snapshot.
                </p>
              </div>
            </header>

            <form onSubmit={handleRelease}>
              <div className="dialog-body">
                <div className="field">
                  <label className="field-label" htmlFor="report-release-attestation">
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
                  />
                </div>
              </div>

              <footer className="dialog-actions">
                <button
                  className="button button-quiet"
                  type="button"
                  onClick={() => setReleaseDialogOpen(false)}
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  className="button button-primary"
                  type="submit"
                  disabled={submitting || !attestation.trim()}
                >
                  Release report
                </button>
              </footer>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}

export default ReportSnapshotBuilder;
