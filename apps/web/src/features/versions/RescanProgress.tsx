import React from "react";
import { Progress, Badge } from "@clearcut/design-system";

export interface RescanProgressProps {
  affectedCount: number;
  savedCallsCount: number;
  completedCount: number;
  status: "idle" | "running" | "completed";
}

export function RescanProgress({
  affectedCount,
  savedCallsCount,
  completedCount,
  status,
}: RescanProgressProps) {
  return (
    <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
            Selective Re-scan Execution
          </h4>
          <p className="text-xs text-slate-500">
            Rescanning {affectedCount} affected clearance items • {savedCallsCount} search calls saved by lineage carryover
          </p>
        </div>
        <Badge
          label={status === "completed" ? "Completed" : "In Progress"}
          variant={status === "completed" ? "success" : "primary"}
        />
      </div>

      <Progress value={completedCount} max={affectedCount} label="Affected Items Rescanned" />
    </div>
  );
}
