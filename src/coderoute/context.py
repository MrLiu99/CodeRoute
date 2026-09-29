from dataclasses import asdict

from .tools.workspace import files
from .tools.files import FileTools
from .requirements import issue_requirements


class ContextBuilder:
    def __init__(self, workspace, limit):
        self.workspace = workspace
        self.limit = limit

    def build(self, role, state):
        context = {"issue": state.issue, "revision": state.revision,
                   "recent_roles": state.history[-6:], "issue_requirements": issue_requirements(state.issue)}
        paths = [p.relative_to(self.workspace.root).as_posix() for p in files(self.workspace.root)]
        visible = []
        used = 0
        for path in paths:
            if used + len(path) > self.limit or len(visible) >= 200:
                break
            visible.append(path)
            used += len(path)
        context.update(repository_files=visible, repository_files_truncated=len(visible) < len(paths))
        if role == "analyzer":
            context.update({"previous_hypothesis": state.analysis,
                            "debug_feedback": state.debug_feedback,
                            "review_feedback": state.review})
        elif role == "developer":
            context.update({"analysis": state.analysis, "debug_feedback": state.debug_feedback,
                            "review_feedback": state.review,
                            "test_result": asdict(state.test_result) if state.test_result else None})
        elif role == "debugger":
            context.update({"analysis": state.analysis,
                            "test_result": asdict(state.test_result) if state.test_result else None})
        elif role == "reviewer":
            context.update({"analysis": state.analysis, "patch_summary": state.developer_result,
                            "test_result": asdict(state.test_result) if state.test_result else None})
        if role in {"developer", "debugger", "reviewer"}:
            diff = self.workspace.diff()
            context.update({"diff": diff[:self.limit], "diff_truncated": len(diff) > self.limit,
                            "modified_files": self.workspace.modified_files()})
        if role in {'analyzer', 'developer', 'debugger', 'reviewer'}:
            # Supply bounded direct evidence, not merely filenames or a claimed test summary.
            candidates = list(dict.fromkeys(context.get("modified_files", []) + [p for p in paths if p.endswith('.py')]))
            evidence = []
            remaining = self.limit
            for path in candidates:
                if remaining <= 0:
                    break
                try:
                    item = FileTools(self.workspace, remaining).read_file(path)
                except (OSError, ValueError):
                    continue
                evidence.append(item)
                remaining -= len(item["content"]) + len(path)
            context.update(review_evidence=evidence,
                           review_evidence_truncated=len(evidence) < len(candidates) or any(e["truncated"] for e in evidence))
        return context
