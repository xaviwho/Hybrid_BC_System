#!/usr/bin/env python3
"""
Experiment 8: checkpoint restore vs delta inversion — measured on the SHIPPED code.

PHASE 3 CHANGE: this experiment no longer contains its own delta or checkpoint
implementation. Everything it measures now runs inside
`orchestrator/twin_manager.py`:

  - the delta/checkpoint storage format          (twin_manager, Phase 3)
  - both branches of Algorithm 2                 (reconstruct_with_stats)
  - the delta-application count u                (returned by the manager)
  - the storage accounting                       (twin.storage_report())

Previously the experiment implemented all of that locally, which meant it was
measuring itself rather than the production path. The local versions have been
deleted.

What is measured, per state model and per checkpoint interval q:
  (a) checkpoint restore  — nearest materialized base, then forward deltas
  (b) delta inversion     — inverse deltas from head (Eq 34)
  and the path the manager actually selects, with its u.

Eq (36) is tested three ways: as the printed equality u = min{n-k, q}, as a bound,
and against the exact form u = min{n-k, (k-1) mod q}.

State models — the choice is not cosmetic. `dense` changes every field every
version, so a delta is the size of a snapshot and the manager's min(delta,
snapshot) fallback stores snapshots instead; the storage comparison is degenerate
by construction. `sparse` moves ~2 of 20 fields per version, which is what IIoT
telemetry looks like.

Runs fully offline. No randomness.

Output: experiments/results/exp8/exp8_recovery_strategy.json
"""

import json
import os
import statistics
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "orchestrator"))
from twin_manager import (  # noqa: E402
    TwinManager, PATH_CHECKPOINT, PATH_INVERSION, KIND_DELTA, KIND_SNAPSHOT,
    KIND_CHECKPOINT,
)

OUTPUT_DIR = os.path.join(_REPO, "experiments", "results", "exp8")

TOTAL_VERSIONS = 1001          # head version n = 1001, index 1000
# Near-head targets {990, 995, 999} added in the Phase 3 follow-up. The original
# set barely sampled the region where inversion wins (n-k < (k-1) mod q), so
# Eq (34)'s branch was selected once in 301 reconstructions and looked vestigial.
# Near-head undo is the common operational case.
TARGETS = [1, 50, 100, 250, 500, 750, 990, 995, 999, 1000]
Q_VALUES = [50, 100, 250]
REPS = 100
WARMUP = 20
STATE_FIELDS = 20
SPARSE_CHANGED = 2
STATE_MODELS = ("dense", "sparse")


def make_state(i: int, model: str = "dense") -> dict:
    """Deterministic state. No randomness in either model."""
    if model == "dense":
        return {f"sensor_{k}": (i * 100 + k) * 0.5 for k in range(STATE_FIELDS)}
    stride = STATE_FIELDS // SPARSE_CHANGED
    return {f"sensor_{k}": (max(i - ((i - k) % stride), 0) * 100 + k) * 0.5
            for k in range(STATE_FIELDS)}


def build_twin(model: str, q: int):
    """Real twin history through the shipped manager, at checkpoint interval q."""
    tm = TwinManager(checkpoint_interval=q)
    twin = tm.create_twin(f"recovery-{model}-q{q}", "sensor", make_state(0, model))
    for i in range(1, TOTAL_VERSIONS):
        twin.update_state(make_state(i, model))
    return twin


def _stats(xs):
    n = len(xs)
    mean = statistics.fmean(xs)
    sd = statistics.pstdev(xs) if n > 1 else 0.0
    xs2 = sorted(xs)
    return {
        "kind": "measured", "n": n,
        "mean": round(mean, 6),
        "p50": round(xs2[int(0.50 * (n - 1))], 6),
        "p95": round(xs2[int(0.95 * (n - 1))], 6),
        "ci95": round(1.96 * sd / (n ** 0.5), 6) if n > 1 else 0.0,
    }


def time_path(twin, k, force_path):
    """Time one reconstruction branch on the shipped manager. Returns (stats, u)
    or (None, None) if that branch is unavailable for this target."""
    try:
        _, st = twin.reconstruct_with_stats(k, force_path=force_path)
    except ValueError:
        return None, None
    for _ in range(WARMUP):
        twin.reconstruct_with_stats(k, force_path=force_path)
    samples = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        twin.reconstruct_with_stats(k, force_path=force_path)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return _stats(samples), st["u"]


