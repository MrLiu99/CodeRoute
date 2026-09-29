class StateSummarizer:
    """Bounded runtime evidence, excluding repository contents and full diffs."""
    def summarize(self, state, allowed, reason):
        return {
            "issue": state.issue[:2000],
            "current_agent": state.current_agent,
            "hypothesis": str(state.analysis.get("hypothesis", ""))[:1500],
            "hypothesis_confidence": state.analysis.get("confidence"),
            "modified_files": state.modified_files[:30],
            "test_status": state.test_result.status if state.test_result else "unverified",
            "test_summary": state.test_result.summary[-2500:] if state.test_result else "",
            "failure_type": state.debug_feedback.get("failure_type"),
            "debug_reason": str(state.debug_feedback.get("reason", ""))[:1500],
            "debug_recommendation": state.debug_feedback.get("recommended_next_agent"),
            "review_accepted": state.review.get("accepted"),
            "review_reason": str(state.review.get("reason", ""))[:1500],
            "review_recommendation": state.review.get("recommended_next_agent"),
            "recent_roles": state.history[-8:],
            "step": state.steps,
            "allowed_actions": list(allowed),
            "constraint_reason": reason,
        }
