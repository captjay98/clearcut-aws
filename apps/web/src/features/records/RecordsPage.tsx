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
  const displayRecords = records ?? [];

  return (
    <Page
      title="Audit & Operations Ledger"
      subtitle="Tenant-scoped immutable record of all state-mutating clearance decisions, rewrites, and releases"
      trail={[{ label: "Records" }]}
    >
      <div className="space-y-6">
        <Banner
          title="Redaction Boundary Guarantee"
          type="info"
        >
          Records contain structured event metadata and receipt projections. Raw screenplay dialogue and third-party secrets are strictly excluded.
        </Banner>

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
