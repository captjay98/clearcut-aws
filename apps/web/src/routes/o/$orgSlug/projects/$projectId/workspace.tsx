import React, { useState, useEffect } from "react";
import { Page, Card, Badge } from "@clearcut/design-system";
import { ClaimTable } from "../../../../../features/evidence/ClaimTable.tsx";
import { loadProjectItems } from "../../../../../lib/loaders.ts";

export function ScreenplayWorkspaceRoute({
  params,
}: {
  params?: { orgSlug: string; projectId: string };
}) {
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    loadProjectItems(
      params?.orgSlug || "acme-films",
      params?.projectId || "proj-01"
    ).then(setItems);
  }, [params?.orgSlug, params?.projectId]);

  return (
    <Page
      title="Screenplay Clearance Workspace"
      subtitle="Side-by-side script inspection with cited Parallel evidence claims"
      trail={[{ label: "Overview", href: "." }, { label: "Workspace" }]}
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Annotated Screenplay">
          <div className="font-mono text-xs p-4 bg-slate-100 dark:bg-slate-900 rounded space-y-2">
            <p>EXT. SUNSET BLVD - DAY</p>
            <p>A classic 1968 FORD MUSTANG cruises down the avenue.</p>
            <p>SARAH (30s) sits sipping a CAN OF COCA-COLA.</p>
          </div>
        </Card>
        <Card title="Cited Evidence Claims">
          <ClaimTable />
        </Card>
      </div>
    </Page>
  );
}
