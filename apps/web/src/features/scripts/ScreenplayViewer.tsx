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
  /** Resolve every flag on a line (multiple terms may share one action line). */
  resolveLineFlags?: (line: ScriptLine) => FlagAnnotation[];
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

type TextSegment = { text: string; annotation?: FlagAnnotation };

/** Non-overlapping underlined spans, in reading order. */
function buildSegments(text: string, annotations: FlagAnnotation[]): TextSegment[] {
  const marks: { start: number; end: number; annotation: FlagAnnotation }[] = [];
  const lower = text.toLowerCase();
  for (const annotation of annotations) {
    const term = annotation.term.toLowerCase();
    if (!term) continue;
    const start = lower.indexOf(term);
    if (start < 0) continue;
    marks.push({ start, end: start + term.length, annotation });
  }
  marks.sort((a, b) => a.start - b.start || b.end - a.end);
  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const mark of marks) {
    if (mark.start < cursor) continue;
    if (mark.start > cursor) segments.push({ text: text.slice(cursor, mark.start) });
    segments.push({
      text: text.slice(mark.start, mark.end),
      annotation: mark.annotation,
    });
    cursor = mark.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });
  if (segments.length === 0) segments.push({ text });
  return segments;
}

/**
 * Renders one screenplay line. Flagged terms become margin-marked underlines
 * rather than inline chips, so the reading line stays intact — the mock's
 * scriptLine() behaviour. Multiple flags on one line each get a mark.
 */
function ScriptLineView({
  line,
  annotations,
  selectedItemId,
  onSelectFlag,
}: {
  line: ScriptLine;
  annotations: FlagAnnotation[];
  selectedItemId?: string | null;
  onSelectFlag?: (annotation: FlagAnnotation) => void;
}) {
  const className = LINE_CLASS[line.type] ?? "script-action";

  if (annotations.length === 0) {
    return <p className={className}>{line.text}</p>;
  }

  const segments = buildSegments(line.text, annotations);

  return (
    <p className={className}>
      {annotations.length > 0 && (
        <span className="margin-marks" aria-hidden="true">
          {annotations.map((annotation) => {
            const selected = annotation.itemId === selectedItemId;
            return (
              <span
                key={annotation.itemId}
                className={`margin-mark ${annotation.severityClass} ${selected ? "is-selected" : ""}`.trim()}
                title={`${annotation.term} — ${annotation.shortCategory}`}
              >
                <span className="mark-glyph">{annotation.glyph}</span>
                {annotation.shortCategory}
              </span>
            );
          })}
        </span>
      )}
      {segments.map((segment, index) => {
        if (!segment.annotation) {
          return <React.Fragment key={`t-${index}`}>{segment.text}</React.Fragment>;
        }
        const annotation = segment.annotation;
        const selected = annotation.itemId === selectedItemId;
        return (
          <button
            key={`${annotation.itemId}-${index}`}
            className={`flag ${annotation.severityClass} ${selected ? "is-selected" : ""}`.trim()}
            type="button"
            aria-pressed={selected}
            title={`${annotation.shortCategory} — ${annotation.status}`}
            onClick={() => onSelectFlag?.(annotation)}
          >
            {segment.text}
          </button>
        );
      })}
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
  resolveLineFlags,
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
              const annotations = resolveLineFlags ? resolveLineFlags(line) : [];
              return (
                <ScriptLineView
                  // Line order is the line's identity within a scene.
                  // eslint-disable-next-line react/no-array-index-key
                  key={`${scene.number}-${index}`}
                  line={line}
                  annotations={annotations}
                  selectedItemId={selectedItemId}
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
