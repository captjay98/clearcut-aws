import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import {
  api,
  type ClearanceItem,
  type MonitoringPolicy,
  type MonitoringRun,
  type Project,
  type ReportPreview,
  type ReportRelease,
  type ReportSnapshot,
  type ScriptVersion,
  type TrustEvaluation,
} from "@clearcut/contracts";
import { ReportReceiptView } from "../../../../../features/reports/ReportReceiptView";
import { ReportSnapshotBuilder } from "../../../../../features/reports/ReportSnapshotBuilder";
import {
  ReportDocument,
  type ReportSourceRow,
} from "../../../../../features/reports/ReportDocument";
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

  // Exhibit data for the live report document. Each holds only what the
  // clearance service returned; nothing here is fabricated on failure.
  const [versions, setVersions] = useState<ScriptVersion[]>([]);
  const [items, setItems] = useState<ClearanceItem[]>([]);
  const [sources, setSources] = useState<ReportSourceRow[]>([]);
  const [sourcesComplete, setSourcesComplete] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [monitoringRuns, setMonitoringRuns] = useState<MonitoringRun[]>([]);
  const [monitoringPolicy, setMonitoringPolicy] = useState<MonitoringPolicy | null>(null);
  const [trustEvaluations, setTrustEvaluations] = useState<TrustEvaluation[]>([]);
  const [documentLoading, setDocumentLoading] = useState(true);

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

  // Exhibit data loads independently of the snapshot lifecycle so the live
  // document renders even before any snapshot exists. Exhibit C has no
  // project-wide sources endpoint, so it is aggregated from per-item detail
  // (getClearanceItem carries authorityTier + url/publisher/excerpt/stance)
  // and flattened across every item. Failures surface as honest empty/partial
  // states rather than fabricated rows.
  useEffect(() => {
    let active = true;

    const loadDocument = async () => {
      setDocumentLoading(true);
      setSourcesComplete(false);

      const [
        versionsResult,
        itemsResult,
        projectResult,
        runsResult,
        policyResult,
        evaluationsResult,
      ] = await Promise.all([
        api.listProjectVersions({ params: { orgId: orgSlug, projectId } }),
        api.listClearanceItems({ params: { orgId: orgSlug, projectId } }),
        api.getProject({ params: { orgId: orgSlug, projectId } }),
        api.listMonitoringRuns({ params: { orgId: orgSlug, projectId } }),
        api.getMonitoringPolicy({ params: { orgId: orgSlug, projectId } }),
        api.listTrustEvaluations({ params: { orgId: orgSlug, projectId } }),
      ]);
      if (!active) return;

      setVersions(versionsResult.ok ? versionsResult.value : []);
      const loadedItems = itemsResult.ok ? itemsResult.value : [];
      setItems(loadedItems);
      setProject(projectResult.ok ? projectResult.value : null);
      setMonitoringRuns(runsResult.ok ? runsResult.value : []);
      setMonitoringPolicy(policyResult.ok ? policyResult.value : null);
      setTrustEvaluations(evaluationsResult.ok ? evaluationsResult.value : []);

      // Exhibit C: fetch each item's detail and flatten its cited snapshots +
      // claims into source rows. ItemDetailEvidenceClaim carries authorityTier
      // and stance; ItemDetailSourceSnapshot carries url/publisher/excerpt.
      const detailResults = await Promise.all(
        loadedItems.map((item) =>
          api.getClearanceItem({
            params: { orgId: orgSlug, projectId, itemId: item.itemId },
          }),
        ),
      );
      if (!active) return;

      const aggregated: ReportSourceRow[] = [];
      let everyItemResolved = true;
      detailResults.forEach((result, index) => {
        if (!result.ok) {
          everyItemResolved = false;
          return;
        }
        const detail = result.value;
        const snapshotsById = new Map(
          detail.snapshots.map((snapshot) => [snapshot.snapshotId, snapshot]),
        );
        detail.claims.forEach((claim) => {
          const cited = snapshotsById.get(claim.snapshotId);
          aggregated.push({
            key: `${detail.itemId}-${claim.claimId}`,
            itemId: detail.itemId,
            entityName: detail.entityName,
            authorityTier: claim.authorityTier,
            publisher: cited?.publisher ?? "",
            url: cited?.url ?? "",
            retrievedAt: cited?.retrievedAt ?? "",
            excerpt: cited?.excerpt ?? "",
            stance: claim.stance,
          });
        });
      });

      setSources(aggregated);
      setSourcesComplete(everyItemResolved);
      setDocumentLoading(false);
    };

    void loadDocument();
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

      <ReportDocument
        versions={versions}
        items={items}
        sources={sources}
        sourcesComplete={sourcesComplete}
        project={project}
        monitoringRuns={monitoringRuns}
        monitoringPolicy={monitoringPolicy}
        trustEvaluations={trustEvaluations}
        snapshot={snapshot}
        loading={documentLoading}
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
