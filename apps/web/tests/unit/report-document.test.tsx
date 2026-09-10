// @vitest-environment jsdom

import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type {
  ClearanceItem,
  MonitoringPolicy,
  MonitoringRun,
  Project,
  ReportSnapshot,
  ScriptVersion,
  TrustEvaluation,
} from "@clearcut/contracts";
import {
  ReportDocument,
  type ReportDocumentProps,
  type ReportSourceRow,
} from "../../src/features/reports/ReportDocument";

afterEach(cleanup);

function baseProps(overrides: Partial<ReportDocumentProps> = {}): ReportDocumentProps {
  return {
    versions: [],
    items: [],
    sources: [],
    sourcesComplete: true,
    project: null,
    monitoringRuns: [],
    monitoringPolicy: null,
    trustEvaluations: [],
    snapshot: null,
    loading: false,
    ...overrides,
  };
}

function switchTo(label: string): void {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(label) }));
}

const version: ScriptVersion = {
  versionId: "ver-1",
  scriptId: "script-1",
  projectId: "project-1",
  versionNumber: 2,
  revisionLabel: "Blue Revision",
  title: "The Heist",
  ordinal: 2,
  sourceArtifactId: null,
  parseRunId: null,
  sourceHash: "abc123def456",
  parserVersion: "1.0.0",
  sceneCount: 42,
  elementCount: 500,
  createdAt: "2026-08-19T10:00:00Z",
};

const item: ClearanceItem = {
  itemId: "item-1",
  projectId: "project-1",
  version: 1,
  category: "brands_and_trademarks",
  entityName: "Coca-Cola",
  status: "needs_review",
  severity: "High",
  confidence: 0.82,
  scene: 12,
  displayStatus: "needs_review",
};

const source: ReportSourceRow = {
  key: "item-1-claim-1",
  itemId: "item-1",
  entityName: "Coca-Cola",
  authorityTier: "tier_1_authoritative",
  publisher: "USPTO",
  url: "https://tsdr.uspto.gov/example",
  retrievedAt: "2026-08-19T11:00:00Z",
  excerpt: "Registered trademark in class 32.",
  stance: "supporting",
};

