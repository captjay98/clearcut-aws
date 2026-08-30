import React, { useState } from "react";
import { Page, Card, Badge } from "@clearcut/design-system";

export function RecordsPage() {
  const [filterType, setFilterType] = useState("all");

  const sampleRecords = [
    {
      id: "rec-1",
      action: "evidence_decision_recorded",
      target: "Item CC-101 (Coca-Cola)",
      actor: "Sarah (Reviewer)",
      time: "10 mins ago",
      status: "Committed",
    },
    {
      id: "rec-2",
      action: "rewrite_proposal_approved",
      target: "Rewrite RW-201",
      actor: "David (Admin)",
      time: "1 hour ago",
      status: "Committed",
    },
  ];

  return (
    <Page
      title="Operations & Audit Records"
      subtitle="Immutable cross-module activity ledger, tool executions, and decision receipts"
      trail={[{ label: "Operations Records" }]}
    >
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            {["all", "decisions", "rewrites", "system"].map((f) => (
              <button
                key={f}
                onClick={() => setFilterType(f)}
                className={`px-3 py-1 text-xs rounded capitalize font-medium ${
                  filterType === f
                    ? "bg-slate-900 dark:bg-white text-white dark:text-slate-900"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <span className="text-xs text-slate-500">Zero raw script text or secrets logged</span>
        </div>

        <Card title="Authoritative Audit Trail">
          <div className="divide-y divide-slate-100 dark:divide-slate-800 font-mono text-xs">
            {sampleRecords.map((r) => (
              <div key={r.id} className="py-3 flex items-center justify-between">
                <div>
                  <span className="font-semibold text-slate-900 dark:text-white">{r.action}</span>
                  <span className="ml-2 text-slate-500 font-sans">{r.target} • {r.actor}</span>
                </div>
                <div className="flex items-center space-x-2 font-sans">
                  <Badge label={r.status} variant="success" />
                  <span className="text-slate-400">{r.time}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Page>
  );
}
