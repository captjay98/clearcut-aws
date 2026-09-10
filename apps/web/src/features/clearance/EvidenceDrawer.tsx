import React from "react";
import { Link } from "@tanstack/react-router";
import type { ClearanceItem } from "@clearcut/contracts";
import type { ClearanceItemDetail } from "@clearcut/contracts";
import { Badge, Banner } from "../../components/ds";
import { displayCategory, displayStatus, displayStatusTone } from "./itemPresentation";
import { EvidencePanel } from "./EvidencePanel";

export interface EvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  item: ClearanceItem | null;
  detail?: ClearanceItemDetail;
  orgSlug: string;
  projectId: string;
  loading?: boolean;
}

/**
 * The selected flag's cited evidence. The mock shows this as the stage's right
 * pane; here it is a modal so it can also be reached from the flag list and the
 * item surface, which is why it traps focus and closes on Escape.
 *
 * Focus order matters and is asserted: the close control is the first focusable
 * and "Review Item →" is the last, so Shift+Tab from the top lands on the review
 * link and Tab from it returns to close.
 */
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
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
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

  const claims = detail?.claims ?? [];

  return (
    <div className="backdrop">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
        tabIndex={-1}
        data-testid="evidence-drawer"
        className="dialog wide"
      >
        <header className="dialog-head">
          <div className="min-w-0">
            <span className="slug-heading">{displayCategory(item.category)}</span>
            <h2 id="evidence-drawer-title" className="gap-t-1">
              {item.entityName} evidence
            </h2>
            <div className="cluster gap-t-1">
              <Badge tone={displayStatusTone(item)}>{displayStatus(item)}</Badge>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button is-bare"
            type="button"
            onClick={onClose}
            aria-label="Close evidence drawer"
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>

        <div className="dialog-body">
          {loading || !detail ? (
            <p role="status" className="small muted">
              Loading authoritative evidence state…
            </p>
          ) : claims.length === 0 ? (
            <Banner
              tone="is-warning"
              icon="⚠"
              title="Unresolved: zero cited evidence"
              message={
                <>
                  {detail.evidenceState.reason} Zero evidence is unresolved, never clearance. No
                  fallback claims are invented.
                </>
              }
            />
          ) : (
            <EvidencePanel
              item={item}
              claims={claims}
              snapshots={detail.snapshots}
              conflictDescriptions={(detail.conflicts ?? []).map((conflict) => conflict.description)}
            />
          )}
        </div>

        <footer className="dialog-actions">
          <button className="button button-quiet" type="button" onClick={onClose}>
            Close Drawer
          </button>
          <Link
            className="button button-primary"
            to="/o/$orgSlug/projects/$projectId/items/$itemId"
            params={{ orgSlug, projectId, itemId: item.itemId }}
          >
            Review Item →
          </Link>
        </footer>
      </div>
    </div>
  );
}

export default EvidenceDrawer;
