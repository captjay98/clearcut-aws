import React from "react";
import { Page, Card, StatGrid, Progress } from "@clearcut/design-system";

export function ProjectOverviewRoute() {
  return (
    <Page
      title="Project Clearance Overview"
      subtitle="Screenplay clearance tracking, metrics, and script versions"
      trail={[
        { label: "Clearance Projects", href: "../projects" },
        { label: "The Last Station" },
      ]}
      actions={
        <a
          href="workspace"
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
        >
          Open Script Workspace
        </a>
      }
    >
      <StatGrid
        stats={[
          { label: "Total Items", value: 38 },
          { label: "Needs Review", value: 14, description: "Awaiting human review" },
          { label: "Cleared", value: 20, description: "Approved as is / modified" },
          { label: "Blockers", value: 4, description: "Unresolved legal risk" },
        ]}
      />

      <Card title="Overall Clearance Progress">
        <Progress value={20} max={38} label="Items Cleared" />
      </Card>
    </Page>
  );
}
