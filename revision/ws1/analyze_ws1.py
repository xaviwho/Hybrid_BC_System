"""WS1 analysis: dev (Werkzeug) vs prod (gunicorn), single host, 5 repetitions.

Inputs: results/v2/raw/ws1/<profile>/rep<k>/{exp1/exp1_latency_real.json,
exp1/exp1_requests.jsonl, clock_pre.json, clock_post.json}

A run without exp1_latency_real.json (2 of 10: the end-of-run digest timed out,
see CHECKPOINT1.md) is rebuilt from its per-request rows with exp1's own
_stats / steady_state_tps / reconciliation_gate. Its wall time per level is the
monotonic span first submit -> last return, which omits only thread start-up.
Such runs are marked `reconstructed` and carry no run digest.

Clock: every duration is on WSL CLOCK_MONOTONIC, which ran slow during WS1
(AUDIT_WS0 F1). Each run's rate against the Windows host is the mean of its pre-
and post-run calibration; `corrected` values divide durations (multiply rates)
by it. The host clock itself ran 2 % slow against UTC when checked on
2026-09-29 (revision/ws1/clock_vs_ntp_2026-09-29.json), so corrected values are
host-referenced, not UTC-referenced. dev-vs-prod ratios are taken within each
repetition, where both profiles ran back to back, so slow drift cancels.

Output: results/v2/ws1/ws1_summary.json and a printed table.
"""
import collections
import glob
import json
import math
import os
import statistics as st
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "experiments"))
import exp1_latency_real as e1  # noqa: E402

RAW = os.path.join(REPO, "results", "v2", "raw", "ws1")
OUT = os.path.join(REPO, "results", "v2", "ws1")
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228}


def agg(xs):
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if n == 0:
        return {"n": 0}
    m = st.fmean(xs)
    sd = st.stdev(xs) if n > 1 else 0.0
    return {"n": n, "mean": round(m, 4), "median": round(st.median(xs), 4),
            "sd": round(sd, 4), "min": round(min(xs), 4), "max": round(max(xs), 4),
            "ci95_half": round(T975[n - 1] * sd / math.sqrt(n), 4) if n > 1 else None}


def rebuild(rows_path):
    """exp1 throughput block rebuilt from per-request rows."""
    by = collections.defaultdict(list)
    for line in open(rows_path):
        r = json.loads(line)
        by[r["phase"]].append(r)
    out = collections.defaultdict(list)
    for phase, reqs in by.items():
        _, cls, cs = phase.split(":")
        c = int(cs[1:])
        ok = [r for r in reqs if r["ok"]]
        wall = max(r["t_return_mono"] for r in reqs) - min(r["t_submit_mono"] for r in reqs)
        tps = len(ok) / wall
        ack = e1._stats([r.get("ack_ms") for r in ok])
        ss = e1.steady_state_tps(ok, c)
        out[cls].append({
            "concurrency": c, "n_sent": len(reqs), "n_ok": len(ok), "errors": len(reqs) - len(ok),
            "wall_s": {"kind": "derived", "value": round(wall, 3),
                       "derivation": "max t_return_mono - min t_submit_mono (rebuilt)"},
            "throughput_tps": {"kind": "derived", "value": round(tps, 3)},
            "throughput_steady_tps": {"kind": "derived", "value": round(ss, 3) if ss else None},
            "ack_latency_ms": ack,
            "stage_fabric_ms": e1._stats([r.get("fabric_ms") for r in ok]),
            "stage_readback_ms": e1._stats([r.get("readback_ms") for r in ok]),
            "stage_policy_ms": e1._stats([r.get("policy_ms") for r in ok]),
            "stage_outbox_ms": e1._stats([r.get("outbox_ms") for r in ok]),
            "reconciliation_gate": e1.reconciliation_gate(c, tps, ack.get("mean")),
        })
    for cls in out:
        out[cls].sort(key=lambda r: r["concurrency"])
    return dict(out)


