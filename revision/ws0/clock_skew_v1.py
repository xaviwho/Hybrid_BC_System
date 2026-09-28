"""WS0: detect wall-clock steps in the frozen v1 exp1 rows.

Each row carries t_submit / t_return from time.time() (CLOCK_REALTIME) and
rtt_ms from perf_counter (CLOCK_MONOTONIC), read around the same HTTP call.
With no clock step, (t_return - t_submit) * 1000 equals rtt_ms to within
microseconds. Writes revision/ws0/clock_skew_v1.json.
"""
import json
import math
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V1 = os.path.join(ROOT, "results", "v1")

d = json.load(open(os.path.join(V1, "RESULTS.json")))
rows = [json.loads(l) for l in open(os.path.join(V1, "raw", "exp1", "exp1_requests.jsonl"))]
rows = [r for r in rows if r.get("t_return") and r.get("rtt_ms") is not None]
for r in rows:
    r["skew_ms"] = (r["t_return"] - r["t_submit"]) * 1000 - r["rtt_ms"]
big = [r for r in rows if abs(r["skew_ms"]) > 50]

# Back-to-back c=1 and c=2 levels: the realtime span can only exceed the
# perf_counter wall time if the two clocks run at different rates.
rate = {}
for cls, levels in d["raw"]["exp1"]["throughput"].items():
    for L in levels:
        if L["concurrency"] in (1, 2):
            rs = [r for r in rows if r["phase"] == f"throughput:{cls}:c{L['concurrency']}"]
            span = max(r["t_return"] for r in rs) - min(r["t_submit"] for r in rs)
            rate[f"{cls}:c{L['concurrency']}"] = round(L["wall_s"]["value"] / span, 4)


def dist(rs, f):
    v = sorted(r[f] for r in rs)
    n = len(v)
    return {"n": n, "mean": round(st.fmean(v), 3), "median": round(st.median(v), 3),
            "p95_nearest_rank": v[max(0, math.ceil(0.95 * n) - 1)], "max": v[-1],
            "n_over_1000ms": sum(x > 1000 for x in v)}


lat = [r for r in rows if r["phase"].startswith("latency") and r.get("anchor_ms") is not None]
res = {
    "rows": len(rows),
    "rows_abs_skew_gt_50ms": len(big),
    "skew_ms_min": round(min(r["skew_ms"] for r in rows), 1),
    "skew_ms_max": round(max(r["skew_ms"] for r in rows), 1),
    "skew_ms_median_all_rows": round(st.median(r["skew_ms"] for r in rows), 3),
    "skew_ms_median_positive_steps": round(st.median(r["skew_ms"] for r in big if r["skew_ms"] > 0), 1),
    "affected_rows_by_phase": {p: sum(1 for r in big if r["phase"] == p)
                               for p in sorted({r["phase"] for r in big})},
    "perf_wall_over_realtime_span_c1_c2": rate,
    "server_realtime_timings_latency_phase": {
        "anchor_ms": dist(lat, "anchor_ms"),
        "queue_wait_ms": dist(lat, "queue_wait_ms"),
    },
}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "clock_skew_v1.json"), "w") as f:
    json.dump(res, f, indent=1)
print(json.dumps(res, indent=1))
