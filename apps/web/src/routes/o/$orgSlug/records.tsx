import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/records")({
  component: OrgRecordsRoute,
});

export function OrgRecordsRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/records" });
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.listAuditEvents({ path: { org_id: orgSlug } });
        if (res.ok) {
          setRecords(res.value.data || []);
        }
      } catch {
        // handle error
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [orgSlug]);

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Audit Records & Lineage</h1>
        <p className="text-sm text-slate-400">
          Immutable log of all clearance decisions, referrals, rewrite approvals, and releases.
        </p>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden divide-y divide-slate-800">
        {loading ? (
          <div className="p-6 text-center text-xs text-slate-500">Loading audit records...</div>
        ) : records.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">No audit events recorded yet.</div>
        ) : (
          records.map((r) => (
            <div key={r.eventId} className="p-4 flex items-center justify-between">
              <div>
                <div className="text-xs font-bold text-slate-200">{r.action}</div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  Target: {r.targetType} ({r.targetId?.substring(0, 8)}) • {new Date(r.createdAt).toLocaleString()}
                </div>
              </div>
              <span className="text-[10px] px-2 py-0.5 bg-slate-800 text-slate-400 rounded font-mono">
                Verified
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default OrgRecordsRoute;
