# Quarantined: pre-Phase-2 experiment suite

Moved here in WS0 (revision audit, `revision/AUDIT_WS0.md` §2.3). Do not run.

These scripts silently switch to `simulation_mode` when a service health check
fails, and draw latency, gas and failure events from `np.random`. They produced
none of the numbers in `results/v1/RESULTS.json`. Their replacements:

| Quarantined | Replaced by |
|---|---|
| `exp1_latency_throughput.py` | `experiments/exp1_latency_real.py` |
| `exp3_gas_efficiency.py` | `experiments/exp3_gas_real.py` |
| `exp4_lifecycle_overhead.py` | `experiments/exp4_lifecycle_real.py` |
| `exp5_exactly_once.py` | `experiments/exp5_exactly_once_real.py` |
| `run_all_experiments.py` | none: run each `*_real.py`, then `consolidate_results.py` |

Kept, not deleted, so the provenance trail in `DATA_SOURCES.md` and
`PHASE0_FINDINGS.md` still resolves.
