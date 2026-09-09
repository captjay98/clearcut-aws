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
import { Badge, Banner, EmptyState, Page, Section } from "../../../../../components/ds";

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
    <Page
      trail={[
        { label: "Projects", to: "/o/$orgSlug/projects", params: { orgSlug } },
        { label: "Versions" },
      ]}
      eyebrow="Saved snapshots"
      title="Script Versions, Diffing & Lineage"
      lede="Track committed script revisions. Each revision is compared to its predecessor and can trigger a selective, human-confirmed re-scan of only the clearance items its changes affect."
      actions={
        <button
          ref={uploadButtonRef}
          className="button button-primary"
          type="button"
          onClick={() => setUploadOpen(true)}
        >
          Import Revision
        </button>
      }
      notice={
        versionsQuery.isError && (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Script versions unavailable"
            message={(versionsQuery.error as Error).message}
            role="alert"
          />
        )
      }
    >
      {/* Immutable version timeline. A revision never edits an earlier version,
          so this list only ever grows. */}
      <Section
        title={`Recorded Script Versions (${versions.length})`}
        description="Revised script pages are printed on coloured stock in production — white first, then blue, pink, yellow — so the label doubles as the crew's at-a-glance marker."
      >
        {versionsQuery.isLoading ? (
          <p role="status" className="small muted">
            Loading script versions…
          </p>
        ) : versions.length === 0 ? (
          <EmptyState
            icon="⑂"
            title="No versions yet"
            description="No committed script versions are available for this project. Import a revision to create the first saved snapshot."
          />
        ) : (
          <div className="list">
            {versions.map((version, index) => {
              const isSelected = version.versionId === selectedVersionId;
              return (
                <div className="list-row is-static" key={version.versionId}>
                  <div className="list-main">
                    <button
                      className="list-main-button"
                      type="button"
                      onClick={() => selectVersion(version.versionId)}
                      aria-pressed={isSelected}
                      aria-current={isSelected ? "true" : undefined}
                    >
                      <span className="list-title">Version {version.versionNumber}</span>
                      <span className="list-meta">
                        <span className="mono">{version.revisionLabel}</span>
                        <span>Created {new Date(version.createdAt).toLocaleString()}</span>
                        <span>
                          {version.sceneCount} scenes · {version.elementCount} elements
                        </span>
                      </span>
                    </button>
                  </div>
                  <div className="list-aside">
                    {index === 0 ? (
                      <Badge tone="is-success">Latest Revision</Badge>
                    ) : (
                      <Badge>Prior Revision</Badge>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Section>

      {/* Predecessor diff + impact summary for the selected version */}
      {selectedVersionId && (
        <Section
          title="Changes Against Predecessor"
          actions={
            diff &&
            diff.beforeVersionId && (
              <button
                className="button button-primary button-sm"
                type="button"
                onClick={() => setConfirmOpen(true)}
                disabled={diff.summary.affectedElementCount === 0}
              >
                Selective Re-scan…
              </button>
            )
          }
        >
          {diffQuery.isLoading ? (
            <p role="status" className="small muted">
              Loading persisted comparison…
            </p>
          ) : diffQuery.isError ? (
            <Banner
              tone="is-danger"
              icon="⚠"
              title="Comparison unavailable"
              message={(diffQuery.error as Error).message}
              role="alert"
            />
          ) : diff && !diff.beforeVersionId ? (
            <Banner
              icon="○"
              title="No predecessor to compare"
              message="This is the project's first version, so it has no predecessor to compare against. Import a revision to generate a diff."
            />
          ) : diff ? (
            <div className="stack">
              <VersionDiffViewer
                beforeLabel={diff.beforeLabel}
                afterLabel={diff.afterLabel}
                elements={diff.elements}
              />
              <Banner
                icon="⑂"
                title="Lineage carry-forward"
                message={
                  <>
                    {diff.summary.affectedElementCount} affected item(s);{" "}
                    {diff.summary.carriedForwardItemCount} item(s) and{" "}
                    {diff.summary.carriedForwardEvidenceCount} evidence claim(s) carried forward by
                    lineage. Predecessor decisions remain historical and require fresh human
                    confirmation; carried-forward or absent evidence is never treated as cleared.
                  </>
                }
              />
            </div>
          ) : null}
        </Section>
      )}

      {/* Reload-safe rescan progress, reconstructed from the persisted job */}
      {rescanJobId && jobQuery.data && diff && (
        <Section title="Re-scan Progress">
          <RescanProgress job={jobQuery.data} summary={diff.summary} />
        </Section>
      )}

      <ScriptUploadModal
        isOpen={isUploadOpen}
        onClose={() => setUploadOpen(false)}
        orgSlug={orgSlug}
        projectId={projectId}
        purpose="revision"
        returnFocusRef={uploadButtonRef}
        successFocusRef={uploadButtonRef}
        nextVersionNumber={versions.length + 1}
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
    </Page>
  );
}

export default VersionsRoute;
