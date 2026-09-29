import json

from .client import ModelReply


class LightweightDemoClient:
    """High-confidence routing except uncertain failure diagnosis to exercise escalation."""
    mode = "mock"

    def complete(self, messages, timeout):
        summary = json.loads(messages[-1]["content"])
        failed = summary["current_agent"] == "tester"
        return ModelReply(json.dumps({
            "choice": "debugger" if failed else "developer",
            "confidence": 0.4 if failed else 0.9,
            "reason": "Scripted low-confidence failure diagnosis" if failed else "Scripted clear patch decision",
        }), model="scripted-lightweight")
