import React from "react";
import type { TrustEvaluation } from "@clearcut/contracts";
import { Badge, Card } from "../../components/ds";
import {
  EVALUATION_STAGE_LABELS,
  dimensionLabel,
  formatStamp,
  readHeadline,
  weakestGradedDimension,
} from "./rubricPresentation";

export interface TrustScoreCardProps {
  evaluation: TrustEvaluation;
}

/**
 * The headline card: the server-derived score, what it is the mean of, and the
 * weakest dimension behind it.
 *
 * `headlineScore` is rendered exactly as received. It is not recomputed from the
 * dimension rows, so the ring can never disagree with the table beneath it. A
 * null headline draws no ring at all: an empty ring reads as a zero, and nothing
 * here was graded zero — nothing was graded.
 */
export function TrustScoreCard({ evaluation }: TrustScoreCardProps) {
  const headline = readHeadline(evaluation);
  const weakest = weakestGradedDimension(evaluation.dimensions);

  return (
    <Card accent testId="trust-score-summary">
      <div className="cluster score-summary">
        {headline.score === null ? (
          <div className="stack-sm" data-testid="trust-score-unscored">
            <Badge tone="is-warning">Not scored</Badge>
          </div>
        ) : (
          <div
            className="score-ring"
            style={{ "--score": headline.score } as React.CSSProperties}
            data-score={headline.score}
            data-testid="trust-score-ring"
            role="img"
            aria-label={`Quality score ${headline.score} out of 100, the mean of ${evaluation.scoredDimensionsCount} graded dimension${evaluation.scoredDimensionsCount === 1 ? "" : "s"}`}
          />
        )}
        <div>
          <h2>{headline.title}</h2>
          <p className="small muted">
            {headline.detail}
            {weakest && (
              <>
                {" Weakest: "}
                {dimensionLabel(weakest.dimension).plain.toLowerCase()} at{" "}
                <span className="mono">{weakest.score}</span>.
              </>
            )}
          </p>
          <p className="small muted gap-t-1">
            {EVALUATION_STAGE_LABELS[evaluation.stage] ?? evaluation.stage} · graded{" "}
            {formatStamp(evaluation.createdAt)}
          </p>
        </div>
      </div>
      {evaluation.critique && (
        <p className="small gap-t-4">{evaluation.critique}</p>
      )}
    </Card>
  );
}

export default TrustScoreCard;
