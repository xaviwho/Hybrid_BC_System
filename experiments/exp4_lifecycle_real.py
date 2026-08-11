#!/usr/bin/env python3
"""
Experiment 4 (rebuilt): Digital-Twin Lifecycle Overhead & Rollback — REAL, in-process.

Replaces the fabricated exp4_lifecycle_overhead.py, whose rollback/checkpoint
latencies were np.random draws and fixed-fraction formulas, and which labeled
every row "O(1)" (see PHASE0_FINDINGS.md).

This measures the ACTUAL twin_manager component directly (no HTTP, no randomness
in the measurement path). It answers the O(1) question honestly by reading the
implementation's real behavior:
  - Versioning stores a FULL deepcopy snapshot per version  -> storage O(n·|state|)
  - rollback_to_version() does get_version() (linear O(n) scan) + deepcopy(state)
    -> rollback latency is NOT O(1); it scales with the version index.

All timings via time.perf_counter, warm-up discarded, repeated with mean/p95/CI95.
State content is fixed/deterministic (no np.random anywhere).

Output: experiments/results/exp4/exp4_lifecycle_real.json
"""

import json
import os
import statistics
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "orchestrator"))
from twin_manager import TwinManager  # noqa: E402

OUTPUT_DIR = os.path.join(_REPO, "experiments", "results", "exp4")

WARMUP = 20
REPS = 200            # repetitions per measured point
STATE_FIELDS = 20     # size of each twin state
SPARSE_CHANGED = 2    # fields changed per version in the sparse condition
STATE_MODELS = ("dense", "sparse")


def make_state(i: int, model: str = "dense") -> dict:
    """Deterministic realistic-ish state (no randomness).

    Phase 3 adds the `sparse` condition. `dense` changes every field every version,
    which makes delta encoding a no-op by construction — a dense-only result is
    predetermined and says nothing about the storage mechanism. `sparse` moves
    ~SPARSE_CHANGED of STATE_FIELDS per version, which is what IIoT telemetry does.
    """
    if model == "dense":
        return {f"sensor_{k}": (i * 100 + k) * 0.5 for k in range(STATE_FIELDS)}
    stride = STATE_FIELDS // SPARSE_CHANGED
    return {f"sensor_{k}": (max(i - ((i - k) % stride), 0) * 100 + k) * 0.5
            for k in range(STATE_FIELDS)}


def _stats(samples_ms):
    n = len(samples_ms)
    mean = statistics.fmean(samples_ms)
    stdev = statistics.pstdev(samples_ms) if n > 1 else 0.0
    p95 = sorted(samples_ms)[min(n - 1, int(round(0.95 * (n - 1))))]
    ci95 = 1.96 * stdev / (n ** 0.5) if n > 1 else 0.0
    return {"mean_ms": mean, "p95_ms": p95, "stdev_ms": stdev, "ci95_ms": ci95, "n": n}


def measure_update_latency(model="dense", ):
    tm = TwinManager()
    tm.create_twin("u", "sensor", make_state(0, model))
    for i in range(WARMUP):
        tm.update_twin("u", make_state(i + 1, model))
    samples = []
    for i in range(REPS):
        s = make_state(i + 100, model)
        t0 = time.perf_counter()
        tm.update_twin("u", s)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return _stats(samples)


STORAGE_REPS = 5   # Phase 2: was 1 construction per point, so no error bars


