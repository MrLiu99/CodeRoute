import argparse
import json
import uuid
from datetime import datetime
from pathlib import Path

from .config import Config, load_local_env
from .factory import build_harness


def main(argv=None):
    parser = argparse.ArgumentParser(description="CodeRoute Python repair harness")
    parser.add_argument("--repo", required=True)
    issue_group = parser.add_mutually_exclusive_group(required=True)
    issue_group.add_argument("--issue")
    issue_group.add_argument("--issue-file")
    parser.add_argument("--config")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--workflow", choices=["single", "fixed", "llm", "dynamic", "hybrid"], default="single",
                        help="single, fixed roles, LLM routing, or rule + LLM routing")
    parser.add_argument("--output", default="runs", help="Parent of unique run directories")
    args = parser.parse_args(argv)
    try:
        load_local_env(Path.cwd() / ".env")
        config = Config.load(args.config)
        issue = Path(args.issue_file).read_text(encoding="utf-8") if args.issue_file else args.issue
        if not issue.strip():
            raise ValueError("Issue must not be empty")
        if args.mode == "mock":
            manifest = Path(args.repo) / "coderoute_demo.json"
            if not manifest.is_file() or json.loads(manifest.read_text()).get("fixture") != "empty_config_v1":
                raise ValueError("mock mode only supports examples/demo_repo; use live for other repos")
        run_dir = Path(args.output).absolute().resolve() / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        harness = build_harness(config, args.workflow, args.mode)
        state = harness.run(args.repo, issue, run_dir)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({"mode": state.mode, "status": state.status, "reason": state.stop_reason,
                      "steps": state.steps, "modified_files": state.modified_files,
                      "test_status": state.test_result.status if state.test_result else None,
                      "workflow": args.workflow, "roles": state.history,
                      "review_accepted": state.review.get("accepted"),
                      "artifacts": str(run_dir)}, ensure_ascii=False, indent=2))
    return 0 if state.status == "succeeded" else 1
