import React from "react";

export interface ScriptLine {
  type: "scene_heading" | "action" | "character" | "parenthetical" | "dialogue" | "transition";
  text: string;
  flag?: string;
}

export interface ScriptScene {
  number: number;
  slug: string;
  page: number | null;
  lines: ScriptLine[];
}

/**
 * What the viewer needs to know about a flagged term. The route resolves this
 * from the project's clearance items so the viewer stays a renderer.
 */
export interface FlagAnnotation {
  itemId: string;
  /** Abbreviated category printed in the margin, e.g. MARK or MUSIC. */
  shortCategory: string;
  /** Severity class from the design system: is-blocked, is-high, is-medium, is-low. */
  severityClass: string;
  glyph: string;
  status: string;
  /** The flagged term inside the line, so only it is underlined. */
  term: string;
}

export interface ScreenplayViewerProps {
  title?: string;
  version?: string;
  scenes?: ScriptScene[];
  loading?: boolean;
  selectedItemId?: string | null;
  /** Revision stock for the page edge: white, blue, pink, yellow, green, goldenrod. */
  stock?: string;
  resolveFlag?: (flag: string) => FlagAnnotation | null;
  onSelectFlag?: (annotation: FlagAnnotation) => void;
}

const LINE_CLASS: Record<ScriptLine["type"], string> = {
  scene_heading: "scene-heading",
  action: "script-action",
  character: "script-character",
  parenthetical: "script-paren",
  dialogue: "script-dialogue",
  // The mock's fixture has no transitions, so there is no dedicated rule. A
  // transition is action text set right, which is how it reads on the page.
  transition: "script-action text-right",
};

/**
 * Renders one screenplay line. A flagged term becomes a margin-marked underline
 * rather than an inline chip, so the reading line stays intact — the mock's
 * scriptLine() behaviour.
 */
function ScriptLineView({
  line,
  annotation,
  selected,
  onSelectFlag,
}: {
  line: ScriptLine;
  annotation: FlagAnnotation | null;
  selected: boolean;
  onSelectFlag?: (annotation: FlagAnnotation) => void;
}) {
  const className = LINE_CLASS[line.type] ?? "script-action";

  if (!annotation) {
    return <p className={className}>{line.text}</p>;
  }

  const at = line.text.toLowerCase().indexOf(annotation.term.toLowerCase());
  const flagButton = (text: string) => (
    <button
      className={`flag ${annotation.severityClass} ${selected ? "is-selected" : ""}`.trim()}
      type="button"
      aria-pressed={selected}
      title={`${annotation.shortCategory} — ${annotation.status}`}
      onClick={() => onSelectFlag?.(annotation)}
    >
      {text}
    </button>
  );

  return (
    <p className={className}>
      <span
        className={`margin-mark ${annotation.severityClass} ${selected ? "is-selected" : ""}`.trim()}
        aria-hidden="true"
      >
        <span className="mark-glyph">{annotation.glyph}</span>
        {annotation.shortCategory}
      </span>
      {at >= 0 ? (
        <>
          {line.text.slice(0, at)}
          {flagButton(line.text.slice(at, at + annotation.term.length))}
          {line.text.slice(at + annotation.term.length)}
        </>
      ) : (
        flagButton(line.text)
      )}
    </p>
  );
}

export function ScreenplayViewer({
  title,
  version,
  scenes = [],
  loading = false,
  selectedItemId = null,
  stock = "white",
  resolveFlag,
  onSelectFlag,
}: ScreenplayViewerProps) {
  if (loading) {
    return (
      <div className="script-stage" data-testid="screenplay-viewer">
        <div className="script-stage-head">
          <p role="status" className="small muted">
            Loading screenplay…
          </p>
        </div>
      </div>
    );
  }

  if (scenes.length === 0) {
    return (
      <div className="script-stage" data-testid="screenplay-viewer">
        <div className="script-stage-head">
          <div className="empty-state">
            <span className="empty-icon" aria-hidden="true">
              ⌑
            </span>
            <h3>No committed screenplay</h3>
            <p>
              Import and commit a script version as Fountain or Final Draft to read it here.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="script-stage" data-testid="screenplay-viewer">
      <div className="script-stage-head">
        <span className="slug-heading">{title ?? "Screenplay"}</span>
        {version && <p className="mono muted small">{version}</p>}
      </div>

      {scenes.map((scene) => (
        <section
          className="script-page"
          key={scene.number}
          style={{ "--stock": `var(--rev-${stock})` } as React.CSSProperties}
          aria-label={scene.page ? `Page ${scene.page}` : `Scene ${scene.number}`}
        >
          <span className="stock-strip" aria-hidden="true" />
          {scene.page !== null && (
            <span className="page-number" aria-hidden="true">
              {scene.page}.
            </span>
          )}
          <article className="script-scene" id={`scene-${scene.number}`}>
            <p className="scene-heading" data-testid="scene-heading">
              <span className="scene-number is-left" aria-hidden="true">
                {scene.number}
              </span>
              {scene.slug}
              <span className="scene-number is-right" aria-hidden="true">
                {scene.number}
              </span>
            </p>
            {scene.lines.map((line, index) => {
              const annotation = line.flag && resolveFlag ? resolveFlag(line.flag) : null;
              return (
                <ScriptLineView
                  // Line order is the line's identity within a scene.
                  // eslint-disable-next-line react/no-array-index-key
                  key={`${scene.number}-${index}`}
                  line={line}
                  annotation={annotation}
                  selected={Boolean(annotation && annotation.itemId === selectedItemId)}
                  onSelectFlag={onSelectFlag}
                />
              );
            })}
          </article>
        </section>
      ))}
    </div>
  );
}

export default ScreenplayViewer;
