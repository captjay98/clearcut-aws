// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { JudgeDimensionScore, TrustEvaluation } from "@clearcut/contracts";
import { RubricTable } from "../../src/features/trust/RubricTable";
import { TrustScoreCard } from "../../src/features/trust/TrustScoreCard";
import { cadenceLabel } from "../../src/features/governance/cadence";
import { learningStageActions } from "../../src/features/trust/rubricPresentation";

afterEach(cleanup);

function dimension(
  overrides: Partial<JudgeDimensionScore> & Pick<JudgeDimensionScore, "dimension">,
): JudgeDimensionScore {
  return {
    status: "scored",
    score: 90,
    rationale: "",
    ...overrides,
  };
}

function evaluation(overrides: Partial<TrustEvaluation> = {}): TrustEvaluation {
  return {
    evaluationId: "eval-1",
    orgId: "org-1",
    projectId: "project-1",
    runId: "run-1",
    stage: "research",
    headlineScore: 88,
    scoredDimensionsCount: 2,
    blockersCount: 0,
    dimensions: [],
    gates: [],
    provenance: {
      rubricVersion: "2.4",
      promptVersion: "cc-research-17",
      policyVersion: "3.2",
    },
    createdAt: "2026-08-19T10:00:00Z",
    ...overrides,
  };
}

describe("the headline score is the server's, not a local average", () => {
  it("renders the persisted headline even when the rows would average differently", () => {
    render(
      <TrustScoreCard
        evaluation={evaluation({
          headlineScore: 88,
          scoredDimensionsCount: 2,
          dimensions: [
            dimension({ dimension: "detection_recall", score: 10 }),
            dimension({ dimension: "claim_grounding", score: 20 }),
          ],
        })}
      />,
    );

    const ring = screen.getByTestId("trust-score-ring");
    expect(ring.getAttribute("data-score")).toBe("88");
    expect(ring.getAttribute("aria-label")).toContain("88 out of 100");
    expect(ring.getAttribute("aria-label")).toContain("mean of 2 graded dimensions");
    // A locally averaged 15 would contradict the record it is drawn from.
    expect(screen.queryByText("15")).toBeNull();
  });

  it("reports a null headline as unscored rather than as zero", () => {
    render(
      <TrustScoreCard
        evaluation={evaluation({
          headlineScore: null,
          scoredDimensionsCount: 0,
          dimensions: [
            dimension({ dimension: "detection_recall", status: "incomplete", score: null }),
          ],
        })}
      />,
    );

    expect(screen.queryByTestId("trust-score-ring")).toBeNull();
    expect(screen.getByTestId("trust-score-unscored").textContent).toContain(
      "Not scored",
    );
    expect(screen.getByText(/no honest mean to show/i)).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
  });
});

describe("an ungraded dimension is never drawn as a zero", () => {
  it("renders incomplete and not-applicable rows without a meter or a number", () => {
    const { container } = render(
      <RubricTable
        dimensions={[
          dimension({ dimension: "detection_recall", score: 91 }),
          dimension({ dimension: "rewrite_usefulness", status: "incomplete", score: null }),
          dimension({
            dimension: "rescan_correctness",
            status: "not_applicable",
            score: null,
          }),
        ]}
      />,
    );

    expect(screen.getByText("Not graded")).toBeTruthy();
    expect(screen.getByText("Not applicable at this stage")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();

    // Exactly one meter: the one graded dimension.
    const meters = container.querySelectorAll(".meter span");
    expect(meters).toHaveLength(1);
    expect((meters[0] as HTMLElement).style.width).toBe("91%");
  });

  it("still renders a failed dimension's judged score", () => {
    const { container } = render(
      <RubricTable
        dimensions={[
          dimension({ dimension: "legal_boundary", status: "failed", score: 0 }),
        ]}
      />,
    );

    expect(container.querySelectorAll(".meter span")).toHaveLength(1);
    expect(screen.getByText("0")).toBeTruthy();
  });
});

describe("stored tokens are displayed through their label maps", () => {
  it("never prints a raw cadence token", () => {
    expect(cadenceLabel("off")).toBe("Off");
    expect(cadenceLabel("manual")).toBe("Manual only");
    expect(cadenceLabel("daily")).toBe("Daily");
    expect(cadenceLabel("weekly")).toBe("Weekly");
  });

  it("offers only the stage transitions the server actually accepts", () => {
    expect(learningStageActions("candidate").promote).toBeUndefined();
    expect(learningStageActions("shadow").promote).toBeUndefined();
    expect(learningStageActions("canary").promote?.label).toBe("Adopt it");
    expect(learningStageActions("canary").rollback).toBeDefined();
    expect(learningStageActions("promoted").promote).toBeUndefined();
    expect(learningStageActions("promoted").rollback).toBeDefined();
    expect(learningStageActions("rolled_back").rollback).toBeUndefined();
  });
});
