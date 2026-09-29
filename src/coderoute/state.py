from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TestResult:
    status: str
    revision: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    returncode: Optional[int] = None
    log_path: str = ""
    summary: str = ""


@dataclass
class RepairState:
    issue: str
    source_repo: str
    workspace: str
    mode: str
    revision: str = ""
    status: str = "running"
    stop_reason: str = ""
    steps: int = 0
    modified_files: list = field(default_factory=list)
    test_result: Optional[TestResult] = None
    current_agent: Optional[str] = None
    analysis: dict = field(default_factory=dict)
    debug_feedback: dict = field(default_factory=dict)
    developer_result: dict = field(default_factory=dict)
    review: dict = field(default_factory=dict)
    review_revision: Optional[str] = None
    history: list = field(default_factory=list)

    def update_revision(self, revision):
        if revision != self.revision:
            self.revision = revision
            self.test_result = None
            self.review = {}
            self.review_revision = None

    def verified(self):
        return bool(self.test_result and self.test_result.status == "passed"
                    and self.test_result.revision == self.revision)

    def accepted(self):
        return bool(self.verified() and self.review.get("accepted") is True
                    and self.review_revision == self.revision)
