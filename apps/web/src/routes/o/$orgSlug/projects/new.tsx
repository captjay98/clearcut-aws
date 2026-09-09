import React, { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type ApiError,
  type Job,
  type Project,
  type ScriptVersion,
} from "@clearcut/contracts";
import { ScriptUploadModal } from "../../../../features/scripts/ScriptUploadModal";
import { JobProgress } from "../../../../features/operations/JobProgress";
import { Badge, Banner, Card, Page } from "../../../../components/ds";

interface NewClearanceSearch {
  projectId?: string;
  versionId?: string;
  jobId?: string;
}

function optionalSearchId(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function toQueryError(error: ApiError): Error & ApiError {
  return Object.assign(new Error(error.message), error);
}

function formatLockDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

/**
 * The mock's wizard heads each step with a numbered marker that becomes a tick
 * once the step is persisted, and announces position for screen readers because
 * the marker itself is decorative.
 */
function StepHead({
  number,
  title,
  done,
  current,
  headingRef,
}: {
  number: number;
  title: string;
  done: boolean;
  current: boolean;
  headingRef?: React.Ref<HTMLHeadingElement>;
}) {
  return (
    <div className="cluster step-head" {...(current ? { "aria-current": "step" as const } : {})}>
      <span
        className={`step-num ${done ? "is-done" : current ? "is-current" : ""}`.trim()}
        aria-hidden="true"
      >
        {done ? "✓" : number}
      </span>
      <h2 className="step-title" ref={headingRef} tabIndex={headingRef ? -1 : undefined}>
        {title}
        <span className="sr-only">
          {` — step ${number} of 3${done ? ", done" : current ? ", current step" : ""}`}
        </span>
      </h2>
      {done && <Badge tone="is-success">Done</Badge>}
    </div>
  );
}

export const Route = createFileRoute("/o/$orgSlug/projects/new")({
  validateSearch: (search: Record<string, unknown>): NewClearanceSearch => ({
    projectId: optionalSearchId(search.projectId),
    versionId: optionalSearchId(search.versionId),
    jobId: optionalSearchId(search.jobId),
  }),
  component: NewProjectRoute,
});

export function NewProjectRoute() {
  const { orgSlug } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [productionType, setProductionType] = useState("");
  const [productionStage, setProductionStage] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [targetLockDate, setTargetLockDate] = useState("");
  const [reviewBrief, setReviewBrief] = useState("");
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const uploadTriggerRef = React.useRef<HTMLButtonElement>(null);
  const checkScriptHeadingRef = React.useRef<HTMLHeadingElement>(null);
  const [observedJob, setObservedJob] = useState<Job | null>(null);

  const projectQuery = useQuery({
    queryKey: ["new-clearance-project", orgSlug, search.projectId],
    enabled: Boolean(search.projectId),
    queryFn: async () => {
      const result = await api.getProject({
        params: { orgId: orgSlug, projectId: search.projectId! },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
  });

  const versionsQuery = useQuery({
    queryKey: ["new-clearance-versions", orgSlug, search.projectId],
    enabled: Boolean(search.projectId),
    queryFn: async () => {
      const result = await api.listProjectVersions({
        params: { orgId: orgSlug, projectId: search.projectId! },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
  });

  const persistedVersion = React.useMemo(() => {
    const versions = versionsQuery.data ?? [];
    if (search.versionId) {
      return versions.find((version) => version.versionId === search.versionId) ?? null;
    }
    return [...versions].sort((left, right) => right.versionNumber - left.versionNumber)[0] ?? null;
  }, [search.versionId, versionsQuery.data]);

  const updateSearch = (next: NewClearanceSearch, replace = false) =>
    navigate({
      to: "/o/$orgSlug/projects/new",
      params: { orgSlug },
      search: next,
      replace,
    });

  const createMutation = useMutation({
    mutationFn: async () => {
      const result = await api.createProject({
        params: { orgId: orgSlug },
        body: {
          title: title.trim(),
          description: description.trim() || null,
          productionType: productionType || null,
          productionStage: productionStage || null,
          jurisdiction: jurisdiction.trim() || null,
          targetLockDate: targetLockDate || null,
          reviewBrief: reviewBrief.trim() || null,
        },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
    onSuccess: (project: Project) => {
      queryClient.setQueryData(["new-clearance-project", orgSlug, project.projectId], project);
      void updateSearch({ projectId: project.projectId }, true);
    },
  });

  const detectionMutation = useMutation({
    mutationFn: async (version: ScriptVersion) => {
      const result = await api.startDetection({
        params: {
          orgId: orgSlug,
          projectId: version.projectId,
          versionId: version.versionId,
        },
      });
      if (!result.ok) throw toQueryError(result.error);
      return result.value;
    },
    onSuccess: (job) => {
      void updateSearch(
        {
          projectId: search.projectId,
          versionId: persistedVersion?.versionId,
          jobId: job.jobId,
        },
        true,
      );
    },
  });

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    createMutation.mutate();
  };

  const handleVersionCommitted = async (version: ScriptVersion) => {
    queryClient.setQueryData<ScriptVersion[]>(
      ["new-clearance-versions", orgSlug, version.projectId],
      (current = []) => [
        ...current.filter((candidate) => candidate.versionId !== version.versionId),
        version,
      ],
    );
    await updateSearch({ projectId: version.projectId, versionId: version.versionId }, true);
  };

  const project = projectQuery.data;
  const projectUnavailable = Boolean(search.projectId && projectQuery.isError);
  const versionUnavailable = Boolean(search.projectId && versionsQuery.isError);

  const detailsDone = Boolean(project);
  const importDone = Boolean(persistedVersion);
  const checkDone = Boolean(
    observedJob &&
      search.jobId &&
      observedJob.jobId === search.jobId &&
      observedJob.status === "succeeded" &&
      observedJob.jobType === "detection" &&
      observedJob.target.type === "script_version" &&
      observedJob.target.id === persistedVersion?.versionId &&
      observedJob.resultSummary?.scriptVersionId === persistedVersion?.versionId,
  );

  return (
    <Page
      width="narrow"
      trail={[
        { label: "Projects", to: "/o/$orgSlug/projects", params: { orgSlug } },
        { label: "New clearance" },
      ]}
      eyebrow="Start here"
      title="New Clearance"
      lede="Three steps: describe the production, bring in the script, and let ClearCut check it. You make every call after that. ClearCut supports qualified human review; it does not provide legal advice or a clearance decision."
    >
      {/* The three steps are an ordered list: they are a sequence, and each one's
          marker reports whether it is persisted yet. */}
      <ol aria-label="New clearance steps" style={{ listStyle: "none", padding: 0 }}>
      <li className="section">
        <StepHead number={1} title="Describe production" done={detailsDone} current={!detailsDone} />

        {search.projectId && projectQuery.isPending ? (
          <Card>
            <p role="status" className="small muted">
              Loading persisted production details…
            </p>
          </Card>
        ) : projectUnavailable ? (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Production unavailable"
            message={projectQuery.error?.message}
            role="alert"
            titleIsHeading
          />
        ) : project ? (
          <Card>
            <div className="stack">
              <div>
                <strong>{project.title}</strong>
                {project.description && <p className="small gap-t-2">{project.description}</p>}
              </div>
              <dl className="report-meta">
                <div>
                  <dt>Production type</dt>
                  <dd>{project.productionType ?? "Not provided"}</dd>
                </div>
                <div>
                  <dt>Production stage</dt>
                  <dd>{project.productionStage ?? "Not provided"}</dd>
                </div>
                <div>
                  <dt>Jurisdiction</dt>
                  <dd>{project.jurisdiction ?? "Not provided"}</dd>
                </div>
                <div>
                  <dt>Target lock date</dt>
                  <dd>
                    {project.targetLockDate ? formatLockDate(project.targetLockDate) : "Not provided"}
                  </dd>
                </div>
              </dl>
              {project.reviewBrief && <p className="small">{project.reviewBrief}</p>}
              <p className="small muted">
                Saved project: <span className="mono">{project.projectId}</span>
              </p>
            </div>
          </Card>
        ) : (
          <form onSubmit={handleSubmit}>
            {createMutation.isError && (
              <Banner
                tone="is-danger"
                icon="⚠"
                title="Could not save the production"
                message={createMutation.error.message}
                role="alert"
                className="gap-b-4"
              />
            )}
            <Card>
              <div className="form-grid">
                <label className="field field-full" htmlFor="title">
                  <span className="field-label">Project / Screenplay Title</span>
                  <input
                    id="title"
                    type="text"
                    required
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="e.g. Signal Check"
                  />
                </label>

                <label className="field field-full" htmlFor="description">
                  <span className="field-label">Description / Production Notes (Optional)</span>
                  <textarea
                    id="description"
                    rows={3}
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="Feature screenplay draft for pre-production evidence review."
                  />
                </label>

                <label className="field" htmlFor="production-type">
                  <span className="field-label">Production Type</span>
                  <select
                    id="production-type"
                    value={productionType}
                    onChange={(event) => setProductionType(event.target.value)}
                  >
                    <option value="">Select type</option>
                    <option value="Feature film">Feature film</option>
                    <option value="Short film">Short film</option>
                    <option value="Television">Television</option>
                    <option value="Digital series">Digital series</option>
                  </select>
                </label>

                <label className="field" htmlFor="production-stage">
                  <span className="field-label">Production Stage</span>
                  <select
                    id="production-stage"
                    value={productionStage}
                    onChange={(event) => setProductionStage(event.target.value)}
                  >
                    <option value="">Select stage</option>
                    <option value="Development">Development</option>
                    <option value="Pre-production">Pre-production</option>
                    <option value="Production">Production</option>
                    <option value="Post-production">Post-production</option>
                  </select>
                </label>

                <label className="field" htmlFor="jurisdiction">
                  <span className="field-label">Jurisdiction</span>
                  <input
                    id="jurisdiction"
                    type="text"
                    value={jurisdiction}
                    onChange={(event) => setJurisdiction(event.target.value)}
                  />
                </label>

                <label className="field" htmlFor="target-lock-date">
                  <span className="field-label">Target Lock Date</span>
                  <input
                    id="target-lock-date"
                    type="date"
                    value={targetLockDate}
                    onChange={(event) => setTargetLockDate(event.target.value)}
                  />
                </label>

                <label className="field field-full" htmlFor="review-brief">
                  <span className="field-label">Review Brief</span>
                  <textarea
                    id="review-brief"
                    rows={3}
                    value={reviewBrief}
                    onChange={(event) => setReviewBrief(event.target.value)}
                    placeholder="Describe the evidence review priorities and unresolved concerns."
                  />
                </label>
              </div>

              <div className="cluster gap-t-5" style={{ justifyContent: "flex-end" }}>
                <button
                  className="button button-quiet"
                  type="button"
                  onClick={() => navigate({ to: "/o/$orgSlug/projects", params: { orgSlug } })}
                >
                  Cancel
                </button>
                <button
                  className="button button-primary"
                  type="submit"
                  disabled={createMutation.isPending || !title.trim()}
                >
                  {createMutation.isPending ? "Saving…" : "Save and bring in script"}
                </button>
              </div>
            </Card>
          </form>
        )}
      </li>

      <li className="section">
        <StepHead
          number={2}
          title="Bring in script"
          done={importDone}
          current={detailsDone && !importDone}
        />

        {!search.projectId ? (
          <Card quiet>
            <p className="small muted">
              Save the production details before importing a screenplay.
            </p>
          </Card>
        ) : versionUnavailable ? (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Script versions unavailable"
            message={versionsQuery.error?.message}
            role="alert"
          />
        ) : versionsQuery.isPending ? (
          <Card>
            <p role="status" className="small muted">
              Loading persisted script versions…
            </p>
          </Card>
        ) : persistedVersion ? (
          <Card>
            <div className="stack">
              <p className="small">
                Version {persistedVersion.versionNumber} is ready for a check.
              </p>
              <div className="grid grid-2">
                <div className="stat">
                  <span className="stat-label">Persisted scenes</span>
                  <span className="stat-value" data-testid="version-scene-count">
                    {persistedVersion.sceneCount}
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">Persisted elements</span>
                  <span className="stat-value" data-testid="version-element-count">
                    {persistedVersion.elementCount}
                  </span>
                </div>
              </div>
            </div>
          </Card>
        ) : (
          <Card>
            <div className="stack">
              <p className="small muted">
                Upload a Fountain or Final Draft file, or paste screenplay text. Parser counts come
                from the persisted version.
              </p>
              <div className="cluster">
                <button
                  ref={uploadTriggerRef}
                  className="button button-primary"
                  type="button"
                  onClick={() => setIsUploadOpen(true)}
                >
                  Bring in script
                </button>
              </div>
            </div>
          </Card>
        )}
      </li>

      <li className="section">
        <StepHead
          number={3}
          title="Check script"
          done={checkDone}
          current={importDone && !checkDone}
          headingRef={checkScriptHeadingRef}
        />

        {!persistedVersion ? (
          <Card quiet>
            <p className="small muted">Commit a script version before starting the check.</p>
          </Card>
        ) : search.jobId && search.projectId ? (
          <JobProgress
            orgSlug={orgSlug}
            projectId={search.projectId}
            jobId={search.jobId}
            expectedVersionId={persistedVersion.versionId}
            onJobChange={setObservedJob}
          />
        ) : (
          <Card>
            <div className="stack">
              <p className="small muted">
                Start an observable check for persisted version {persistedVersion.versionNumber}.
                Progress and terminal counts are read from the operation record.
              </p>
              {detectionMutation.isError && (
                <Banner
                  tone="is-danger"
                  icon="⚠"
                  title="Check unavailable"
                  message={detectionMutation.error.message}
                  role="alert"
                  titleIsHeading
                />
              )}
              <div className="cluster">
                <button
                  className="button button-primary"
                  type="button"
                  onClick={() => detectionMutation.mutate(persistedVersion)}
                  disabled={detectionMutation.isPending}
                >
                  {detectionMutation.isPending ? "Starting check…" : "Check script"}
                </button>
              </div>
            </div>
          </Card>
        )}
      </li>
      </ol>

      {search.projectId && (
        <ScriptUploadModal
          isOpen={isUploadOpen}
          onClose={() => setIsUploadOpen(false)}
          orgSlug={orgSlug}
          projectId={search.projectId}
          returnFocusRef={uploadTriggerRef}
          successFocusRef={checkScriptHeadingRef}
          nextVersionNumber={(versionsQuery.data?.length ?? 0) + 1}
          onSuccess={handleVersionCommitted}
        />
      )}
    </Page>
  );
}

export default NewProjectRoute;
