#!/usr/bin/env python3
"""
WS8 — consolidate every v2 result into results/v2/RESULTS.json (single source of truth).

Inputs (all under results/v2/):
  ws1/ws1_summary.json                 laptop single host, dev vs prod
  ws2/ws2_summary.json, raw/ws2/...    Azure multi_vm: delay, block cutting, baseline
  raw/ws2_probe/stage_probe.json       endorsement-stage probe
  raw/ws3/<part>/<cfg>/rep*/result.json
  raw/ws4/<arm>/rep*/exp1/...
  raw/ws5/rep*/result.json
  raw/ws7/<exp>/rep*/...
Rules enforced (revision brief):
  3/4  every metric carries kind: measured | derived (+ derivation) | modelled;
       an untagged metric fails consolidation.
  5    every chain-dependent Azure experiment records the same deployment
       (genesis hash, registry address, runtime-code keccak); disagreement fails.
       WS1 ran on the laptop deployment and is recorded as such.
  6    anything not run is listed as NOT_RUN with its reason.
  7    repetitions and CIs are carried with each aggregate.
Exit status 1 on any rule violation (the file is still written, with `errors`).
"""
import glob
import json
import math
import os
import statistics as st
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(REPO, "results", "v2")
RAW = os.path.join(V2, "raw")
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
errors, metrics, not_run, experiments = [], [], [], {}


def agg(xs):
    xs = [x for x in xs if x is not None]
    n = len(xs)
    if not n:
        return None
    m, sd = st.fmean(xs), (st.stdev(xs) if n > 1 else 0.0)
    return {"mean": round(m, 4), "median": round(st.median(xs), 4), "sd": round(sd, 4), "n": n,
            "ci95_half": round(T975.get(n - 1, 1.96) * sd / math.sqrt(n), 4) if n > 1 else None}


def M(metric, value, unit, kind, source, derivation=None, **kw):
    if kind not in ("measured", "derived", "modelled"):
        errors.append(f"{metric}: invalid kind {kind!r}")
    if kind == "derived" and not derivation:
        errors.append(f"{metric}: derived without derivation")
    if value is None:
        errors.append(f"{metric}: value is None (list it in not_run instead)")
    metrics.append(dict({"metric": metric, "value": value, "unit": unit, "kind": kind,
                         "source": source}, **({"derivation": derivation} if derivation else {}), **kw))


def load(path):
    return json.load(open(path)) if os.path.exists(path) else None


def deployment_of(digest):
    e = (digest or {}).get("ethereum", {})
    return (e.get("genesis_hash"), (e.get("contract_address") or "").lower(), e.get("contract_code_keccak"))


# ---------------------------------------------------------------- WS1 (laptop)
def ws1():
    s = load(os.path.join(V2, "ws1", "ws1_summary.json"))
    if not s:
        not_run.append({"id": "WS1", "reason": "ws1_summary.json absent"}); return
    experiments["WS1"] = {"status": "OK", "topology_mode": "single_host (laptop WSL2, 4 cores)",
                          "deployment": "laptop v2 (WS0.5)", "reps": 5,
                          "summary": "results/v2/ws1/ws1_summary.json",
                          "raw": "results/v2/raw/ws1/", "config_hashes": s["config_hashes"],
                          "caveat": "WSL CLOCK_MONOTONIC ran at 0.91-0.96 of the host clock (revision/CHECKPOINT1.md)"}
    for cls, levels in s["table"].items():
        for band, cs in (("below", ["1", "2", "4", "8"]), ("above", ["10", "12", "14", "16", "20", "24", "32"])):
            r = [levels[c]["prod_over_dev"]["tps"]["mean"] for c in cs if c in levels]
            M(f"ws1_tps_prod_over_dev_{band}_threshold_{cls}", round(st.fmean(r), 4), "ratio", "derived", "WS1",
              "mean over levels of the per-level mean of paired prod_k/dev_k TPS ratios",
              levels=cs, per_level_ci95=[levels[c]["prod_over_dev"]["tps"]["ci95_half"] for c in cs if c in levels])
    M("ws1_gate_failures", len(s["gate_failures"]), "count", "measured", "WS1")


