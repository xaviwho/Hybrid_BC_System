#!/usr/bin/env python3
"""
Experiment 7 (rebuilt): Heterogeneity-Aware Delta Compression (HADC) — REAL data.

Contribution 4. Replaces the synthetic np.random "FlexSim" event stream (see
PHASE0_FINDINGS.md) with REAL digital-twin version deltas produced by the live
twin_manager, and REAL (measured) compression sizes via zlib.

Setup: build twins of heterogeneous entity classes (machine / conveyor / sensor / AGV)
in twin_manager, apply a deterministic per-class state evolution (NO np.random), and take
the actual serialized deltas between consecutive versions from twin_manager's history.

Compared on those real deltas:
  - Uniform      : one fixed codec (zlib level 6) for every class.
  - HADC         : per-class codec chosen from a set {store, zlib-1/6/9} by measured
                   best mean ratio on that class's deltas (heterogeneity-aware).

Every byte count is measured on real serialized data; the only determinism is the
(seed-free, reproducible) state evolution so the run is repeatable.

Output: experiments/results/exp7/exp7_hadc_real.json
"""

import json
import os
import sys
import zlib

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "orchestrator"))
from twin_manager import TwinManager  # noqa: E402

OUTPUT_DIR = os.path.join(_REPO, "experiments", "results", "exp7")

STEPS = 500  # state updates per twin -> version deltas

# Codec set. Each is (name, compress_fn) operating on bytes -> bytes.
CODECS = {
    "store":  lambda b: b,
    "zlib-1": lambda b: zlib.compress(b, 1),
    "zlib-6": lambda b: zlib.compress(b, 6),
    "zlib-9": lambda b: zlib.compress(b, 9),
}
UNIFORM_CODEC = "zlib-6"


def evolve(cls, i):
    """Deterministic, class-distinct state at step i (no randomness). Different classes
    have genuinely different delta characteristics — the point of heterogeneity."""
    if cls == "sensor":       # slowly drifting floats
        return {"temp": round(20 + (i % 100) * 0.05, 3), "hum": round(40 + (i % 50) * 0.1, 3),
                "pressure": round(1013 + (i % 30) * 0.2, 3)}
    if cls == "machine":      # mostly-constant status + monotonic counters
        return {"status": ["idle", "run", "run", "run", "fault"][i % 5],
                "cycles": i, "spindle_rpm": 1500 if i % 5 else 0, "tool": f"T{i % 8}"}
    if cls == "conveyor":     # stepwise speed/load
        return {"speed_mps": [0.0, 0.5, 1.0, 1.0, 0.5][i % 5], "load_kg": (i * 7) % 250,
                "belt_id": f"B{i % 4}", "jam": (i % 137 == 0)}
    if cls == "agv":          # moving coordinates + battery drain
        return {"x": round((i * 1.3) % 100, 2), "y": round((i * 0.7) % 60, 2),
                "battery": round(100 - (i % 100) * 0.9, 2), "route": f"R{i % 6}"}
    return {"v": i}


def build_deltas(cls):
    """Real twin_manager version history -> serialized deltas (changed fields per step)."""
    tm = TwinManager()
    tm.create_twin(cls, cls, evolve(cls, 0))
    twin = tm.get_twin(cls)
    for i in range(1, STEPS):
        twin.update_state(evolve(cls, i))
    versions = twin.get_version_history()  # real version objects
    deltas = []
    prev = None
    for v in versions:
        state = v["state"]
        if prev is None:
            delta = state
        else:
            delta = {k: val for k, val in state.items() if prev.get(k) != val}
        deltas.append(json.dumps(delta, sort_keys=True).encode())
        prev = state
    return deltas


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 70)
    print("  EXPERIMENT 7 (rebuilt): REAL HADC on twin_manager deltas")
    print("=" * 70)

    classes = ["machine", "conveyor", "sensor", "agv"]
    per_class = {}
    total_raw = total_uniform = total_hadc = 0

    for cls in classes:
        deltas = build_deltas(cls)
        # Compress a BLOCK of the delta stream (the realistic archival/anchoring unit):
        # the class's deltas concatenated. Per-delta compression is dominated by codec
        # header overhead; block compression is what real storage does.
        blob = b"\n".join(deltas)
        raw = len(blob)
        codec_sizes = {name: len(fn(blob)) for name, fn in CODECS.items()}
        best_codec = min(codec_sizes, key=codec_sizes.get)
        uniform_size = codec_sizes[UNIFORM_CODEC]
        hadc_size = codec_sizes[best_codec]
        per_class[cls] = {
            "n_deltas": len(deltas),
            "raw_bytes": raw,
            "codec_bytes": codec_sizes,
            "uniform_codec": UNIFORM_CODEC,
            "uniform_bytes": uniform_size,
            "hadc_codec": best_codec,
            "hadc_bytes": hadc_size,
            "uniform_ratio": round(raw / uniform_size, 3),
            "hadc_ratio": round(raw / hadc_size, 3),
        }
        total_raw += raw
        total_uniform += uniform_size
        total_hadc += hadc_size

    savings_vs_uniform = 100.0 * (1 - total_hadc / total_uniform)
    chosen = {per_class[c]["hadc_codec"] for c in classes}
    heterogeneous = len(chosen) > 1
    results = {
        "experiment": "exp7_hadc_real",
        "measured": True,
        "data_source": "real twin_manager version deltas (deterministic multi-class workload)",
        "steps_per_twin": STEPS,
        "classes": classes,
        "per_class": per_class,
        "total_raw_bytes": total_raw,
        "total_uniform_bytes": total_uniform,
        "total_hadc_bytes": total_hadc,
        "overall_uniform_ratio": round(total_raw / total_uniform, 3),
        "overall_hadc_ratio": round(total_raw / total_hadc, 3),
        "hadc_storage_savings_vs_uniform_pct": round(savings_vs_uniform, 2),
        "codecs_selected": sorted(chosen),
        "heterogeneous_selection": heterogeneous,
        "finding": (
            "Block-level compression of REAL twin_manager version deltas reaches "
            f"~{round(total_raw / total_uniform, 1)}x (uniform zlib-6). Per-class codec "
            f"selection (HADC) improves on uniform by {round(savings_vs_uniform, 1)}%. "
            + ("Classes selected DIFFERENT codecs, supporting the heterogeneity thesis."
               if heterogeneous else
               "HONEST CAVEAT: with a generic codec set (zlib levels + store) all classes "
               "selected the same codec (" + list(chosen)[0] + "), so the gain comes from "
               "level selection, NOT structural heterogeneity. Substantiating a strong "
               "heterogeneity claim would require structurally distinct codecs (e.g. "
               "float-delta/XOR for numeric classes vs dictionary/RLE for categorical). "
               "As measured, Contribution 4's heterogeneity benefit is modest.")
        ),
    }
    path = os.path.join(OUTPUT_DIR, "exp7_hadc_real.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"  {'class':>9} {'n':>5} {'raw':>8} {'uniform':>9} {'hadc':>9}  best-codec")
    for cls in classes:
        p = per_class[cls]
        print(f"  {cls:>9} {p['n_deltas']:>5} {p['raw_bytes']:>8} {p['uniform_bytes']:>9} "
              f"{p['hadc_bytes']:>9}  {p['hadc_codec']}")
    print(f"  overall: uniform ratio {results['overall_uniform_ratio']}x | "
          f"HADC ratio {results['overall_hadc_ratio']}x | "
          f"HADC saves {results['hadc_storage_savings_vs_uniform_pct']}% vs uniform")
    print(f"  JSON: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
