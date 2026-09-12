import React, { useMemo } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import type { ClearanceItem, ClearanceItemDetail } from "@clearcut/contracts";
import { Badge, Banner } from "../../components/ds";
import {
  clearanceItemDetailQueryOptions,
} from "../../queries/clearanceItems";
import {
  authorityLabel,
  bearingLabel,
  clampCleanExcerpt,
  cleanExcerpt,
  displayCategory,
  displayStatus,
  displayStatusTone,
  formatStamp,
  severityWord,
} from "./itemPresentation";
import { ResearchProgress } from "./ResearchProgress";

export interface EvidenceWorkbenchProps {
  orgSlug: string;
  projectId: string;
  item: ClearanceItem | null;
  researchJobId?: string | null;
  onResearchSettled?: () => void;
  onRunResearch?: () => void;
  researchPending?: boolean;
  /** Open the full evidence modal (table of all sources). */
  onOpenDetail?: () => void;
}

function pickPrimaryClaim(detail: ClearanceItemDetail | undefined) {
  const claims = detail?.claims ?? [];
  if (!claims.length) return null;
  return claims.find((c) => bearingLabel(c.stance) === "Supports") ?? claims[0]!;
}

/**
 * Mock workspace right pane: workbench for the *active* flag only.
 * Flags themselves live in the scene rail and the script margin.
 */