# ---------------------------------------------------------------- WS2 (Azure)
def ws2(deps):
    s = load(os.path.join(V2, "ws2", "ws2_summary.json"))
    if not s:
        not_run.append({"id": "WS2", "reason": "ws2_summary.json absent (run revision/ws2/analyze_ws2.py)"}); return
    experiments["WS2"] = {"status": "OK", "topology_mode": "multi_vm (Azure: Korea Central + Japan East)",
                          "summary": "results/v2/ws2/ws2_summary.json", "raw": "results/v2/raw/ws2/",
                          "configs": {k: {x: v[x] for x in ("netem_one_way_ms", "max_message_count",
                                                            "batch_timeout_s", "reps", "gate_failures")}
                                      for k, v in s["configs"].items()}}
    for f in glob.glob(os.path.join(RAW, "ws2", "*", "rep*", "exp1", "exp1_latency_real.json")):
        deps.append(("WS2", f, deployment_of(load(f)["provenance"].get("run_digest_start"))))
    for name, cfg in s["configs"].items():
        for cls, fx in cfg["fixtures"].items():
            M(f"ws2_{name}_{cls}_floor_ack_ms", fx["floor_ack_ms_c1"], "ms", "measured", "WS2",
              reps=cfg["reps"], note="rep-median of mean ack at c=1")
            if fx["observed_transition_c"] is not None:
                M(f"ws2_{name}_{cls}_transition_c", fx["observed_transition_c"], "clients", "derived", "WS2",
                  "smallest c with rep-median mean ack < 0.75 x floor", predicted=fx["predicted_transition_c"])
            M(f"ws2_{name}_{cls}_peak_tps", fx["peak_tps"], "tps", "derived", "WS2",
              "max over levels of rep-mean n_ok/wall_s")
    for cls, fit in s.get("delay_fit", {}).items():
        if fit.get("slope_round_trips") is not None:
            M(f"ws2_delay_round_trips_{cls}", fit["slope_round_trips"], "RTTs", "derived", "WS2",
              "least-squares slope of floor(c=1) on added RTT = 2 x netem one-way", points=fit["points_added_rtt_ms_vs_floor_ms"])
    p = load(os.path.join(RAW, "ws2_probe", "stage_probe.json"))
    if p:
        for k, v in p["variants_ms"].items():
            M(f"ws2_probe_{k}_ms", v["mean"], "ms", "measured", "WS2 stage probe", ci95_half=v["ci95_half"], n=v["n"])
        M("ws2_probe_order_commit_ms", p["order_commit_ms"]["mean"], "ms", "derived", "WS2 stage probe",
          p["order_commit_ms"]["derivation"], ci95_half=p["order_commit_ms"]["ci95_half"])
    else:
        not_run.append({"id": "WS2.endorsement_probe", "reason": "stage_probe.json absent"})


