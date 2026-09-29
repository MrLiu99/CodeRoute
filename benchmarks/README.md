# Authored Python repair fixtures

Ten small cases cover blank input, zero bounds, pagination, mutable defaults,
falsey cache values, stable ordering, exception retry policy, weighted averages,
cross-file units, and inventory state updates. These are authored smoke fixtures,
not SWE-bench or a representative repository-level dataset.

Each case contains:

- `repo/`: buggy source and public tests, copied into the agent workspace.
- `issue.txt`: behavior contract supplied to the agent.
- `holdout/`: independent acceptance tests, copied only into a separate evaluator workspace after the repair run.
- `case.json`: difficulty metadata and reference edits, never supplied to the agent.

Reference edits are fixture validation aids, not constraints on the model's patch.
Both original failures and reference successes are checked before evaluation.
Tests in `holdout/` are withheld from the agent's tool context, not a security sandbox.

Run `python evaluate.py` to validate fixtures without model calls. Use
`python evaluate.py --live --cases 02_zero_bound --config configs/default.json`
to compare all four methods on one case. Default live batch cap is four runs;
use an explicit `--max-runs` to permit a larger experiment. Each run retains its
metrics, trajectory, final diff and acceptance report. Reports include failed runs.

`scripts/generate_benchmarks.py` regenerates these fixtures and overwrites authored
fixture files; run it only when deliberately updating the dataset. It does not
touch completed run workspaces.