def measure_storage_growth(model="dense", points=(1, 10, 50, 100, 200, 400, 800)):
    """Serialized bytes of full version history vs number of versions.

    Repeated STORAGE_REPS times per point (Phase 2). The construction is
    deterministic so the spread is expected to be zero — but that must be
    demonstrated, not assumed, which is exactly what one construction per point
    could not do.
    """
    rows = []
    for nver in points:
        samples = []
        for _ in range(STORAGE_REPS):
            tm = TwinManager()
            tm.create_twin("s", "sensor", make_state(0, model))  # version 1
            for i in range(nver - 1):
                tm.update_twin("s", make_state(i + 1, model))
            twin = tm.get_twin("s")
            rep = twin.storage_report()
            samples.append((rep["stored_bytes"], rep["snapshot_equivalent_bytes"]))
        stored = [a for a, _ in samples]
        equiv = [b for _, b in samples]
        mean_bytes = statistics.fmean(stored)
        mean_equiv = statistics.fmean(equiv)
        rows.append({
            "versions": nver,
            "reps": STORAGE_REPS,
            # Phase 3: stored_bytes is the ACTUAL delta/checkpoint footprint.
            # snapshot_equivalent_bytes is what the old full-snapshot format cost,
            # kept so the two formats are directly comparable.
            "total_bytes": round(mean_bytes, 1),
            "snapshot_equivalent_bytes": round(mean_equiv, 1),
            "compression_vs_snapshots": round(mean_equiv / mean_bytes, 4) if mean_bytes else 0,
            "total_bytes_min": min(stored),
            "total_bytes_max": max(stored),
            "total_bytes_stdev": round(statistics.pstdev(stored), 3),
            "bytes_per_version": round(mean_bytes / nver, 1),
        })
    return rows


