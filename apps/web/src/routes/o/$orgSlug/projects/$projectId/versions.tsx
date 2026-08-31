import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/versions")({
  component: VersionsRoute,
});

export function VersionsRoute() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId/versions" });
  const [versions, setVersions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.listProjectVersions({ path: { org_id: orgSlug, project_id: projectId } });
        if (res.ok) {
          setVersions(res.value.data || []);
        }
      } catch {
        // handle error
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [orgSlug, projectId]);

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Script Versions & Lineage</h1>
        <p className="text-sm text-slate-400">
          Track revisions, re-scans, and affected items across version changes.
        </p>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-lg divide-y divide-slate-800">
        {loading ? (
          <div className="p-6 text-center text-xs text-slate-500">Loading versions...</div>
        ) : versions.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">No script versions recorded.</div>
        ) : (
          versions.map((v) => (
            <div key={v.versionId} className="p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="text-sm font-bold text-white">Version {v.ordinal}</span>
                  <span className="text-[10px] px-2 py-0.5 bg-slate-800 text-slate-400 rounded font-mono">
                    {v.sourceHash?.substring(0, 12)}...
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  Created {new Date(v.createdAt).toLocaleString()} • Parser: {v.parserVersion}
                </div>
              </div>
              <span className="text-xs px-2.5 py-1 bg-amber-950/60 border border-amber-900 text-amber-400 font-bold rounded">
                Active Revision
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default VersionsRoute;
