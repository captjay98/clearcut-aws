from clearcut.detection.domain.candidates import CandidateItem
from clearcut.evaluation.domain.gates import GateResult, GateSeverity
from clearcut.evaluation.domain.rubric import (
    DimensionStatus,
    JudgeDimension,
    JudgeVerdict,
    get_stage_eligible_dimensions,
)
from clearcut.evaluation.ports.judge import (
    JudgeAttemptMetadata,
    JudgeInvocationMetadata,
    JudgePort,
    JudgeRequest,
    JudgeSuccess,
    TokenUsage,
)


class HermeticJudgeAdapter(JudgePort):
    @property
    def requested_model(self) -> str:
        return "hermetic-test-only"

    async def evaluate(self, request: JudgeRequest) -> JudgeSuccess:
        usage = TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)
        verdicts = self.evaluate_stage(
            request.stage,
            list(request.candidates),
            list(request.gate_results),
        )
        attempt = JudgeAttemptMetadata(
            ordinal=1,
            status="succeeded",
            returned_model="hermetic-test-only",
            response_id="hermetic-test-only",
            usage=usage,
            latency_ms=0,
            error=None,
        )
        return JudgeSuccess(
            verdicts=tuple(verdicts),
            critique="Hermetic test-only evaluation.",
            metadata=JudgeInvocationMetadata(
                requested_model="hermetic-test-only",
                returned_model="hermetic-test-only",
                response_id="hermetic-test-only",
                usage=usage,
                latency_ms=0,
                repair_count=0,
                attempts=(attempt,),
            ),
        )

    def evaluate_stage(
        self,
        stage: str,
        candidates: list[CandidateItem],
        gate_results: list[GateResult],
    ) -> list[JudgeVerdict]:
        eligible = get_stage_eligible_dimensions(stage)
        blockers = [g for g in gate_results if not g.passed and g.severity == GateSeverity.BLOCKER]

        verdicts: list[JudgeVerdict] = []
        for dim in JudgeDimension:
            if dim not in eligible:
                verdicts.append(
                    JudgeVerdict.create(
                        dimension=dim,
                        status=DimensionStatus.NOT_APPLICABLE,
                        score=None,
                        rationale=f"Dimension {dim.value} not evaluated at stage '{stage}'",
                    )
                )
            elif blockers:
                verdicts.append(
                    JudgeVerdict.create(
                        dimension=dim,
                        status=DimensionStatus.FAILED,
                        score=0.0,
                        rationale="Deterministic blockers failed",
                    )
                )
            else:
                # Default baseline score for eligible detection dimensions
                score = 90.0 if dim == JudgeDimension.DETECTION_RECALL else 85.0
                verdicts.append(
                    JudgeVerdict.create(
                        dimension=dim,
                        status=DimensionStatus.SCORED,
                        score=score,
                        rationale=f"Hermetic evaluation passed for {dim.value}",
                    )
                )

        return verdicts
