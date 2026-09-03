import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import {
  CadenceSelector,
  type MonitoringCadence,
} from "../../../../../features/monitoring/CadenceSelector";
import { MonitoredSourcesTable } from "../../../../../features/monitoring/MonitoredSourcesTable";
import { ChangeSignalCard } from "../../../../../features/monitoring/ChangeSignalCard";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/watch")({
  component: WatchRoute,
});

function isMonitoringCadence(value: string): value is MonitoringCadence {
  return ["daily", "weekly", "biweekly", "monthly"].includes(value);
}

export function WatchRoute() {
  const { orgSlug, projectId } = useParams({
    from: "/o/$orgSlug/projects/$projectId/watch",
  });
  const [cadence, setCadence] = useState<MonitoringCadence>("weekly");
  const [running, setRunning] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadConfig = async () => {
    try {
      const result = await api.getMonitoringPolicy({
        params: { orgId: orgSlug, projectId },
      });
      if (result.ok && isMonitoringCadence(result.value.cadence)) {
        setCadence(result.value.cadence);
      }
    } catch {
      // The currently persisted cadence remains visible.
    }
  };

  useEffect(() => {
    void loadConfig();
  }, [orgSlug, projectId]);

  const handleChangeCadence = async (newCadence: MonitoringCadence) => {
    setCadence(newCadence);
    try {
      await api.changeMonitoringCadence({
        params: { orgId: orgSlug, projectId },
        body: { cadence: newCadence },
      });
    } catch {
      // The monitoring policy query will restore persisted state on reload.
    }
  };

  const handleRunCheck = async () => {
    setRunning(true);
    setFeedback(null);
    try {
      const result = await api.startMonitoringRun({
        params: { orgId: orgSlug, projectId },
      });
      if (result.ok) {
        setFeedback("Monitoring run accepted. Review persisted results when processing completes.");
      } else {
        setFeedback(`Error: ${result.error.message}`);
      }
    } catch {
      setFeedback("Error: The monitoring service is unavailable.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl font-sans">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Source Monitoring & Cadence</h1>
          <p className="text-sm text-slate-400">
            Scheduled monitoring of cited sources and attributable source changes.
          </p>
        </div>

        <button
          type="button"
          onClick={handleRunCheck}
          disabled={running}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-bold rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500 shrink-0"
        >
          {running ? "Starting Source Check..." : "Run Immediate Source Check"}
        </button>
      </div>

      {feedback ? (
        <div role="status" className="p-3 bg-slate-900 border border-slate-800 rounded text-xs text-slate-300">
          {feedback}
        </div>
      ) : null}

      <CadenceSelector currentCadence={cadence} onChangeCadence={handleChangeCadence} />
      <MonitoredSourcesTable />
      <ChangeSignalCard />
    </div>
  );
}

export default WatchRoute;
