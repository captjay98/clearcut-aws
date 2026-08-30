import React from "react";
import { Page, Card, Badge } from "@clearcut/design-system";
import { VersionDiffViewer } from "../features/versions/VersionDiffViewer.tsx";
import { RescanProgress } from "../features/versions/RescanProgress.tsx";

export function ProjectVersionsRoute() {
  return (
    <Page
      title="Script Revisions & History"
      subtitle="Immutable screenplay version lineage, diffs, and selective re-scan checkpoints"
      trail={[
        { label: "Overview", href: "." },
        { label: "Revisions & History" },
      ]}
    >
      <div className="space-y-6">
        <RescanProgress
          affectedCount={2}
          savedCallsCount={36}
          completedCount={2}
          status="completed"
        />

        <Card title="Version Lineage & Stock History">
          <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
            <div className="py-3 flex items-center justify-between">
              <div>
                <span className="font-semibold text-slate-900 dark:text-white">v2 - Blue Revision</span>
                <span className="ml-2 text-slate-400">Approved Greeking (2 items modified)</span>
              </div>
              <Badge label="Active Clearance Version" variant="success" />
            </div>
            <div className="py-3 flex items-center justify-between text-slate-500">
              <div>
                <span>v1 - White Production Draft</span>
                <span className="ml-2 text-slate-400">Initial Import (38 items detected)</span>
              </div>
              <Badge label="Superseded (Immutable)" variant="neutral" />
            </div>
          </div>
        </Card>

        <Card title="Structural Script Diff (v1 → v2)">
          <VersionDiffViewer
            beforeVersionLabel="v1 (White Draft)"
            afterVersionLabel="v2 (Blue Revision)"
            diffs={[
              {
                elementId: "e1",
                orderIndex: 1,
                beforeText: "JOHN sips a can of Coca-Cola.",
                afterText: "JOHN sips a can of Sparkling Soda.",
                classification: "modified",
              },
              {
                elementId: "e2",
                orderIndex: 2,
                beforeText: "He looks at the sunset over the valley.",
                afterText: "He looks at the sunset over the valley.",
                classification: "unchanged",
              },
            ]}
          />
        </Card>
      </div>
    </Page>
  );
}
