import React from "react";
import { Page, Card, Badge, Banner } from "@clearcut/design-system";

export function SettingsPage() {
  return (
    <Page
      title="Organization Settings & Data Governance"
      subtitle="Policy configurations, retention rules, and organization deletion governance"
      trail={[{ label: "Organization Settings" }]}
    >
      <div className="space-y-6">
        <Banner
          title="Protected Configuration Governance"
          type="info"
        >
          Policy updates and retention alterations require Owner authentication with multi-factor re-authorization.
        </Banner>

        <Card title="Data Retention & Immutability Rules">
          <div className="space-y-3 text-xs text-slate-600 dark:text-slate-400">
            <p>
              • <strong>Core Evidence Policy:</strong> Retained evidence snapshots and decision records have no automated age-based expiration.
            </p>
            <p>
              • <strong>Immutable Lineage:</strong> Decisions, audit events, and historical script versions are strictly immutable.
            </p>
          </div>
        </Card>

        <Card title="Danger Zone — Organization Deletion">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">
                Schedule Organization Deletion
              </span>
              <p className="text-xs text-slate-500">
                Enters a 30-day read-only grace period before permanent, unrecoverable purge.
              </p>
            </div>
            <button
              type="button"
              className="px-3 py-1.5 text-xs font-semibold text-rose-600 border border-rose-300 dark:border-rose-800 rounded hover:bg-rose-50 dark:hover:bg-rose-950/30"
            >
              Schedule Deletion
            </button>
          </div>
        </Card>
      </div>
    </Page>
  );
}
