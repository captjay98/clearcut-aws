import { describe, it, expect } from "vitest";
import React from "react";
import { ImportStep } from "../../src/features/ingestion/import-step.tsx";
import { ParseReview } from "../../src/features/ingestion/parse-review.tsx";
import { AnalysisProgress } from "../../src/features/ingestion/analysis-progress.tsx";
import { NewProjectRoute } from "../../src/routes/o.$orgSlug.projects.new.tsx";

describe("Ingestion Components and Routes", () => {
  it("renders ImportStep component", () => {
    expect(ImportStep).toBeDefined();
    const elem = React.createElement(ImportStep, {
      onFileSelected: () => {},
      onPasteSubmitted: () => {},
    });
    expect(elem.type).toBe(ImportStep);
  });

  it("renders ParseReview component", () => {
    expect(ParseReview).toBeDefined();
    const elem = React.createElement(ParseReview, {
      title: "Test Script",
      sceneCount: 5,
      elementCount: 30,
      onConfirm: () => {},
      onCancel: () => {},
    });
    expect(elem.type).toBe(ParseReview);
  });

  it("renders AnalysisProgress component", () => {
    expect(AnalysisProgress).toBeDefined();
    const elem = React.createElement(AnalysisProgress, {
      status: "running",
      progressPercent: 60,
    });
    expect(elem.type).toBe(AnalysisProgress);
  });

  it("renders NewProjectRoute wizard", () => {
    expect(NewProjectRoute).toBeDefined();
    const elem = React.createElement(NewProjectRoute, { orgSlug: "paramount" });
    expect(elem.type).toBe(NewProjectRoute);
  });
});
