"""WS0: recompute the exp1 reconciliation gate from the frozen v1 data.

Reads results/v1 only. Writes revision/ws0/gate_recompute.json.

Per concurrency level:
  tps_reported   RESULTS.json value = n_ok / wall_s (wall_s from perf_counter)
  tps_realtime   n_ok / (max t_return - min t_submit), time.time() stamps
  lockstep_pred  n / (c * ceil(n / c)): the ratio observed/expected that a
                 closed loop of c workers draining a finite batch of n requests
                 produces when every request in a round takes the same time.
                 Exact below the block-cutting threshold, where BatchTimeout
                 paces every round.
"""
import collections
import json
import math
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V1 = os.path.join(ROOT, "results", "v1")
TOL = 0.25  # exp1_latency_real.GATE_TOLERANCE at v1

d = json.load(open(os.path.join(V1, "RESULTS.json")))
tp = d["raw"]["exp1"]["throughput"]
rows = [json.loads(l) for l in open(os.path.join(V1, "raw", "exp1", "exp1_requests.jsonl"))]
by_phase = collections.defaultdict(list)
for r in rows:
    by_phase[r["phase"]].append(r)

out = []
for cls, levels in tp.items():
    for L in levels:
        c = L["concurrency"]
        rs = [r for r in by_phase[f"throughput:{cls}:c{c}"] if r.get("ok")]
        n = len(rs)
        ack = st.fmean(r["ack_ms"] for r in rs)
        span = max(r["t_return"] for r in rs) - min(r["t_submit"] for r in rs)
        g = L["reconciliation_gate"]
        exp_tps = c / (ack / 1000)
        tps_rep = L["throughput_tps"]["value"]
        tps_rt = n / span
        out.append({
            "class": cls, "c": c, "n_ok": n,
            "wall_s": L["wall_s"]["value"],
            "realtime_span_s": round(span, 3),
            "ack_mean_ms_stored": L["ack_latency_ms"]["mean"],
            "ack_mean_ms_recomputed": round(ack, 3),
            "expected_tps_stored": g["expected_tps"],
            "expected_tps_recomputed": round(exp_tps, 3),
            "tps_reported": tps_rep,
            "tps_realtime": round(tps_rt, 3),
            "rel_err_stored": g["relative_error"],
            "rel_err_recomputed": round(abs(tps_rep - exp_tps) / exp_tps, 3),
            "rel_err_realtime": round(abs(tps_rt - exp_tps) / exp_tps, 3),
            "passed_stored": g["passed"],
            "passes_if_realtime": abs(tps_rt - exp_tps) / exp_tps <= TOL,
            "observed_over_expected": round(tps_rep / exp_tps, 4),
            "lockstep_pred": round(n / (c * math.ceil(n / c)), 4),
        })

arith = [o for o in out
         if abs(o["ack_mean_ms_stored"] - o["ack_mean_ms_recomputed"]) > 0.001
         or abs(o["expected_tps_stored"] - o["expected_tps_recomputed"]) > 0.0015
         or abs(o["rel_err_stored"] - o["rel_err_recomputed"]) > 0.0015]
summary = {
    "levels": len(out),
    "stored_arithmetic_mismatches": len(arith),
    "passed_stored": sum(o["passed_stored"] for o in out),
    "observed_below_expected": sum(o["tps_reported"] < o["expected_tps_recomputed"] for o in out),
    "max_rel_err_stored": max(o["rel_err_stored"] for o in out),
    "would_fail_on_realtime_span": [[o["class"], o["c"], o["rel_err_realtime"]]
                                    for o in out if not o["passes_if_realtime"]],
    "sub_threshold_lockstep_fit": [[o["class"], o["c"], o["observed_over_expected"], o["lockstep_pred"]]
                                   for o in out if o["c"] <= 8],
}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gate_recompute.json"), "w") as f:
    json.dump({"summary": summary, "levels": out}, f, indent=1)
print(json.dumps(summary, indent=1))
