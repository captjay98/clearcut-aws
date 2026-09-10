import React, { useEffect, useState } from "react";
import { Link, createFileRoute, useParams } from "@tanstack/react-router";
import {
  api,
  type ClearanceItem,
  type Project,
  type ScriptVersion,
} from "@clearcut/contracts";
import {
  Badge,
  Banner,
  Card,
  EmptyState,
  Page,
  Progress,
  Section,
  StatGrid,
  type Stat,
  type Tone,
} from "../../../../../components/ds";

export const Route = createFileRoute("/o/$orgSlug/projects/$projectId/")({
  component: ProjectOverviewRoute,
});

/**
 * Statuses that mean a person still has to act. Anything else is either settled
 * or not yet researched, and the overview says which rather than implying a
 * decision that was never recorded.
 */
const ATTENTION_STATUSES = new Set([
  "needs_review",
  "conflict",
  "referred",
  "blocked",
  "unresolved",
]);

function isAttention(item: ClearanceItem): boolean {
  return ATTENTION_STATUSES.has(item.status);
}

function formatDate(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleDateString();
}

function statusTone(status: string): Tone {
  if (status === "verified" || status === "ruled_out" || status === "cleared") {
    return "is-success";
  }
  if (status === "conflict" || status === "blocked") {
    return "is-danger";
  }
  if (ATTENTION_STATUSES.has(status)) {
    return "is-warning";
  }
  return "";
}

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function ProjectOverviewRoute() {
  const { orgSlug, projectId } = useParams({ from: "/o/$orgSlug/projects/$projectId/" });
  const [project, setProject] = useState<Project | null>(null);
  const [versions, setVersions] = useState<ScriptVersion[]>([]);
  const [items, setItems] = useState<ClearanceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [projectRes, versionsRes, itemsRes] = await Promise.all([
          api.getProject({ params: { orgId: orgSlug, projectId } }),
          api.listProjectVersions({ params: { orgId: orgSlug, projectId } }),
          api.listClearanceItems({ params: { orgId: orgSlug, projectId } }),
        ]);
        if (cancelled) {
          return;
        }
        if (projectRes.ok) {
          setProject(projectRes.value);
        } else {
          setError(projectRes.error.message || "Could not load this project.");
        }
        if (versionsRes.ok) {
          setVersions(versionsRes.value ?? []);
        }
        if (itemsRes.ok) {
          setItems(itemsRes.value ?? []);
        }
      } catch {
        if (!cancelled) {
          setError("Network error while loading this project.");
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
  }, [orgSlug, projectId]);

  const imported = versions.length > 0;
  const researched = items.length > 0;
  const attention = items.filter(isAttention);
  const settled = items.filter((item) => !isAttention(item));
  const currentVersion = imported ? versions[versions.length - 1] : null;
  const settledPercent = researched ? Math.round((settled.length / items.length) * 100) : 0;

  // An unresearched project has no findings to count, so those stats read as a
  // dash instead of implying a clean result.
  const stats: Stat[] = [
    {
      label: "Flags raised",
      value: researched ? items.length : "—",
      hint: researched ? "across ten categories" : "no detection has run",
      to: researched ? "/o/$orgSlug/projects/$projectId/items" : undefined,
      params: researched ? { orgSlug, projectId } : undefined,
      search: researched ? { sort: "severity", dir: "desc" } : undefined,
    },
    {
      label: "Settled",
      value: researched ? `${settled.length}/${items.length}` : "—",
      hint: "have a recorded decision",
      tone: researched && attention.length === 0 ? "is-success" : "",
    },
    {
      label: "Needs attention",
      value: researched ? attention.length : "—",
      hint: "conflict, referred, unresolved",
      tone: attention.length ? "is-warning" : "",
      to: researched && attention.length ? "/o/$orgSlug/projects/$projectId/items" : undefined,
      params: researched && attention.length ? { orgSlug, projectId } : undefined,
      search: researched && attention.length ? { status: "attention" } : undefined,
    },
    {
      label: "Current version",
      value: currentVersion ? `v${currentVersion.ordinal}` : "—",
      hint: currentVersion ? currentVersion.revisionLabel : "not imported",
      to: "/o/$orgSlug/projects/$projectId/versions",
      params: { orgSlug, projectId },
    },
  ];

  const milestones: readonly (readonly [string, boolean])[] = [
    ["Script imported", imported],
    ["Detection run", researched],
    ["All flags settled", researched && attention.length === 0],
    ["Revision committed", versions.length > 1],
  ];

  const leadParts = [
    project?.productionStage,
    project?.jurisdiction,
    project?.targetLockDate ? `lock ${formatDate(project.targetLockDate)}` : null,
  ].filter(Boolean);

  return (
    <Page
      trail={[
        { label: "Projects", to: "/o/$orgSlug/projects", params: { orgSlug } },
        { label: project?.title ?? "Project" },
      ]}
      eyebrow={project?.productionType ?? undefined}
      title={project?.title ?? "Project"}
      lede={leadParts.length > 0 ? leadParts.join(" · ") : undefined}
      actions={
        <Link
          className="button button-secondary"
          to="/o/$orgSlug/projects/$projectId/workspace"
          params={{ orgSlug, projectId }}
        >
          Open screenplay
        </Link>
      }
      notice={
        error && (
          <Banner
            tone="is-danger"
            icon="⚠"
            title="Could not load this project"
            message={error}
            role="alert"
          />
        )
      }
    >
      {!loading && !error && (
        <>
          <StatGrid stats={stats} />

          <div className="grid grid-2 gap-t-8">
            <Section
              title="Needs a decision"
              description="Flags waiting on a person before delivery."
              actions={
                <Link
                  className="button button-quiet button-sm"
                  to="/o/$orgSlug/projects/$projectId/items"
                  params={{ orgSlug, projectId }}
                >
                  View all flags
                </Link>
              }
            >
              {attention.length > 0 ? (
                <div className="list">
                  {attention.slice(0, 8).map((item) => (
                    <Link
                      key={item.itemId}
                      className="list-row"
                      to="/o/$orgSlug/projects/$projectId/items/$itemId"
                      params={{ orgSlug, projectId, itemId: item.itemId }}
                    >
                      <div className="list-main">
                        <span className="list-title">{item.entityName}</span>
                        <span className="list-meta">
                          <span>{humanize(item.category)}</span>
                          {item.claimCount !== undefined && (
                            <span>
                              {item.claimCount} source{item.claimCount === 1 ? "" : "s"}
                            </span>
                          )}
                          {item.dueAt && <span>Due {formatDate(item.dueAt)}</span>}
                        </span>
                      </div>
                      <div className="list-aside">
                        <Badge tone={statusTone(item.status)}>{humanize(item.status)}</Badge>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : researched ? (
                <EmptyState
                  icon="✓"
                  title="Nothing blocking"
                  description="Every flagged item has a recorded human decision."
                />
              ) : (
                <EmptyState
                  icon="◦"
                  title="No detection has run yet"
                  description="Import a screenplay as Fountain or Final Draft, then run detection to raise flags."
                />
              )}
            </Section>

            <Section title="Progress">
              <Card>
                <div className="stack">
                  <div className="cluster-between">
                    <span className="small">Flags settled</span>
                    <span className="mono">{researched ? `${settledPercent}%` : "—"}</span>
                  </div>
                  <Progress percent={settledPercent} />
                  <div className="divider" />
                  <div className="stack-sm">
                    {milestones.map(([label, done]) => (
                      <div className="cluster-between" key={label}>
                        <span className={`small ${done ? "" : "muted"}`}>{label}</span>
                        {done ? <Badge tone="is-success">Done</Badge> : <Badge>Pending</Badge>}
                      </div>
                    ))}
                  </div>
                </div>
              </Card>
            </Section>
          </div>
        </>
      )}
    </Page>
  );
}

export default ProjectOverviewRoute;
