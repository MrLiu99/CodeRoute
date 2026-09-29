from ..tools.pytest_runner import run_tests


class TesterAgent:
    """Deterministic execution role: reports evidence without LLM inference."""
    def run(self, workspace, root, number, timeout, output_limit):
        return run_tests(workspace, root, number, timeout, output_limit)
