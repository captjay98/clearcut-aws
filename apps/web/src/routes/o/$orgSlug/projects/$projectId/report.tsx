import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/report")({
  component: ReportRoute,
});

export function ReportRoute() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId/report" });
  const [report, setReport] = useState<any | null>(null);
  const [attestation, setAttestation] = useState("");
  const [releasing, setReleasing] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadReport = async () => {
    try {
      const res = await api.getReportStatus({ path: { org_id: orgSlug, project_id: projectId } });
      if (res.ok) {
        setReport(res.value.data);
      }
    } catch {
      // handle error
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReport();
  }, [orgSlug, projectId]);

  const handleCreateSnapshot = async () => {
    setFeedback(null);
    try {
      const res = await api.createReportSnapshot({
        path: { org_id: orgSlug, project_id: projectId },
        body: {},
      });
      if (res.ok) {
        setFeedback("New report snapshot prepared.");
        loadReport();
      } else {
        setFeedback(`Error: ${res.error.message}`);
      }
    } catch {
      setFeedback("Network error creating snapshot");
    }
  };

  const handleRelease = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!report?.snapshotId || !attestation.trim()) return;
    setReleasing(true);
    setFeedback(null);

    try {
      const res = await api.releaseReport({
        path: { org_id: orgSlug, project_id: projectId },
        body: { snapshotId: report.snapshotId, attestation },
      });

      if (res.ok) {
        setFeedback("Report released and committed to audit log with immutable verification hash.");
        loadReport();
      } else {
        setFeedback(`Error: ${res.error.message}`);
      }
    } catch {
      setFeedback("Network error releasing report");
    } finally {
      setReleasing(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Governed Clearance Report</h1>
        <p className="text-sm text-slate-400">
          Prepare reproducible, version-bound pre-clearance dossiers for qualified human review.
        </p>
      </div>

      {feedback && (
        <div
          role="alert"
          className={`p-3 rounded text-xs ${
            feedback.startsWith("Error")
              ? "bg-red-950/50 border border-red-900 text-red-400"
              : "bg-emerald-950/50 border border-emerald-900 text-emerald-400"
          }`}
        >
          {feedback}
        </div>
      )}

      <div className="p-6 bg-slate-900 border border-slate-800 rounded-lg space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider font-bold">Report Status</div>
            <div className="text-lg font-bold text-white mt-0.5">
              {report?.isReleased ? "✅ Released Dossier" : "Draft Pre-Clearance Dossier"}
            </div>
          </div>
          <span
            className={`text-xs px-3 py-1 font-bold rounded uppercase ${
              report?.isReleased
                ? "bg-emerald-950 text-emerald-400 border border-emerald-900"
                : "bg-amber-950 text-amber-400 border border-amber-900"
            }`}
          >
            {report?.status || "draft"}
          </span>
        </div>

        {report?.contentHash && (
          <div className="p-3 bg-slate-950 rounded border border-slate-800 font-mono text-xs">
            <div className="text-[11px] text-slate-500">SHA-256 Binding Manifest Hash:</div>
            <div className="text-amber-400 mt-1 break-all">{report.contentHash}</div>
          </div>
        )}

        {!report?.isReleased ? (
          <div className="space-y-3 pt-2">
            {!report?.snapshotId ? (
              <button
                type="button"
                onClick={handleCreateSnapshot}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold rounded"
              >
                Generate Report Snapshot
              </button>
            ) : (
              <form onSubmit={handleRelease} className="space-y-3">
                <div>
                  <label htmlFor="attestation" className="block text-xs font-medium text-slate-300 mb-1">
                    Human Reviewer Sign-Off Attestation
                  </label>
                  <textarea
                    id="attestation"
                    required
                    rows={2}
                    value={attestation}
                    onChange={(e) => setAttestation(e.target.value)}
                    placeholder="I attest that I have reviewed all sourced evidence claims and approved the pre-clearance findings."
                    className="w-full px-3 py-2 text-xs bg-slate-800 border border-slate-700 rounded text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </div>
                <button
                  type="submit"
                  disabled={releasing}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
                >
                  {releasing ? "Releasing Dossier..." : "Sign & Release Governed Report"}
                </button>
              </form>
            )}
          </div>
        ) : (
          <div className="text-xs text-slate-400 pt-2 border-t border-slate-800">
            Dossier is signed and locked. Viewable and exportable for legal counsel review.
          </div>
        )}
      </div>
    </div>
  );
}

export default ReportRoute;
