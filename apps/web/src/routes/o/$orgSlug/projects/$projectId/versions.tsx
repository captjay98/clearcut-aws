import React from "react";
import { Page } from "@clearcut/design-system";
import { VersionDiffViewer } from "../../../../../features/versions/VersionDiffViewer.tsx";

export function ProjectVersionsRoute() {
  return (
    <Page
      title="Script Revisions & Lineage"
      subtitle="Track script changes across production revisions and monitor selective re-scan results"
      trail={[{ label: "Overview", href: "." }, { label: "Revisions" }]}
    >
      <VersionDiffViewer />
    </Page>
  );
}
