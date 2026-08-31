import React from "react";

export interface ClearanceItem {
  id: string;
  category: string;
  category_label?: string;
  text: string;
  scene: number;
  page: number;
  status: string;
  workflow_status: string;
  research_status: string;
  disposition_status?: string;
  claims_count?: number;
}

export interface ClearanceItemCardProps {
  item: ClearanceItem;
  isSelected?: boolean;
  onSelect?: (item: ClearanceItem) => void;
  onOpenDrawer?: (item: ClearanceItem) => void;
}

export function ClearanceItemCard({
  item,
  isSelected = false,
  onSelect,
  onOpenDrawer,
}: ClearanceItemCardProps) {
  const getStatusBadgeClass = (status: string, workflow: string) => {
    if (status === "cleared" || workflow === "closed") {
      return "bg-emerald-950/80 text-emerald-400 border-emerald-800";
    }
    if (status === "needs_rewrite" || status === "rewrite") {
      return "bg-purple-950/80 text-purple-400 border-purple-800";
    }
    if (status === "escalated" || status === "referred") {
      return "bg-rose-950/80 text-rose-400 border-rose-800";
    }
    if (status === "researching") {
      return "bg-blue-950/80 text-blue-400 border-blue-800 animate-pulse";
    }
    // pending / needs_call
    return "bg-amber-950/80 text-amber-400 border-amber-800";
  };

  return (
    <div
      data-testid="clearance-item-card"
      onClick={() => onSelect?.(item)}
      className={`p-3.5 rounded-lg border transition-all cursor-pointer flex flex-col justify-between space-y-2.5 ${
        isSelected
          ? "bg-amber-950/20 border-amber-500/80 shadow-md ring-1 ring-amber-500/40"
          : "bg-slate-900/90 border-slate-800 hover:border-slate-700 hover:bg-slate-900"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-sm font-bold text-white tracking-tight">{item.text}</span>
            <span className="text-[10px] px-2 py-0.5 bg-slate-800 text-slate-300 rounded font-medium">
              {item.category}
            </span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            Scene {item.scene} • Page {item.page} •{" "}
            <span className="font-semibold text-slate-400">
              {item.claims_count || 0} claims cited
            </span>
          </div>
        </div>

        <span
          className={`text-[10px] px-2 py-0.5 rounded border font-bold uppercase tracking-wider ${getStatusBadgeClass(
            item.status,
            item.workflow_status
          )}`}
        >
          {item.status.replace("_", " ")}
        </span>
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-slate-800/80 text-xs">
        <span className="text-[11px] text-slate-500">
          Research: <span className="capitalize text-slate-400">{item.research_status || "completed"}</span>
        </span>
        <button
          type="button"
          data-testid="open-evidence-drawer-btn"
          onClick={(e) => {
            e.stopPropagation();
            onOpenDrawer?.(item);
          }}
          className="text-xs font-bold text-amber-500 hover:text-amber-400 hover:underline inline-flex items-center space-x-1"
        >
          <span>View Evidence Claims</span>
          <span>→</span>
        </button>
      </div>
    </div>
  );
}

export default ClearanceItemCard;
