import React, { useState } from "react";
import { Page, Card, Badge, Banner } from "@clearcut/design-system";
import { ReleaseDialog } from "./ReleaseDialog.tsx";

export interface ReportStatus {
  snapshot_id: string;
  version_label: string;
  content_hash: string;
  is_released: boolean;
}

export function ReportPage({
  reportStatus,
}: {
  reportStatus?: ReportStatus | null;
}) {
  const [isReleaseOpen, setIsReleaseOpen] = useState(false);
  const [isReleased, setIsReleased] = useState(reportStatus?.is_released ?? false);

  return (
    <Page
      title="Pre-Clearance Report & Dossier Export"
      subtitle="Generate version-bound clearance dossiers, record accountable releases, and export"
      trail={[
        { label: "Overview", href: "." },
        { label: "Clearance Report" },
      ]}
    >
      <div className="space-y-6">
        <Banner
          title="Legal Boundary Compliance Notice"
          variant="info"
          message="ClearCut dossiers provide sourced factual findings and workflow coordination. ClearCut does not provide legal advice or clearance guarantees."
        />

        <Card title="Current Report Snapshot Status">
          <div className="flex items-center justify-between">
            <div className="space-y-1 text-xs">
              <div className="flex items-center space-x-2">
                <span className="font-semibold text-slate-900 dark:text-white">
                  Snapshot {reportStatus?.version_label || "v2-2026-08-30"}
                </span>
                <Badge
                  label={isReleased ? "Released" : "Generated (Draft)"}
                  variant={isReleased ? "success" : "primary"}
                />
              </div>
              <p className="text-slate-500 font-mono text-[11px]">
                Content Hash: {reportStatus?.content_hash || "sha256:8f49a88c..."} • Bound to {reportStatus?.version_label || "v2 (Blue Revision)"}
              </p>
            </div>

            <div className="flex items-center space-x-2">
              {!isReleased ? (
                <button
                  type="button"
                  onClick={() => setIsReleaseOpen(true)}
                  className="px-3 py-1.5 text-xs font-semibold bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  Release Report...
                </button>
              ) : (
                <button
                  type="button"
                  className="px-3 py-1.5 text-xs font-semibold bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded"
                >
                  Download Dossier (PDF)
                </button>
              )}
            </div>
          </div>
        </Card>

        <ReleaseDialog
          isOpen={isReleaseOpen}
          onClose={() => setIsReleaseOpen(false)}
          onConfirm={(attestation) => {
            setIsReleased(true);
            setIsReleaseOpen(false);
          }}
          versionLabel={reportStatus?.version_label || "v2 (Blue Revision)"}
        />
      </div>
    </Page>
  );
}
