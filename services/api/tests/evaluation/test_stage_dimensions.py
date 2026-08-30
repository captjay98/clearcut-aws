from clearcut.evaluation.domain.rubric import JudgeDimension


def test_all_ten_dimensions_declared():
    assert len(JudgeDimension) == 10
    expected_dimensions = {
        "detection_recall",
        "claim_grounding",
        "citation_provenance",
        "source_authority",
        "conflict_identification",
        "appropriate_uncertainty",
        "rewrite_usefulness",
        "rescan_correctness",
        "legal_boundary",
        "tool_efficiency",
    }
    assert {d.value for d in JudgeDimension} == expected_dimensions

def test_detection_stage_dimension_eligibility():
    from clearcut.evaluation.domain.rubric import get_stage_eligible_dimensions

    detection_eligible = get_stage_eligible_dimensions("detection")
    assert JudgeDimension.DETECTION_RECALL in detection_eligible
    assert JudgeDimension.APPROPRIATE_UNCERTAINTY in detection_eligible
    assert JudgeDimension.LEGAL_BOUNDARY in detection_eligible
    assert JudgeDimension.TOOL_EFFICIENCY in detection_eligible

    # Downstream dimensions must NOT be eligible during detection stage
    assert JudgeDimension.CLAIM_GROUNDING not in detection_eligible
    assert JudgeDimension.CITATION_PROVENANCE not in detection_eligible
    assert JudgeDimension.REWRITE_USEFULNESS not in detection_eligible
