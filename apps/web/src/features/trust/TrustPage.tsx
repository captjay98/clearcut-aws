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
  const dimensions = trustData?.dimensions ?? [];
  const hasData = !!trustData && dimensions.length > 0;
  const headlineScore = hasData
    ? trustData?.headline_score ??
      Number(
        (dimensions.reduce((acc, curr) => acc + curr.score, 0) / dimensions.length).toFixed(1)
      )
    : null;
  const weakestDimension = trustData?.weakest_dimension ?? "—";

  return (
    <Page
      title="Trust, Rubric & Learning Governance"
      subtitle="Independent judge evaluation across 10 dimensions, gate thresholds, and gated prompt learning"
      trail={[{ label: "Trust" }]}
    >
      <div className="space-y-6">
        {!hasData ? (
          <Banner
            title="Evaluation not yet available"
            variant="info"
            message="No judge evaluation has been run for this organization yet. Rubric scores appear here once an evaluation run completes."
          />
        ) : (
          <>
            <StatGrid
              stats={[
                { label: "Overall Rubric Score", value: `${headlineScore}/10` },
                { label: "Weakest Dimension", value: weakestDimension },
                { label: "Deterministic Gate Warnings", value: String(trustData?.gate_warnings_count ?? 0) },
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
          </>
        )}
      </div>
    </Page>
  );
}
