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
      queryClient.setQueryData(
        ["new-clearance-project", orgSlug, project.projectId],
        project,
      );
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
    await updateSearch(
      { projectId: version.projectId, versionId: version.versionId },
      true,
    );
  };

  const project = projectQuery.data;
  const projectUnavailable = Boolean(search.projectId && projectQuery.isError);
  const versionUnavailable = Boolean(search.projectId && versionsQuery.isError);

  return (
    <div className="mx-auto max-w-3xl space-y-5 py-8">
      <header>
        <h1 className="text-2xl font-bold text-white">New Clearance</h1>
        <p className="mt-1 text-sm text-slate-400">
          Build a persisted pre-clearance evidence workspace. ClearCut supports qualified human review; it does not provide legal advice or a clearance decision.
        </p>
      </header>

      <ol aria-label="New clearance steps" className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {["Describe production", "Bring in script", "Check script"].map((label, index) => {
          const completed =
            index === 0
              ? Boolean(project)
              : index === 1
                ? Boolean(persistedVersion)
                : Boolean(
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
            <li key={label} className="rounded border border-slate-800 bg-slate-900 p-3 text-xs text-slate-300">
              <span className="mr-2 font-mono text-amber-400">{completed ? "✓" : index + 1}</span>
              {label}
            </li>
          );
        })}
      </ol>

      <section className="rounded-lg border border-slate-800 bg-slate-900 p-6 shadow">
        <h2 className="text-lg font-bold text-white">Describe production</h2>
        {search.projectId && projectQuery.isPending ? (
          <p role="status" className="mt-3 text-xs text-slate-400">Loading persisted production details…</p>
        ) : projectUnavailable ? (
          <div role="alert" className="mt-3 rounded border border-rose-900 bg-rose-950/40 p-3">
            <h3 className="font-bold text-rose-200">Production unavailable</h3>
            <p className="mt-1 text-xs text-rose-300">{projectQuery.error?.message}</p>
          </div>
        ) : project ? (
          <div className="mt-3 rounded border border-emerald-900 bg-emerald-950/20 p-4">
            <p className="font-bold text-emerald-200">{project.title}</p>
            {project.description && <p className="mt-1 text-xs text-slate-300">{project.description}</p>}
            <dl className="mt-3 grid grid-cols-1 gap-2 text-xs text-slate-300 sm:grid-cols-2">
              <div><dt className="text-slate-500">Production type</dt><dd>{project.productionType ?? "Not provided"}</dd></div>
              <div><dt className="text-slate-500">Production stage</dt><dd>{project.productionStage ?? "Not provided"}</dd></div>
              <div><dt className="text-slate-500">Jurisdiction</dt><dd>{project.jurisdiction ?? "Not provided"}</dd></div>
              <div>
                <dt className="text-slate-500">Target lock date</dt>
                <dd>{project.targetLockDate ? new Date(`${project.targetLockDate}T00:00:00`).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" }) : "Not provided"}</dd>
              </div>
            </dl>
            {project.reviewBrief && <p className="mt-3 text-xs text-slate-300">{project.reviewBrief}</p>}
            <p className="mt-2 text-[11px] text-slate-500">Saved project: {project.projectId}</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            {createMutation.isError && (
              <div role="alert" className="rounded border border-rose-900 bg-rose-950/50 p-3 text-xs text-rose-300">
                {createMutation.error.message}
              </div>
            )}
            <div>
              <label htmlFor="title" className="block text-xs font-medium text-slate-300">
                Project / Screenplay Title
              </label>
              <input
                id="title"
                type="text"
                required
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="e.g. Signal Check"
              />
            </div>
            <div>
              <label htmlFor="description" className="block text-xs font-medium text-slate-300">
                Description / Production Notes (Optional)
              </label>
              <textarea
                id="description"
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-amber-500"
                placeholder="Feature screenplay draft for pre-production evidence review."
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="production-type" className="block text-xs font-medium text-slate-300">Production Type</label>
                <select
                  id="production-type"
                  value={productionType}
                  onChange={(event) => setProductionType(event.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white"
                >
                  <option value="">Select type</option>
                  <option value="Feature film">Feature film</option>
                  <option value="Short film">Short film</option>
                  <option value="Television">Television</option>
                  <option value="Digital series">Digital series</option>
                </select>
              </div>
              <div>
                <label htmlFor="production-stage" className="block text-xs font-medium text-slate-300">Production Stage</label>
                <select
                  id="production-stage"
                  value={productionStage}
                  onChange={(event) => setProductionStage(event.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white"
                >
                  <option value="">Select stage</option>
                  <option value="Development">Development</option>
                  <option value="Pre-production">Pre-production</option>
                  <option value="Production">Production</option>
                  <option value="Post-production">Post-production</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="jurisdiction" className="block text-xs font-medium text-slate-300">Jurisdiction</label>
                <input
                  id="jurisdiction"
                  type="text"
                  value={jurisdiction}
                  onChange={(event) => setJurisdiction(event.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white"
                />
              </div>
              <div>
                <label htmlFor="target-lock-date" className="block text-xs font-medium text-slate-300">Target Lock Date</label>
                <input
                  id="target-lock-date"
                  type="date"
                  value={targetLockDate}
                  onChange={(event) => setTargetLockDate(event.target.value)}
                  className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white"
                />
              </div>
            </div>
            <div>
              <label htmlFor="review-brief" className="block text-xs font-medium text-slate-300">Review Brief</label>
              <textarea
                id="review-brief"
                rows={3}
                value={reviewBrief}
                onChange={(event) => setReviewBrief(event.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white"
                placeholder="Describe the evidence review priorities and unresolved concerns."
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => navigate({ to: "/o/$orgSlug/projects", params: { orgSlug } })}
                className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending || !title.trim()}
                className="rounded-md bg-amber-600 px-4 py-2 text-xs font-bold text-white shadow hover:bg-amber-700 disabled:opacity-50"
              >
                {createMutation.isPending ? "Saving…" : "Save and bring in script"}
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900 p-6 shadow">
        <h2 className="text-lg font-bold text-white">Bring in script</h2>
        {!search.projectId ? (
          <p className="mt-2 text-xs text-slate-500">Save the production details before importing a screenplay.</p>
        ) : versionUnavailable ? (
          <div role="alert" className="mt-3 rounded border border-rose-900 bg-rose-950/40 p-3 text-xs text-rose-300">
            Script versions are unavailable. {versionsQuery.error?.message}
          </div>
        ) : versionsQuery.isPending ? (
          <p role="status" className="mt-2 text-xs text-slate-400">Loading persisted script versions…</p>
        ) : persistedVersion ? (
          <div className="mt-3 space-y-3">
            <p className="text-sm font-bold text-emerald-200">
              Version {persistedVersion.versionNumber} is ready for a check.
            </p>
            <dl className="grid grid-cols-2 gap-3">
              <div className="rounded border border-slate-800 bg-slate-950/50 p-3">
                <dt className="text-[11px] text-slate-400">Persisted scenes</dt>
                <dd data-testid="version-scene-count" className="text-lg font-bold text-white">{persistedVersion.sceneCount}</dd>
              </div>
              <div className="rounded border border-slate-800 bg-slate-950/50 p-3">
                <dt className="text-[11px] text-slate-400">Persisted elements</dt>
                <dd data-testid="version-element-count" className="text-lg font-bold text-white">{persistedVersion.elementCount}</dd>
              </div>
            </dl>
          </div>
        ) : (
          <div className="mt-3">
            <p className="mb-3 text-xs text-slate-400">Upload a file or paste screenplay text. Parser counts will come from the persisted version.</p>
            <button
              ref={uploadTriggerRef}
              type="button"
              onClick={() => setIsUploadOpen(true)}
              className="rounded bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700"
            >
              Bring in script
            </button>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900 p-6 shadow">
        <h2
          ref={checkScriptHeadingRef}
          tabIndex={-1}
          className="text-lg font-bold text-white"
        >
          Check script
        </h2>
        {!persistedVersion ? (
          <p className="mt-2 text-xs text-slate-500">Commit a script version before starting the check.</p>
        ) : search.jobId && search.projectId ? (
          <div className="mt-4">
            <JobProgress
              orgSlug={orgSlug}
              projectId={search.projectId}
              jobId={search.jobId}
              expectedVersionId={persistedVersion.versionId}
              onJobChange={setObservedJob}
            />
          </div>
        ) : (
          <div className="mt-3">
            <p className="text-xs text-slate-400">
              Start an observable check for persisted version {persistedVersion.versionNumber}. Progress and terminal counts are read from the operation record.
            </p>
            {detectionMutation.isError && (
              <div role="alert" className="mt-3 rounded border border-rose-900 bg-rose-950/40 p-3">
                <h3 className="font-bold text-rose-200">Check unavailable</h3>
                <p className="mt-1 text-xs text-rose-300">{detectionMutation.error.message}</p>
              </div>
            )}
            <button
              type="button"
              onClick={() => detectionMutation.mutate(persistedVersion)}
              disabled={detectionMutation.isPending}
              className="mt-4 rounded bg-amber-600 px-4 py-2 text-xs font-bold text-white hover:bg-amber-700 disabled:opacity-50"
            >
              {detectionMutation.isPending ? "Starting check…" : "Check script"}
            </button>
          </div>
        )}
      </section>

      {search.projectId && (
        <ScriptUploadModal
          isOpen={isUploadOpen}
          onClose={() => setIsUploadOpen(false)}
          orgSlug={orgSlug}
          projectId={search.projectId}
          returnFocusRef={uploadTriggerRef}
          successFocusRef={checkScriptHeadingRef}
          onSuccess={handleVersionCommitted}
        />
      )}
    </div>
  );
}

export default NewProjectRoute;