# ---------------------------------------------------------------- WS3
def ws3():
    res = [load(f) for f in glob.glob(os.path.join(RAW, "ws3", "*", "*", "rep*", "result.json"))]
    res = [r for r in res if r]
    if not res:
        not_run.append({"id": "WS3", "reason": "no results under results/v2/raw/ws3"}); return
    experiments["WS3"] = {"status": "OK", "raw": "results/v2/raw/ws3/", "runs": len(res)}
    by = {}
    for r in res:
        key = (r["part"], r.get("k"), r.get("coord"), r.get("lambda_offered"), r.get("hook"), r.get("case"))
        by.setdefault(key, []).append(r)
    for (part, k, coord, lam, hook, case), rs in sorted(by.items(), key=str):
        if part == "drain":
            a = agg([r["mu_relay_backlogged"] for r in rs])
            if a:
                M(f"ws3_mu_relay_k{k}_{coord}_lambda{lam}", a["mean"], "anchors/s", "derived", "WS3 drain",
                  "delivered-count slope while queue depth >= max(2,k)", ci95_half=a["ci95_half"], reps=a["n"])
            M(f"ws3_tqueue_p95_ms_k{k}_{coord}_lambda{lam}", agg([r["t_queue_ms"]["p95"] for r in rs])["mean"],
              "ms", "measured", "WS3 drain", reps=len(rs))
            M(f"ws3_gas_wasted_k{k}_{coord}_lambda{lam}", sum(r["chain"]["gas_wasted"] for r in rs), "gas",
              "measured", "WS3 drain (on-chain receipts)", reps=len(rs))
        elif part == "fault":
            tag = f"k{k}_{coord}_{hook}"
            M(f"ws3_fault_{tag}_anchors_equal_records", all(r["anchors_equal_records"] for r in rs), "bool",
              "measured", "WS3 fault (DataRegistered logs)", reps=len(rs))
            M(f"ws3_fault_{tag}_duplicate_anchors", sum(r["duplicate_anchors"] for r in rs), "count",
              "measured", "WS3 fault (DataRegistered logs)", reps=len(rs))
            M(f"ws3_fault_{tag}_reverted_txs", sum(r["chain"]["reverted_txs"] for r in rs), "count",
              "measured", "WS3 fault (on-chain receipts)", reps=len(rs))
            M(f"ws3_fault_{tag}_gas_wasted", sum(r["chain"]["gas_wasted"] for r in rs), "gas", "measured",
              "WS3 fault (on-chain receipts)", reps=len(rs))
            ttr = agg([r["time_to_recovery_s"] for r in rs])
            if ttr:
                M(f"ws3_fault_{tag}_time_to_recovery_s", ttr["mean"], "s", "measured", "WS3 fault",
                  ci95_half=ttr["ci95_half"], reps=ttr["n"])
            held = agg([x for r in rs for x in (r.get("recovery_of_held_rows_s") or [])])
            if held:
                M(f"ws3_fault_{tag}_crashed_row_recovery_s", held["mean"], "s", "measured", "WS3 fault",
                  ci95_half=held["ci95_half"], n=held["n"],
                  note="kill -> the row the crashed relay held is delivered by a survivor")
            fired = sum(1 for r in rs if r["relay1_killed"])
            M(f"ws3_fault_{tag}_fault_fired", fired, f"of {len(rs)} reps", "measured", "WS3 fault")
        elif part == "safety":
            a = agg([r["detection_rate"] for r in rs])
            M(f"ws3_{case}_detection_rate", a["mean"] if a else None, "fraction", "measured",
              "WS3 safety (auditor / reconciliation sweep)", reps=len(rs))
            if case == "withhold":
                M("ws3_withhold_repaired_all", all(r.get("anchors_after_repair_equal_records") for r in rs),
                  "bool", "measured", "WS3 safety", reps=len(rs))


