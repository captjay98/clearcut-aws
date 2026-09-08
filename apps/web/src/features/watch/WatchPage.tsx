import React, { useState } from "react";
import { Page, Card, Badge, Banner } from "@clearcut/design-system";

export interface WatchConfig {
  cadence: string;
  lastRunAt?: string;
  nextRunAt?: string;
  monitoredCount?: number;
}

export function WatchPage({
  config,
}: {
  config?: WatchConfig | null;
}) {
  const [cadence, setCadence] = useState(config?.cadence || "weekly");

  return (
    <Page
      title="Evidence Watch & Source Monitoring"
      subtitle="Configure scheduled source rechecks and review material delta signals"
      trail={[{ label: "Overview", href: "." }, { label: "Watch" }]}
    >
      <div className="space-y-6">
        <Banner
          title="Parallel Web Monitoring Notice"
          type="info"
        >
          Evidence watch performs scheduled rechecks using Parallel Search and Extract to detect source modifications.
        </Banner>

        <Card title="Monitoring Cadence Configuration">
          <div className="space-y-4 text-xs">
            <div className="flex items-center justify-between">
              <div>
                <label className="font-semibold text-slate-900 dark:text-white block">
                  Recheck Frequency
                </label>
                <p className="text-slate-500">
                  Controls how frequently ClearCut checks external evidence sources.
                </p>
              </div>
              <select
                value={cadence}
                onChange={(e) => setCadence(e.target.value)}
                className="p-2 border border-slate-300 dark:border-slate-700 rounded bg-white dark:bg-slate-800 text-slate-900 dark:text-white font-medium"
              >
                <option value="off">Off</option>
                <option value="manual">Manual Only</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>

            <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-slate-500">
              <span>Next Scheduled Recheck: <strong>{config?.nextRunAt || "2026-09-06T12:00:00Z"}</strong></span>
              <span>Monitored Sources: <strong>{config?.monitoredCount || 38}</strong></span>
            </div>
          </div>
        </Card>
      </div>
    </Page>
  );
}
