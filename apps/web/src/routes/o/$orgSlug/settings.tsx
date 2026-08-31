import React from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";

export const Route = createFileRoute("/o/$orgSlug/settings")({
  component: SettingsRoute,
});

export function SettingsRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/settings" });

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Workspace Settings</h1>
        <p className="text-sm text-slate-400">
          Organization policies, retention periods, and verification thresholds.
        </p>
      </div>

      <div className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4">
        <h2 className="text-sm font-bold text-slate-200">Clearance Governance</h2>

        <div className="flex items-center justify-between py-2 border-b border-slate-800">
          <div>
            <div className="text-xs font-semibold text-slate-300">Dual Legal Sign-Off</div>
            <div className="text-[11px] text-slate-500">Require 2 qualified reviewers before final release export</div>
          </div>
          <input type="checkbox" defaultChecked className="rounded bg-slate-800 border-slate-700 text-amber-500 focus:ring-amber-500" />
        </div>

        <div className="flex items-center justify-between py-2 border-b border-slate-800">
          <div>
            <div className="text-xs font-semibold text-slate-300">Strict Source Authority</div>
            <div className="text-[11px] text-slate-500">Reject non-canonical sources during automated evidence extraction</div>
          </div>
          <input type="checkbox" defaultChecked className="rounded bg-slate-800 border-slate-700 text-amber-500 focus:ring-amber-500" />
        </div>

        <div className="flex items-center justify-between py-2">
          <div>
            <div className="text-xs font-semibold text-slate-300">Retention Horizon</div>
            <div className="text-[11px] text-slate-500">Number of days before inactive audit payloads are archived</div>
          </div>
          <span className="text-xs px-2 py-1 bg-slate-800 rounded text-slate-300 font-mono">365 days</span>
        </div>
      </div>
    </div>
  );
}

export default SettingsRoute;