# ---------------------------------------------------------------- WS4
def ws4(deps):
    arms = {}
    for f in glob.glob(os.path.join(RAW, "ws4", "*", "rep*", "exp1", "exp1_latency_real.json")):
        arm = f.split(os.sep)[-4]
        j = load(f)
        arms.setdefault(arm, []).append(j)
        deps.append(("WS4", f, deployment_of(j["provenance"].get("run_digest_start"))))
    if not arms:
        not_run.append({"id": "WS4", "reason": "no results under results/v2/raw/ws4"}); return
    experiments["WS4"] = {"status": "OK", "raw": "results/v2/raw/ws4/", "reps": {a: len(v) for a, v in arms.items()}}
    series = {("sync", "mixed"): "sync_anchor", ("async", "mixed"): "async_outbox", ("async", "fabric_only"): "fabric_only"}
    for (arm, cls), label in series.items():
        runs = [j for j in arms.get(arm, []) if cls in j["throughput"]]
        if not runs:
            continue
        for c in [lv["concurrency"] for lv in runs[0]["throughput"][cls]]:
            ack = agg([next(x for x in j["throughput"][cls] if x["concurrency"] == c)["ack_latency_ms"]["mean"] for j in runs])
            tps = agg([next(x for x in j["throughput"][cls] if x["concurrency"] == c)["throughput_tps"]["value"] for j in runs])
            M(f"ws4_{label}_c{c}_ack_ms", ack["mean"], "ms", "measured", "WS4", ci95_half=ack["ci95_half"], reps=ack["n"])
            M(f"ws4_{label}_c{c}_tps", tps["mean"], "tps", "derived", "WS4", "n_ok / wall_s",
              ci95_half=tps["ci95_half"], reps=tps["n"])
    lat = [j["latency"]["mixed"] for j in arms.get("async", []) if "mixed" in j.get("latency", {})]
    if lat:
        tc = agg([x["completion_latency_ms"]["mean"] for x in lat])
        ta = agg([x["ack_latency_ms"]["mean"] for x in lat])
        M("ws4_async_tcmp_ms_c1", tc["mean"], "ms", "measured", "WS4 (sequential, 200/rep)", ci95_half=tc["ci95_half"], reps=tc["n"])
        M("ws4_async_tack_ms_c1", ta["mean"], "ms", "measured", "WS4 (sequential, 200/rep)", ci95_half=ta["ci95_half"], reps=ta["n"])


# ---------------------------------------------------------------- WS5
def ws5():
    rs = [load(f) for f in sorted(glob.glob(os.path.join(RAW, "ws5", "rep*", "result.json")))]
    rs = [r for r in rs if r]
    if not rs:
        not_run.append({"id": "WS5.crash_window", "reason": "no results under results/v2/raw/ws5"}); return
    experiments["WS5"] = {"status": "OK", "raw": "results/v2/raw/ws5/", "reps": len(rs),
                          "auditor": "tools/auditor/orbit_audit.py", "sweep": "tools/reconcile.py"}
    for k in ("orphans_created", "orphans_detected", "orphans_repaired", "anchors_after_repair", "auditor_passed"):
        M(f"ws5_{k}", sum(r[k] or 0 for r in rs), "count", "measured", "WS5 crash window", reps=len(rs))
    M("ws5_all_orphans_detected_and_repaired",
      all(r["orphans_created"] == r["orphans_detected"] == r["orphans_repaired"] and r["anchors_equal_hybrid_records"] for r in rs),
      "bool", "measured", "WS5 crash window", reps=len(rs))
    M("ws5_sweep_s", agg([r["sweep_s"] for r in rs])["mean"], "s", "measured", "WS5 (full-ledger ListRecords scan)")


