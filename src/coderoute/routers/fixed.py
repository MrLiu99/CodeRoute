from .base import BaseRouter, RouteDecision


class FixedRouter(BaseRouter):
    """Deterministic workflow with explicit failure/review branches; no model routing."""
    name = "fixed"

    def route(self, state, query=None):
        return RouteDecision(self.choose(state), "fixed", "Fixed workflow transition")

    def choose(self, state):
        previous = state.current_agent
        if previous is None:
            return "analyzer"
        if previous == "analyzer":
            return "developer"
        if previous == "developer":
            return "tester"
        if previous == "tester":
            return "reviewer" if state.verified() else "debugger"
        if previous == "debugger":
            return state.debug_feedback["recommended_next_agent"]
        if previous == "reviewer":
            if state.accepted():
                return "finish"
            return state.review.get("recommended_next_agent", "developer")
        raise ValueError("Invalid workflow state")
