import React from "react";
import type { ClearanceItem } from "@clearcut/contracts";
import { Badge } from "../../components/ds";
import { displayCategory, displayStatus, displayStatusTone } from "./itemPresentation";

export interface ClearanceItemCardProps {
  item: ClearanceItem;
  isSelected?: boolean;
  onSelect?: (item: ClearanceItem) => void;
  onOpenDrawer?: (item: ClearanceItem) => void;
}

/**
 * One flag in the workspace's flag list, using the mock's list-row vocabulary.
 * The row itself selects the item and carries a nested control that opens the
 * evidence drawer, so it is a container rather than a button.
 */
export function ClearanceItemCard({
  item,
  isSelected = false,
  onSelect,
  onOpenDrawer,
}: ClearanceItemCardProps) {
  return (
    <div
      data-testid="clearance-item-card"
      className={`list-row is-static ${isSelected ? "" : ""}`.trim()}
      aria-current={isSelected ? "true" : undefined}
    >
      <div className="list-main">
        <button
          className="list-main-button"
          type="button"
          onClick={() => onSelect?.(item)}
          aria-pressed={isSelected}
        >
          <span className="list-title">{item.entityName}</span>
          <span className="list-meta">
            <span>{displayCategory(item.category)}</span>
            <span>
              {item.claimCount ?? 0} source{(item.claimCount ?? 0) === 1 ? "" : "s"}
              {item.sourcesDisagree ? " · conflict" : ""}
            </span>
            {item.scene != null && <span>Scene {item.scene}</span>}
            {item.disposition && <span>{item.disposition.replace(/_/g, " ")}</span>}
          </span>
        </button>
      </div>

      <div className="list-aside">
        <Badge tone={displayStatusTone(item)}>{displayStatus(item)}</Badge>
        <button
          className="button button-quiet button-sm"
          type="button"
          data-testid="open-evidence-drawer-btn"
          onClick={() => onOpenDrawer?.(item)}
        >
          View Evidence Claims →
        </button>
      </div>
    </div>
  );
}

export default ClearanceItemCard;
