import React from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Banner, EmptyState, Page, Section } from "../../../components/ds";
import {
  organizationProjectsQueryOptions,
  resolveProjectScope,
} from "../../../queries/organizationProjects";
import { sessionContextQueryOptions } from "../../../queries/session";
import {
  latestEvaluation,
  learningCandidatesQueryOptions,
  trustEvaluationsQueryOptions,
} from "../../../queries/trust";
import {
  promoteLearningCandidateMutationOptions,
  rollbackLearningCandidateMutationOptions,
} from "../../../mutations/learningCommands";
import { GateChecklist } from "../../../features/trust/GateChecklist";
import { LearningCandidateCard } from "../../../features/trust/LearningCandidateCard";
import { ProvenanceCard } from "../../../features/trust/ProvenanceCard";
import { RubricTable } from "../../../features/trust/RubricTable";
import { TrustScoreCard } from "../../../features/trust/TrustScoreCard";
import { ProtectedRulesBanner } from "../../../features/governance/ProtectedRulesBanner";
import { canManageGovernance } from "../../../features/governance/capabilities";

interface TrustSearch {
  projectId?: string;
}

export const Route = createFileRoute("/o/$orgSlug/trust")({
  validateSearch: (search: Record<string, unknown>): TrustSearch => ({
    projectId:
      typeof search.projectId === "string" && search.projectId.length > 0
        ? search.projectId
        : undefined,
  }),
  component: TrustRoute,
});

function errorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : String(error);
}

