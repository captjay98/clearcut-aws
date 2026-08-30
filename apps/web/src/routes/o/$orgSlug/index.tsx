import React, { useState, useEffect } from "react";
import { Page, Card, Badge } from "@clearcut/design-system";
import { loadOrgProjects } from "../../../lib/loaders.ts";

export function OrgProjectsRoute({ params }: { params?: { orgSlug: string } }) {
  const [projects, setProjects] = useState<any[]>([]);

  useEffect(() => {
    loadOrgProjects(params?.orgSlug || "acme-films").then(setProjects);
  }, [params?.orgSlug]);

  return (
    <Page
      title="Projects"
      subtitle="Clearance projects and active screenplay evidence workspaces"
      trail={[{ label: "Projects" }]}
    >
      <div className="space-y-4">
        {projects.map((proj) => (
          <Card key={proj.id || proj.projectId} title={proj.name || proj.title}>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-600 dark:text-slate-400">
                {proj.description || "Active pre-clearance workspace"}
              </span>
              <Badge label="In Review" variant="primary" />
            </div>
          </Card>
        ))}
      </div>
    </Page>
  );
}
