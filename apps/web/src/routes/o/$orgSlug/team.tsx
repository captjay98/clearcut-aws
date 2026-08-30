import React from "react";
import { Page, Card, Badge } from "@clearcut/design-system";

export function OrgTeamRoute() {
  const members = [
    { name: "Alice Owner", email: "alice@acmefilms.com", role: "Owner" },
    { name: "Bob Reviewer", email: "bob@acmefilms.com", role: "Reviewer" },
    { name: "Charlie Editor", email: "charlie@acmefilms.com", role: "Editor" },
  ];

  return (
    <Page
      title="Team & Permissions"
      subtitle="Manage workspace members and fixed role access controls"
      trail={[{ label: "Team" }]}
    >
      <Card title="Organization Members">
        <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
          {members.map((m) => (
            <div key={m.email} className="py-3 flex items-center justify-between">
              <div>
                <span className="font-semibold text-slate-900 dark:text-white">{m.name}</span>
                <span className="ml-2 text-slate-400">{m.email}</span>
              </div>
              <Badge label={m.role} variant="primary" />
            </div>
          ))}
        </div>
      </Card>
    </Page>
  );
}
