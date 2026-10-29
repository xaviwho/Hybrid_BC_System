#!/usr/bin/env python3
"""
R2-1 — orderer crash and the transactional outbox's forward progress.

Reviewer (round 2): "explicitly discuss how an orderer crash affects the
transactional outbox's forward progress". Measured on the Azure multi_vm testbed
(single-consenter Raft orderer, as deployed):

  t < 0          closed-loop HYBRID load at concurrency c (mixed fixture) with one
                 lease relay; c is chosen above the relay's capacity so an anchor
                 backlog exists when the orderer dies
  t = 0          orderer container SIGKILLed (crash, not a clean stop)
  t = OUTAGE     orderer restarted from its own ledger/WAL
  t = OUTAGE+POST  load stopped

Reported:
  ingest     requests, successes and failures before/during/after the outage;
             error causes; time from orderer restart to the first successful ack
  outbox     queue depth and anchors delivered every 0.5 s; anchors delivered
             DURING the outage (forward progress of already-committed records)
  ambiguity  failed requests whose record nevertheless committed on Fabric
             (checked on the ledger before any retry)
  repair     every failed request retried once with the same payload; then the
             reconciliation sweep (--repair) for any record committed without
             an outbox row
  safety     anchors (DataRegistered events) == HYBRID records on Fabric, and
             zero duplicate anchors

Orderer control: ORDERER_KILL_CMD / ORDERER_START_CMD (default: ssh orbit-c docker).
Output: <out>/rep<k>/result.json (+ requests.jsonl, samples.json, relay log).
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harnesslib as H  # noqa: E402
import fabric_client  # noqa: E402
from outbox import Outbox  # noqa: E402

KILL = os.getenv("ORDERER_KILL_CMD", "ssh -n orbit-c 'sudo docker kill orderer.example.com'")
START = os.getenv("ORDERER_START_CMD", "ssh -n orbit-c 'sudo docker start orderer.example.com'")


def idem_key(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--c", type=int, default=10)
    ap.add_argument("--pre", type=float, default=60)
    ap.add_argument("--outage", type=float, default=60)
    ap.add_argument("--post", type=float, default=120)
    ap.add_argument("--out", default=os.path.join(H.REPO, "results", "v2", "raw", "r2_orderer"))
    a = ap.parse_args()
    from exp1_latency_real import payload

    tag = f"r2ord-r{a.rep}-{int(time.time())}"
    d = os.path.join(a.out, f"rep{a.rep}")
    os.makedirs(d, exist_ok=True)
    ob = Outbox(os.environ["OUTBOX_DB"])
    w3, contract, addr = H.chain()
    b0 = w3.eth.block_number + 1
    H.services("prod")
    relays = H.Relays(1, "lease", d)

    rows, lock, seq = [], threading.Lock(), [0]
    stop = threading.Event()
    sess = threading.local()

    def worker():
        s = sess.__dict__.setdefault("s", requests.Session())
        while not stop.is_set():
            with lock:
                i = seq[0]; seq[0] += 1
            x = payload("mixed", i)
            x["id"] = f"{tag}-{i}"
            r = {"i": i, "key": idem_key(x), "t_submit": time.monotonic()}
            try:
                resp = s.post(H.ORCH + "/ingest_data", json=x, timeout=90)
                r.update(status=resp.status_code)
                j = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                r.update(outbox_id=j.get("outbox_id"), error=j.get("error"),
                         ack_ms=(j.get("timing_ms") or {}).get("ack_ms"))
            except requests.RequestException as e:
                r.update(status=None, error=type(e).__name__)
            r["t_return"] = time.monotonic()
            with lock:
                rows.append(r)
            if r["status"] not in (200, 202):
                stop.wait(1.0)                       # client back-off on failure

    samples = []

    def sampler():
        mine = Outbox(ob.db_path)
        while not stop.is_set() or len(samples) < 2:
            q = mine._conn().execute(
                "SELECT SUM(state='pending'), SUM(state='delivered') FROM outbox WHERE twin_key LIKE ?",
                (tag + "-%",)).fetchone()
            samples.append([round(time.monotonic(), 3), q[0] or 0, q[1] or 0])
            time.sleep(0.5)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(a.c)]
    smp = threading.Thread(target=sampler, daemon=True)
    try:
        t_load = time.monotonic()
        smp.start()
        for t in threads:
            t.start()
        time.sleep(a.pre)
        t_kill = time.monotonic()
        subprocess.run(KILL, shell=True, capture_output=True, text=True)
        t_killed = time.monotonic()
        time.sleep(a.outage)
        t_start = time.monotonic()
        subprocess.run(START, shell=True, capture_output=True, text=True)
        t_started = time.monotonic()
        time.sleep(a.post)
        stop.set()
        for t in threads:
            t.join(120)
        smp.join(5)
        t_end = time.monotonic()

        failed = [r for r in rows if r.get("status") not in (200, 202)]
        # ambiguity: did the record commit on Fabric although the client saw a failure?
        with ThreadPoolExecutor(max_workers=8) as ex:
            found = list(ex.map(lambda r: fabric_client.read_iot_data(r["key"]), failed))
        ambiguous = [r for r, f in zip(failed, found) if f]

        # retry every failed request once, same payload (same idempotency key)
        def retry(r):
            x = payload("mixed", r["i"]); x["id"] = f"{tag}-{r['i']}"
            try:
                resp = requests.post(H.ORCH + "/ingest_data", json=x, timeout=120)
                j = resp.json()
                return {"i": r["i"], "status": resp.status_code, "replay": j.get("idempotency_replay"),
                        "replay_source": j.get("replay_source"), "outbox_id": j.get("outbox_id")}
            except (requests.RequestException, ValueError) as e:
                return {"i": r["i"], "status": None, "error": type(e).__name__}
        with ThreadPoolExecutor(max_workers=a.c) as ex:
            retries = list(ex.map(retry, failed))
        ids = [x[0] for x in ob._conn().execute("SELECT id FROM outbox WHERE twin_key LIKE ?", (tag + "-%",))]
        drained = H.wait_delivered(ob, ids, timeout=1200)
        sweep = H.run_reconcile(tag, os.path.join(d, "reconcile_repair.json"), repair=True)
        ids = [x[0] for x in ob._conn().execute("SELECT id FROM outbox WHERE twin_key LIKE ?", (tag + "-%",))]
        drained = H.wait_delivered(ob, ids, timeout=1200) and drained
    finally:
        stop.set()
        relays.stop()

    ev = H.events_for(contract, ids, b0)
    c = sweep.get("counts", {})
    hybrid_on_fabric = sum(v for k, v in c.items() if k != "fabric_only")
    rel = lambda t: round(t - t_kill, 3)  # noqa: E731
    win = {"pre": (t_load, t_kill), "outage": (t_kill, t_started), "post": (t_started, t_end)}

    def in_win(r, w):
        lo, hi = win[w]
        return lo <= r["t_submit"] < hi

    phase = {}
    for w in win:
        rs = [r for r in rows if in_win(r, w)]
        ok = [r for r in rs if r.get("status") in (200, 202)]
        errs = {}
        for r in rs:
            if r.get("status") not in (200, 202):
                key = f"{r.get('status')}: {str(r.get('error'))[:60]}"
                errs[key] = errs.get(key, 0) + 1
        span = win[w][1] - win[w][0]
        phase[w] = {"requests": len(rs), "ok": len(ok), "failed": len(rs) - len(ok),
                    "ok_per_s": round(len(ok) / span, 3) if span > 0 else None, "errors": errs}
    first_ok_after = min((r["t_return"] for r in rows if r.get("status") in (200, 202) and r["t_submit"] >= t_started),
                         default=None)
    delivered_rows = [ob.get(i) for i in ids]
    deliv_during = sum(1 for r in delivered_rows if r and r["delivered_mono"] and t_kill <= r["delivered_mono"] < t_started)
    depth_at = lambda t: min(samples, key=lambda s: abs(s[0] - t))[1] if samples else None  # noqa: E731
    res = {
        "rep": a.rep, "tag": tag, "c": a.c, "relays": "k=1 lease",
        "timeline_s": {"pre": a.pre, "outage_requested": a.outage, "post": a.post,
                       "kill_cmd_s": round(t_killed - t_kill, 3), "start_cmd_s": round(t_started - t_start, 3)},
        "ingest_by_phase": phase,
        "time_to_first_ack_after_restart_s": round(first_ok_after - t_started, 3) if first_ok_after else None,
        "outbox": {"queue_depth_at_kill": depth_at(t_kill), "queue_depth_at_restart": depth_at(t_started),
                   "anchors_delivered_during_outage": deliv_during,
                   "relay_rate_during_outage_per_s": round(deliv_during / (t_started - t_kill), 3)},
        "ambiguous_failed_but_committed": len(ambiguous),
        "retries": {"n": len(retries), "status": {str(s): sum(1 for r in retries if r.get("status") == s)
                                                  for s in {r.get("status") for r in retries}},
                    "replays": sum(1 for r in retries if r.get("replay"))},
        "sweep": {"counts": c, "repaired": sum(1 for g in sweep.get("gaps", []) if g.get("repair")),
                  "sweep_s": sweep.get("sweep_s"), "error": sweep.get("error")},
        "all_delivered": drained,
        "hybrid_records_on_fabric": hybrid_on_fabric,
        "anchors_on_chain": sum(len(v) for v in ev.values()),
        "anchors_equal_hybrid_records": sum(len(v) for v in ev.values()) == hybrid_on_fabric,
        "duplicate_anchors": sum(1 for v in ev.values() if len(v) > 1),
    }
    with open(os.path.join(d, "requests.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(dict(r, t_submit_rel=rel(r["t_submit"]), t_return_rel=rel(r["t_return"]))) + "\n")
    with open(os.path.join(d, "samples.json"), "w") as f:
        json.dump({"t_kill": 0, "t_restart": rel(t_started), "samples": [[rel(s[0]), s[1], s[2]] for s in samples]}, f)
    with open(os.path.join(d, "result.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
