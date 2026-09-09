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

/**
 * Row emphasis, using the design system's row tones. An addition and a removal
 * are both changes but not the same kind of risk, so they do not read alike.
 */
const KIND_ROW_CLASS: Record<ScriptDiffChangeKind, string> = {
  unchanged: "",
  moved: "is-row-accent",
  modified: "is-row-warning",
  added: "is-row-accent",
  removed: "is-row-danger",
};

/** Deterministic, collision-free key for a diff element row. */
function rowKey(element: ScriptDiffElement, index: number): string {
  const before = element.beforeElementId ?? "∅";
  const after = element.afterElementId ?? "∅";
  return `${element.changeKind}:${before}->${after}:${index}`;
}

/**
 * Before and after for one element. Deletions and insertions use <del> and
 * <ins>, which the design system already styles as struck danger text and
 * tinted success text, so the change kind is legible without colour alone.
 */
function BeforeAfter({ element }: { element: ScriptDiffElement }) {
  const { changeKind, text } = element;

  if (changeKind === "added") {
    return (
      <>
        <section>
          <p className="diff-text muted">(none)</p>
        </section>
        <section>
          <p className="diff-text">
            <ins>{text}</ins>
          </p>
        </section>
      </>
    );
  }
  if (changeKind === "removed") {
    return (
      <>
        <section>
          <p className="diff-text">
            <del>{text}</del>
          </p>
        </section>
        <section>
          <p className="diff-text muted">(none)</p>
        </section>
      </>
    );
  }
  if (changeKind === "modified") {
    return (
      <>
        <section>
          <p className="diff-text">
            <del>{text}</del>
          </p>
        </section>
        <section>
          <p className="diff-text">
            <ins>{text}</ins>
          </p>
        </section>
      </>
    );
  }
  return (
    <>
      <section>
        <p className="diff-text">{text}</p>
      </section>
      <section>
        <p className="diff-text">{text}</p>
      </section>
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
    <div data-testid="script-diff-viewer" className="stack">
      <div className="tabs" role="group" aria-label="Filter changes by kind">
        <button
          className="tab"
          type="button"
          onClick={() => setFilter("all")}
          aria-pressed={filter === "all"}
        >
          All ({elements.length})
        </button>
        {KIND_ORDER.map((kind) => (
          <button
            className="tab"
            type="button"
            key={kind}
            onClick={() => setFilter(kind)}
            aria-pressed={filter === kind}
          >
            {KIND_LABEL[kind]} ({counts[kind]})
          </button>
        ))}
      </div>

      <div className="list">
        <div className="list-row is-static">
          <div className="list-main">
            <div className="grid grid-2">
              <span className="field-label">{beforeLabel ?? "No predecessor"} (Prior)</span>
              <span className="field-label">{afterLabel} (Approved Revision)</span>
            </div>
          </div>
        </div>

        {visible.length === 0 ? (
          <div className="list-row is-static">
            <div className="list-main">
              <p className="small muted">
                {elements.length === 0
                  ? "No element-level changes are recorded for this revision."
                  : "No elements match the selected change kind."}
              </p>
            </div>
          </div>
        ) : (
          visible.map((element, index) => (
            <div
              className={`list-row is-static ${KIND_ROW_CLASS[element.changeKind]}`.trim()}
              key={rowKey(element, index)}
              data-testid="diff-row"
              data-change-kind={element.changeKind}
              data-confidence={element.confidence}
            >
              <div className="list-main">
                <div className="diff">
                  <BeforeAfter element={element} />
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default VersionDiffViewer;
