import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import {
  api,
  type ReportPreview,
  type ReportRelease,
  type ReportSnapshot,
} from "@clearcut/contracts";
import { ReportReceiptView } from "../../../../../features/reports/ReportReceiptView";
import { ReportSnapshotBuilder } from "../../../../../features/reports/ReportSnapshotBuilder";

const LEGAL_BOUNDARY =
  "ClearCut provides sourced findings for qualified human review. It does not provide legal advice or final legal clearance.";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/report")({
  component: ReportRoute,
});

export function ReportRoute() {
  const { orgSlug, projectId } = useParams({
    from: "/o/$orgSlug/projects/$projectId/report",
  });
  const [preview, setPreview] = useState<ReportPreview | null>(null);
  const [snapshot, setSnapshot] = useState<ReportSnapshot | null>(null);
  const [release, setRelease] = useState<ReportRelease | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [feedbackIsError, setFeedbackIsError] = useState(false);
  const [loading, setLoading] = useState(true);

  const showError = (message: string) => {
    setFeedbackIsError(true);
    setFeedback(message);
  };

  const showSuccess = (message: string) => {
    setFeedbackIsError(false);
    setFeedback(message);
  };

  useEffect(() => {
    let active = true;

    const loadReport = async () => {
      setLoading(true);
      const previewResult = await api.previewReport({
        params: { orgId: orgSlug, projectId },
      });
      if (!active) return;
      if (!previewResult.ok) {
        setPreview(null);
        showError(previewResult.error.message);
        setLoading(false);
        return;
      }
      setPreview(previewResult.value);

      const historyResult = await api.listReportHistory({
        params: { orgId: orgSlug, projectId },
      });
      if (!active) return;
      if (!historyResult.ok) {
        showError(historyResult.error.message);
        setLoading(false);
        return;
      }

      const latest = historyResult.value[0];
      if (!latest) {
        setSnapshot(null);
        setRelease(null);
        setLoading(false);
        return;
      }

      const snapshotResult = await api.getReportSnapshot({
        params: {
          orgId: orgSlug,
          projectId,
          snapshotId: latest.snapshotId,
        },
      });
      if (!active) return;
      if (!snapshotResult.ok) {
        showError(snapshotResult.error.message);
        setLoading(false);
        return;
      }
      setSnapshot(snapshotResult.value);

      if (
        latest.releaseId &&
        latest.releasedBy &&
        latest.releasedAt &&
        latest.attestation
      ) {
        const metadataResult = await api.getReportDownloadMetadata({
          params: {
            orgId: orgSlug,
            projectId,
            releaseId: latest.releaseId,
          },
        });
        if (!active) return;
        if (!metadataResult.ok) {
          showError(metadataResult.error.message);
          setLoading(false);
          return;
        }
        setRelease({
          releaseId: latest.releaseId,
          snapshotId: latest.snapshotId,
          releasedBy: latest.releasedBy,
          releasedAt: latest.releasedAt,
          attestation: latest.attestation,
          contentHash: latest.contentHash,
          artifactId: metadataResult.value.artifactId,
          downloadUrl: metadataResult.value.downloadUrl,
        });
      } else {
        setRelease(null);
      }
      setLoading(false);
    };

    void loadReport();
    return () => {
      active = false;
    };
  }, [orgSlug, projectId]);

  const handleCreateSnapshot = async () => {
    setFeedback(null);
    setLoading(true);
    const result = await api.generateReportSnapshot({
      params: { orgId: orgSlug, projectId },
      body: {},
    });
    setLoading(false);
    if (!result.ok) {
      showError(result.error.message);
      return;
    }

    setSnapshot(result.value);
    setRelease(null);
    showSuccess(
      "A frozen, version-bound report snapshot was created for accountable review.",
    );
  };

  const handleRelease = async (attestation: string) => {
    setFeedback(null);
    if (!snapshot) {
      const message =
        "Create a frozen report snapshot before requesting release.";
      showError(message);
      throw new Error(message);
    }

    setLoading(true);
    const result = await api.releaseReport({
      params: { orgId: orgSlug, projectId, snapshotId: snapshot.snapshotId },
      body: { attestation },
    });
    setLoading(false);
    if (!result.ok) {
      showError(result.error.message);
      throw new Error(result.error.message);
    }

    setRelease(result.value);
    setSnapshot({ ...snapshot, status: "released" });
    showSuccess(
      "The frozen clearance report was released without regeneration.",
    );
  };

  return (
    <main className="max-w-5xl space-y-6 font-sans">
      <header>
        <h1 className="text-2xl font-bold text-white">Clearance report</h1>
        <p className="mt-1 text-sm text-slate-400">
          Freeze a version-bound evidence record, then release that exact
          snapshot through a separate accountable action.
        </p>
      </header>

      <p className="rounded border border-amber-900/70 bg-amber-950/30 p-3 text-xs text-amber-200">
        {LEGAL_BOUNDARY}
      </p>

      {feedback && (
        <div
          role="alert"
          className={`rounded border p-3 text-xs ${
            feedbackIsError
              ? "border-rose-900 bg-rose-950/50 text-rose-300"
              : "border-emerald-900 bg-emerald-950/50 text-emerald-400"
          }`}
        >
          {feedback}
        </div>
      )}

      {preview && (
        <section
          aria-label="Report preview counts"
          className="grid grid-cols-2 gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm text-slate-300 sm:grid-cols-4"
        >
          <div>Total items: {preview.totalItems}</div>
          <div>Resolved workflow items: {preview.clearedItems}</div>
          <div>Flagged for review: {preview.flaggedItems}</div>
          <div>Unresolved risk: {preview.unresolvedRisk}</div>
        </section>
      )}

      <ReportSnapshotBuilder
        snapshotId={snapshot?.snapshotId}
        versionLabel={snapshot?.versionId}
        contentHash={snapshot?.contentHash}
        isReleased={release !== null}
        onRelease={handleRelease}
        onCreateSnapshot={handleCreateSnapshot}
        loading={loading}
      />

      {release && (
        <ReportReceiptView
          releaseId={release.releaseId}
          releasedBy={release.releasedBy}
          releasedAt={release.releasedAt}
          manifestHash={release.contentHash}
          attestation={release.attestation}
          downloadUrl={release.downloadUrl}
        />
      )}
    </main>
  );
}

export default ReportRoute;