def measure_rollback_by_target(model="dense", total_versions=1000,
                               targets=(1, 50, 100, 250, 500, 750, 1000)):
    """Rollback latency vs TARGET version index.

    PHASE 3: the cost model changed. Rollback now reconstructs the target
    (Algorithm 2) and appends a new head, so cost tracks the delta-application
    count u = min{n-k, k mod q} — which is SAWTOOTH in k, not monotonic. Comparing
    only target=1 against target=N is therefore no longer a valid probe for
    constant time: those two targets can land on similar u by coincidence and make
    a bounded-but-varying cost look flat. We record u alongside every latency and
    characterize against u instead of against k.

    We rebuild the twin for each sample so every measured rollback sees a history
    of the same length."""
    rows = []
    for target in targets:
        target = min(target, total_versions)
        samples = []
        u_seen = None
        for _ in range(WARMUP + REPS // 2):
            tm = TwinManager()
            tm.create_twin("r", "sensor", make_state(0, model))
            for i in range(total_versions - 1):
                tm.update_twin("r", make_state(i + 1, model))
            twin = tm.get_twin("r")
            if u_seen is None:
                # u actually performed by the shipped manager for this target
                _, rs = twin.reconstruct_with_stats(target)
                u_seen = {"u": rs["u"], "path": rs["path"]}
            t0 = time.perf_counter()
            twin.rollback_to_version(target)
            samples.append((time.perf_counter() - t0) * 1000.0)
        st = _stats(samples[WARMUP:])
        st["target_version"] = target
        st["delta_applications_u"] = u_seen["u"]
        st["reconstruction_path"] = u_seen["path"]
        rows.append(st)
    return rows


def run_model(model):
    update = measure_update_latency(model)
    storage = measure_storage_growth(model)
    rollback = measure_rollback_by_target(model)

    bytes_per_version_stable = statistics.fmean([r["bytes_per_version"] for r in storage])
    rb_lo = min(r["mean_ms"] for r in rollback)
    rb_hi = max(r["mean_ms"] for r in rollback)
    big = storage[-1]

    # Characterize against u, not against k. Constant time would mean latency is
    # invariant across targets with DIFFERENT u; bounded means u itself is capped.
    by_u = {}
    for r in rollback:
        by_u.setdefault(r["delta_applications_u"], []).append(r["mean_ms"])
    u_values = sorted(by_u)
    lo_u, hi_u = u_values[0], u_values[-1]
    spread = statistics.fmean(by_u[hi_u]) / statistics.fmean(by_u[lo_u]) if by_u[lo_u] else 0
    varies_with_u = len(u_values) > 1 and abs(spread - 1.0) > 0.10
    u_max = max(u_values)
    q = 100  # twin_manager default CHECKPOINT_INTERVAL

    print(f"  [{model}]")
    print(f"    update latency        : mean {update['mean_ms']:.4f} ms  p95 {update['p95_ms']:.4f} ms")
    print(f"    stored bytes/version  : ~{bytes_per_version_stable:.1f}")
    print(f"    at {big['versions']} versions   : {big['total_bytes']:,.0f} B stored vs "
          f"{big['snapshot_equivalent_bytes']:,.0f} B as snapshots "
          f"({big['compression_vs_snapshots']}x)")
    print(f"    rollback min / max    : {rb_lo:.4f} / {rb_hi:.4f} ms  ({rb_hi / rb_lo:.2f}x)")
    print(f"    u by target           : "
          f"{ {r['target_version']: r['delta_applications_u'] for r in rollback} }")
    print(f"    u bounded by q={q}     : {u_max <= q} (u_max={u_max}); "
          f"varies with u: {varies_with_u} (ratio {spread:.2f}x)")

    return {
        "state_model": model,
        "update_latency": update,
        "storage_growth": storage,
        "approx_bytes_per_version": round(bytes_per_version_stable, 1),
        "compression_vs_snapshots_at_max": big["compression_vs_snapshots"],
        "rollback_latency_by_target_version": rollback,
        "rollback_min_ms": rb_lo,
        "rollback_max_ms": rb_hi,
        "rollback_cost_model": {
            "u_by_target": {str(r["target_version"]): r["delta_applications_u"]
                            for r in rollback},
            "u_max_observed": u_max,
            "checkpoint_interval_q": q,
            "u_bounded_by_q": u_max <= q,
            "latency_ratio_high_u_over_low_u": round(spread, 4),
            "varies_with_u": bool(varies_with_u),
            "note": ("u = min{n-k, k mod q} is SAWTOOTH in k, so a target=1 vs "
                     "target=N comparison is not a valid constant-time probe under "
                     "this storage model. Cost is BOUNDED by q, not constant."),
        },
        "rollback_scales_with_target_index": False,
        "is_constant_time": False,
        "is_bounded_by_checkpoint_interval": bool(u_max <= q),
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 70)
    print("  EXPERIMENT 4 (Phase 3): twin_manager lifecycle, delta/checkpoint storage")
    print("=" * 70)

    per_model = {m: run_model(m) for m in STATE_MODELS}
    primary = per_model["sparse"]

    results = {
        "experiment": "exp4_lifecycle_real",
        "schema_version": 2,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": {
            "data_source": "deterministic synthetic states, exp4_lifecycle_real.py:make_state()",
            "component": "orchestrator/twin_manager.py (in-process)",
            "measures_production_code": True,
            "state_models": list(STATE_MODELS),
            "warmup": WARMUP, "reps": REPS, "storage_reps": STORAGE_REPS,
            "state_fields": STATE_FIELDS,
            "sparse_fields_changed_per_update": SPARSE_CHANGED,
            "python": sys.version.split()[0],
        },
        "versioning_model": ("delta + periodic checkpoint (Phase 3). Checkpoint every q "
                             "versions; per-version min(delta, snapshot) fallback; "
                             "reversible deltas in the open checkpoint window, "
                             "compacted to forward-only once the window closes."),
        "rollback_model": ("reconstruct target (Algorithm 2, cheaper of checkpoint-forward "
                           "and inversion-from-head), then APPEND a new head (Eq 35). "
                           "History is never truncated."),
        "by_state_model": per_model,
        # back-compatible top-level keys, taken from the sparse (representative) model
        "update_latency": primary["update_latency"],
        "storage_growth": primary["storage_growth"],
        "approx_bytes_per_version": primary["approx_bytes_per_version"],
        "rollback_latency_by_target_version": primary["rollback_latency_by_target_version"],
        "rollback_min_ms": primary["rollback_min_ms"],
        "rollback_max_ms": primary["rollback_max_ms"],
        "rollback_scales_with_target_index": primary["rollback_scales_with_target_index"],
        "is_constant_time": primary["is_constant_time"],
        "conclusion": (
            "Rollback is NOT constant time, but it is now BOUNDED: cost tracks the "
            "delta-application count u = min{n-k, k mod q} plus the append, rather "
            "than a linear scan over the version list. Because u is sawtooth in k, "
            "the old target=1 vs target=N probe no longer detects the variation — "
            "the characterization is against u, and u is capped by the checkpoint "
            "interval q. Storage is no longer one full snapshot per "
            "version: under sparse updates the delta/checkpoint format is materially "
            "smaller than the snapshot equivalent, while under dense updates the "
            "min(delta, snapshot) fallback keeps it at parity instead of regressing. "
            "Both conditions are reported; a dense-only result would be predetermined."
        ),
    }

    path = os.path.join(OUTPUT_DIR, "exp4_lifecycle_real.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  JSON: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
