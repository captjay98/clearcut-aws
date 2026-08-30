from abc import ABC, abstractmethod

from clearcut.detection.domain.candidates import CandidateItem
from clearcut.scripts.domain.elements import ScriptElement


class ModelRuntimePort(ABC):
    @abstractmethod
    def detect_candidates(self, elements: list[ScriptElement]) -> list[CandidateItem]:
        pass
