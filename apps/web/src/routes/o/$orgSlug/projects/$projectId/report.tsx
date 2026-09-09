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
import { Banner, Page } from "../../../../../components/ds";

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
    <Page
      trail={[
        { label: "Projects", to: "/o/$orgSlug/projects", params: { orgSlug } },
        { label: "Clearance report" },
      ]}
      eyebrow="Delivery"
      title="Clearance report"
      lede="Freeze a version-bound evidence record, then release that exact snapshot through a separate accountable action."
      notice={
        <p role="note" className="banner is-warning">
          <span className="banner-icon" aria-hidden="true">
            ⚖
          </span>
          <span className="banner-body">{LEGAL_BOUNDARY}</span>
        </p>
      }
    >
      {feedback && (
        <Banner
          tone={feedbackIsError ? "is-danger" : "is-success"}
          icon={feedbackIsError ? "⚠" : "✓"}
          message={feedback}
          role="alert"
          className="gap-b-6"
        />
      )}

      {preview && (
        <section className="section" aria-label="Report preview counts">
          {/* Each count keeps its label and value in one element: the release
              spec reads them as single exact strings. */}
          <div className="grid grid-4">
            <p className="card card-quiet">Total items: {preview.totalItems}</p>
            <p className="card card-quiet">Resolved workflow items: {preview.clearedItems}</p>
            <p className="card card-quiet">Flagged for review: {preview.flaggedItems}</p>
            <p className="card card-quiet">Unresolved risk: {preview.unresolvedRisk}</p>
          </div>
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
    </Page>
  );
}

export default ReportRoute;
