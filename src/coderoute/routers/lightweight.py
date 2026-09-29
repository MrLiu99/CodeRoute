from .llm import LLMRouter


class LightweightRouter(LLMRouter):
    """Chat-compatible decision adapter; no claim about a specific Jev protocol."""
    name = "lightweight"

    def route(self, state, query=None):
        decision = super().route(state, query)
        decision.source = "lightweight"
        return decision
