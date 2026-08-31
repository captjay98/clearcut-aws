import React from "react";

export interface ProtectedConfigCardProps {
  policyVersion?: string;
  promptVersion?: string;
  retentionDays?: number;
}

export function ProtectedConfigCard({
  policyVersion = "2026.08.30-v1",
  promptVersion = "prompts-v2.1",
  retentionDays = 365,
}: ProtectedConfigCardProps) {
  return (
    <div
      data-testid="protected-config-card"
      className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4 font-sans shadow-sm"
    >
      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
        <div>
          <h3 className="text-sm font-bold text-white">Protected Configurations & Policy Gates</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Immutable guardrails and strict human-only configuration boundaries.
          </p>
        </div>
        <span className="text-xs px-2.5 py-1 bg-amber-950 border border-amber-900 text-amber-400 font-bold rounded flex items-center space-x-1">
          <span>🔒</span>
          <span>Human-Gated Only</span>
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
        <div className="p-3 bg-slate-950 border border-slate-800 rounded">
          <span className="text-[10px] text-slate-500 font-bold uppercase">Clearance Policy Version</span>
          <div className="text-sm font-mono font-bold text-slate-200 mt-1">{policyVersion}</div>
        </div>

        <div className="p-3 bg-slate-950 border border-slate-800 rounded">
          <span className="text-[10px] text-slate-500 font-bold uppercase">Detection Prompt Set</span>
          <div className="text-sm font-mono font-bold text-slate-200 mt-1">{promptVersion}</div>
        </div>

        <div className="p-3 bg-slate-950 border border-slate-800 rounded">
          <span className="text-[10px] text-slate-500 font-bold uppercase">Audit Retention Horizon</span>
          <div className="text-sm font-mono font-bold text-slate-200 mt-1">{retentionDays} Days</div>
        </div>
      </div>

      <div className="p-3 bg-slate-950/60 rounded border border-slate-800 text-xs text-slate-400 flex items-start space-x-2">
        <span className="text-amber-500 font-bold">ℹ️</span>
        <p>
          Permissions, sign-off thresholds, category definitions, and legal-boundary language can only be modified by authenticated human administrators. Automated agents cannot modify protected rules.
        </p>
      </div>
    </div>
  );
}

export default ProtectedConfigCard;
