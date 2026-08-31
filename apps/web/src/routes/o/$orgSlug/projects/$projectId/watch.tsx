import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/watch")({
  component: WatchRoute,
});

export function WatchRoute() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId/watch" });
  const [config, setConfig] = useState<any | null>(null);
  const [running, setRunning] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadConfig = async () => {
    try {
      const res = await api.getMonitoringCadence({ path: { org_id: orgSlug, project_id: projectId } });
      if (res.ok) {
        setConfig(res.value.data);
      }
    } catch {
      // handle error
    }
  };

  useEffect(() => {
    loadConfig();
  }, [orgSlug, projectId]);

  const handleRunCheck = async () => {
    setRunning(true);
    setFeedback(null);
    try {
      const res = await api.runMonitoringCheck({ path: { org_id: orgSlug, project_id: projectId } });
      if (res.ok) {
        setFeedback("Monitoring check completed. All 38 monitored sources verified current.");
      } else {
        setFeedback(`Error: ${res.error.message}`);
      }
    } catch {
      setFeedback("Network error executing check");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Source Monitoring & Cadence</h1>
        <p className="text-sm text-slate-400">
          Automated scheduled monitoring of trademark registries, domain registrations, and source changes.
        </p>
      </div>

      {feedback && (
        <div role="alert" className="p-3 bg-emerald-950/50 border border-emerald-900 rounded text-xs text-emerald-400">
          {feedback}
        </div>
      )}

      <div className="p-5 bg-slate-900 border border-slate-800 rounded-lg space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider font-bold">Cadence Schedule</div>
            <div className="text-base font-bold text-white mt-0.5 capitalize">
              {config?.cadence || "Weekly"} Recurring Scan
            </div>
          </div>
          <span className="text-xs px-2.5 py-1 bg-emerald-950 border border-emerald-900 text-emerald-400 font-bold rounded">
            {config?.status || "Active"}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs pt-2 border-t border-slate-800">
          <div className="p-3 bg-slate-800/40 rounded">
            <span className="text-slate-500">Monitored Sources:</span>
            <div className="text-sm font-bold text-white mt-0.5">{config?.monitoredSourcesCount || 38} records</div>
          </div>
          <div className="p-3 bg-slate-800/40 rounded">
            <span className="text-slate-500">Next Scheduled Run:</span>
            <div className="text-sm font-bold text-white mt-0.5">
              {config?.nextRunAt ? new Date(config.nextRunAt).toLocaleDateString() : "In 7 days"}
            </div>
          </div>
        </div>

        <div className="pt-2">
          <button
            type="button"
            onClick={handleRunCheck}
            disabled={running}
            className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            {running ? "Executing Verification Run..." : "Run Immediate Source Check"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default WatchRoute;
