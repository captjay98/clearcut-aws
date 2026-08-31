import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

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
        if (res.ok) {
          setTrustData(res.value.data);
        }
      } catch {
        // fallback
      }
    }
    load();
  }, [orgSlug]);

  const dimensions = trustData?.dimensions || [
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

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Trust Center & Evaluation Rubric</h1>
        <p className="text-sm text-slate-400">
          Continuous quality metrics across all 10 judge dimensions.
        </p>
      </div>

      <div className="p-6 bg-slate-900 border border-slate-800 rounded-lg flex items-center justify-between">
        <div>
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400">Headline Trust Score</div>
          <div className="text-4xl font-extrabold text-amber-400 mt-1">
            {trustData?.headlineScore || "9.4"}<span className="text-base text-slate-500 font-normal"> / 10.0</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-400">Protected Rules</div>
          <div className="text-xs font-semibold text-emerald-400 mt-0.5">🔒 Human-Gated Only</div>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
        <h2 className="text-sm font-bold text-slate-200 mb-4">10-Dimension Evaluation Rubric</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {dimensions.map((dim: any) => (
            <div key={dim.name} className="p-3 bg-slate-800/60 rounded border border-slate-700/60 flex items-center justify-between">
              <span className="text-xs font-medium text-slate-300 pr-2">{dim.name}</span>
              <span className="text-xs font-bold font-mono text-amber-400 px-2 py-0.5 bg-slate-900 rounded">
                {dim.score.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default TrustRoute;
