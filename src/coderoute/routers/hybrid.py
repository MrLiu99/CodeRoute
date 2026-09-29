import math
from dataclasses import asdict

from .base import BaseRouter, RouteDecision
from .lightweight import LightweightRouter
from .llm import LLMRouter
from .rules import RuleGate


class HybridRouter(BaseRouter):
    name = "hybrid"

    def __init__(self, threshold=0.65, lightweight=None, strong=None):
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("confidence_threshold must be a finite number in [0,1]")
        self.threshold = threshold
        self.lightweight = lightweight or LightweightRouter()
        self.strong = strong or LLMRouter()

    def route(self, state, query=None):
        allowed, reason = RuleGate().allowed(state)
        if len(allowed) == 1:
            return RouteDecision(allowed[0], "rule", reason)
        if query is None:
            raise ValueError("Hybrid routing requires both model tiers")
        attempts = []
        try:
            light = self.lightweight.route(state, lambda messages: query(messages, tier="lightweight"))
            RuleGate().validate(state, light.choice)
            attempts.append(asdict(light))
            if light.confidence >= self.threshold:
                light.attempts = attempts
                return light
            escalation = "low_confidence"
        except (ValueError, RuntimeError, OSError) as error:
            # Budget exhaustion is a separate exception and must never trigger another call.
            escalation = "lightweight_error"
            attempts.append({"source": "lightweight", "error_type": type(error).__name__})
        strong = self.strong.route(state, lambda messages: query(messages, tier="strong"))
        RuleGate().validate(state, strong.choice)
        attempts.append(asdict(strong))
        strong.escalation_reason = escalation
        strong.attempts = attempts
        return strong