def run_model(model):
    per_q = {}
    eq_checks, bound_checks, exact_checks = [], [], []
    storage = None

    for q in Q_VALUES:
        twin = build_twin(model, q)
        n = len(twin.versions)
        head_idx = n - 1
        rep = twin.storage_report()
        if storage is None or q == 100:
            storage = rep      # report storage at the default interval

        # Integrity of the whole history, from the shipped verifier (Eq 33).
        verified = twin.verify_all()

        rows = []
        for k in TARGETS:
            if k > n:
                continue
            idx = k - 1
            ck_stats, u_ck = time_path(twin, k, PATH_CHECKPOINT)
            inv_stats, u_inv = time_path(twin, k, PATH_INVERSION)

            # what the manager selects on its own
            _, sel = twin.reconstruct_with_stats(k)
            u_sel = sel["u"]

            eq36 = min(head_idx - idx, q)
            exact = min(head_idx - idx, idx % q)
            eq_checks.append(u_sel == eq36)
            bound_checks.append(u_sel <= eq36)
            exact_checks.append(u_sel == exact)

            rows.append({
                "target_version": k,
                "checkpoint_interval_q": q,
                "head_version": n,
                "checkpoint_restore": {
                    "latency_ms": ck_stats,
                    "delta_applications_u": {"kind": "measured", "value": u_ck},
                },
                "delta_inversion_from_head": {
                    "latency_ms": inv_stats,
                    "delta_applications_u": {"kind": "measured", "value": u_inv},
                    "available": inv_stats is not None,
                },
                "selected_path": {"kind": "measured", "value": sel["path"]},
                "u_selected_measured": {"kind": "measured", "value": u_sel},
                "u_eq36_predicted": {"kind": "modeled", "value": eq36,
                                     "formula": "min{n-k, q}"},
                "u_exact_predicted": {"kind": "modeled", "value": exact,
                                      "formula": "min{n-k, (k-1) mod q}"},
                "eq36_equality_holds": {"kind": "derived", "value": u_sel == eq36,
                                        "derivation": "u_measured == min{n-k, q}"},
                "eq36_bound_holds": {"kind": "derived", "value": u_sel <= eq36,
                                     "derivation": "u_measured <= min{n-k, q}"},
                "exact_formula_holds": {"kind": "derived", "value": u_sel == exact,
                                        "derivation": "u_measured == min{n-k, (k-1) mod q}"},
            })
            ck_mean = ck_stats["mean"] if ck_stats else float("nan")
            inv_mean = inv_stats["mean"] if inv_stats else float("nan")
            print(f"   [{model}] k={k:>4} q={q:>3}: ckpt {ck_mean:>8.4f} ms (u={u_ck}) | "
                  f"invert {inv_mean:>9.4f} ms (u={u_inv}) | selected {sel['path']:<10} "
                  f"u={u_sel:>3} | eq36={eq36:>3} exact={exact:>3} "
                  f"{'OK' if u_sel == exact else 'MISMATCH'}")

        per_q[str(q)] = {
            "measurements": rows,
            "integrity": {"kind": "measured", "versions_checked": verified["checked"],
                          "failures": len(verified["failures"]), "ok": verified["ok"]},
            "storage": rep,
        }

    return {
        "state_model": model,
        "by_checkpoint_interval": per_q,
        "storage_at_q100": storage,
        "eq36_validation": {
            "kind": "derived",
            "equality_holds_at": f"{sum(eq_checks)}/{len(eq_checks)}",
            "bound_holds_at": f"{sum(bound_checks)}/{len(bound_checks)}",
            "exact_formula_holds_at": f"{sum(exact_checks)}/{len(exact_checks)}",
            "conclusion": (
                "Eq (36) u = min{n-k, q} is valid as an UPPER BOUND and invalid as an "
                "EQUALITY: checkpoint restore costs ((k-1) mod q) applications, not q. "
                "The exact cost is u = min{n-k, (k-1) mod q}. Measured here from the "
                "shipped twin_manager, not from an experiment-local implementation."),
        },
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 78)
    print("  EXPERIMENT 8 (Phase 3): recovery strategy, measured on the shipped manager")
    print("=" * 78)

    per_model = {model: run_model(model) for model in STATE_MODELS}

    results = {
        "experiment": "exp8_recovery_strategy",
        "schema_version": 2,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": {
            "data_source": ("real twin_manager version histories built in "
                            "exp8_recovery_strategy.py:build_twin(); storage format, "
                            "reconstruction and u all come from the production manager"),
            "measures_production_code": True,
            "state_models": list(STATE_MODELS),
            "checkpoint_intervals": Q_VALUES,
            "total_versions": TOTAL_VERSIONS,
            "reps_per_point": REPS,
            "warmups_discarded": WARMUP,
            "state_fields": STATE_FIELDS,
            "sparse_fields_changed_per_update": SPARSE_CHANGED,
            "python": sys.version.split()[0],
        },
        "by_state_model": per_model,
    }
    path = os.path.join(OUTPUT_DIR, "exp8_recovery_strategy.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)

    print("\n  " + "-" * 74)
    for m, r in per_model.items():
        v = r["eq36_validation"]
        s = r["storage_at_q100"]
        print(f"  [{m}] Eq(36) equality {v['equality_holds_at']} | bound "
              f"{v['bound_holds_at']} | exact {v['exact_formula_holds_at']}")
        print(f"       storage {s['stored_bytes']:,} B vs snapshots "
              f"{s['snapshot_equivalent_bytes']:,} B = {s['ratio_vs_snapshots']}x "
              f"| kinds {s['counts_by_kind']}")
    print(f"  JSON: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
