import React, { useEffect, useState } from "react";
import { createFileRoute, Link, useNavigate, useParams } from "@tanstack/react-router";
import { api, type Project } from "@clearcut/contracts";
import { Banner, EmptyState, Page, Section, StatGrid, type Stat } from "../../../../components/ds";

export const Route = createFileRoute("/o/$orgSlug/projects/")({
  component: ProjectsListRoute,
});

const DAY_MS = 24 * 60 * 60 * 1000;

function formatDate(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleDateString();
}

/**
 * Aggregates shown on the organization's project list. Every one is derived from
 * the projects payload itself: cross-project evidence counts would need a call
 * per project, and a number we cannot source is a number we do not show.
 */
function buildStats(projects: readonly Project[]): Stat[] {
  const now = Date.now();
  const upcomingLocks = projects.filter((project) => {
    if (!project.targetLockDate) {
      return false;
    }
    const lock = new Date(project.targetLockDate).getTime();
    return !Number.isNaN(lock) && lock >= now && lock - now <= 30 * DAY_MS;
  }).length;
  const jurisdictions = new Set(
    projects.map((project) => project.jurisdiction).filter((value): value is string => Boolean(value)),
  );

  return [
    { label: "Active projects", value: projects.length },
    {
      label: "Locks within 30 days",
      value: upcomingLocks,
      tone: upcomingLocks ? "is-warning" : "",
      hint: "Target lock date",
    },
    { label: "Jurisdictions", value: jurisdictions.size, hint: "Declared across projects" },
  ];
}

export function ProjectsListRoute() {
  const { orgSlug } = useParams({ from: "/o/$orgSlug/projects/" });
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await api.listProjects({ params: { orgId: orgSlug } });
        if (cancelled) {
          return;
        }
        if (res.ok) {
          setProjects(res.value ?? []);
        } else {
          setError(res.error.message || "Failed to load projects");
        }
      } catch {
        if (!cancelled) {
          setError("Network error while loading projects");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();

    return () => {
      cancelled = true;
    };
  }, [orgSlug]);

  return (
    <Page
      trail={[{ label: "Projects" }]}
      eyebrow={orgSlug}
      title="Clearance Projects"
      lede="Active clearance work, open human gates, and delivery readiness across the organization."
      actions={
        <Link className="button button-primary" to="/o/$orgSlug/projects/new" params={{ orgSlug }}>
          + New Project
        </Link>
      }
      notice={
        error && (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Could not load projects"
            message={error}
            role="alert"
          />
        )
      }
    >
      {!loading && !error && <StatGrid stats={buildStats(projects)} columns={3} />}

      <Section
        title="Your projects"
        description="Each project keeps its own script versions, evidence, and decisions."
      >
        {loading ? (
          <div className="list" aria-busy="true">
            <div className="list-row is-static">
              <div className="list-main">
                <span className="skeleton" style={{ width: "40%" }} />
              </div>
            </div>
          </div>
        ) : projects.length === 0 ? (
          <EmptyState
            icon="▤"
            title="No clearance projects yet"
            description="Create a project, then import a screenplay as Fountain or Final Draft to start detection."
            action={
              <Link
                className="button button-primary"
                to="/o/$orgSlug/projects/new"
                params={{ orgSlug }}
              >
                Create project
              </Link>
            }
          />
        ) : (
          <div className="list">
            {projects.map((project) => {
              const lock = formatDate(project.targetLockDate);
              return (
                <button
                  key={project.projectId}
                  className="list-row"
                  type="button"
                  onClick={() =>
                    navigate({
                      to: "/o/$orgSlug/projects/$projectId",
                      params: { orgSlug, projectId: project.projectId },
                    })
                  }
                >
                  <div className="list-main">
                    <span className="list-title">{project.title}</span>
                    <span className="list-meta">
                      {project.productionType && <span>{project.productionType}</span>}
                      {project.productionStage && <span>{project.productionStage}</span>}
                      {project.jurisdiction && <span>{project.jurisdiction}</span>}
                      {lock && <span>Lock {lock}</span>}
                      <span>Created {formatDate(project.createdAt)}</span>
                    </span>
                  </div>
                  <div className="list-aside">
                    <span className="badge">Open</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Section>
    </Page>
  );
}

export default ProjectsListRoute;
