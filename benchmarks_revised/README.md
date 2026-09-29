# Versioned fixture corrections

`12_atomic_transfers_v2` replaces the ambiguous specification of `12_atomic_transfers`
in `configs/release-suite.json`. It explicitly specifies `KeyError` for unknown
accounts and `ValueError` for invalid amounts or insufficient funds. Its repository,
public tests, holdout tests, and reference edits are unchanged from the original.

The original remains under `benchmarks_extended/12_atomic_transfers`; completed
historical results are not rescored. The release suite contains 14 tasks, counting
only the revised transfer case. The two versions are not separate tasks for a
success-rate denominator. Do not compare their scores as an isolated agent improvement.
