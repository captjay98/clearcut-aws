import React from "react";
import { Page } from "@clearcut/design-system";
import { ImportStep } from "../../../../features/ingestion/import-step.tsx";

export function NewProjectRoute() {
  return (
    <Page
      title="New Clearance Project"
      subtitle="Import a screenplay in FDX, Fountain, or paste format to begin pre-clearance"
      trail={[{ label: "Projects", href: ".." }, { label: "New" }]}
    >
      <ImportStep />
    </Page>
  );
}
