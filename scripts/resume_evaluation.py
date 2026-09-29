"""Resume a stopped live batch without repeating completed model calls.

Finished repair runs are recovered from their artifacts. If a run stopped inside
the repair loop without final artifacts, refuse instead of silently hiding it.
"""
import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from coderoute.config import Config, load_local_env
from coderoute.evaluation import acceptance, case_fingerprint, export_results, save
from coderoute.factory import build_harness


def resume(output, benchmarks):
    output = Path(output).resolve()
    experiment = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    config = Config(**experiment["config"])
    load_local_env(Path.cwd() / ".env")
    if (output / "code_fingerprints.json").exists():
        for name, digest in json.loads((output / "code_fingerprints.json").read_text()).items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                raise ValueError("Execution code changed since original batch: " + name)
    cases = [Path(benchmarks).resolve() / name for name in experiment["cases"]]
    for case in cases:
        if case_fingerprint(case) != experiment["cases"][case.name]:
            raise ValueError("Benchmark changed since original batch: " + case.name)
    workflows = experiment["workflows"]
    for workflow in workflows:
        build_harness(config, workflow)
    rows = json.loads((output / "results.json").read_text(encoding="utf-8")) if (output / "results.json").exists() else []
    completed = {(r["case"], r["workflow"], r["repeat"]) for r in rows}
    save(output / ("resume-" + uuid.uuid4().hex[:8] + ".json"), {
        "time": datetime.now().isoformat(), "completed_before_resume": len(rows),
        "resume_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    })
    for repeat in range(experiment["repeats"]):
        for index, case in enumerate(cases):
            offset = (index + repeat) % len(workflows)
            for workflow in workflows[offset:] + workflows[:offset]:
                if (case.name, workflow, repeat + 1) in completed:
                    continue
                root = output / f"{case.name}-{workflow}-r{repeat + 1}"
                if root.exists():
                    if not (root / "final_state.json").exists() or not (root / "metrics.json").exists():
                        raise ValueError("Incomplete repair artifacts require explicit recovery: " + str(root))
                    print("Recovering finished repair " + root.name, flush=True)
                else:
                    print("Starting " + root.name, flush=True)
                    build_harness(config, workflow).run(case / "repo",
                        (case / "issue.txt").read_text(encoding="utf-8"), root)
                state = json.loads((root / "final_state.json").read_text(encoding="utf-8"))
                metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
                result_path = root / "acceptance_run" / "result.json"
                error = ""
                if result_path.exists():
                    status = json.loads(result_path.read_text(encoding="utf-8"))["status"]
                else:
                    target = root / "acceptance_run"
                    if target.exists():
                        target = root / ("acceptance_resume-" + uuid.uuid4().hex[:8])
                    status = "not_run"
                    try:
                        if state["workspace"] and Path(state["workspace"]).is_dir():
                            status = acceptance(Path(state["workspace"]), case, target, config).status
                    except (OSError, ValueError, RuntimeError) as exc:
                        status, error = "execution_error", str(exc)
                unchanged = case_fingerprint(case) == experiment["cases"][case.name]
                row = {"case": case.name, "workflow": workflow, "repeat": repeat + 1,
                       "status": state["status"], "acceptance_status": status,
                       "success": state["status"] == "succeeded" and status == "passed" and unchanged,
                       "source_unchanged": unchanged, "stop_reason": state["stop_reason"],
                       "acceptance_error": error, "artifacts": str(root),
                       "api_models": ";".join(metrics.get("api_models", []))}
                for key in ("steps", "llm_calls", "router_model_calls", "lightweight_model_calls",
                            "lightweight_decisions", "llm_escalations", "input_tokens", "output_tokens", "latency_seconds"):
                    row[key] = metrics.get(key, 0)
                rows.append(row)
                export_results(output, rows)
                print(json.dumps({k: row[k] for k in ("case", "workflow", "status", "acceptance_status", "success")}), flush=True)
                if not unchanged:
                    raise ValueError("Original case changed during resume")
    print("Artifacts: " + str(output), flush=True)
    return 0 if all(row["success"] for row in rows) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="Existing eval directory; ensure no evaluator is still running")
    parser.add_argument("--benchmarks", default="benchmarks")
    args = parser.parse_args()
    raise SystemExit(resume(args.output, args.benchmarks))
