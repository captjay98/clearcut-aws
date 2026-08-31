import React, { useState } from "react";

export interface DiffSegment {
  type: "unchanged" | "added" | "removed";
  text: string;
  lineNumber?: number;
}

export interface ScriptDiffViewerProps {
  baseVersionLabel?: string;
  targetVersionLabel?: string;
  segments?: DiffSegment[];
}

export function ScriptDiffViewer({
  baseVersionLabel = "v1 (Original Draft)",
  targetVersionLabel = "v2 (Blue Revision)",
  segments = [],
}: ScriptDiffViewerProps) {
  const [viewMode, setViewMode] = useState<"split" | "unified">("unified");

  const displaySegments: DiffSegment[] =
    segments.length > 0
      ? segments
      : [
          { type: "unchanged", text: "EXT. DOWNTOWN ROOFTOP - DUSK", lineNumber: 1 },
          {
            type: "removed",
            text: "LEO checks his Vega Camera as the horizon turns cobalt.",
            lineNumber: 2,
          },
          {
            type: "added",
            text: "LEO checks his Aero Optics Mark IV as the horizon turns cobalt.",
            lineNumber: 2,
          },
          { type: "unchanged", text: "LEO: Mina, do you copy? The feed is live.", lineNumber: 3 },
          { type: "unchanged", text: "INT. SURVEILLANCE VAN - CONTINUOUS", lineNumber: 4 },
          {
            type: "removed",
            text: "A vintage radio plays Blue Monday in the background.",
            lineNumber: 5,
          },
          {
            type: "added",
            text: "A vintage radio plays an ambient synth drone in the background.",
            lineNumber: 5,
          },
        ];

  return (
    <div
      data-testid="script-diff-viewer"
      className="bg-slate-950 border border-slate-800 rounded-lg overflow-hidden flex flex-col font-mono text-xs shadow-inner"
    >
      {/* Header bar */}
      <div className="px-4 py-2.5 bg-slate-900 border-b border-slate-800 flex items-center justify-between font-sans shrink-0">
        <div className="flex items-center space-x-2 text-xs font-bold text-slate-200">
          <span className="px-2 py-0.5 bg-red-950/80 border border-red-900 text-red-400 rounded font-mono">
            {baseVersionLabel}
          </span>
          <span className="text-slate-500">→</span>
          <span className="px-2 py-0.5 bg-emerald-950/80 border border-emerald-900 text-emerald-400 rounded font-mono">
            {targetVersionLabel}
          </span>
        </div>

        <div className="flex items-center space-x-1 text-xs">
          <button
            type="button"
            onClick={() => setViewMode("unified")}
            className={`px-2.5 py-1 rounded font-medium ${
              viewMode === "unified" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Unified Diff
          </button>
          <button
            type="button"
            onClick={() => setViewMode("split")}
            className={`px-2.5 py-1 rounded font-medium ${
              viewMode === "split" ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Split View
          </button>
        </div>
      </div>

      {/* Diff content */}
      <div className="p-4 overflow-x-auto space-y-1">
        {displaySegments.map((seg, idx) => {
          if (seg.type === "added") {
            return (
              <div
                key={idx}
                className="flex items-start space-x-3 px-2 py-1 bg-emerald-950/30 text-emerald-300 border-l-2 border-emerald-500 rounded-r"
              >
                <span className="text-emerald-500 select-none font-bold">+</span>
                <span className="flex-1">{seg.text}</span>
              </div>
            );
          }
          if (seg.type === "removed") {
            return (
              <div
                key={idx}
                className="flex items-start space-x-3 px-2 py-1 bg-red-950/30 text-red-400 border-l-2 border-red-500 rounded-r line-through opacity-80"
              >
                <span className="text-red-500 select-none font-bold">-</span>
                <span className="flex-1">{seg.text}</span>
              </div>
            );
          }
          return (
            <div key={idx} className="flex items-start space-x-3 px-2 py-0.5 text-slate-400">
              <span className="text-slate-600 select-none">&nbsp;</span>
              <span className="flex-1">{seg.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default ScriptDiffViewer;
