"""WS2 analysis (Azure multi_vm): delay sweep, block-cutting sweep, baseline.

Input: results/v2/raw/ws2/<config>/rep<k>/{exp1/*, rtt.json, vmstat_*.txt}
Output: results/v2/ws2/ws2_summary.json and a printed digest.

Per config x fixture x level, across repetitions: mean/median/SD/95% t-CI of
TPS (gated n/wall and steady-state), ack mean/p50/p95, and stage means.
Model checks (Eq. 8):
  transition  observed c* = smallest level whose rep-median ack mean is below
              0.75 x the c=1 floor; predicted c* = MaxMessageCount.
  floor       ack at c=1 against BatchTimeout (floor - BT = fixed per-request cost).
  delay       floor(c=1) against added RTT (2 x netem one-way): least-squares
              slope = effective inter-host round trips per acknowledged request.
"""
import glob
import json
import math
import os
import statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(REPO, "results", "v2", "raw", "ws2")
OUT = os.path.join(REPO, "results", "v2", "ws2")
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
CONFIG = {  # name: (netem one-way ms, MMC, BT seconds)
    "base": (0, 10, 2.0), "d10": (10, 10, 2.0), "d25": (25, 10, 2.0), "d50": (50, 10, 2.0),
    "m5": (0, 5, 2.0), "m20": (0, 20, 2.0), "t05": (0, 10, 0.5), "t1": (0, 10, 1.0)}


def agg(xs):
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if not n:
        return {"n": 0}
    m, sd = st.fmean(xs), (st.stdev(xs) if n > 1 else 0.0)
    return {"n": n, "mean": round(m, 3), "median": round(st.median(xs), 3), "sd": round(sd, 3),
            "ci95_half": round(T975.get(n - 1, 1.96) * sd / math.sqrt(n), 3) if n > 1 else None}


def vmstat_busy(path):
    busy = []
    for ln in open(path):
        p = ln.split()
        if len(p) > 16 and p[0].isdigit():
            busy.append(100 - int(p[14]))     # vmstat -t: col 15 = id
    return round(st.fmean(busy), 1) if busy else None


def main():
    os.makedirs(OUT, exist_ok=True)
    summary = {"workstream": "WS2", "topology_mode": "multi_vm", "configs": {}}
    for name, (ms, mmc, bt) in CONFIG.items():
        runs = []
        for d in sorted(glob.glob(os.path.join(RAW, name, "rep*"))):
            f = os.path.join(d, "exp1", "exp1_latency_real.json")
            if not os.path.exists(f):
                continue
            j = json.load(open(f))
            rtt = json.load(open(os.path.join(d, "rtt.json"))) if os.path.exists(os.path.join(d, "rtt.json")) else {}
            cpu = {os.path.basename(v)[7:-4]: vmstat_busy(v) for v in glob.glob(os.path.join(d, "vmstat_*.txt"))}
            runs.append({"rep": d.split("rep")[-1], "j": j, "rtt": rtt, "cpu": cpu})
        if not runs:
            continue
        cfg = {"netem_one_way_ms": ms, "max_message_count": mmc, "batch_timeout_s": bt,
               "reps": len(runs), "config_hashes": sorted({r["j"]["provenance"]["config_hash"] for r in runs}),
               "gate_failures": sum(len(r["j"].get("reconciliation_gate_failures", [])) for r in runs),
               "rtt_ms": {pair: agg([r["rtt"].get(pair, {}).get("avg") for r in runs])
                          for pair in sorted({p for r in runs for p in r["rtt"]})},
               "cpu_busy_pct": {h: agg([r["cpu"].get(h) for r in runs])
                                for h in sorted({h for r in runs for h in r["cpu"]})},
               "fixtures": {}}
        for cls in runs[0]["j"]["throughput"]:
            levels = [lv["concurrency"] for lv in runs[0]["j"]["throughput"][cls]]
            table = {}
            for c in levels:
                cell = {}
                vals = [next(x for x in r["j"]["throughput"][cls] if x["concurrency"] == c) for r in runs]
                cell["tps"] = agg([v["throughput_tps"]["value"] for v in vals])
                cell["tps_steady"] = agg([(v.get("throughput_steady_tps") or {}).get("value") for v in vals])
                for k in ("mean", "p50", "p95"):
                    cell[f"ack_{k}"] = agg([v["ack_latency_ms"].get(k) for v in vals])
                for s in ("fabric", "readback", "policy", "outbox"):
                    cell[f"stage_{s}"] = agg([(v.get(f"stage_{s}_ms") or {}).get("mean") for v in vals])
                table[str(c)] = cell
            floor = table[str(levels[0])]["ack_mean"]["median"]   # rep-median of mean ack at c=1
            trans = next((c for c in levels if table[str(c)]["ack_mean"]["median"] < 0.75 * floor), None)
            cfg["fixtures"][cls] = {"levels": table, "floor_ack_ms_c1": floor,
                                    "observed_transition_c": trans, "predicted_transition_c": mmc,
                                    "floor_minus_bt_ms": round(floor - bt * 1000, 1),
                                    "peak_tps": max(table[str(c)]["tps"]["mean"] for c in levels)}
        summary["configs"][name] = cfg
    # delay fit: floor(c=1) vs added RTT
    fits = {}
    for cls in ("mixed", "fabric_only"):
        pts = [(2 * CONFIG[n][0], summary["configs"][n]["fixtures"][cls]["floor_ack_ms_c1"])
               for n in ("base", "d10", "d25", "d50") if n in summary["configs"]
               and cls in summary["configs"][n]["fixtures"]]
        if len(pts) >= 2:
            mx, my = st.fmean(p[0] for p in pts), st.fmean(p[1] for p in pts)
            sxx = sum((p[0] - mx) ** 2 for p in pts)
            b = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx if sxx else None
            fits[cls] = {"points_added_rtt_ms_vs_floor_ms": pts, "slope_round_trips": round(b, 2) if b else None,
                         "intercept_ms": round(my - b * mx, 1) if b else None}
    summary["delay_fit"] = fits
    with open(os.path.join(OUT, "ws2_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    for name, cfg in summary["configs"].items():
        for cls, fx in cfg["fixtures"].items():
            print(f"{name:5} {cls:13} reps={cfg['reps']} floor={fx['floor_ack_ms_c1']:.0f}ms "
                  f"c*={fx['observed_transition_c']} (pred {fx['predicted_transition_c']}) "
                  f"peak={fx['peak_tps']:.2f}TPS gatefail={cfg['gate_failures']}")
    print("delay fit:", json.dumps(fits))


if __name__ == "__main__":
    main()
