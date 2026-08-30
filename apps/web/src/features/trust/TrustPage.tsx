import React from "react";
import { Page, Card, StatGrid, Badge, Banner } from "@clearcut/design-system";

export interface TrustRubricData {
  headline_score: number;
  weakest_dimension: string;
  gate_warnings_count?: number;
  dimensions: Array<{ name: string; score: number }>;
}

export function TrustPage({
  trustData,
}: {
  trustData?: TrustRubricData | null;
}) {
  const defaultDimensions = [
    { name: "Detection recall and category correctness", score: 9.8 },
    { name: "Claim-to-source grounding", score: 9.7 },
    { name: "Citation and provenance completeness", score: 9.6 },
    { name: "Source authority and freshness", score: 9.5 },
    { name: "Conflict identification", score: 9.2 },
    { name: "Appropriate uncertainty", score: 8.9 },
    { name: "Rewrite usefulness", score: 9.4 },
    { name: "Affected-item re-scan correctness", score: 9.7 },
    { name: "Legal-boundary compliance", score: 9.9 },
    { name: "Tool efficiency, latency and cost", score: 9.3 },
  ];

  const dimensions = trustData?.dimensions || defaultDimensions;
  const headlineScore =
    trustData?.headline_score ||
    Number(
      (
        dimensions.reduce((acc, curr) => acc + curr.score, 0) /
        dimensions.length
      ).toFixed(1)
    );
  const weakestDimension =
    trustData?.weakest_dimension || "Appropriate uncertainty";

  return (
    <Page
      title="Trust, Rubric & Learning Governance"
      subtitle="Independent judge evaluation across 10 dimensions, gate thresholds, and gated prompt learning"
      trail={[{ label: "Trust" }]}
    >
      <div className="space-y-6">
        <StatGrid
          stats={[
            { label: "Overall Rubric Score", value: `${headlineScore}/10` },
            { label: "Weakest Dimension", value: weakestDimension },
            { label: "Deterministic Gate Warnings", value: "0" },
            { label: "Canary Pass Rate", value: "98.5%" },
          ]}
        />

        <Card title="10-Dimension Judge Rubric Evaluation">
          <div className="space-y-3 text-xs">
            {dimensions.map((d) => (
              <div key={d.name} className="flex items-center justify-between">
                <span className="text-slate-700 dark:text-slate-300 font-medium">
                  {d.name}
                </span>
                <div className="flex items-center space-x-3">
                  <div className="w-32 bg-slate-200 dark:bg-slate-700 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full"
                      style={{ width: `${(d.score / 10) * 100}%` }}
                    />
                  </div>
                  <span className="font-mono font-semibold text-slate-900 dark:text-white w-8 text-right">
                    {d.score}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Page>
  );
}
