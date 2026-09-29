class RuleGate:
    """Shared admissibility constraints, also enforced after every router decision."""
    def allowed(self, state):
        if state.accepted():
            return ("finish",), "Current revision passed tests and review"
        if not state.analysis:
            return ("analyzer",), "A localization hypothesis is required"
        if state.current_agent == "developer":
            return ("tester",), "Developer must be followed by test execution"
        if state.verified():
            if state.review_revision == state.revision and state.review.get("accepted") is False:
                return ("analyzer", "developer"), "Review rejected this revision; address its feedback"
            return ("reviewer",), "Current passing tests require review"
        if state.current_agent == "debugger":
            return ("analyzer", "developer"), "Choose re-localization or patching from debug evidence"
        if state.current_agent == "analyzer":
            return ("analyzer", "developer"), "Choose further analysis or implementation"
        if state.test_result and state.test_result.status != "passed":
            return ("analyzer", "developer", "debugger"), "Tests failed; choose the appropriate recovery role"
        return ("analyzer", "developer"), "Additional analysis or implementation is needed"

    def validate(self, state, choice):
        allowed, reason = self.allowed(state)
        if choice not in allowed:
            raise ValueError(f"Illegal route {choice!r}; allowed={allowed}. {reason}")
