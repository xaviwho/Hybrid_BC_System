#!/usr/bin/env python3
"""
WS5 crash-window test: kill the orchestrator between the Fabric commit and the
outbox write, N times, then prove the reconciliation sweep closes the gap.

  1. orchestrator (prod, gunicorn) with TEST_CRASH_AFTER_FABRIC=1: every request
     commits privately, then the worker exits before the outbox transaction;
     gunicorn starts a new worker. No relay runs.
  2. N HYBRID requests, one at a time (each gets no response).
  3. orchestrator restarted normally; sweep in report mode: orphans listed.
  4. sweep --repair: orphans enqueued with sigma/c rebuilt from Fabric; relay runs.
  5. auditor on the N ids: every record anchored with c' = c; DataRegistered
     events == N (from the contract, not the relay).

Reported: orphans created (N), detected by the sweep, repaired, anchors after
repair, auditor pass count.
"""
import argparse
import hashlib
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harnesslib as H  # noqa: E402
from outbox import Outbox  # noqa: E402


def idem_key(x):
    # the orchestrator's get_idempotency_key() for a request without the header
    return hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--N", type=int, default=30)
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(H.REPO, "results", "v2", "raw", "ws5"))
    a = ap.parse_args()
    from exp1_latency_real import payload
    tag = f"ws5-crash-r{a.rep}-{int(time.time())}"
    d = os.path.join(a.out, f"rep{a.rep}")
    os.makedirs(d, exist_ok=True)
    ob = Outbox(os.environ["OUTBOX_DB"])
    w3, contract, addr = H.chain()
    b0 = w3.eth.block_number + 1

    H.services("prod", extra_env={"TEST_CRASH_AFTER_FABRIC": "1"})
    ids, outcomes = [], []
    for i in range(a.N):
        x = payload("mixed", i)
        x["id"] = f"{tag}-{i}"
        ids.append(idem_key(x))
        H.wait_health()
        try:
            r = requests.post(H.ORCH + "/ingest_data", json=x, timeout=120)
            outcomes.append(r.status_code)
        except requests.RequestException as e:
            outcomes.append(type(e).__name__)
    time.sleep(2)
    on_fabric = sum(1 for rec in __import__("fabric_client").iter_records()
                    if rec.get("envelope") and json.loads(rec["envelope"]).get("x", {}).get("id", "").startswith(tag))
    in_outbox = sum(1 for i in ids if ob.get(i))

    H.services("prod")                        # hook off
    relays = H.Relays(1, "lease", os.path.join(d, "relay"))
    try:
        # One sweep: --repair classifies every record first (detection), then
        # enqueues the orphans it found (repair).
        repaired = H.run_reconcile(tag, os.path.join(d, "reconcile_repair.json"), repair=True)
        before = repaired
        delivered = H.wait_delivered(ob, ids, timeout=600)
    finally:
        relays.stop()
    audit = H.run_auditor(ids, os.path.join(d, "audit.json"), from_block=b0)
    ev = H.events_for(contract, ids, b0)
    res = {
        "rep": a.rep, "tag": tag, "N_trials": a.N,
        "client_outcomes": {str(k): outcomes.count(k) for k in set(outcomes)},
        "records_on_fabric": on_fabric,
        "outbox_rows_after_crashes": in_outbox,
        "orphans_created": on_fabric - in_outbox,
        "orphans_detected": before.get("counts", {}).get("orphan", 0),
        "orphans_repaired": sum(1 for g in repaired.get("gaps", []) if g.get("repair") == "enqueued"),
        "all_delivered_after_repair": delivered,
        "anchors_after_repair": sum(len(v) for v in ev.values()),
        "duplicate_anchors": sum(1 for v in ev.values() if len(v) > 1),
        "auditor_passed": audit.get("passed"),
        "anchors_equal_hybrid_records": sum(len(v) for v in ev.values()) == on_fabric,
        "sweep_s": before.get("sweep_s"),
    }
    with open(os.path.join(d, "result.json"), "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
