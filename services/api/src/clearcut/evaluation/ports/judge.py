from abc import ABC, abstractmethod

from clearcut.detection.domain.candidates import CandidateItem
from clearcut.evaluation.domain.gates import GateResult
from clearcut.evaluation.domain.rubric import JudgeVerdict


class JudgePort(ABC):
    @abstractmethod
    def evaluate_stage(
        self,
        stage: str,
        candidates: list[CandidateItem],
        gate_results: list[GateResult],
    ) -> list[JudgeVerdict]:
        pass
