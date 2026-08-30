import React from "react";
import { Page, Card, Badge, StatGrid } from "@clearcut/design-system";

export function TrustPage() {
  const dimensions = [
    { name: "Detection Recall & Category Correctness", score: 98 },
    { name: "Claim-to-Source Grounding", score: 96 },
    { name: "Citation & Provenance Completeness", score: 100 },
    { name: "Source Authority & Freshness", score: 94 },
    { name: "Conflict Identification", score: 92 },
    { name: "Appropriate Uncertainty", score: 95 },
    { name: "Rewrite Usefulness", score: 97 },
    { name: "Affected-Item Re-scan Correctness", score: 99 },
    { name: "Legal-Boundary Compliance", score: 100 },
    { name: "Tool Efficiency, Latency & Cost", score: 95 },
  ];

  return (
    <Page
      title="Trust, Rubric & Learning Governance"
      subtitle="Verifiable evaluation grades, 10-dimension rubric benchmarks, and gated learning"
      trail={[{ label: "Trust & Governance" }]}
    >
      <div className="space-y-6">
        <StatGrid
          stats={[
            { label: "Overall Quality Grade", value: "96.6%", change: "+0.4%", positive: true },
            { label: "Zero-Guarantees Compliance", value: "100%", positive: true },
            { label: "Deterministic Gate Pass Rate", value: "100%", positive: true },
          ]}
        />

        <Card title="10-Dimension Judge Rubric Evaluation">
          <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
            {dimensions.map((d) => (
              <div key={d.name} className="py-2.5 flex items-center justify-between">
                <span className="font-medium text-slate-900 dark:text-white">{d.name}</span>
                <div className="flex items-center space-x-3">
                  <span className="font-mono font-semibold text-slate-700 dark:text-slate-300">
                    {d.score}/100
                  </span>
                  <Badge label="Passed" variant="success" />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </Page>
  );
}