describe("ReportDocument renders only real data", () => {
  it("renders Exhibit A version rows from the supplied versions", () => {
    render(<ReportDocument {...baseProps({ versions: [version] })} />);
    // Exhibit A is the default active tab.
    expect(screen.getByText("Blue Revision")).toBeTruthy();
    expect(screen.getByText("The Heist")).toBeTruthy();
    expect(screen.getByText("abc123def456")).toBeTruthy();
  });

  it("renders Exhibit B flag rows with entity, category, severity, confidence, scene", () => {
    render(<ReportDocument {...baseProps({ items: [item] })} />);
    switchTo("B · Flags");
    expect(screen.getByText("Coca-Cola")).toBeTruthy();
    expect(screen.getByText("Brands and trademarks")).toBeTruthy();
    expect(screen.getByText("High")).toBeTruthy();
    expect(screen.getByText("82%")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
  });

  it("renders Exhibit C source rows with authority, publisher link, excerpt, and stance", () => {
    render(<ReportDocument {...baseProps({ sources: [source], sourcesComplete: true })} />);
    switchTo("C · Sources");
    expect(screen.getByText("tier_1_authoritative")).toBeTruthy();
    const link = screen.getByRole("link", { name: /USPTO/ });
    expect(link.getAttribute("href")).toBe("https://tsdr.uspto.gov/example");
    expect(screen.getByText(/Registered trademark in class 32/)).toBeTruthy();
    expect(screen.getByText("supporting")).toBeTruthy();
  });

  it("renders Exhibit D project details from the supplied project", () => {
    const project: Project = {
      projectId: "project-1",
      orgId: "org-1",
      title: "The Heist",
      description: "A caper.",
      productionType: "Feature",
      productionStage: "Development",
      jurisdiction: "US",
      targetLockDate: "2026-12-01",
      reviewBrief: "Full pre-clearance.",
      createdAt: "2026-08-01T09:00:00Z",
    };
    render(<ReportDocument {...baseProps({ project })} />);
    switchTo("D · Project");
    expect(screen.getByText("A caper.")).toBeTruthy();
    expect(screen.getByText("Feature")).toBeTruthy();
    expect(screen.getByText("Full pre-clearance.")).toBeTruthy();
  });

  it("renders Exhibit E monitoring runs and trust evaluations", () => {
    const run: MonitoringRun = {
      runId: "run-1",
      projectId: "project-1",
      status: "completed",
      itemsChecked: 10,
      changesDetected: 2,
      createdAt: "2026-08-19T12:00:00Z",
    };
    const policy: MonitoringPolicy = {
      projectId: "project-1",
      cadence: "weekly",
      active: true,
    };
    const evaluation: TrustEvaluation = {
      evaluationId: "eval-1",
      orgId: "org-1",
      projectId: "project-1",
      runId: "run-1",
      stage: "final",
      headlineScore: 88,
      scoredDimensionsCount: 3,
      blockersCount: 0,
      dimensions: [],
      gates: [],
      provenance: {
        rubricVersion: "2.4",
        promptVersion: "cc-17",
        policyVersion: "3.2",
        returnedModel: "gemini-pro",
      },
      createdAt: "2026-08-19T12:30:00Z",
    };
    render(
      <ReportDocument
        {...baseProps({
          monitoringRuns: [run],
          monitoringPolicy: policy,
          trustEvaluations: [evaluation],
        })}
      />,
    );
    switchTo("E · Trust");
    expect(screen.getByText("weekly")).toBeTruthy();
    expect(screen.getByText("gemini-pro")).toBeTruthy();
    expect(screen.getByText("88")).toBeTruthy();
    expect(screen.getByText("2.4")).toBeTruthy();
  });

  it("lists unresolved items in the open-items appendix", () => {
    const settled: ClearanceItem = {
      ...item,
      itemId: "item-2",
      entityName: "Verified Mark",
      disposition: "verified",
    };
    const pending: ClearanceItem = {
      ...item,
      itemId: "item-3",
      entityName: "Pending Mark",
      disposition: "pending",
    };
    render(<ReportDocument {...baseProps({ items: [settled, pending] })} />);
    switchTo("Open items");
    expect(screen.getByText("Pending Mark")).toBeTruthy();
    expect(screen.queryByText("Verified Mark")).toBeNull();
  });

  it("shows the released snapshot's frozen content hash in the binding tab", () => {
    const snapshot: ReportSnapshot = {
      snapshotId: "snap-1",
      projectId: "project-1",
      versionId: "ver-1",
      generatedAt: "2026-08-19T13:00:00Z",
      status: "released",
      contentHash: "deadbeefcafef00d",
      bindingManifest: {
        policyVersion: "3.2",
        promptVersion: "cc-17",
        rubricVersion: "2.4",
        judgeModel: "gemini-pro",
        headlineScore: 88,
      },
      artifactId: "artifact-1",
    };
    render(<ReportDocument {...baseProps({ snapshot })} />);
    switchTo("Binding");
    expect(screen.getByText("deadbeefcafef00d")).toBeTruthy();
    expect(screen.getByText("gemini-pro")).toBeTruthy();
    expect(screen.getByText("3.2")).toBeTruthy();
  });
});

describe("ReportDocument states honest empties, never fabrications", () => {
  it("states no versions rather than inventing one", () => {
    render(<ReportDocument {...baseProps()} />);
    expect(screen.getByText(/No script versions available/)).toBeTruthy();
  });

  it("states zero evidence is unresolved when sources are complete but empty", () => {
    render(<ReportDocument {...baseProps({ sources: [], sourcesComplete: true })} />);
    switchTo("C · Sources");
    expect(screen.getByText(/Zero evidence is unresolved/)).toBeTruthy();
  });

  it("discloses that evidence could not be retrieved when aggregation is incomplete", () => {
    render(<ReportDocument {...baseProps({ sources: [], sourcesComplete: false })} />);
    switchTo("C · Sources");
    expect(screen.getByText(/Evidence could not be retrieved/)).toBeTruthy();
    expect(screen.getByText(/No source has been invented/)).toBeTruthy();
  });

  it("states project details are not available when no project is returned", () => {
    render(<ReportDocument {...baseProps({ project: null })} />);
    switchTo("D · Project");
    expect(screen.getByText(/Project details not available/)).toBeTruthy();
  });

  it("marks a draft binding as computed at generation rather than hashing nothing", () => {
    render(<ReportDocument {...baseProps({ snapshot: null })} />);
    switchTo("Binding");
    expect(screen.getByText(/No frozen snapshot has been generated yet/)).toBeTruthy();
    expect(screen.getByText(/Computed at generation/)).toBeTruthy();
  });

  it("always renders the persistent legal disclaimer", () => {
    render(<ReportDocument {...baseProps()} />);
    expect(
      screen.getByText(/It is not legal advice and does not certify clearance/),
    ).toBeTruthy();
  });
});
