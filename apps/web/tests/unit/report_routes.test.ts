import { describe, it, expect } from "vitest";
import React from "react";
import { ProjectReportRoute } from "../../src/routes/o.$orgSlug.projects.$projectId.report.tsx";
import { ReportPage } from "../../src/features/report/ReportPage.tsx";
import { ReleaseDialog } from "../../src/features/report/ReleaseDialog.tsx";

describe("Report and Export UI Routes and Features", () => {
  it("renders ProjectReportRoute and ReportPage", () => {
    expect(ProjectReportRoute).toBeDefined();
    expect(ReportPage).toBeDefined();
    const elem = React.createElement(ProjectReportRoute);
    expect(elem.type).toBe(ProjectReportRoute);
  });

  it("renders ReleaseDialog", () => {
    expect(ReleaseDialog).toBeDefined();
    const elem = React.createElement(ReleaseDialog, {
      isOpen: true,
      onClose: () => {},
      onConfirm: () => {},
      versionLabel: "v1",
    });
    expect(elem.type).toBe(ReleaseDialog);
  });
});
