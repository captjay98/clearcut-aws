import React from "react";

interface AnalysisProgressProps {
  status: "queued" | "running" | "succeeded" | "failed";
  progressPercent: number;
}

export function AnalysisProgress({ status, progressPercent }: AnalysisProgressProps) {
  return (
    <div className="p-6 text-center space-y-4">
      <h3 className="text-xl font-bold text-slate-900 dark:text-white capitalize">
        Pre-Clearance Analysis {status}
      </h3>
      <p className="text-sm text-slate-500">
        Parsing screenplay elements, extracting clearance items, and gathering Parallel search evidence.
      </p>

      <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-3 overflow-hidden">
        <div
          className="bg-blue-600 h-3 rounded-full transition-all duration-300"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      <p className="text-xs text-slate-400">{progressPercent}% complete</p>
    </div>
  );
}
