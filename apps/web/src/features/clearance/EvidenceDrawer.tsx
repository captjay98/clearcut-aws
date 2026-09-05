import React from "react";
import { Link } from "@tanstack/react-router";
import type { ClearanceItem } from "@clearcut/contracts";
import type { ClearanceItemDetail } from "@clearcut/contracts";

export interface EvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  item: ClearanceItem | null;
  detail?: ClearanceItemDetail;
  orgSlug: string;
  projectId: string;
  loading?: boolean;
}

function stanceClass(stance: string): string {
  if (stance === "supporting") {
    return "bg-emerald-950 text-emerald-400 border-emerald-800";
  }
  if (stance === "conflicting") {
    return "bg-rose-950 text-rose-400 border-rose-800";
  }
  return "bg-amber-950 text-amber-400 border-amber-800";
}

export function EvidenceDrawer({
  isOpen,
  onClose,
  item,
  detail,
  orgSlug,
  projectId,
  loading = false,
}: EvidenceDrawerProps) {
  const dialogRef = React.useRef<HTMLDivElement>(null);
  const closeButtonRef = React.useRef<HTMLButtonElement>(null);
  const previousFocusRef = React.useRef<HTMLElement | null>(null);
  const onCloseRef = React.useRef(onClose);
  const itemId = item?.itemId;

  React.useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  React.useEffect(() => {
    if (!isOpen || !itemId) return;

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const focusFrame = window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          "button:not(:disabled), a[href], input:not(:disabled), " +
            "textarea:not(:disabled), select:not(:disabled), " +
            "[tabindex]:not([tabindex='-1'])",
        ),
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const activeElement = document.activeElement;
      if (
        activeElement === dialogRef.current ||
        !activeElement ||
        !dialogRef.current.contains(activeElement)
      ) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleKeyDown);
      const previousFocus = previousFocusRef.current;
      previousFocusRef.current = null;
      window.requestAnimationFrame(() => {
        if (previousFocus?.isConnected) previousFocus.focus();
      });
    };
  }, [isOpen, itemId]);

  if (!isOpen || !item) return null;

  const snapshots = new Map(
    (detail?.snapshots ?? []).map((snapshot) => [
      snapshot.snapshotId,
      snapshot,
    ]),
  );
  const claims = detail?.claims ?? [];

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="evidence-drawer-title"
      tabIndex={-1}
      data-testid="evidence-drawer"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-lg bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col font-sans"
    >
      <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/90 shrink-0">
        <div>
          <div className="flex items-center space-x-2">
            <h2
              id="evidence-drawer-title"
              className="text-base font-bold text-white tracking-tight"
            >
              {item.entityName} evidence
            </h2>
            <span className="text-[10px] px-2 py-0.5 bg-slate-800 text-slate-300 rounded font-medium">
              {item.category}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">Status: {item.status}</p>
        </div>

        <button
          ref={closeButtonRef}
          type="button"
          onClick={onClose}
          aria-label="Close evidence drawer"
          className="text-slate-400 hover:text-white text-xl font-bold p-1"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
        {loading || !detail ? (
          <div className="py-12 text-center text-slate-500 font-mono">
            Loading authoritative evidence state…
          </div>
        ) : claims.length === 0 ? (
          <div className="p-6 bg-amber-950/20 border border-amber-900/60 rounded-lg text-center space-y-2">
            <div className="text-2xl">⚠️</div>
            <h3 className="text-sm font-bold text-amber-300">
              Unresolved Risk: Zero Evidence Claims
            </h3>
            <p className="text-slate-400 text-xs">
              {detail.evidenceState.reason}
            </p>
            <p className="text-slate-400 text-xs">
              Zero evidence is unresolved, never clearance. No fallback claims
              are invented.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
              <span>Cited Source Snapshots ({claims.length})</span>
              <span className="text-[10px] text-amber-300 font-medium">
                Cited provenance
              </span>
            </div>

            {claims.map((claim) => {
              const snapshot = snapshots.get(claim.snapshotId);
              return (
                <article
                  key={claim.claimId}
                  className="p-4 bg-slate-950 border border-slate-800 rounded-lg space-y-2.5 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-2">
                    {snapshot ? (
                      <a
                        href={snapshot.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-testid="source-snapshot-url"
                        className="font-bold text-amber-400 hover:underline hover:text-amber-300 text-xs flex items-center space-x-1"
                      >
                        <span>{snapshot.title}</span>
                        <span className="text-[10px]">↗</span>
                      </a>
                    ) : (
                      <span className="text-xs text-amber-300">
                        Cited source snapshot unavailable
                      </span>
                    )}

                    <span
                      data-testid="claim-stance-badge"
                      className={`text-[10px] px-2 py-0.5 rounded border font-bold uppercase ${stanceClass(
                        claim.stance,
                      )}`}
                    >
                      {claim.stance}
                    </span>
                  </div>

                  <div className="flex items-center space-x-2 text-[10px] text-slate-400">
                    <span className="px-1.5 py-0.5 bg-slate-900 rounded border border-slate-800 font-mono">
                      {claim.authorityTier}
                    </span>
                    {snapshot && (
                      <>
                        <span>•</span>
                        <span>{snapshot.publisher}</span>
                      </>
                    )}
                  </div>

                  <blockquote className="text-xs text-slate-300 italic border-l-2 border-amber-500/80 pl-3 py-0.5 bg-slate-900/40 rounded-r">
                    “{claim.provenanceExcerpt}”
                  </blockquote>

                  {snapshot && (
                    <div className="text-[10px] text-slate-500 font-mono pt-1">
                      Retrieved:{" "}
                      {new Date(snapshot.retrievedAt).toLocaleString()}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </div>

      <div className="px-5 py-3 border-t border-slate-800 bg-slate-900/90 flex items-center justify-between shrink-0">
        <button
          type="button"
          onClick={onClose}
          className="px-3 py-1.5 text-xs text-slate-400 hover:text-white"
        >
          Close Drawer
        </button>

        <Link
          to="/o/$orgSlug/projects/$projectId/items/$itemId"
          params={{ orgSlug, projectId, itemId: item.itemId }}
          className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded shadow focus:outline-none focus:ring-2 focus:ring-amber-500"
        >
          Review Item →
        </Link>
      </div>
    </div>
  );
}

export default EvidenceDrawer;
