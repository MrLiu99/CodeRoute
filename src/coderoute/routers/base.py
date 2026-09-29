from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RouteDecision:
    choice: str
    source: str
    reason: str
    confidence: Optional[float] = None
    escalation_reason: Optional[str] = None
    attempts: list = field(default_factory=list)


class BaseRouter:
    name = "base"

    def route(self, state, query=None):
        raise NotImplementedError
