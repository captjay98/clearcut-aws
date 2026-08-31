import React from "react";

export interface RubricDimension {
  name: string;
  score: number;
  threshold?: number;
  description?: string;
}

export interface RubricVisualizerProps {
  headlineScore?: number;
  weakestDimension?: string;
  dimensions?: RubricDimension[];
}

export function RubricVisualizer({
  headlineScore = 9.4,
  weakestDimension = "Appropriate uncertainty",
  dimensions = [
    { name: "Detection recall and category correctness", score: 9.8, threshold: 9.0 },
    { name: "Claim-to-source grounding", score: 9.7, threshold: 9.0 },
    { name: "Citation and provenance completeness", score: 9.6, threshold: 9.0 },
    { name: "Source authority and freshness", score: 9.5, threshold: 9.0 },
    { name: "Conflict identification", score: 9.2, threshold: 8.5 },
    { name: "Appropriate uncertainty", score: 8.9, threshold: 8.5 },
    { name: "Rewrite usefulness", score: 9.4, threshold: 8.5 },
    { name: "Affected-item re-scan correctness", score: 9.7, threshold: 9.0 },
    { name: "Legal-boundary compliance", score: 9.9, threshold: 9.5 },
    { name: "Tool efficiency, latency and cost", score: 9.3, threshold: 8.5 },
  ],
}: RubricVisualizerProps) {
  return (
    <div data-testid="rubric-visualizer" className="space-y-4 font-sans">
      {/* Headline Trust Summary */}
      <div className="p-6 bg-slate-900 border border-slate-800 rounded-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm">
        <div>
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Overall ClearCut Trust Score
          </div>
          <div className="text-4xl font-extrabold text-amber-400 mt-1 flex items-baseline space-x-1">
            <span>{headlineScore.toFixed(1)}</span>
            <span className="text-base text-slate-500 font-normal">/ 10.0</span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            Weakest dimension: <span className="font-medium text-slate-300">{weakestDimension}</span>
          </div>
        </div>

        <div className="flex flex-col sm:items-end text-xs space-y-1">
          <span className="px-3 py-1 bg-emerald-950/80 border border-emerald-900 text-emerald-400 font-bold rounded-full">
            ● Quality Gates Passing
          </span>
          <span className="text-[11px] text-slate-500">Continuous Regression Testing Active</span>
        </div>
      </div>

      {/* 10 Dimension Cards Grid */}
      <div className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
          10-Dimension Evaluation Rubric
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {dimensions.map((dim) => {
            const percentage = (dim.score / 10) * 100;
            return (
              <div
                key={dim.name}
                data-testid="rubric-dimension-card"
                className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg space-y-2 shadow-sm"
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-slate-200">{dim.name}</span>
                  <span className="font-mono font-bold text-amber-400 px-2 py-0.5 bg-slate-950 rounded">
                    {dim.score.toFixed(1)}
                  </span>
                </div>

                {/* Score bar */}
                <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-amber-500 h-1.5 rounded-full transition-all"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default RubricVisualizer;