export function EvidenceWorkbench({
  orgSlug,
  projectId,
  item,
  researchJobId,
  onResearchSettled,
  onRunResearch,
  researchPending,
  onOpenDetail,
}: EvidenceWorkbenchProps) {
  const itemId = item?.itemId ?? "";
  const detailQuery = useQuery({
    ...clearanceItemDetailQueryOptions({ orgId: orgSlug, projectId, itemId }),
    enabled: Boolean(itemId),
  });
  const detail = detailQuery.data;

  const primaryClaim = useMemo(() => pickPrimaryClaim(detail), [detail]);
  const primarySnapshot = useMemo(() => {
    if (!primaryClaim || !detail) return null;
    return detail.snapshots.find((s) => s.snapshotId === primaryClaim.snapshotId) ?? null;
  }, [primaryClaim, detail]);

  if (!item) {
    return (
      <aside className="evidence-drawer" aria-label="Evidence workbench">
        <div className="drawer-head">
          <div className="min-w-0">
            <span className="slug-heading">Evidence</span>
            <h2 className="gap-t-1">No flag selected</h2>
          </div>
        </div>
        <div className="drawer-body">
          <div className="drawer-phase">
            <Banner
              tone=""
              icon="○"
              title="Select a flag"
              message="Pick a term in the script or the scene rail. Evidence for that passage appears here."
            />
          </div>
        </div>
      </aside>
    );
  }

  const claimCount = detail?.evidenceState.claimCount ?? item.claimCount ?? 0;
  const researchStatus = detail?.researchStatus;
  const phase:
    | "running"
    | "empty"
    | "has-evidence"
    | "idle" =
    researchJobId || researchStatus === "running" || researchStatus === "pending"
      ? "running"
      : claimCount > 0
        ? "has-evidence"
        : researchStatus === "completed" || researchStatus === "failed"
          ? "empty"
          : "idle";

  const disagreeCount = (detail?.claims ?? []).filter(
    (c) => bearingLabel(c.stance) === "Disagrees",
  ).length;

  return (
    <aside className="evidence-drawer" aria-label="Evidence workbench">
      <div className="drawer-head">
        <div className="min-w-0">
          <span className="slug-heading">{displayCategory(item.category)}</span>
          <h2 className="gap-t-1">{item.entityName}</h2>
          <p className="mono muted gap-t-1 small">
            {item.itemId.slice(-8)} · Scene {item.scene ?? "—"}
            {item.page != null ? ` · p.${item.page}` : ""}
          </p>
        </div>
      </div>

      <div className="drawer-body">
        <div className="cluster">
          <Badge tone={displayStatusTone(item)}>{displayStatus(item)}</Badge>
          <Badge>{severityWord(item)} priority</Badge>
        </div>

        {researchJobId ? (
          <ResearchProgress
            orgSlug={orgSlug}
            projectId={projectId}
            jobId={researchJobId}
            entityName={item.entityName}
            onSettled={() => onResearchSettled?.()}
          />
        ) : null}

        {phase === "running" && !researchJobId ? (
          <div className="drawer-phase">
            <div className="cluster">
              <span className="spinner" role="status" aria-label="Searching" />
              <strong className="small">Searching for sources…</strong>
            </div>
            <p className="small muted gap-t-2">
              Detection flagged this passage. Research has not returned yet.
            </p>
            <div className="stack-sm gap-t-3" aria-hidden="true">
              <div className="skeleton" style={{ width: "86%" }} />
              <div className="skeleton" style={{ width: "62%" }} />
            </div>
          </div>
        ) : null}

        {phase === "idle" ? (
          <div className="drawer-phase">
            <Banner
              tone=""
              icon="⊘"
              title="Needs research"
              message="No cited claims yet. Run research to retrieve sources for this passage."
            />
            <div className="cluster gap-t-3" style={{ justifyContent: "flex-end" }}>
              <button
                type="button"
                className="button button-primary button-sm"
                disabled={researchPending}
                onClick={() => onRunResearch?.()}
              >
                {researchPending ? "Starting…" : "Run research"}
              </button>
            </div>
          </div>
        ) : null}

        {phase === "empty" ? (
          <div className="drawer-phase">
            <Banner
              tone=""
              icon="⊘"
              title="No attributable source found"
              message="A bounded search ended without a citeable source. This is unresolved — not a clearance result."
            />
          </div>
        ) : null}

        {phase === "has-evidence" && detail ? (
          <>
            <article className="source-card" data-testid="workbench-primary-source">
              <div className="cluster-between">
                <span className="slug-heading">Best available source</span>
                <Badge tone="is-accent">
                  {authorityLabel(primaryClaim?.authorityTier ?? "secondary")}
                </Badge>
              </div>
              {primarySnapshot ? (
                <p className="small gap-t-2">
                  <a href={primarySnapshot.url} target="_blank" rel="noopener noreferrer">
                    <strong>{cleanExcerpt(primarySnapshot.title)}</strong>
                  </a>
                </p>
              ) : null}
              <blockquote className="small">
                {clampCleanExcerpt(
                  primaryClaim?.claimText ?? primarySnapshot?.excerpt ?? "",
                  220,
                )}
              </blockquote>
              <div className="source-foot">
                <span className="mono muted small">
                  retrieved {formatStamp(primarySnapshot?.retrievedAt)}
                </span>
                {primarySnapshot && (
                  <a
                    className="button button-quiet button-sm"
                    href={primarySnapshot.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Provenance
                  </a>
                )}
              </div>
            </article>

            <div className="stack-sm gap-t-3">
              <button
                type="button"
                className="button button-quiet"
                data-testid="open-evidence-drawer-btn"
                onClick={() => onOpenDetail?.()}
              >
                <span>
                  <strong>{claimCount}</strong> source{claimCount === 1 ? "" : "s"} retrieved
                  {disagreeCount > 0
                    ? ` · ${disagreeCount} disagree${disagreeCount === 1 ? "s" : ""}`
                    : ""}
                </span>
                <span aria-hidden="true"> →</span>
              </button>
              <Link
                className="button button-quiet button-sm"
                to="/o/$orgSlug/projects/$projectId/items/$itemId"
                params={{ orgSlug, projectId, itemId: item.itemId }}
              >
                Full record
              </Link>
            </div>

            {item.sourcesDisagree || disagreeCount > 0 ? (
              <Banner
                tone="is-warning"
                icon="⚠"
                title="Conflict retained"
                message="Sources disagree on this flag; a human must decide."
              />
            ) : null}

            {item.confidence != null && (
              <div>
                <div className="cluster-between">
                  <span className="slug-heading">Confidence</span>
                  <span className="mono small">{item.confidence}%</span>
                </div>
                <div className="meter gap-t-2">
                  <span style={{ width: `${item.confidence}%` }} />
                </div>
              </div>
            )}
          </>
        ) : null}

        <div className="cluster-between gap-t-4">
          <span className="slug-heading">Assignee</span>
          <span className="small">
            {item.assignedTo ? item.assignedTo.slice(0, 8) : "Unassigned"}
          </span>
        </div>
      </div>

      <div className="drawer-foot">
        <div className="stack-sm">
          {claimCount > 0 && (
            <button
              type="button"
              className="button button-secondary button-sm"
              onClick={() => onOpenDetail?.()}
            >
              All sources
            </button>
          )}
          <Link
            className="button button-primary button-sm"
            to="/o/$orgSlug/projects/$projectId/items/$itemId"
            params={{ orgSlug, projectId, itemId: item.itemId }}
          >
            Full record
          </Link>
        </div>
      </div>
    </aside>
  );
}

export default EvidenceWorkbench;