export function TrustRoute() {
  const { orgSlug } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: "/o/$orgSlug/trust" });
  const queryClient = useQueryClient();

  const sessionQuery = useQuery(sessionContextQueryOptions());
  const canGovern = canManageGovernance(sessionQuery.data?.role ?? null);

  // Trust reads are project-scoped but this route is organization-scoped, so the
  // project is resolved from the projects the caller can actually see. Nothing is
  // fabricated, and a resolved project is always named on screen.
  const projectsQuery = useQuery(organizationProjectsQueryOptions(orgSlug));
  const projects = projectsQuery.data ?? [];
  const scope = resolveProjectScope(projects, search.projectId);
  const resolvedProject = projects.find(
    (project) => project.projectId === scope.projectId,
  );

  const evaluationsQuery = useQuery({
    ...trustEvaluationsQueryOptions({
      orgId: orgSlug,
      projectId: scope.projectId ?? "",
    }),
    enabled: Boolean(scope.projectId),
  });

  const candidatesQuery = useQuery(learningCandidatesQueryOptions(orgSlug));

  const promoteMutation = useMutation(
    promoteLearningCandidateMutationOptions(orgSlug, queryClient),
  );
  const rollbackMutation = useMutation(
    rollbackLearningCandidateMutationOptions(orgSlug, queryClient),
  );

  const evaluation = latestEvaluation(evaluationsQuery.data ?? []);
  const candidates = candidatesQuery.data ?? [];
  const stageError =
    errorMessage(promoteMutation.error) ?? errorMessage(rollbackMutation.error);
  const stagePendingId =
    (promoteMutation.isPending || rollbackMutation.isPending
      ? (promoteMutation.variables ?? rollbackMutation.variables)
      : undefined) ?? null;

  const loadError =
    errorMessage(projectsQuery.error) ?? errorMessage(evaluationsQuery.error);

  return (
    <Page
      trail={[{ label: "AI trust" }]}
      eyebrow="How ClearCut stays careful"
      title="Trust Center & Evaluation Rubric"
      lede="ClearCut checks its own work. Every pass is graded by a separate reviewer against a fixed rubric, and improvements are tried on a small slice before they are adopted — and can be reverted."
      notice={
        loadError && (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Could not read the evaluation record"
            message={`${loadError} No score or gate outcome has been inferred in the meantime.`}
            role="alert"
          />
        )
      }
    >
      {/* ── Project scope ──────────────────────────────────────────────── */}
      <Section
        title="Which project this reads"
        description="An evaluation belongs to the run that produced it, and a run belongs to a project. This surface is organization-scoped, so the project is named rather than assumed."
      >
        {projectsQuery.isPending ? (
          <p role="status" className="small muted">
            Resolving which projects you can see…
          </p>
        ) : projects.length === 0 ? (
          <EmptyState
            icon="▤"
            title="No project to evaluate yet"
            description="Trust evaluations are recorded per project. Create a project and import a script, and its graded runs will appear here."
          />
        ) : (
          <div className="stack">
            {scope.requestedButNotVisible && (
              <Banner
                tone="is-warning"
                icon="⚠"
                title="That project is not one you can see"
                message="The project id in the address is not among the projects available to you, so nothing has been read for it. Choose one below."
                role="status"
              />
            )}

            {projects.length === 1 && scope.projectId ? (
              <p className="small muted" data-testid="trust-project-scope">
                Reading <strong>{resolvedProject?.title}</strong> — the only project
                you can see in this organization.
              </p>
            ) : (
              <div className="field" data-testid="trust-project-scope">
                <label className="field-label" htmlFor="trust-project">
                  Project to read
                </label>
                <select
                  id="trust-project"
                  value={scope.projectId ?? ""}
                  onChange={(event) => {
                    const next = event.target.value;
                    void navigate({
                      search: next ? { projectId: next } : {},
                    });
                  }}
                >
                  <option value="">Choose a project…</option>
                  {projects.map((project) => (
                    <option key={project.projectId} value={project.projectId}>
                      {project.title}
                    </option>
                  ))}
                </select>
                <p className="field-hint">
                  {scope.projectId
                    ? `Reading ${resolvedProject?.title ?? "the selected project"}.`
                    : "More than one project is visible, so none has been picked for you."}
                </p>
              </div>
            )}
          </div>
        )}
      </Section>

      {/* ── The graded run ─────────────────────────────────────────────── */}
      {scope.projectId && (
        <>
          {evaluationsQuery.isPending ? (
            <p role="status" className="small muted">
              Loading the evaluation record…
            </p>
          ) : evaluationsQuery.isError ? null : evaluation === null ? (
            <Section title="What the judge grades">
              <EmptyState
                icon="○"
                title="No run has been graded yet"
                description={`No deterministic or judge evaluation has been persisted for ${resolvedProject?.title ?? "this project"} yet, so there is no score, no rubric row and no version binding to show. None is inferred in the meantime.`}
              />
            </Section>
          ) : (
            <>
              <div className="grid grid-3">
                <TrustScoreCard evaluation={evaluation} />
                <GateChecklist gates={evaluation.gates} />
                <ProvenanceCard provenance={evaluation.provenance} />
              </div>

              <Section
                title="What the judge grades"
                description="Scored by a separate model on a separate prompt. The headline above is the mean of the dimensions that carry a score, derived once on the server, so it cannot disagree with this table."
              >
                <RubricTable dimensions={evaluation.dimensions} />
              </Section>
            </>
          )}
        </>
      )}

      {/* ── Learning lifecycle ─────────────────────────────────────────── */}
      <Section
        title="Improvements waiting on a decision"
        description="A learning candidate is checked against every past case and tried on a small slice of real searches before it is adopted, and can be reverted afterwards."
      >
        {candidatesQuery.isPending ? (
          <p role="status" className="small muted">
            Loading learning candidates…
          </p>
        ) : candidatesQuery.isError ? (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Could not read the learning candidates"
            message={`${errorMessage(candidatesQuery.error)} No lifecycle stage has been inferred.`}
            role="alert"
          />
        ) : candidates.length === 0 ? (
          <EmptyState
            icon="◦"
            title="No learning candidate raised yet"
            description="Nothing is proposed for this organization. When a candidate is raised, its stage and its regression evidence appear here before anything is adopted."
          />
        ) : (
          <div className="stack">
            {candidates.map((candidate) => (
              <LearningCandidateCard
                key={candidate.candidateId}
                candidate={candidate}
                canGovern={canGovern}
                pending={stagePendingId === candidate.candidateId}
                error={
                  stagePendingId === null &&
                  (promoteMutation.variables === candidate.candidateId ||
                    rollbackMutation.variables === candidate.candidateId)
                    ? stageError
                    : null
                }
                onPromote={(candidateId) => {
                  rollbackMutation.reset();
                  promoteMutation.mutate(candidateId);
                }}
                onRollback={(candidateId) => {
                  promoteMutation.reset();
                  rollbackMutation.mutate(candidateId);
                }}
              />
            ))}
          </div>
        )}
      </Section>

      <div className="gap-t-6">
        <ProtectedRulesBanner />
      </div>
    </Page>
  );
}

export default TrustRoute;
