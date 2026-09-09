import React from "react";
import type { JudgeDimensionScore } from "@clearcut/contracts";
import { Badge, DataTable } from "../../components/ds";
import {
  DIMENSION_STATUS_LABELS,
  dimensionLabel,
  dimensionStatusTone,
  hasRenderableScore,
  meterPercent,
} from "./rubricPresentation";

export interface RubricTableProps {
  dimensions: readonly JudgeDimensionScore[];
}

/**
 * The dimensions the judge graded, one row each.
 *
 * A dimension whose status is `incomplete` or `not_applicable` carries no score.
 * It renders as not-scored — no meter and no number — because a zero-width meter
 * or a printed `0` would read as a failing grade for something that was never
 * graded. A `failed` dimension does render its number: the judge reached a
 * verdict there.
 */
export function RubricTable({ dimensions }: RubricTableProps) {
  const rows = dimensions.map((dimension) => {
    const label = dimensionLabel(dimension.dimension);
    const scored = hasRenderableScore(dimension);
    return [
      <>
        <strong className="small">{label.plain}</strong>
        {dimension.rationale && (
          <>
            <br />
            <span className="small muted">{dimension.rationale}</span>
          </>
        )}
      </>,
      scored ? (
        <div className="score-cell">
          <span className="meter" aria-hidden="true">
            <span style={{ width: `${meterPercent(dimension.score as number)}%` }} />
          </span>
          <span className="mono">{dimension.score}</span>
        </div>
      ) : (
        <Badge tone={dimensionStatusTone(dimension.status)}>
          {DIMENSION_STATUS_LABELS[dimension.status] ?? dimension.status}
        </Badge>
      ),
      <span className="small muted">{label.formal}</span>,
    ];
  });

  return (
    <div data-testid="rubric-visualizer">
      <DataTable
        caption="Judge rubric scores for this graded run"
        columns={[
          { label: "Graded on" },
          { label: "Score" },
          { label: "Rubric dimension" },
        ]}
        rows={rows}
      />
    </div>
  );
}

export default RubricTable;
