import React, { useRef, useState } from "react";
import {
  createFileRoute,
  useNavigate,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { ScriptVersion } from "@clearcut/contracts";

import {
  jobQueryOptions,
  listProjectVersionsQueryOptions,
  scriptVersionDiffQueryOptions,
} from "../../../../../queries/scriptVersions";
import { startSelectiveRescanMutationOptions } from "../../../../../mutations/scriptVersionCommands";
import { ScriptUploadModal } from "../../../../../features/scripts/ScriptUploadModal";
import { VersionDiffViewer } from "../../../../../features/versions/VersionDiffViewer";
import { RescanProgress } from "../../../../../features/versions/RescanProgress";
import { SelectiveRescanDialog } from "../../../../../features/versions/SelectiveRescanDialog";

interface VersionsSearch {
  versionId?: string;
  rescanJobId?: string;
}

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/versions")({
  validateSearch: (search: Record<string, unknown>): VersionsSearch => ({
    versionId: typeof search.versionId === "string" ? search.versionId : undefined,
    rescanJobId:
      typeof search.rescanJobId === "string" ? search.rescanJobId : undefined,
  }),
  component: VersionsRoute,
});

export function VersionsRoute() {
  const { orgSlug, projectId } = useParams({
    from: "/o/$orgSlug/projects/$projectId/versions",
  });
  const { versionId, rescanJobId } = useSearch({
    from: "/o/$orgSlug/projects/$projectId/versions",
  });
  const navigate = useNavigate({ from: "/o/$orgSlug/projects/$projectId/versions" });
  const queryClient = useQueryClient();

  const [isUploadOpen, setUploadOpen] = useState(false);
  const [isConfirmOpen, setConfirmOpen] = useState(false);
  const uploadButtonRef = useRef<HTMLButtonElement>(null);

  const versionsQuery = useQuery(
    listProjectVersionsQueryOptions({ orgSlug, projectId }),
  );
  const versions = versionsQuery.data ?? [];

  // The selected version drives the persisted diff/impact view. Falls back to
  // the newest committed version so the page is never empty when data exists.
  const selectedVersionId = versionId ?? versions[0]?.versionId;

  const diffQuery = useQuery({
    ...scriptVersionDiffQueryOptions({
      orgSlug,
      projectId,
      versionId: selectedVersionId ?? "",
    }),
    enabled: Boolean(selectedVersionId),
  });

  // Reload-safe: the running rescan is reconstructed purely from getJob keyed by
  // the rescanJobId held in the URL. No localStorage, no client-side timer.
  const jobQuery = useQuery({
    ...jobQueryOptions({ orgSlug, projectId, jobId: rescanJobId ?? "" }),
    enabled: Boolean(rescanJobId),
  });

  const rescanMutation = useMutation(
    selectedVersionId
      ? startSelectiveRescanMutationOptions({
          orgSlug,
          projectId,
          versionId: selectedVersionId,
          queryClient,
        })
      : { mutationFn: async () => Promise.reject(new Error("No version selected.")) },
  );

  const handleRevisionCommitted = (version: ScriptVersion) => {
    void navigate({
      search: (prev) => ({ ...prev, versionId: version.versionId }),
    });
  };

  const handleConfirmRescan = () => {
    if (!selectedVersionId) return;
    rescanMutation.mutate(undefined, {
      onSuccess: (job) => {
        setConfirmOpen(false);
        void navigate({
          search: (prev) => ({
            ...prev,
            versionId: selectedVersionId,
            rescanJobId: job.jobId,
          }),
        });
      },
    });
  };

  const selectVersion = (id: string) => {
    void navigate({ search: (prev) => ({ ...prev, versionId: id }) });
  };

  const diff = diffQuery.data;

  return (
    <div className="space-y-6 max-w-5xl font-sans">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Script Versions, Diffing &amp; Lineage
          </h1>
          <p className="text-sm text-slate-400">
            Track committed script revisions. Each revision is compared to its
            predecessor and can trigger a selective, human-confirmed re-scan of
            only the clearance items its changes affect.
          </p>
        </div>
        <button
          ref={uploadButtonRef}
          type="button"
          onClick={() => setUploadOpen(true)}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded shadow shrink-0"
        >
          Import Revision
        </button>
      </div>

      {versionsQuery.isError && (
        <div
          role="alert"
          className="rounded border border-rose-900 bg-rose-950/50 p-3 text-xs text-rose-300"
        >
          {(versionsQuery.error as Error).message}
        </div>
      )}

      {/* Immutable version timeline */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg divide-y divide-slate-800 shadow-sm">
        <div className="px-4 py-3 border-b border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-400">
          Recorded Script Versions ({versions.length})
        </div>
        {versionsQuery.isLoading ? (
          <div className="p-8 text-center text-xs text-slate-500">
            Loading script versions…
          </div>
        ) : versions.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">
            No committed script versions are available for this project.
          </div>
        ) : (
          versions.map((version, index) => {
            const isSelected = version.versionId === selectedVersionId;
            return (
              <button
                key={version.versionId}
                type="button"
                onClick={() => selectVersion(version.versionId)}
                aria-current={isSelected ? "true" : undefined}
                className={`w-full text-left p-4 flex items-center justify-between ${
                  isSelected ? "bg-amber-950/30" : "hover:bg-slate-800/50"
                }`}
              >
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
                  {index === 0 ? "Latest Revision" : "Prior Revision"}
                </span>
              </button>
            );
          })
        )}
      </div>

      {/* Predecessor diff + impact summary for the selected version */}
      {selectedVersionId && (
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">
              Changes Against Predecessor
            </h2>
            {diff && diff.beforeVersionId && (
              <button
                type="button"
                onClick={() => setConfirmOpen(true)}
                disabled={diff.summary.affectedElementCount === 0}
                className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-bold text-xs rounded shadow"
              >
                Selective Re-scan…
              </button>
            )}
          </div>

          {diffQuery.isLoading ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-8 text-center text-xs text-slate-500">
              Loading persisted comparison…
            </div>
          ) : diffQuery.isError ? (
            <div
              role="alert"
              className="rounded border border-rose-900 bg-rose-950/50 p-3 text-xs text-rose-300"
            >
              {(diffQuery.error as Error).message}
            </div>
          ) : diff && !diff.beforeVersionId ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-xs text-slate-400">
              This is the project's first version, so it has no predecessor to
              compare against. Import a revision to generate a diff.
            </div>
          ) : diff ? (
            <>
              <VersionDiffViewer
                beforeLabel={diff.beforeLabel}
                afterLabel={diff.afterLabel}
                elements={diff.elements}
              />
              <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 text-xs text-slate-400">
                {diff.summary.affectedElementCount} affected item(s);{" "}
                {diff.summary.carriedForwardItemCount} item(s) and{" "}
                {diff.summary.carriedForwardEvidenceCount} evidence claim(s)
                carried forward by lineage. Predecessor decisions remain
                historical and require fresh human confirmation; carried-forward
                or absent evidence is never treated as cleared.
              </div>
            </>
          ) : null}
        </section>
      )}

      {/* Reload-safe rescan progress, reconstructed from the persisted job */}
      {rescanJobId && jobQuery.data && diff && (
        <section className="space-y-2">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">
            Re-scan Progress
          </h2>
          <RescanProgress job={jobQuery.data} summary={diff.summary} />
        </section>
      )}

      <ScriptUploadModal
        isOpen={isUploadOpen}
        onClose={() => setUploadOpen(false)}
        orgSlug={orgSlug}
        projectId={projectId}
        purpose="revision"
        returnFocusRef={uploadButtonRef}
        successFocusRef={uploadButtonRef}
        onSuccess={handleRevisionCommitted}
      />

      {diff && (
        <SelectiveRescanDialog
          isOpen={isConfirmOpen}
          summary={diff.summary}
          isStarting={rescanMutation.isPending}
          onConfirm={handleConfirmRescan}
          onClose={() => setConfirmOpen(false)}
        />
      )}
    </div>
  );
}

export default VersionsRoute;