# ---------------------------------------------------------------- WS7
def ws7(deps):
    def one(exp):
        fs = sorted(glob.glob(os.path.join(RAW, "ws7", exp, "rep*", exp + "*", "*.json")))
        return [load(f) for f in fs if not f.endswith("run_digest.json")]
    for exp in ("exp2", "exp3", "exp4", "exp5", "exp8"):
        dg = [load(f) for f in glob.glob(os.path.join(RAW, "ws7", exp, "rep*", "run_digest.json"))]
        for d in dg:
            deps.append((f"WS7 {exp}", "run_digest.json", deployment_of(d)))
    e2 = one("exp2")
    if e2:
        j = e2[0]
        M("privacy_routing_accuracy", round(j["routing_accuracy"] * 100, 2), "%", "measured", "WS7 exp2")
        M("privacy_sensitive_leaks", j["leak_count"], "count", "measured", "WS7 exp2")
        M("privacy_policy_coverage", round(j["coverage"]["coverage"] * 100, 2), "%", "derived", "WS7 exp2",
          "explicit_rule_fields / observed_fields")
    e3 = [j for j in one("exp3") if "gas_per_record_by_batch" in j]
    if e3:
        j = e3[0]
        M("gas_per_record_single", j["single_anchor_gas"]["mean"], "gas", "measured", "WS7 exp3")
        for row in j["gas_per_record_by_batch"]:
            M(f"gas_root_anchor_N{row['batch_size']}", row["root_anchor_gas"]["mean"], "gas", "measured", "WS7 exp3")
            M(f"gas_reduction_N{row['batch_size']}", row["gas_reduction_pct"]["value"], "%", "derived", "WS7 exp3",
              row["gas_reduction_pct"]["derivation"])
        M("gas_root_flat_in_N", j["root_gas_flat_in_N"]["value"], "bool", "measured", "WS7 exp3",
          relative_spread=j["root_gas_flat_in_N"]["relative_spread"])
    e4 = [j for j in one("exp4") if "rollback_min_ms" in j]
    if e4:
        j = e4[0]
        M("rollback_latency_min_ms", j["rollback_min_ms"], "ms", "measured", "WS7 exp4")
        M("rollback_latency_max_ms", j["rollback_max_ms"], "ms", "measured", "WS7 exp4")
        for model, blk in j.get("by_state_model", {}).items():
            last = blk["storage_growth"][-1]
            M(f"storage_ratio_{model}_{last['versions']}_versions", last["compression_vs_snapshots"], "x", "derived",
              "WS7 exp4", "snapshot_equivalent_bytes / stored_bytes")
    e5 = [j for j in one("exp5") if "exactly_once_holds" in j]
    if e5:
        M("exactly_once_holds_all_reps", all(j["exactly_once_holds"] for j in e5), "bool", "measured",
          "WS7 exp5 (DataRegistered logs)", reps=len(e5))
    e8 = [j for j in one("exp8") if "by_state_model" in j]
    if e8:
        experiments["WS7.exp8"] = {"status": "OK", "raw": "results/v2/raw/ws7/exp8/"}
    got = {"exp2": e2, "exp3": e3, "exp4": e4, "exp5": e5, "exp8": e8}
    experiments["WS7"] = {"status": "OK" if all(got.values()) else "PARTIAL", "raw": "results/v2/raw/ws7/",
                          "present": [k for k, v in got.items() if v]}
    for k, v in got.items():
        if not v:
            not_run.append({"id": f"WS7.{k}", "reason": "no output under results/v2/raw/ws7"})


def main():
    deps = []
    ws1(); ws2(deps); ws3(); ws4(deps); ws5(); ws7(deps)
    ws6 = load(os.path.join(V2, "ws6_status.json"))
    not_run.append(ws6 or {"id": "WS6", "status": "NOT_RUN",
                           "reason": "SmartBFT (Fabric v3.x) not attempted; evaluation scoped to crash-fault tolerance"})
    ids = {d for _, _, d in deps if d[0]}
    if len(ids) > 1:
        errors.append(f"single-deployment rule violated: {sorted(ids)}")
    commit = subprocess.run(["git", "-c", "safe.directory=*", "-C", REPO, "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    out = {
        "schema_version": 3, "results_set": "v2", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "commit": commit,
        "deployment": {"genesis_hash": next(iter(ids))[0] if len(ids) == 1 else None,
                       "contract_address": next(iter(ids))[1] if len(ids) == 1 else None,
                       "contract_code_keccak": next(iter(ids))[2] if len(ids) == 1 else None,
                       "experiments_checked": len(deps)},
        "experiments": experiments, "not_run": not_run,
        "kind_counts": {k: sum(1 for m in metrics if m["kind"] == k) for k in ("measured", "derived", "modelled")},
        "metrics": metrics, "errors": errors,
    }
    os.makedirs(V2, exist_ok=True)
    with open(os.path.join(V2, "RESULTS.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"metrics {len(metrics)} {out['kind_counts']}; experiments {sorted(experiments)}; "
          f"not_run {[x['id'] for x in not_run]}; errors {len(errors)}")
    for e in errors:
        print("  ERROR:", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
