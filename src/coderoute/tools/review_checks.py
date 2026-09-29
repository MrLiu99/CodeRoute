"""Additional tests run on a disposable copy, never in the repair workspace."""
import ast
from dataclasses import asdict

from .workspace import Workspace
from .pytest_runner import run_tests


class ReviewChecks:
    def __init__(self, root, limit):
        self.root = root
        self.limit = limit
        self.probes = []
        self.executions = 0
        self.revision = None
        self.last_result = None

    def add(self, requirement_ids, reason, code, allowed):
        if (not isinstance(requirement_ids, list) or not requirement_ids
                or not all(isinstance(i, str) and i in allowed for i in requirement_ids)
                or len(set(requirement_ids)) != len(requirement_ids)):
            raise ValueError('Use distinct IDs from issue_requirements')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('Explain the requirement checked by this test')
        if not isinstance(code, str) or not code.strip() or len(code) > 12000:
            raise ValueError('Provide pytest code of at most 12000 characters')
        try:
            tree = ast.parse(code)
        except SyntaxError as error:
            raise ValueError('Supplemental test syntax is invalid: ' + str(error)) from None
        tests = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_')]
        if not 1 <= len(tests) <= 3:
            raise ValueError('Provide one to three focused pytest test functions per probe, not a large generated suite')
        if any(p['code'] == code for p in self.probes):
            return
        if len(self.probes) >= self.limit:
            raise ValueError('Supplemental test limit reached; existing tests cannot be removed')
        self.probes.append({'requirement_ids': requirement_ids, 'reason': reason, 'code': code})
        self.revision = None

    def run(self, workspace, timeout, output_limit):
        self.executions += 1
        root = self.root / ('review-check-' + str(self.executions))
        root.mkdir()
        revision = workspace.revision()
        copy = Workspace(workspace.root, root)
        target = copy.root / '__coderoute_review__'
        if target.exists():
            raise ValueError('Reserved review-check directory exists in source')
        target.mkdir()
        for index, probe in enumerate(self.probes):
            (target / ('test_probe_' + str(index) + '.py')).write_text(probe['code'], encoding='utf-8')
        result = run_tests(copy, root, 1, timeout, output_limit, ['__coderoute_review__'])
        # run_tests also rejects mutations to the disposable copy during execution.
        if workspace.revision() != revision:
            result.status = 'repair_workspace_changed_during_review_check'
        self.revision = revision
        self.last_result = {**asdict(result), 'revision': revision, 'probe_count': len(self.probes),
                            'artifact_directory': str(root), 'scope': 'model_authored_supplemental_tests'}
        return self.last_result

    def passed(self, revision):
        return bool(self.probes and self.revision == revision and self.last_result
                    and self.last_result['status'] == 'passed')
