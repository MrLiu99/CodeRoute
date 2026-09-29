import json

from .client import ModelReply


class MultiDemoClient:
    """Scripted role fixture; tools and tests are real, reasoning is not."""
    mode = "mock"

    def __init__(self):
        self.actions = iter([
            ("read_file", {"path": "config_reader.py"}),
            ("submit", {"suspected_files": ["config_reader.py"],
                        "hypothesis": "Blank text reaches json.loads", "confidence": 0.9}),
            ("edit_file", {"path": "config_reader.py", "old": "    return json.loads(text)",
                           "new": '    if text == "":\n        return {}\n    return json.loads(text)'}),
            ("submit", {"change_summary": "Handle empty strings"}),
            ("submit", {"failure_type": "incomplete_patch", "reason": "Whitespace remains unhandled",
                        "recommended_next_agent": "developer", "confidence": 0.9}),
            ("edit_file", {"path": "config_reader.py", "old": 'if text == "":',
                           "new": "if not text.strip():"}),
            ("submit", {"change_summary": "Handle whitespace-only text"}),
            ("read_file", {"path": "tests/test_config_reader.py"}),
            ("submit", {"accepted": True, "risk_level": "low", "reason": "Focused fix with passing tests",
                        "recommended_next_agent": "developer", "confidence": 0.9}),
        ])

    def complete(self, messages, timeout):
        if messages[0]["content"].startswith("You are CodeRoute's runtime router."):
            summary = json.loads(messages[-1]["content"])
            allowed = summary["allowed_actions"]
            if len(allowed) == 1:
                choice = allowed[0]
            elif summary["current_agent"] == "tester" and "debugger" in allowed:
                choice = "debugger"
            else:
                choice = "developer"
            return ModelReply(json.dumps({"choice": choice, "confidence": 0.9,
                "reason": "Scripted routing fixture, not learned reasoning"}), model="scripted-router")
        tool, args = next(self.actions)
        if tool == 'submit':
            context = json.loads(messages[1]['content'])
            if 'suspected_files' in args:
                args['requirement_plan'] = [{'id': r['id'], 'check': 'Check blank input handling and preservation'}
                                           for r in context['issue_requirements']]
            if 'accepted' in args:
                args['requirement_checks'] = [{'id': r['id'], 'status': 'met', 'reason': 'Scripted blank handling check',
                    'evidence': [{'path': 'config_reader.py', 'quote': 'return {}'}]}
                    for r in context['issue_requirements']]
        return ModelReply(json.dumps({"tool": tool, "args": args}), model="scripted-multi-demo")
