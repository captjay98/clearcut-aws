import React, { useState } from "react";
import { Page, Card, Badge } from "@clearcut/design-system";

export function WatchPage() {
  const [cadence, setCadence] = useState("daily");

  return (
    <Page
      title="Evidence Watch & Source Monitoring"
      subtitle="Automated scheduled Search & Extract rechecks and source change monitoring"
      trail={[
        { label: "Overview", href: "." },
        { label: "Evidence Watch" },
      ]}
    >
      <div className="space-y-6">
        <Card title="Monitoring Cadence Configuration">
          <div className="flex items-center space-x-4">
            <label className="text-xs font-medium text-slate-700 dark:text-slate-300">
              Scheduled Recheck Frequency:
            </label>
            <select
              value={cadence}
              onChange={(e) => setCadence(e.target.value)}
              className="p-2 text-xs border border-slate-300 dark:border-slate-700 rounded bg-white dark:bg-slate-800"
            >
              <option value="off">Off (Disabled)</option>
              <option value="manual">Manual Re-scan Only</option>
              <option value="daily">Daily Scheduled Recheck</option>
              <option value="weekly">Weekly Scheduled Recheck</option>
            </select>
          </div>
        </Card>

        <Card title="Active Watched Clearance Items">
          <div className="divide-y divide-slate-100 dark:divide-slate-800 text-xs">
            <div className="py-3 flex items-center justify-between">
              <div>
                <span className="font-semibold text-slate-900 dark:text-white">Coca-Cola</span>
                <span className="ml-2 text-slate-400">USPTO Record (https://uspto.gov/trademarks)</span>
              </div>
              <div className="flex items-center space-x-2">
                <Badge label="Daily Watch" variant="primary" />
                <Badge label="No Change Detected" variant="success" />
              </div>
            </div>
          </div>
        </Card>
      </div>
    </Page>
  );
}
