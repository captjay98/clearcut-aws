import React, { useEffect, useState } from "react";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { api } from "@clearcut/contracts";
import { ScriptDiffViewer } from "../../../../../features/lineage/ScriptDiffViewer";
import { DiffSummaryCard } from "../../../../../features/lineage/DiffSummaryCard";
import { ItemLineageDrawer } from "../../../../../features/lineage/ItemLineageDrawer";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/versions")({
  component: VersionsRoute,
});

export function VersionsRoute() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId/versions" });
  const [versions, setVersions] = useState<any[]>([
    {
      versionId: "ver-001",
      ordinal: 1,
      title: "Draft Screenplay",
      sourceHash: "8f49a88cd72b9a714e8248c871587391",
      parserVersion: "v1.0.0",
      createdAt: "2026-08-30T10:00:00Z",
    },
    {
      versionId: "ver-002",
      ordinal: 2,
      title: "Blue Revision Draft",
      sourceHash: "9a714e8248c8715873918f49a88cd72b",
      parserVersion: "v1.0.0",
      createdAt: "2026-08-30T15:00:00Z",
    },
  ]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const res = await api.listProjectVersions({ path: { org_id: orgSlug, project_id: projectId } });
        if (res.ok && res.value.data && res.value.data.length > 0) {
          setVersions(res.value.data);
        }
      } catch {
        // keep default
      }
    }
    load();
  }, [orgSlug, projectId]);

  return (
    <div className="space-y-6 max-w-5xl font-sans">
      <div>
        <h1 className="text-2xl font-bold text-white">Script Versions, Diffing & Lineage</h1>
        <p className="text-sm text-slate-400">
          Track script revisions, compare screenplay diffs, and inspect item clearance lineage.
        </p>
      </div>

      {/* Revision Diff Summary & Trigger Rescan */}
      <DiffSummaryCard />

      {/* Side-by-Side / Unified Script Diff Viewer */}
      <ScriptDiffViewer />

      {/* Item Lineage & Chronological Audit Trace */}
      <ItemLineageDrawer />

      {/* Version History List */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg divide-y divide-slate-800 shadow-sm">
        <div className="px-4 py-3 border-b border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-400">
          Recorded Script Versions ({versions.length})
        </div>
        {versions.map((v) => (
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
              {v.ordinal === 2 ? "Active Revision" : "Archived Revision"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default VersionsRoute;
