import React from "react";
import { Page, Card, Badge } from "@clearcut/design-system";

export function InviteRoute() {
  return (
    <Page
      title="Accept Invitation"
      subtitle="Join Acme Films on ClearCut pre-clearance workspace"
    >
      <Card title="Invitation Details">
        <p className="text-xs text-slate-600 dark:text-slate-400">
          You have been invited to join <strong>Acme Films</strong> as a <strong>Reviewer</strong>.
        </p>
      </Card>
    </Page>
  );
}
