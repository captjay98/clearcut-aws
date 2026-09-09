import React from "react";
import type { LearningCandidate } from "@clearcut/contracts";
import { Badge, Banner, Card, StatGrid } from "../../components/ds";
import {
  LEARNING_SCOPE_LABELS,
  LEARNING_STAGE_LABELS,
  formatPassRate,
  formatStamp,
  learningStageActions,
  learningStageTone,
  promotionGateShortfall,
} from "./rubricPresentation";

export interface LearningCandidateCardProps {
  candidate: LearningCandidate;
  /** False for every role but Owner; the server authorizes again regardless. */
  canGovern: boolean;
  pending: boolean;
  error?: string | null;
  onPromote: (candidateId: string) => void;
  onRollback: (candidateId: string) => void;
}

/**
 * One bounded learning candidate and the governed actions its stage allows.
 *
 * The actions follow the server's stage machine, not the storyboard: adopting is
 * reachable only from the 10% trial, reverting only from the trial or an adopted
 * change, and a reverted candidate is terminal. A stage with no action explains
 * why instead of offering a button that would be refused.
 */
export function LearningCandidateCard({
  candidate,
  canGovern,
  pending,
  error,
  onPromote,
  onRollback,
}: LearningCandidateCardProps) {
  const actions = learningStageActions(candidate.stage);
  const shortfall = actions.promote ? promotionGateShortfall(candidate) : null;
  const regression = `${candidate.regressionCasesPassed}/${candidate.regressionCasesTotal}`;

  return (
    <Card
      eyebrow={LEARNING_SCOPE_LABELS[candidate.scope] ?? candidate.scope}
      title={candidate.title ?? "Untitled candidate"}
      badge={
        <Badge tone={learningStageTone(candidate.stage)}>
          {LEARNING_STAGE_LABELS[candidate.stage] ?? candidate.stage}
        </Badge>
      }
      testId="learning-candidate-card"
      actions={
        canGovern ? (
          <>
            {actions.promote && (
              <button
                className="button button-primary"
                type="button"
                disabled={pending}
                onClick={() => onPromote(candidate.candidateId)}
              >
                {pending ? "Working…" : actions.promote.label}
              </button>
            )}
            {actions.rollback && (
              <button
                className="button button-danger"
                type="button"
                disabled={pending}
                onClick={() => onRollback(candidate.candidateId)}
              >
                {pending ? "Working…" : actions.rollback.label}
              </button>
            )}
          </>
        ) : undefined
      }
    >
      {candidate.summary && <p className="small">{candidate.summary}</p>}
      <p className="small muted gap-t-2">
        A candidate may only change query phrasing, retrieval or category
        examples, a prompt refinement, or an organization preference. It touches no
        permissions, no blocking rules, and no category definitions.
      </p>

      <div className="gap-t-5">
        <StatGrid
          columns={4}
          stats={[
            {
              label: "Past cases",
              value: regression,
              hint:
                candidate.regressionCasesTotal === 0
                  ? "none run yet"
                  : candidate.regressionCasesPassed === candidate.regressionCasesTotal
                    ? "all still pass"
                    : "some failing",
              tone:
                candidate.regressionCasesTotal === 0
                  ? "is-warning"
                  : candidate.regressionCasesPassed === candidate.regressionCasesTotal
                    ? "is-success"
                    : "is-danger",
            },
            {
              label: "10% trial",
              value: formatPassRate(candidate.canaryPassRate),
              hint: "passing rate",
            },
            { label: "Version", value: candidate.version },
            {
              label:
                candidate.stage === "rolled_back"
                  ? "Reverted"
                  : candidate.stage === "promoted"
                    ? "Adopted"
                    : "Raised",
              value: formatStamp(
                candidate.rolledBackAt ?? candidate.promotedAt ?? candidate.createdAt,
              ),
            },
          ]}
        />
      </div>

      {candidate.rollbackReason && (
        <p className="small gap-t-4">Reverted because: {candidate.rollbackReason}</p>
      )}

      {actions.waiting && (
        <div className="gap-t-4">
          <Banner icon="○" message={actions.waiting} />
        </div>
      )}

      {shortfall && (
        <div className="gap-t-4">
          <Banner
            tone="is-warning"
            icon="⚠"
            title="Adopting would be refused right now"
            message={shortfall}
          />
        </div>
      )}

      {!canGovern && (actions.promote || actions.rollback) && (
        <div className="gap-t-4">
          <Banner
            icon="⚖"
            message="Adopting or reverting a learning candidate is an Owner decision. The record shows the current stage; the action is not yours to take."
          />
        </div>
      )}

      {error && (
        <div className="gap-t-4">
          <Banner
            tone="is-danger"
            icon="⚠"
            title="The stage did not change"
            message={error}
            role="alert"
          />
        </div>
      )}
    </Card>
  );
}

export default LearningCandidateCard;
