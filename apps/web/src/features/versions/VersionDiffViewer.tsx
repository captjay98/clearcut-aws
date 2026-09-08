import React, { useMemo, useState } from "react";
import type { ScriptDiffChangeKind, ScriptDiffElement } from "@clearcut/contracts";

export interface VersionDiffViewerProps {
  beforeLabel?: string | null;
  afterLabel?: string;
  elements: ScriptDiffElement[];
}

type FilterKind = "all" | ScriptDiffChangeKind;

const KIND_ORDER: ScriptDiffChangeKind[] = [
  "unchanged",
  "moved",
  "modified",
  "added",
  "removed",
];

const KIND_LABEL: Record<ScriptDiffChangeKind, string> = {
  unchanged: "Unchanged",
  moved: "Moved",
  modified: "Modified",
  added: "Added",
  removed: "Removed",
};

// Row styling keeps the mock's revision-stock vocabulary: additions read green,
// removals read struck-through rose, modifications pair the two, moves are amber.
const KIND_ROW_CLASS: Record<ScriptDiffChangeKind, string> = {
  unchanged: "text-slate-500",
  moved: "bg-amber-50/50 dark:bg-amber-950/20",
  modified: "bg-amber-50/50 dark:bg-amber-950/20",
  added: "bg-emerald-50/50 dark:bg-emerald-950/20",
  removed: "bg-rose-50/50 dark:bg-rose-950/20",
};

/** Deterministic, collision-free key for a diff element row. */
function rowKey(element: ScriptDiffElement, index: number): string {
  const before = element.beforeElementId ?? "∅";
  const after = element.afterElementId ?? "∅";
  return `${element.changeKind}:${before}->${after}:${index}`;
}

function BeforeAfter({ element }: { element: ScriptDiffElement }) {
  const { changeKind, text } = element;
  if (changeKind === "added") {
    return (
      <>
        <div className="text-slate-400 italic">(none)</div>
        <div className="text-emerald-600 dark:text-emerald-400 font-semibold">{text}</div>
      </>
    );
  }
  if (changeKind === "removed") {
    return (
      <>
        <div className="text-rose-600 dark:text-rose-400 line-through pr-2">{text}</div>
        <div className="text-slate-400 italic">(none)</div>
      </>
    );
  }
  if (changeKind === "modified") {
    return (
      <>
        <div className="text-rose-600 dark:text-rose-400 line-through pr-2">{text}</div>
        <div className="text-emerald-600 dark:text-emerald-400 font-semibold pl-2">{text}</div>
      </>
    );
  }
  // unchanged / moved: same text on both sides
  return (
    <>
      <div>{text}</div>
      <div>{text}</div>
    </>
  );
}

export function VersionDiffViewer({
  beforeLabel = null,
  afterLabel = "Revision",
  elements,
}: VersionDiffViewerProps) {
  const [filter, setFilter] = useState<FilterKind>("all");

  const counts = useMemo(() => {
    const tally: Record<ScriptDiffChangeKind, number> = {
      unchanged: 0,
      moved: 0,
      modified: 0,
      added: 0,
      removed: 0,
    };
    for (const element of elements) tally[element.changeKind] += 1;
    return tally;
  }, [elements]);

  const visible = useMemo(
    () => (filter === "all" ? elements : elements.filter((e) => e.changeKind === filter)),
    [elements, filter],
  );

  return (
    <div
      data-testid="script-diff-viewer"
      className="border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden"
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 dark:border-slate-800 p-3 bg-slate-50 dark:bg-slate-900">
        <button
          type="button"
          onClick={() => setFilter("all")}
          aria-pressed={filter === "all"}
          className={`px-2.5 py-1 text-xs font-bold rounded ${
            filter === "all"
              ? "bg-amber-600 text-white"
              : "text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          All ({elements.length})
        </button>
        {KIND_ORDER.map((kind) => (
          <button
            key={kind}
            type="button"
            onClick={() => setFilter(kind)}
            aria-pressed={filter === kind}
            className={`px-2.5 py-1 text-xs font-bold rounded ${
              filter === kind
                ? "bg-amber-600 text-white"
                : "text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
            }`}
          >
            {KIND_LABEL[kind]} ({counts[kind]})
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 p-3 text-slate-600 dark:text-slate-400 font-sans font-medium text-xs">
        <div>{beforeLabel ?? "No predecessor"} (Prior)</div>
        <div>{afterLabel} (Approved Revision)</div>
      </div>

      {visible.length === 0 ? (
        <div className="p-8 text-center text-xs text-slate-500">
          {elements.length === 0
            ? "No element-level changes are recorded for this revision."
            : "No elements match the selected change kind."}
        </div>
      ) : (
        <div className="divide-y divide-slate-100 dark:divide-slate-800 font-mono text-xs">
          {visible.map((element, index) => (
            <div
              key={rowKey(element, index)}
              data-testid="diff-row"
              data-change-kind={element.changeKind}
              data-confidence={element.confidence}
              className={`grid grid-cols-2 p-3 ${KIND_ROW_CLASS[element.changeKind]}`}
            >
              <BeforeAfter element={element} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default VersionDiffViewer;