def load_runs():
    runs = []
    for d in sorted(glob.glob(os.path.join(RAW, "*", "rep*"))):
        profile, rep = d.split(os.sep)[-2], int(d.split(os.sep)[-1][3:])
        summ = os.path.join(d, "exp1", "exp1_latency_real.json")
        cal = [json.load(open(os.path.join(d, f)))["monotonic_rate_vs_host"]
               for f in ("clock_pre.json", "clock_post.json")]
        if os.path.exists(summ):
            j = json.load(open(summ))
            tp, how, chash = j["throughput"], "stored", j["provenance"]["config_hash"]
        else:
            tp, how, chash = rebuild(os.path.join(d, "exp1", "exp1_requests.jsonl")), "reconstructed", None
        runs.append({"profile": profile, "rep": rep, "source": how, "config_hash": chash,
                     "clock_rate_vs_host": {"pre": cal[0], "post": cal[1],
                                            "mean": round(st.fmean(cal), 5),
                                            "half_spread": round(abs(cal[0] - cal[1]) / 2, 5)},
                     "throughput": tp})
    return runs


def main():
    runs = load_runs()
    os.makedirs(OUT, exist_ok=True)
    classes = list(runs[0]["throughput"].keys())
    levels = [r["concurrency"] for r in runs[0]["throughput"][classes[0]]]
    gate_fail = [(r["profile"], r["rep"], cls, lv["concurrency"])
                 for r in runs for cls in r["throughput"] for lv in r["throughput"][cls]
                 if not lv["reconciliation_gate"]["passed"]]
    table = {}
    for cls in classes:
        table[cls] = {}
        for c in levels:
            cell = {}
            per = {}
            for r in runs:
                lv = next(x for x in r["throughput"][cls] if x["concurrency"] == c)
                k = r["clock_rate_vs_host"]["mean"]
                per[(r["profile"], r["rep"])] = {
                    "tps": lv["throughput_tps"]["value"],
                    "tps_corr": lv["throughput_tps"]["value"] * k,
                    "tps_steady": (lv.get("throughput_steady_tps") or {}).get("value"),
                    "ack_mean": lv["ack_latency_ms"]["mean"],
                    "ack_mean_corr": lv["ack_latency_ms"]["mean"] / k,
                    "ack_p50": lv["ack_latency_ms"]["p50"],
                    "ack_p95": lv["ack_latency_ms"]["p95"],
                    "readback": (lv.get("stage_readback_ms") or {}).get("mean"),
                    "fabric": (lv.get("stage_fabric_ms") or {}).get("mean"),
                }
            for p in ("dev", "prod"):
                vals = [v for (pp, _), v in per.items() if pp == p]
                cell[p] = {m: agg([v[m] for v in vals]) for m in vals[0]}
            reps = sorted({k for (_, k) in per})
            cell["prod_over_dev"] = {
                m: agg([per[("prod", k)][m] / per[("dev", k)][m] for k in reps
                        if per[("dev", k)][m] and per[("prod", k)][m] is not None])
                for m in ("tps", "ack_mean", "ack_p95", "readback")}
            table[cls][str(c)] = cell
    summary = {
        "workstream": "WS1", "topology_mode": "single_host (laptop, WSL2)",
        "runs": [{k: v for k, v in r.items() if k != "throughput"} for r in runs],
        "gate_failures": gate_fail,
        "config_hashes": sorted({r["config_hash"] for r in runs if r["config_hash"]}),
        "table": table,
    }
    with open(os.path.join(OUT, "ws1_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)

    print(f"runs: {len(runs)} ({sum(r['source'] == 'reconstructed' for r in runs)} reconstructed); "
          f"gate failures: {len(gate_fail)}; config hashes: {summary['config_hashes']}")
    print("clock rate vs host per run:",
          {f"{r['profile']}{r['rep']}": r["clock_rate_vs_host"]["mean"] for r in runs})
    hdr = f"{'fixture':13}{'c':>3} | {'dev TPS':>14} {'prod TPS':>14} {'prod/dev':>15} | {'dev ack':>9} {'prod ack':>9} {'ack p/d':>15}"
    print(hdr)
    for cls in classes:
        for c in levels:
            cell = table[cls][str(c)]
            f = lambda a: f"{a['mean']:.2f}±{a['ci95_half']:.2f}"  # noqa: E731
            g = lambda a: f"{a['mean']:.3f}±{a['ci95_half']:.3f}"  # noqa: E731
            print(f"{cls:13}{c:>3} | {f(cell['dev']['tps']):>14} {f(cell['prod']['tps']):>14} "
                  f"{g(cell['prod_over_dev']['tps']):>15} | {cell['dev']['ack_mean']['mean']:>9.0f} "
                  f"{cell['prod']['ack_mean']['mean']:>9.0f} {g(cell['prod_over_dev']['ack_mean']):>15}")


if __name__ == "__main__":
    main()
