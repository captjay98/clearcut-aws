import React, { useState } from "react";

export interface LearningCandidate {
  id: string;
  candidateType: string;
  description: string;
  lifecycle: "candidate" | "shadow" | "promoted" | "rolled_back";
  impactScore: number;
}

export interface LearningCandidateTableProps {
  candidates?: LearningCandidate[];
}

export function LearningCandidateTable({ candidates = [] }: LearningCandidateTableProps) {
  const [localCandidates, setLocalCandidates] = useState<LearningCandidate[]>(
    candidates.length > 0
      ? candidates
      : [
          {
            id: "cand-1",
            candidateType: "Query Phrasing Refinement",
            description: "Enhanced Parallel search query templates for fictional beverage trademarks in Scene 4.",
            lifecycle: "shadow",
            impactScore: 9.6,
          },
          {
            id: "cand-2",
            candidateType: "Category Example Addition",
            description: "Added 4 edge-case examples to Music & Lyrics detection prompt.",
            lifecycle: "candidate",
            impactScore: 9.4,
          },
        ]
  );

  const handlePromote = (id: string) => {
    setLocalCandidates((prev) =>
      prev.map((c) => (c.id === id ? { ...c, lifecycle: "promoted" as const } : c))
    );
  };

  const handleRollback = (id: string) => {
    setLocalCandidates((prev) =>
      prev.map((c) => (c.id === id ? { ...c, lifecycle: "rolled_back" as const } : c))
    );
  };

  return (
    <div
      data-testid="learning-candidates-table"
      className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4 font-sans shadow-sm"
    >
      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
        <div>
          <h3 className="text-sm font-bold text-white">Gated Learning & Candidate Lifecycle</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Canary promotion with automated regression gates and rollback guarantees.
          </p>
        </div>
        <span className="text-xs px-2.5 py-0.5 bg-slate-800 text-slate-300 rounded font-mono">
          Regression Gated
        </span>
      </div>

      <div className="divide-y divide-slate-800 text-xs">
        {localCandidates.map((c) => (
          <div key={c.id} className="py-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-200">{c.candidateType}</span>
                <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded font-mono">
                  {c.id}
                </span>
              </div>
              <p className="text-slate-400">{c.description}</p>
            </div>

            <div className="flex items-center space-x-2 shrink-0">
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                  c.lifecycle === "promoted"
                    ? "bg-emerald-950 text-emerald-400 border border-emerald-900"
                    : c.lifecycle === "rolled_back"
                    ? "bg-red-950 text-red-400 border border-red-900"
                    : "bg-blue-950 text-blue-400 border border-blue-900"
                }`}
              >
                {c.lifecycle}
              </span>

              {c.lifecycle !== "promoted" && c.lifecycle !== "rolled_back" && (
                <button
                  type="button"
                  onClick={() => handlePromote(c.id)}
                  className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded shadow"
                >
                  Promote Candidate
                </button>
              )}

              {c.lifecycle === "promoted" && (
                <button
                  type="button"
                  onClick={() => handleRollback(c.id)}
                  className="px-3 py-1 bg-red-800 hover:bg-red-700 text-white font-bold text-xs rounded shadow"
                >
                  Rollback
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default LearningCandidateTable;
