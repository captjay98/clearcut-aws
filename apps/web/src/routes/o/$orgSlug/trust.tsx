import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { RubricVisualizer } from "../../../features/trust/RubricVisualizer";
import { ProtectedConfigCard } from "../../../features/trust/ProtectedConfigCard";
import { LearningCandidateTable } from "../../../features/trust/LearningCandidateTable";

export const Route = createFileRoute("/o/$orgSlug/trust")({
  component: TrustRoute,
});

export function TrustRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/trust" });
  const [trustData, setTrustData] = useState<any>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.getTrustAndRubric({ path: { org_id: orgSlug } });
        if (res.ok && res.value.data) {
          setTrustData(res.value.data);
        }
      } catch {
        // fallback
      }
    }
    load();
  }, [orgSlug]);

  return (
    <div className="space-y-6 max-w-5xl font-sans">
      <div>
        <h1 className="text-2xl font-bold text-white">Trust Center & Evaluation Rubric</h1>
        <p className="text-sm text-slate-400">
          Continuous quality metrics across all 10 judge dimensions, human-gated policy rules, and canary learning lifecycles.
        </p>
      </div>

      {/* 10-Dimension Rubric Visualizer */}
      <RubricVisualizer
        headlineScore={trustData?.headlineScore}
        weakestDimension={trustData?.weakestDimension}
        dimensions={trustData?.dimensions}
      />

      {/* Protected Configurations Card */}
      <ProtectedConfigCard />

      {/* Gated Learning & Canary Promotion Lifecycle */}
      <LearningCandidateTable />
    </div>
  );
}

export default TrustRoute;
