#!/usr/bin/env python3
"""
WS3 — multi-relay, fault-tolerant anchoring (Reviewer 1.2; closes the mu_relay gap).

Parts (run on the measurement host, orchestrator in prod profile, no other relay):

  drain   mu_relay characterisation. Synthetic outbox rows are inserted open-loop
          at rate lambda for T seconds (they bypass Fabric, so lambda can exceed
          what ingestion could offer); k relays in `lease` or `race` mode deliver
          them. Queue depth is sampled every 0.5 s. Reported per run: offered
          and delivered rates, mu_relay (delivery rate while a backlog exists),
          queue wait (T_queue) and its growth over enqueue time, reverted
          duplicates and gas wasted counted from ON-CHAIN receipts.
  fault   k in {2,3} x mode x {after_broadcast, after_receipt, mid_poll, sigkill}.
          M HYBRID records go through the orchestrator while relay-1 dies at the
          injected point (after it has delivered CRASH_AFTER rows). Verified from
          the contract's event logs: anchors == distinct records, duplicates == 0,
          plus on-chain reverts, gas wasted, time to recovery after the crash.
  safety  tampering relay (auditor must flag c' != c) and withholding relay
          (reconciliation sweep must list and repair).

Every anchor in this workstream is a real transaction on the v2 registry.
Output: <out>/<part>/<config>/rep<k>/result.json plus relay logs and samples.
"""
import argparse
import json
import os
import statistics as st
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harnesslib as H  # noqa: E402
from outbox import Outbox  # noqa: E402

CRASH_AFTER = 3     # relay-1 dies after its 3rd delivery (early enough to fire under k-way sharing)


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))] if xs else None


def drain_run(ob, k, coord, lam, T, d, tag):
    w3, contract, addr = H.chain()
    b0 = w3.eth.block_number + 1
    relays = H.Relays(k, coord, d)
    prefix = f"{tag}"
    sampler = H.Sampler(ob, prefix); sampler.start()
    n = int(lam * T)
    try:
        t_start = time.monotonic()
        for i in range(n):                          # open loop: row i due at t_start + i/lam
            due = t_start + i / lam
            while time.monotonic() < due:
                time.sleep(min(0.002, due - time.monotonic()))
            m = {"deviceId": "ws3", "seq": i, "run": tag}
            c = cm_commit(tag, i)
            ob.commit_and_enqueue(record_id=f"{prefix}-{i}", commitment=c, fabric_tx_id=None,
                                  twin_key=f"{prefix}-{i}", payload={"data_id": f"{prefix}-{i}", "m": m},
                                  anchor_required=True)
        t_enq = time.monotonic()
        ids = [f"{prefix}-{i}" for i in range(n)]
        ok = H.wait_delivered(ob, ids, timeout=1800)
        t_done = time.monotonic()
    finally:
        sampler.stop(); relays.stop()
    b1 = w3.eth.block_number
    rows = [ob.get(i) for i in ids]
    qwait = [(r["started_mono"] - r["created_mono"]) * 1000 for r in rows if r and r["started_mono"]]
    created = [r["created_mono"] - t_start for r in rows if r and r["started_mono"]]
    delivered = sorted(r["delivered_mono"] for r in rows if r and r["delivered_mono"])
    # mu while backlogged: deliveries between the first and last sample with depth >= k
    back = [s for s in sampler.samples if s[1] >= max(2, k)]
    mu = None
    if len(back) >= 4:
        dt = back[-1][0] - back[0][0]
        dd = back[-1][2] - back[0][2]
        mu = dd / dt if dt > 0 else None
    slope = None
    if len(created) > 2:
        mc, mq = st.fmean(created), st.fmean(qwait)
        vc = sum((x - mc) ** 2 for x in created)
        slope = sum((x - mc) * (y - mq) for x, y in zip(created, qwait)) / vc if vc else None
    ev = H.events_for(contract, ids, b0)
    att = ob._conn().execute(
        "SELECT outcome, COUNT(*), SUM(COALESCE(gas_used,0)) FROM relay_attempts WHERE row_id LIKE ? GROUP BY outcome",
        (prefix + "-%",)).fetchall()
    return {
        "part": "drain", "k": k, "coord": coord, "lambda_offered": lam, "T_s": T, "n": n,
        "all_delivered": ok,
        "offered_rate_achieved": round(n / (t_enq - t_start), 3),
        "delivered_rate_overall": round(n / (delivered[-1] - t_start), 3) if delivered else None,
        "mu_relay_backlogged": round(mu, 3) if mu else None,
        "backlog_formed": len(back) >= 4,
        "queue_depth_max": max((s[1] for s in sampler.samples), default=0),
        "t_queue_ms": {"mean": round(st.fmean(qwait), 1) if qwait else None,
                       "p50": pct(qwait, .5), "p95": pct(qwait, .95), "max": max(qwait) if qwait else None},
        "t_queue_growth_ms_per_s": round(slope, 2) if slope is not None else None,
        "drain_after_enqueue_s": round(t_done - t_enq, 2),
        "events": {"ids_with_one": sum(1 for v in ev.values() if len(v) == 1),
                   "ids_with_none": sum(1 for v in ev.values() if not v),
                   "ids_with_many": sum(1 for v in ev.values() if len(v) > 1)},
        "attempts_by_outcome": {o: {"n": n_, "gas": g} for o, n_, g in att},
        "chain": H.chain_reverts(w3, addr, b0, b1),
        "queue_samples": sampler.samples,
    }


