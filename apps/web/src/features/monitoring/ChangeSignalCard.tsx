import React, { useState } from "react";

export interface ChangeSignal {
  id: string;
  sourceTitle: string;
  detectedAt: string;
  signalType: string;
  summary: string;
  previousSnippet: string;
  currentSnippet: string;
  status: "unreviewed" | "reviewed" | "dismissed";
}

export interface ChangeSignalCardProps {
  signals?: ChangeSignal[];
}

export function ChangeSignalCard({ signals = [] }: ChangeSignalCardProps) {
  const [localSignals, setLocalSignals] = useState<ChangeSignal[]>(
    signals.length > 0
      ? signals
      : [
          {
            id: "sig-1",
            sourceTitle: "USPTO Trademark Electronic Search System (TESS)",
            detectedAt: "2026-08-30T08:00:00Z",
            signalType: "New Application Filed",
            summary: "New pending trademark application 'VEGA LENS' filed in Class 09 by Third Party.",
            previousSnippet: "0 active conflicting pending marks in sub-class 09.04.",
            currentSnippet: "1 pending application (Serial #98765432) filed August 2026 for optical equipment.",
            status: "unreviewed",
          },
        ]
  );

  const handleReview = (id: string) => {
    setLocalSignals((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: "reviewed" as const } : s))
    );
  };

  return (
    <div className="space-y-4 font-sans">
      <div className="flex items-center justify-between pb-2 border-b border-slate-800 text-xs font-bold text-slate-300 uppercase tracking-wider">
        <span>Source Change Signals & Alerts ({localSignals.length})</span>
        <span className="text-[10px] text-amber-400 font-normal">Parallel Monitor Triggered</span>
      </div>

      <div className="space-y-3">
        {localSignals.map((signal) => (
          <div
            key={signal.id}
            data-testid="change-signal-card"
            className="p-4 bg-slate-900 border border-slate-800 rounded-lg space-y-3 shadow-sm"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-white text-xs">{signal.sourceTitle}</span>
                  <span className="text-[10px] px-1.5 py-0.5 bg-amber-950 border border-amber-900 text-amber-400 rounded font-medium">
                    {signal.signalType}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1">{signal.summary}</div>
              </div>

              <span
                className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                  signal.status === "reviewed"
                    ? "bg-emerald-950 text-emerald-400 border border-emerald-900"
                    : "bg-rose-950 text-rose-400 border border-rose-900"
                }`}
              >
                {signal.status}
              </span>
            </div>

            {/* Diff highlight */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2.5 bg-slate-950 border border-slate-800 rounded">
                <span className="text-[10px] text-slate-500 font-sans font-bold">Snapshot at Import:</span>
                <p className="text-slate-400 mt-1 text-[11px]">{signal.previousSnippet}</p>
              </div>
              <div className="p-2.5 bg-amber-950/20 border border-amber-900/40 rounded">
                <span className="text-[10px] text-amber-400 font-sans font-bold">Current Live State:</span>
                <p className="text-amber-300 font-bold mt-1 text-[11px]">{signal.currentSnippet}</p>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
              <span className="text-[10px] text-slate-500 font-mono">
                Detected {new Date(signal.detectedAt).toLocaleString()}
              </span>
              {signal.status === "unreviewed" && (
                <button
                  type="button"
                  onClick={() => handleReview(signal.id)}
                  className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
                >
                  Mark Reviewed
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ChangeSignalCard;
