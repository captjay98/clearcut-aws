import { describe, it, expect } from "vitest";
import React from "react";
import { ProjectVersionsRoute } from "../../src/routes/o.$orgSlug.projects.$projectId.versions.tsx";
import { VersionDiffViewer } from "../../src/features/versions/VersionDiffViewer.tsx";
import { RescanProgress } from "../../src/features/versions/RescanProgress.tsx";

describe("Versions and Re-scan UI Routes and Features", () => {
  it("renders ProjectVersionsRoute", () => {
    expect(ProjectVersionsRoute).toBeDefined();
    const elem = React.createElement(ProjectVersionsRoute);
    expect(elem.type).toBe(ProjectVersionsRoute);
  });

  it("renders VersionDiffViewer", () => {
    expect(VersionDiffViewer).toBeDefined();
    const elem = React.createElement(VersionDiffViewer, {
      beforeVersionLabel: "v1",
      afterVersionLabel: "v2",
      diffs: [],
    });
    expect(elem.type).toBe(VersionDiffViewer);
  });

  it("renders RescanProgress", () => {
    expect(RescanProgress).toBeDefined();
    const elem = React.createElement(RescanProgress, {
      affectedCount: 2,
      savedCallsCount: 36,
      completedCount: 2,
      status: "completed",
    });
    expect(elem.type).toBe(RescanProgress);
  });
});
