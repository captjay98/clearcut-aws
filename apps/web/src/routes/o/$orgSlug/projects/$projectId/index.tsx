import React, { useState, useEffect } from "react";
import { Page, Card, StatGrid, Badge } from "@clearcut/design-system";
import { loadProjectOverview } from "../../../../../lib/loaders.ts";

export function ProjectOverviewRoute({
  params,
}: {
  params?: { orgSlug: string; projectId: string };
}) {
  const [overview, setOverview] = useState<any>(null);

  useEffect(() => {
    loadProjectOverview(
      params?.orgSlug || "acme-films",
      params?.projectId || "proj-01"
    ).then(setOverview);
  }, [params?.orgSlug, params?.projectId]);

  return (
    <Page
      title="The Last Reel"
      subtitle="Screenplay Pre-Clearance Project Overview"
      trail={[{ label: "Projects", href: ".." }, { label: "The Last Reel" }]}
    >
      <div className="space-y-6">
        <StatGrid
          stats={[
            { label: "Items Evaluated", value: "38" },
            { label: "High Risk Flags", value: "2" },
            { label: "Verified Claims", value: "38" },
            { label: "Progress", value: "100%" },
          ]}
        />
        <Card title="Clearance Summary">
          <p className="text-xs text-slate-600 dark:text-slate-400">
            38 clearance items detected across 10 protected categories. 2 high-risk trademark flags resolved via Greeking rewrites.
          </p>
        </Card>
      </div>
    </Page>
  );
}
