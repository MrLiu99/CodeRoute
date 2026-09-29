import argparse
import csv
import hashlib
import json
import shutil
import statistics
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .config import Config, load_local_env
from .factory import build_harness
from .tools.files import FileTools
from .tools.pytest_runner import run_tests
from .tools.workspace import Workspace, files


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def case_fingerprint(case):
    digest = hashlib.sha256()
    for path in files(case):
        digest.update(path.relative_to(case).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def suite_cases(path):
    """Resolve an explicit, versioned suite relative to its manifest."""
    manifest = Path(path).resolve()
    entries = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(entries, list) or not entries or not all(isinstance(p, str) and p for p in entries):
        raise ValueError('Suite must be a nonempty JSON list of case directory paths')
    cases = [(manifest.parent / p).resolve() for p in entries]
    if len({p.name for p in cases}) != len(cases):
        raise ValueError('Suite case IDs must be unique')
    if any(not (p / 'case.json').is_file() or not (p / 'issue.txt').is_file()
           or not (p / 'repo').is_dir() or not (p / 'holdout').is_dir() for p in cases):
        raise ValueError('Suite contains an incomplete case')
    return cases


def acceptance(source, case, output, config, edits=None):
    """Fresh copy with public + holdout tests, never passed to the repair agent."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    workspace = Workspace(source, output)
    if edits:
        tools = FileTools(workspace)
        for edit in edits:
            tools.edit_file(**edit)
    target = workspace.root / "tests" / "acceptance"
    if target.exists():
        raise ValueError("Reserved acceptance test directory already exists")
    shutil.copytree(case / "holdout", target)
    result = run_tests(workspace, output, 1, config.test_timeout, config.max_output_chars)
    save(output / "result.json", asdict(result))
    return result


def validate_cases(cases, output, config):
    results = []
    for case in cases:
        manifest = json.loads((case / "case.json").read_text(encoding="utf-8"))
        before = case_fingerprint(case)
        buggy = acceptance(case / "repo", case, output / case.name / "buggy", config)
        fixed = acceptance(case / "repo", case, output / case.name / "reference", config, manifest["reference_edits"])
        valid = buggy.status == "failed" and fixed.status == "passed" and before == case_fingerprint(case)
        row = {"case": case.name, "fingerprint": before, "valid": valid,
               "buggy_status": buggy.status, "reference_status": fixed.status,
               "reference_tests": fixed.passed}
        results.append(row)
        save(output / "validation.json", results)
        print(json.dumps(row), flush=True)
    return results


def summarize(rows):
    result = []
    for workflow in sorted({r["workflow"] for r in rows}):
        group = [r for r in rows if r["workflow"] == workflow]
        row = {"workflow": workflow, "runs": len(group), "successes": sum(r["success"] for r in group)}
        row["success_rate"] = row["successes"] / row["runs"]
        for metric in ("steps", "llm_calls", "router_model_calls", "lightweight_model_calls",
                       "lightweight_decisions", "llm_escalations", "input_tokens", "output_tokens", "latency_seconds"):
            row["avg_" + metric] = statistics.mean(r.get(metric, 0) for r in group)
        result.append(row)
    return result


def export_results(output, rows):
    save(output / "results.json", rows)
    summary = summarize(rows)
    save(output / "summary.json", summary)
    for name, data in (("results.csv", rows), ("summary.csv", summary)):
        if data:
            with (output / name).open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(data[0]))
                writer.writeheader()
                writer.writerows(data)
    lines = ["# Evaluation results", "", "Success requires Harness acceptance AND independent public + holdout tests.",
             "One or few repeats on authored fixtures are not a general benchmark result.", "",
             "| Method | Runs | Success | Avg calls | Router calls | Lightweight calls | Light decisions | Escalations | Avg tokens | Avg seconds |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        lines.append(f"| {r['workflow']} | {r['runs']} | {r['successes']}/{r['runs']} | {r['avg_llm_calls']:.1f} | "
                     f"{r['avg_router_model_calls']:.1f} | {r['avg_lightweight_model_calls']:.1f} | "
                     f"{r['avg_lightweight_decisions']:.1f} | {r['avg_llm_escalations']:.1f} | "
                     f"{r['avg_input_tokens'] + r['avg_output_tokens']:.0f} | {r['avg_latency_seconds']:.2f} |")
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate(cases, workflows, repeats, output, config):
    # Preflight every provider before any paid run; no network calls in construction.
    for workflow in workflows:
        build_harness(config, workflow)
    save(output / "experiment.json", {"mode": "live", "config": asdict(config), "repeats": repeats,
         "workflows": workflows, "cases": {case.name: case_fingerprint(case) for case in cases},
         "case_paths": {case.name: str(case.resolve()) for case in cases}})
    project = Path(__file__).resolve().parents[2]
    execution_files = sorted((project / 'src').rglob('*.py')) + [project / 'evaluate.py', project / 'main.py']
    save(output / 'code_fingerprints.json', {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in execution_files})
    rows = []
    for repeat in range(repeats):
        for case_index, case in enumerate(cases):
            # Rotate method order to reduce a fixed ordering bias.
            offset = (case_index + repeat) % len(workflows)
            order = workflows[offset:] + workflows[:offset]
            for workflow in order:
                name = f"{case.name}-{workflow}-r{repeat + 1}"
                root = output / name
                before = case_fingerprint(case)
                print(f"Starting {name}", flush=True)
                state = build_harness(config, workflow).run(case / "repo",
                    (case / "issue.txt").read_text(encoding="utf-8"), root)
                metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
                test_status = "not_run"
                acceptance_error = ""
                try:
                    if state.workspace and Path(state.workspace).is_dir():
                        test_status = acceptance(Path(state.workspace), case, root / "acceptance_run", config).status
                except (OSError, ValueError, RuntimeError) as error:
                    test_status = "execution_error"
                    acceptance_error = str(error)
                source_unchanged = before == case_fingerprint(case)
                row = {"case": case.name, "workflow": workflow, "repeat": repeat + 1,
                       "status": state.status, "acceptance_status": test_status,
                       "success": state.status == "succeeded" and test_status == "passed" and source_unchanged,
                       "source_unchanged": source_unchanged, "stop_reason": state.stop_reason,
                       "acceptance_error": acceptance_error, "artifacts": str(root),
                       "api_models": ";".join(metrics.get("api_models", []))}
                for key in ("steps", "llm_calls", "router_model_calls", "lightweight_model_calls",
                            "lightweight_decisions", "llm_escalations", "input_tokens", "output_tokens", "latency_seconds"):
                    row[key] = metrics.get(key, 0)
                rows.append(row)
                export_results(output, rows)
                print(json.dumps({k: row[k] for k in ("case", "workflow", "status", "acceptance_status", "success")}), flush=True)
                if not source_unchanged:
                    raise RuntimeError("Source fixture changed during evaluation")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate authored cases or explicitly run live comparisons")
    parser.add_argument("--benchmarks", default="benchmarks")
    parser.add_argument("--suite", help="JSON case-directory list; replaces --benchmarks discovery")
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--config")
    parser.add_argument("--live", action="store_true", help="Make paid model calls; default only validates fixtures")
    parser.add_argument("--workflows", nargs="+", choices=["fixed", "llm", "dynamic", "hybrid"],
                        default=["fixed", "llm", "dynamic", "hybrid"])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-runs", type=int, default=4, help="Reject larger live batches unless explicitly increased")
    parser.add_argument("--output", default="runs")
    args = parser.parse_args(argv)
    try:
        load_local_env(Path.cwd() / ".env")
        config = Config.load(args.config)
        available = ({p.name: p for p in suite_cases(args.suite)} if args.suite else
                     {p.parent.name: p.parent.resolve() for p in Path(args.benchmarks).glob("*/case.json")})
        names = args.cases or sorted(available)
        if not names or len(set(names)) != len(names) or any(name not in available for name in names):
            raise ValueError("Select unique existing benchmark case IDs")
        if args.repeats < 1 or args.max_runs < 1 or len(set(args.workflows)) != len(args.workflows):
            raise ValueError("Positive limits and distinct workflows required")
        if args.live and len(names) * len(args.workflows) * args.repeats > args.max_runs:
            raise ValueError("Batch exceeds --max-runs; select fewer cases/methods or explicitly raise the limit")
        cases = [available[name] for name in names]
        output = Path(args.output).absolute().resolve() / ("eval-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=False)
        rows = evaluate(cases, args.workflows, args.repeats, output, config) if args.live else validate_cases(cases, output, config)
        print("Artifacts: " + str(output), flush=True)
        return 0 if all(row["success" if args.live else "valid"] for row in rows) else 1
    except (ValueError, OSError) as error:
        parser.error(str(error))
