from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol


@dataclass
class AgentOutput:
    role: str
    label: str
    score: float  # confidence 0~1
    rationale: str


class SentimentClassifier(Protocol):
    def predict(self, text: str) -> Dict[str, float]:
        """Return probability per label, e.g., {"긍정":0.7,"중립":0.2,"부정":0.1}."""


class Agent(Protocol):
    role: str

    def run(self, text: str) -> AgentOutput:
        ...

    def critique(self, text: str, others: Dict[str, AgentOutput]) -> AgentOutput:
        """Optional second-round adjustment based on others' opinions."""
        ...
