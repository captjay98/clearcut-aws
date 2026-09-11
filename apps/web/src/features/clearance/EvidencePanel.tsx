import React, { useState } from "react";
import type {
  ItemDetailEvidenceClaim,
  ItemDetailSourceSnapshot,
} from "@clearcut/contracts";
import { Badge } from "../../components/ds";
import {
  authorityLabel,
  bearingLabel,
  bearingTone,
  clampExcerpt,
  formatStamp,
  severityWord,
} from "./itemPresentation";

export interface EvidencePanelItem {
  entityName: string;
  sourcesDisagree?: boolean;
  confidence?: number;
  status: string;
  severity?: "High" | "Medium" | "Low";
  claimCount?: number;
  displayStatus?: string;
}

export interface EvidencePanelProps {
  item: EvidencePanelItem;
  claims: ItemDetailEvidenceClaim[];
  snapshots: ItemDetailSourceSnapshot[];
  conflictDescriptions?: string[];
  /** Keep zero-evidence fail-closed copy when there are no claims. */
  emptyAction?: React.ReactNode;
}

function claimBySnapshot(claims: ItemDetailEvidenceClaim[]): Map<string, ItemDetailEvidenceClaim> {
  const map = new Map<string, ItemDetailEvidenceClaim>();
  for (const claim of claims) {
    const existing = map.get(claim.snapshotId);
    if (!existing) {
      map.set(claim.snapshotId, claim);
    }
  }
  return map;
}

/**
 * Mock-aligned evidence block: primary source card, source table with bearing,
 * clamped excerpts, confidence, and the retained-conflict callout.
 */
export function EvidencePanel({
  item,
  claims,
  snapshots,
  conflictDescriptions = [],
  emptyAction,
}: EvidencePanelProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const snapshotsById = new Map(snapshots.map((snapshot) => [snapshot.snapshotId, snapshot]));
  const primaryClaim = claims[0] ?? null;
  const primarySnapshot = primaryClaim
    ? snapshotsById.get(primaryClaim.snapshotId) ?? null
    : null;
  const claimFor = claimBySnapshot(claims);

  if (claims.length === 0) {
    return (
      <div className="stack">
        <p className="small muted">
          Sourced claims with authority tier and retrieval metadata. 0 sources retrieved for this
          flag.
        </p>
        <p className="small muted">Zero cited evidence remains unresolved. No fallback evidence has been invented.</p>
        {emptyAction}
      </div>
    );
  }

  const hasConflict =
    Boolean(item.sourcesDisagree) ||
    claims.some((claim) => bearingLabel(claim.stance) === "Disagrees") ||
    conflictDescriptions.length > 0;

  const toggleExpanded = (key: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="stack">
      <p className="small muted">
        Sourced claims with authority tier and retrieval metadata. {snapshots.length} source
        {snapshots.length === 1 ? "" : "s"} retrieved for this flag.
      </p>

      {(primaryClaim || primarySnapshot) && (
        <article className="source-card" data-testid="primary-source-card">
          <div className="cluster">
            <span className="small muted">Primary source</span>
            <Badge tone="is-accent">{authorityLabel(primaryClaim?.authorityTier ?? "secondary")}</Badge>
          </div>
          {primarySnapshot ? (
            <p className="gap-t-2">
              <a href={primarySnapshot.url} target="_blank" rel="noopener noreferrer">
                <strong>{primarySnapshot.title}</strong>
              </a>
            </p>
          ) : (
            <p className="gap-t-2">
              <strong>Cited source snapshot unavailable</strong>
            </p>
          )}
          <blockquote className="gap-t-2">
            &ldquo;{clampExcerpt(primaryClaim?.claimText ?? primarySnapshot?.excerpt ?? "", 280)}
            &rdquo;
          </blockquote>
          <p className="small muted gap-t-2">
            retrieved {formatStamp(primarySnapshot?.retrievedAt)} · snapshot retained
            {primarySnapshot ? ` · ${primarySnapshot.publisher}` : ""}
          </p>
          {primarySnapshot && (
            <details className="gap-t-2">
              <summary className="small">Where this came from</summary>
              <p className="small mono gap-t-1">{primarySnapshot.url}</p>
              <p className="small muted">
                origin {primarySnapshot.origin} · snapshot {primarySnapshot.snapshotId}
              </p>
            </details>
          )}
        </article>
      )}

      <div className="table-wrap" data-testid="evidence-source-table">
        <table className="data-table">
          <caption className="sr-only">Sources retrieved for {item.entityName}</caption>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Authority</th>
              <th scope="col">What it says</th>
              <th scope="col">Bearing</th>
            </tr>
          </thead>
          <tbody>
            {snapshots.map((snapshot) => {
              const claim = claimFor.get(snapshot.snapshotId);
              const key = snapshot.snapshotId;
              const full = claim?.claimText || snapshot.excerpt;
              const clamped = clampExcerpt(full, 180);
              const isOpen = expanded.has(key);
              return (
                <tr key={snapshot.snapshotId}>
                  <td>
                    <strong>
                      <a
                        href={snapshot.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-testid="source-snapshot-url"
                      >
                        {snapshot.title}
                      </a>
                    </strong>
                    <div className="small muted mono">
                      {snapshot.snapshotId.slice(-8)} · {formatStamp(snapshot.retrievedAt)}
                    </div>
                  </td>
                  <td>{authorityLabel(claim?.authorityTier ?? "secondary")}</td>
                  <td>
                    {isOpen ? full : clamped}
                    {full.length > clamped.length && (
                      <button
                        type="button"
                        className="button button-quiet button-sm"
                        onClick={() => toggleExpanded(key)}
                      >
                        {isOpen ? "Show less" : "Show more"}
                      </button>
                    )}
                  </td>
                  <td>
                    <span data-testid="claim-stance-badge">
                      <Badge tone={bearingTone(claim?.stance ?? "context")}>
                        {bearingLabel(claim?.stance ?? "context")}
                      </Badge>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {item.confidence != null && (
        <div className="cluster">
          <span className="small muted">Confidence</span>
          <strong>{item.confidence}%</strong>
        </div>
      )}

      {hasConflict && (
        <div className="banner is-warning" role="note" data-testid="conflict-callout">
          <span className="banner-icon" aria-hidden="true">
            ⚠
          </span>
          <span className="banner-body">
            <strong>Conflict retained, not resolved automatically</strong>
            <p className="gap-t-1">
              {conflictDescriptions[0] ??
                "Sources disagree on this flag; a human must decide."}
            </p>
          </span>
        </div>
      )}

      <p className="small muted">Priority {severityWord(item)}</p>
    </div>
  );
}

export default EvidencePanel;
