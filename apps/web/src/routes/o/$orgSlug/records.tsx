import React, { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { api, type AuditRecord } from "@clearcut/contracts";

type RecordsView = "activity" | "runsAndTools" | "evaluations" | "policies" | "operations";

interface RecordsSearch {
  view: RecordsView;
  projectId?: string;
}

const RECORDS_VIEWS = new Set<RecordsView>([
  "activity",
  "runsAndTools",
  "evaluations",
  "policies",
  "operations",
]);

function recordsView(value: unknown): RecordsView {
  return typeof value === "string" && RECORDS_VIEWS.has(value as RecordsView)
    ? (value as RecordsView)
    : "activity";
}

export const Route = createFileRoute("/o/$orgSlug/records")({
  validateSearch: (search: Record<string, unknown>): RecordsSearch => ({
    view: recordsView(search.view),
    projectId:
      typeof search.projectId === "string" && search.projectId.length > 0
        ? search.projectId
        : undefined,
  }),
  component: OrgRecordsRoute,
});

export function OrgRecordsRoute() {
  const { orgSlug } = Route.useParams();
  const search = Route.useSearch();
  const [records, setRecords] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      const result = await api.listRecords({
        params: { orgId: orgSlug },
        query: {
          view: search.view,
          ...(search.projectId ? { projectId: search.projectId } : {}),
        },
      });
      if (!result.ok) {
        setRecords([]);
        setError(result.error.message);
        setLoading(false);
        return;
      }

      setRecords(result.value);
      setLoading(false);
    }

    void load();
  }, [orgSlug, search.projectId, search.view]);

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Audit Records & Lineage</h1>
        <p className="text-sm text-slate-400">
          Immutable log of clearance decisions, referrals, governed approvals, and releases.
        </p>
        <p className="mt-1 text-xs text-slate-500">
          View: {search.view}
          {search.projectId ? ` • Project: ${search.projectId}` : ""}
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded border border-rose-900 bg-rose-950/50 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden divide-y divide-slate-800">
        {loading ? (
          <div className="p-6 text-center text-xs text-slate-500">Loading audit records...</div>
        ) : error ? (
          <div className="p-6 text-center text-xs text-slate-500">
            Records remain unavailable; no empty-ledger conclusion was inferred.
          </div>
        ) : records.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">No audit events recorded yet.</div>
        ) : (
          records.map((record) => (
            <div key={record.recordId} className="p-4 flex items-center justify-between">
              <div>
                <div className="text-xs font-bold text-slate-200">{record.eventType}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  Actor: {record.actorEmail ?? record.actorId} • {new Date(record.timestamp).toLocaleString()}
                </div>
              </div>
              <span className="text-[10px] px-2 py-0.5 bg-slate-800 text-slate-400 rounded font-mono">
                Recorded
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default OrgRecordsRoute;
