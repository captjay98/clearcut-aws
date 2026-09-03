import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api, type ScriptVersion } from "@clearcut/contracts";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/versions")({
  component: VersionsRoute,
});

export function VersionsRoute() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId/versions" });
  const [versions, setVersions] = useState<ScriptVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      const result = await api.listProjectVersions({
        params: { orgId: orgSlug, projectId },
      });
      if (!result.ok) {
        setVersions([]);
        setError(result.error.message);
        setLoading(false);
        return;
      }

      setVersions(result.value);
      setLoading(false);
    }

    void load();
  }, [orgSlug, projectId]);

  return (
    <div className="space-y-6 max-w-5xl font-sans">
      <div>
        <h1 className="text-2xl font-bold text-white">Script Versions, Diffing & Lineage</h1>
        <p className="text-sm text-slate-400">
          Track committed script revisions. Diff and lineage projections appear when authoritative
          revision data is available.
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded border border-rose-900 bg-rose-950/50 p-3 text-xs text-rose-300">
          {error}
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-lg divide-y divide-slate-800 shadow-sm">
        <div className="px-4 py-3 border-b border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-400">
          Recorded Script Versions ({versions.length})
        </div>
        {loading ? (
          <div className="p-8 text-center text-xs text-slate-500">Loading script versions…</div>
        ) : versions.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">
            No committed script versions are available for this project.
          </div>
        ) : (
          versions.map((version, index) => (
            <div key={version.versionId} className="p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="text-sm font-bold text-white">
                    Version {version.versionNumber}
                  </span>
                  <span className="text-[10px] px-2 py-0.5 bg-slate-800 text-slate-400 rounded font-mono">
                    {version.revisionLabel}
                  </span>
                </div>
                <div className="text-xs text-slate-500 mt-1">
                  Created {new Date(version.createdAt).toLocaleString()}
                </div>
              </div>
              <span className="text-xs px-2.5 py-1 bg-amber-950/60 border border-amber-900 text-amber-400 font-bold rounded">
                {index === 0 ? "Active Revision" : "Archived Revision"}
              </span>
            </div>
          ))
        )}
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-xs text-slate-500">
        Script diff and item-lineage views are unavailable until persisted comparison data exists.
      </div>
    </div>
  );
}

export default VersionsRoute;
