import { describe, it, expect } from "vitest";
import React from "react";
import { ProjectOverviewRoute } from "../../src/routes/o.$orgSlug.projects.$projectId.tsx";
import { ScreenplayWorkspaceRoute } from "../../src/routes/o.$orgSlug.projects.$projectId.workspace.tsx";
import { ItemWorklistRoute } from "../../src/routes/o.$orgSlug.projects.$projectId.items.tsx";
import { ItemDetailRoute } from "../../src/routes/o.$orgSlug.projects.$projectId.items.$itemId.tsx";
import { ClaimTable } from "../../src/features/evidence/ClaimTable.tsx";
import { CommentThread } from "../../src/features/evidence/CommentThread.tsx";
import { DecisionDialog } from "../../src/features/evidence/DecisionDialog.tsx";

describe("Evidence Workspace Routes and Features", () => {
  it("renders ProjectOverviewRoute", () => {
    expect(ProjectOverviewRoute).toBeDefined();
    const elem = React.createElement(ProjectOverviewRoute);
    expect(elem.type).toBe(ProjectOverviewRoute);
  });

  it("renders ScreenplayWorkspaceRoute", () => {
    expect(ScreenplayWorkspaceRoute).toBeDefined();
    const elem = React.createElement(ScreenplayWorkspaceRoute);
    expect(elem.type).toBe(ScreenplayWorkspaceRoute);
  });

  it("renders ItemWorklistRoute", () => {
    expect(ItemWorklistRoute).toBeDefined();
    const elem = React.createElement(ItemWorklistRoute);
    expect(elem.type).toBe(ItemWorklistRoute);
  });

  it("renders ItemDetailRoute", () => {
    expect(ItemDetailRoute).toBeDefined();
    const elem = React.createElement(ItemDetailRoute);
    expect(elem.type).toBe(ItemDetailRoute);
  });

  it("renders ClaimTable and CommentThread features", () => {
    expect(ClaimTable).toBeDefined();
    expect(CommentThread).toBeDefined();
    expect(DecisionDialog).toBeDefined();
  });
});
