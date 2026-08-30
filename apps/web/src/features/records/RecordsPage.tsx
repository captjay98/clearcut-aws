import React from "react";
import { Page, Card, Badge, Banner } from "@clearcut/design-system";

export interface AuditRecord {
  event_id: string;
  action: string;
  target_type: string;
  actor_id: string;
  created_at: string;
  redacted_summary: string;
}

export function RecordsPage({
  records = [],
}: {
  records?: AuditRecord[];
}) {
  const defaultRecords: AuditRecord[] = [
    {
      event_id: "aud-001",
      action: "report_snapshot_released",
      target_type: "report_release",
      actor_id: "user-01",
      created_at: "2026-08-30T15:58:30Z",
      redacted_summary: "Released Pre-Clearance Dossier for v2 (Blue Revision)",
    },
    {
      event_id: "aud-002",
      action: "rewrite_proposal_approved",
      target_type: "rewrite_proposal",
      actor_id: "user-02",
      created_at: "2026-08-30T15:20:10Z",
      redacted_summary: "Approved Greeking substitution for item CC-104",
    },
  ];

  const displayRecords =
    records && records.length > 0 ? records : defaultRecords;

  return (
    <Page
      title="Audit & Operations Ledger"
      subtitle="Tenant-scoped immutable record of all state-mutating clearance decisions, rewrites, and releases"
      trail={[{ label: "Records" }]}
    >
      <div className="space-y-6">
        <Banner
          title="Redaction Boundary Guarantee"
          variant="info"
          message="Records contain structured event metadata and receipt projections. Raw screenplay dialogue and third-party secrets are strictly excluded."
        />

        <Card title="Authoritative Audit Events">
          <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
            {displayRecords.map((r) => (
              <div key={r.event_id} className="py-3 flex items-start justify-between">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-slate-900 dark:text-white">
                      {r.action}
                    </span>
                    <Badge label={r.target_type} variant="neutral" />
                  </div>
                  <p className="text-slate-600 dark:text-slate-400">{r.redacted_summary}</p>
                </div>
                <div className="text-right text-[11px] text-slate-400">
                  <span className="font-mono">{r.created_at}</span>
                  <div>Actor: {r.actor_id}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Page>
  );
}