def cm_commit(tag, i):
    return H.cm.h_hex(H.cm.canon({"ws3_drain": tag, "i": i}))


def fault_run(ob, k, coord, hook, M, d, tag):
    w3, contract, addr = H.chain()
    b0 = w3.eth.block_number + 1
    env1 = {} if hook == "sigkill" else {"TEST_CRASH_HOOK": hook, "TEST_CRASH_AFTER": str(CRASH_AFTER)}
    relays = H.Relays(k, coord, d, lease_s=10, per_relay_env={1: env1})
    import threading
    subs = {}
    try:
        th = threading.Thread(target=lambda: subs.update(r=H.submit_hybrid(tag, M, concurrency=6)))
        th.start()
        t_kill = None
        end = time.monotonic() + 600
        while time.monotonic() < end and t_kill is None:
            if hook == "sigkill":
                n1 = ob._conn().execute("SELECT COUNT(*) FROM outbox WHERE delivered_by='relay-1' AND twin_key LIKE ?",
                                        (tag + "-%",)).fetchone()[0]
                if n1 >= CRASH_AFTER:
                    relays.kill(1); t_kill = time.monotonic()
            elif relays.procs[1].poll() is not None:
                t_kill = time.monotonic()
            if not th.is_alive():                   # all submitted: stop waiting once all delivered
                done_ids = [r["outbox_id"] for r in subs.get("r", []) if r["status"] in (200, 202)
                            and r["route"] == "HYBRID"]
                if all((ob.get(i) or {}).get("state") == "delivered" for i in done_ids):
                    break
            time.sleep(0.02)
        th.join()
        ids = [r["outbox_id"] for r in subs["r"] if r["status"] in (200, 202) and r["route"] == "HYBRID"]
        ok = H.wait_delivered(ob, ids, timeout=600)
    finally:
        relays.stop()
    b1 = w3.eth.block_number
    rows = [ob.get(i) for i in ids]
    ev = H.events_for(contract, ids, b0)
    commit_of = {r["outbox_id"]: r["commitment"] for r in subs["r"]}
    delivered = [r["delivered_mono"] for r in rows if r and r["delivered_mono"]]
    # the row relay-1 died holding (hooks log it; SIGKILL: rows relay-1 claimed
    # last and another relay delivered)
    crashed_ids = [x[0] for x in ob._conn().execute(
        "SELECT row_id FROM relay_attempts WHERE relay_id='relay-1' AND outcome='crashed' AND row_id IN (%s)"
        % ",".join("?" * len(ids)), ids).fetchall()] if ids else []
    held = [ob.get(i) for i in crashed_ids] or \
        [r for r in rows if r and r["claimed_by"] == "relay-1" and r["delivered_by"] != "relay-1"]
    return {
        "part": "fault", "k": k, "coord": coord, "hook": hook, "M": M, "crash_after": CRASH_AFTER,
        "submitted_ok": len(ids), "all_delivered": ok, "relay1_killed": t_kill is not None,
        "anchors_on_chain": sum(len(v) for v in ev.values()),
        "distinct_records": len(ids),
        "anchors_equal_records": sum(len(v) for v in ev.values()) == len(ids),
        "duplicate_anchors": sum(1 for v in ev.values() if len(v) > 1),
        "missing_anchors": sum(1 for v in ev.values() if not v),
        "commitments_match": all(len(v) == 1 and v[0]["dataHash"] == commit_of[i] for i, v in ev.items()),
        # brief's definition: latency of the last anchor after the kill (includes the
        # rest of the workload still being ingested)
        "time_to_recovery_s": round(max(delivered) - t_kill, 3) if (t_kill and delivered) else None,
        "rows_held_by_crashed_relay": len(held),
        "crashed_row_ids": crashed_ids,
        # recovery of the row(s) the crashed relay was holding: kill -> delivered by a survivor
        "recovery_of_held_rows_s": [round(r["delivered_mono"] - t_kill, 3) for r in held
                                    if r and r.get("delivered_mono")] if t_kill else None,
        "chain": H.chain_reverts(w3, addr, b0, b1),
        "attempts_by_outcome": {o: n for o, n in ob._conn().execute(
            "SELECT a.outcome, COUNT(*) FROM relay_attempts a JOIN outbox o ON o.id=a.row_id "
            "WHERE o.twin_key LIKE ? GROUP BY a.outcome", (tag + "-%",)).fetchall()},
    }


