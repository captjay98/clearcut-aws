import type {
  DeterministicGateResult,
  JudgeDimensionScore,
  LearningCandidate,
  TrustEvaluation,
} from "@clearcut/contracts";
import type { Tone } from "../../components/ds";

/**
 * Reading vocabulary for the ten rubric dimensions.
 *
 * `plain` is what the surface leads with and `formal` is the rubric's own
 * wording, exactly as the canonical mock pairs them. Both are labels for the
 * server's token — nothing here changes which dimensions exist or what they
 * scored.
 */
export interface DimensionLabel {
  plain: string;
  formal: string;
}

const DIMENSION_LABELS: Readonly<Record<string, DimensionLabel>> = {
  detection_recall: {
    plain: "Finds what matters",
    formal: "Detection recall and category correctness",
  },
  claim_grounding: {
    plain: "Every claim points to its source",
    formal: "Claim-to-source grounding",
  },
  citation_provenance: {
    plain: "Provenance is complete",
    formal: "Citation and provenance completeness",
  },
  source_authority: {
    plain: "Prefers official, current sources",
    formal: "Source authority and freshness",
  },
  conflict_identification: {
    plain: "Spots disagreements",
    formal: "Conflict identification",
  },
  appropriate_uncertainty: {
    plain: "Says what it is unsure of",
    formal: "Appropriate uncertainty",
  },
  rewrite_usefulness: {
    plain: "Rewrites are usable",
    formal: "Rewrite usefulness",
  },
  rescan_correctness: {
    plain: "Re-checks only what changed",
    formal: "Affected-item re-scan correctness",
  },
  legal_boundary: {
    plain: "Draws no legal conclusions",
    formal: "Legal-boundary compliance",
  },
  tool_efficiency: {
    plain: "Stays inside its budget",
    formal: "Tool efficiency, latency and cost",
  },
};

function humanizeToken(token: string): string {
  return token.replace(/_/g, " ").replace(/^./, (first) => first.toUpperCase());
}

/** An unmapped dimension is still shown, under its own token, never dropped. */
export function dimensionLabel(dimension: string): DimensionLabel {
  return (
    DIMENSION_LABELS[dimension] ?? {
      plain: humanizeToken(dimension),
      formal: dimension,
    }
  );
}

/* ── Dimension scoring ──────────────────────────────────────────────────── */

export const DIMENSION_STATUS_LABELS: Readonly<
  Record<JudgeDimensionScore["status"], string>
> = {
  scored: "Graded",
  incomplete: "Not graded",
  not_applicable: "Not applicable at this stage",
  failed: "Failed",
};

/**
 * Whether a dimension carries a number a reader may compare against others.
 *
 * `incomplete` and `not_applicable` carry no score. Drawing them as a zero-width
 * meter or printing `0` would read as a failing grade for something that was
 * never graded, so they are reported as absent instead. A `failed` dimension is
 * a judged zero and does render, because the judge did reach a verdict.
 */
export function hasRenderableScore(
  dimension: Pick<JudgeDimensionScore, "status" | "score">,
): boolean {
  if (dimension.score === null) return false;
  return dimension.status === "scored" || dimension.status === "failed";
}

export function dimensionStatusTone(status: JudgeDimensionScore["status"]): Tone {
  if (status === "failed") return "is-danger";
  if (status === "incomplete") return "is-warning";
  return "";
}

/** Scores are bounded 0..100 server-side; clamp defensively for the meter width. */
export function meterPercent(score: number): number {
  return Math.max(0, Math.min(100, score));
}

/* ── Headline ───────────────────────────────────────────────────────────── */

export interface HeadlineReading {
  /** The server-derived mean, rendered as given. Null when nothing was scored. */
  score: number | null;
  title: string;
  detail: string;
}

/**
 * The headline sentence beside the score ring.
 *
 * `headlineScore` is derived server-side as the mean of the dimensions that
 * carry a score, and is rendered exactly as received. It is never recomputed
 * here: a locally averaged number could disagree with the table printed beneath
 * it, which is the one thing this surface must never do. A null headline means
 * nothing was scored and is reported as such rather than as zero.
 */
export function readHeadline(evaluation: TrustEvaluation): HeadlineReading {
  const blockers = evaluation.blockersCount;
  const warnings = evaluation.gates.filter(
    (gate) => !gate.passed && gate.severity === "warning",
  ).length;

  if (evaluation.headlineScore === null) {
    return {
      score: null,
      title: "Not scored",
      detail:
        "This run persisted an evaluation, but no dimension carries a score yet, " +
        "so there is no honest mean to show.",
    };
  }

  const divisor = evaluation.scoredDimensionsCount;
  const graded = `Mean of ${divisor} graded dimension${divisor === 1 ? "" : "s"}.`;
  const title =
    blockers > 0
      ? `Blocked by ${blockers} check${blockers === 1 ? "" : "s"}`
      : warnings === 0
        ? "No warnings"
        : `${warnings} warning${warnings === 1 ? "" : "s"}`;

  return { score: evaluation.headlineScore, title, detail: graded };
}

/**
 * The weakest dimension among those actually graded, or null when none were.
 * Ungraded dimensions cannot be "weakest": they have no score to compare.
 */
