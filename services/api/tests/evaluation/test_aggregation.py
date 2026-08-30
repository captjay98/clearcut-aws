import uuid6
from clearcut.evaluation.adapters.hermetic_judge import HermeticJudgeAdapter
from clearcut.evaluation.application.evaluate import EvaluationService
from clearcut.evaluation.domain.rubric import DimensionStatus, JudgeDimension, JudgeVerdict


def test_arithmetic_mean_over_eligible_scored_dimensions():
    judge = HermeticJudgeAdapter()
    service = EvaluationService(judge=judge)

    run_id = uuid6.uuid7()
    org_id = uuid6.uuid7()
    project_id = uuid6.uuid7()

    verdicts = [
        JudgeVerdict.create(
            JudgeDimension.DETECTION_RECALL,
            DimensionStatus.SCORED,
            90.0,
            "High recall",
        ),
        JudgeVerdict.create(
            JudgeDimension.APPROPRIATE_UNCERTAINTY,
            DimensionStatus.SCORED,
            80.0,
            "Proper uncertainty",
        ),
        JudgeVerdict.create(
            JudgeDimension.LEGAL_BOUNDARY,
            DimensionStatus.SCORED,
            100.0,
            "No legal advice given",
        ),
        JudgeVerdict.create(
            JudgeDimension.TOOL_EFFICIENCY,
            DimensionStatus.SCORED,
            90.0,
            "Efficient latency",
        ),
        # Downstream dimensions
        JudgeVerdict.create(
            JudgeDimension.CLAIM_GROUNDING,
            DimensionStatus.NOT_APPLICABLE,
            None,
            "Pending research",
        ),
        JudgeVerdict.create(
            JudgeDimension.CITATION_PROVENANCE,
            DimensionStatus.NOT_APPLICABLE,
            None,
            "Pending research",
        ),
        JudgeVerdict.create(
            JudgeDimension.SOURCE_AUTHORITY,
            DimensionStatus.NOT_APPLICABLE,
            None,
            "Pending research",
        ),
        JudgeVerdict.create(
            JudgeDimension.CONFLICT_IDENTIFICATION,
            DimensionStatus.NOT_APPLICABLE,
            None,
            "Pending research",
        ),
        JudgeVerdict.create(
            JudgeDimension.REWRITE_USEFULNESS,
            DimensionStatus.NOT_APPLICABLE,
            None,
            "Pending rewrites",
        ),
        JudgeVerdict.create(
            JudgeDimension.RESCAN_CORRECTNESS,
            DimensionStatus.NOT_APPLICABLE,
            None,
            "Pending revisions",
        ),
    ]

    evaluation = service.aggregate_evaluation(
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        stage="detection",
        verdicts=verdicts,
        blockers_count=0,
    )

    assert evaluation.scored_dimensions_count == 4
    # (90 + 80 + 100 + 90) / 4 = 360 / 4 = 90.0
    assert evaluation.headline_score == 90.0
    assert len(evaluation.verdicts) == 10