def tamper_run(ob, M, d, tag):
    w3, _, _ = H.chain()
    b0 = w3.eth.block_number + 1
    relays = H.Relays(1, "lease", d, per_relay_env={1: {"TEST_TAMPER": "1"}})
    try:
        subs = H.submit_hybrid(tag, M, concurrency=6)
        ids = [r["outbox_id"] for r in subs if r["status"] in (200, 202) and r["route"] == "HYBRID"]
        H.wait_delivered(ob, ids)
    finally:
        relays.stop()
    rep = H.run_auditor(ids, os.path.join(d, "audit.json"), from_block=b0)
    return {"part": "safety", "case": "tamper", "M": len(ids), "auditor_error": rep.get("error"),
            "flagged": len(rep.get("failed", [])), "flagged_as_tamper": rep.get("by_reason", {}).get("TAMPER"),
            "detection_rate": round(len(rep.get("failed", [])) / len(ids), 4) if ids else None}


def withhold_run(ob, M, d, tag):
    w3, _, _ = H.chain()
    b0 = w3.eth.block_number + 1
    relays = H.Relays(1, "lease", d, per_relay_env={1: {"TEST_WITHHOLD": "1"}})
    try:
        subs = H.submit_hybrid(tag, M, concurrency=6)
        ids = [r["outbox_id"] for r in subs if r["status"] in (200, 202) and r["route"] == "HYBRID"]
        H.wait_delivered(ob, ids)
    finally:
        relays.stop()
    # One sweep: --repair classifies every record before repairing it, so its
    # counts are the detection result and its gaps list what it repaired.
    rep1 = H.run_reconcile(tag, os.path.join(d, "reconcile_repair.json"), repair=True)
    honest = H.Relays(1, "lease", os.path.join(d, "honest"))
    try:
        H.wait_delivered(ob, ids)
    finally:
        honest.stop()
    after = H.run_auditor(ids, os.path.join(d, "audit_after.json"), from_block=b0)
    found = rep1.get("counts", {}).get("withheld", 0)
    return {"part": "safety", "case": "withhold", "M": len(ids), "sweep_error": rep1.get("error"),
            "sweep_s": rep1.get("sweep_s"),
            "listed_by_sweep": found,
            "detection_rate": round(found / len(ids), 4) if ids else None,
            "repaired": sum(1 for g in rep1.get("gaps", []) if g.get("repair") == "reset_to_pending"),
            "audit_pass_after_repair": after.get("passed"),
            "anchors_after_repair_equal_records": after.get("passed") == len(ids)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["drain", "fault", "safety", "all"], default="all")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--k", default="1,2,3")
    ap.add_argument("--modes", default="lease,race")
    ap.add_argument("--lambdas", default="2,4,6,8,12,16")
    ap.add_argument("--T", type=float, default=60)
    ap.add_argument("--M", type=int, default=60)
    ap.add_argument("--hooks", default="after_broadcast,after_receipt,mid_poll,sigkill")
    ap.add_argument("--out", default=os.path.join(H.REPO, "results", "v2", "raw", "ws3"))
    a = ap.parse_args()
    ob = Outbox(os.environ["OUTBOX_DB"])
    H.services("prod")               # orchestrator + policy, no relay
    ks = [int(x) for x in a.k.split(",")]
    modes = a.modes.split(",")
    stamp = str(int(time.time()))
    for rep in range(1, a.reps + 1):
        jobs = []
        if a.part in ("drain", "all"):
            jobs += [("drain", f"k{k}_{m}_l{lam}", (k, m, float(lam)))
                     for k in ks for m in modes for lam in a.lambdas.split(",")]
        if a.part in ("fault", "all"):
            jobs += [("fault", f"k{k}_{m}_{h}", (k, m, h))
                     for k in ks if k >= 2 for m in modes for h in a.hooks.split(",")]
        if a.part in ("safety", "all"):
            jobs += [("safety", "tamper", ()), ("safety", "withhold", ())]
        for part, name, p in jobs:
            d = os.path.join(a.out, part, name, f"rep{rep}")
            if os.path.exists(os.path.join(d, "result.json")):
                continue
            os.makedirs(d, exist_ok=True)
            tag = f"ws3-{part}-{name}-r{rep}-{stamp}"
            t0 = time.time()
            if part == "drain":
                res = drain_run(ob, *p, a.T, d, tag)
            elif part == "fault":
                res = fault_run(ob, *p, a.M, d, tag)
            elif name == "tamper":
                res = tamper_run(ob, a.M, d, tag)
            else:
                res = withhold_run(ob, a.M, d, tag)
            res.update(rep=rep, tag=tag, wall_s=round(time.time() - t0, 1))
            with open(os.path.join(d, "result.json"), "w") as f:
                json.dump(res, f, indent=1)
            brief = {k: v for k, v in res.items() if k not in ("queue_samples", "attempts_by_outcome")}
            print(json.dumps(brief), flush=True)


if __name__ == "__main__":
    main()
