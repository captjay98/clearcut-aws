import React from "react";
import { Badge } from "@clearcut/design-system";

export interface DiffRow {
  elementId: string;
  orderIndex: number;
  beforeText: string | null;
  afterText: string | null;
  classification: "unchanged" | "modified" | "added" | "removed";
}

export interface VersionDiffViewerProps {
  beforeVersionLabel?: string;
  afterVersionLabel?: string;
  diffs?: DiffRow[];
}

export function VersionDiffViewer({
  beforeVersionLabel = "v1 (White Pages)",
  afterVersionLabel = "v2 (Blue Pages)",
  diffs = [
    {
      elementId: "e-1",
      orderIndex: 1,
      beforeText: "EXT. SUNSET BLVD - DAY",
      afterText: "EXT. SUNSET BLVD - DAY",
      classification: "unchanged",
    },
    {
      elementId: "e-2",
      orderIndex: 2,
      beforeText: "SARAH (30s) sits sipping a CAN OF COCA-COLA.",
      afterText: "SARAH (30s) sits sipping a CAN OF SPARKLING COLA.",
      classification: "modified",
    },
    {
      elementId: "e-3",
      orderIndex: 3,
      beforeText: null,
      afterText: "She checks her vintage Vega Camera before heading inside.",
      classification: "added",
    },
  ],
}: VersionDiffViewerProps) {
  const displayDiffs = diffs && diffs.length > 0 ? diffs : [];

  return (
    <div className="border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden font-mono text-xs">
      <div className="grid grid-cols-2 bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 p-3 text-slate-600 dark:text-slate-400 font-sans font-medium">
        <div>{beforeVersionLabel} (Prior)</div>
        <div>{afterVersionLabel} (Approved Revision)</div>
      </div>
      <div className="divide-y divide-slate-100 dark:divide-slate-800">
        {displayDiffs.map((d) => {
          if (d.classification === "unchanged") {
            return (
              <div key={d.elementId} className="grid grid-cols-2 p-3 text-slate-500">
                <div>{d.beforeText}</div>
                <div>{d.afterText}</div>
              </div>
            );
          }
          if (d.classification === "modified") {
            return (
              <div key={d.elementId} className="grid grid-cols-2 p-3 bg-amber-50/50 dark:bg-amber-950/20">
                <div className="text-rose-600 line-through pr-2">{d.beforeText}</div>
                <div className="text-emerald-600 font-semibold pl-2">{d.afterText}</div>
              </div>
            );
          }
          if (d.classification === "added") {
            return (
              <div key={d.elementId} className="grid grid-cols-2 p-3 bg-emerald-50/50 dark:bg-emerald-950/20">
                <div className="text-slate-400 italic">(none)</div>
                <div className="text-emerald-600 font-semibold">{d.afterText}</div>
              </div>
            );
          }
          return null;
        })}
      </div>
    </div>
  );
}