export function weakestGradedDimension(
  dimensions: readonly JudgeDimensionScore[],
): JudgeDimensionScore | null {
  const graded = dimensions.filter(hasRenderableScore);
  if (graded.length === 0) return null;
  return graded.reduce((weakest, candidate) =>
    (candidate.score ?? 0) < (weakest.score ?? 0) ? candidate : weakest,
  );
}

/* ── Deterministic gates ────────────────────────────────────────────────── */

/**
 * A reading of the server's gate identifier. The raw `gateName` is displayed
 * beside it, so the reader can always see the token that was recorded.
 */
export function gateLabel(gateName: string): string {
  const withoutSuffix = gateName.replace(/Gate$/, "");
  const spaced = withoutSuffix
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .trim();
  if (spaced.length === 0) return gateName;
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

export function gateOutcome(gate: DeterministicGateResult): {
  label: string;
  tone: Tone;
} {
  if (gate.passed) return { label: "Pass", tone: "is-success" };
  if (gate.severity === "blocker") return { label: "Blocked", tone: "is-danger" };
  if (gate.severity === "warning") return { label: "Warn", tone: "is-warning" };
  return { label: "Note", tone: "" };
}

/* ── Evaluation stage ───────────────────────────────────────────────────── */

export const EVALUATION_STAGE_LABELS: Readonly<
  Record<TrustEvaluation["stage"], string>
> = {
  detection: "Detection pass",
  research: "Research pass",
  final: "Final pass",
};

/* ── Learning candidate lifecycle ───────────────────────────────────────── */

export const LEARNING_STAGE_LABELS: Readonly<
  Record<LearningCandidate["stage"], string>
> = {
  candidate: "Idea",
  shadow: "Tried in private",
  canary: "Testing on 10%",
  promoted: "Adopted",
  rolled_back: "Reverted",
};

export const LEARNING_SCOPE_LABELS: Readonly<
  Record<LearningCandidate["scope"], string>
> = {
  query_phrasing: "Query phrasing",
  retrieval_examples: "Retrieval examples",
  prompt_refinement: "Prompt refinement",
  org_preferences: "Organization preferences",
};

export function learningStageTone(stage: LearningCandidate["stage"]): Tone {
  if (stage === "promoted") return "is-success";
  if (stage === "rolled_back") return "is-danger";
  return "is-accent";
}

/**
 * The governed actions a stage actually offers.
 *
 * This mirrors the server's stage machine rather than the mock's fuller
 * storyboard. `promoteLearningCandidate` targets `promoted`, which is reachable
 * only from `canary`; `rollbackLearningCandidate` is reachable from `canary` and
 * `promoted`, and `rolled_back` is terminal. There is no endpoint that advances
 * `candidate → shadow` or `shadow → canary`, so those stages offer no button —
 * one that always failed would be worse than none, and `waiting` says why.
 */
export interface LearningStageActions {
  promote?: { label: string };
  rollback?: { label: string };
  /** Set when the stage is observable but not actionable from this surface. */
  waiting?: string;
}

export function learningStageActions(
  stage: LearningCandidate["stage"],
): LearningStageActions {
  switch (stage) {
    case "candidate":
      return {
        waiting:
          "Queued for a private trial. Adopting is only offered once the candidate " +
          "has reached the 10% trial, and the pipeline moves it there — no one " +
          "advances it by hand.",
      };
    case "shadow":
      return {
        waiting:
          "Running in private against past cases. Adopting is only offered once " +
          "the candidate has reached the 10% trial.",
      };
    case "canary":
      return {
        promote: { label: "Adopt it" },
        rollback: { label: "Revert" },
      };
    case "promoted":
      return { rollback: { label: "Revert to the old way" } };
    case "rolled_back":
      return {
        waiting:
          "Reverted, and terminal. A new candidate is raised rather than this one " +
          "being restarted, so the reverted decision stays on the record.",
      };
    default:
      return {};
  }
}

/**
 * The promotion gate as the server enforces it: every regression case passing,
 * at least one case, and a canary pass rate at or above 95%.
 *
 * Read locally only to explain a refusal in advance. The server remains the
 * authority — the control is still offered, and the server still decides.
 */
export const CANARY_PASS_RATE_THRESHOLD = 0.95;

export function promotionGateShortfall(
  candidate: Pick<
    LearningCandidate,
    "canaryPassRate" | "regressionCasesPassed" | "regressionCasesTotal"
  >,
): string | null {
  if (candidate.regressionCasesTotal === 0) {
    return "No regression cases have run yet, so there is nothing to promote on.";
  }
  if (candidate.regressionCasesPassed < candidate.regressionCasesTotal) {
    const failing = candidate.regressionCasesTotal - candidate.regressionCasesPassed;
    return `${failing} regression case${failing === 1 ? "" : "s"} still failing; promotion requires all of them to pass.`;
  }
  if (candidate.canaryPassRate < CANARY_PASS_RATE_THRESHOLD) {
    return `The 10% trial is passing ${formatPassRate(candidate.canaryPassRate)}; promotion requires at least ${formatPassRate(CANARY_PASS_RATE_THRESHOLD)}.`;
  }
  return null;
}

/* ── Formatting ─────────────────────────────────────────────────────────── */

export function formatStamp(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleString();
}

export function formatPassRate(rate: number): string {
  const bounded = Math.max(0, Math.min(1, rate));
  return `${Math.round(bounded * 100)}%`;
}
