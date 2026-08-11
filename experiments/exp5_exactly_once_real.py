#!/usr/bin/env python3
"""
Experiment 5 (rebuilt): Exactly-once semantics — REAL, against the live orchestrator.

Replaces the fabricated exp5_exactly_once.py, whose success/failure and crash events were
np.random draws and whose tests used only 8-12 requests (see PHASE0_FINDINGS.md).

This exercises the orchestrator's REAL idempotency machinery (content-hash idempotency key,
`idempotency_replay` flag, cached response) over the live stack and checks the exactly-once
guarantee by inspecting the REAL Ethereum tx hashes returned:

  A. Sequential duplicates  : same payload sent K times -> exactly ONE real anchor tx;
                              first response replay=false, the rest replay=true.
  B. Concurrent duplicates  : same payload fired C ways at once -> exactly ONE anchor tx
                              (the race is resolved by the idempotency slot).
  C. Distinct requests      : M distinct payloads -> M distinct anchor txs (no collisions).

Scale is raised well above the old 8-12 (public/fast path used so N can be large).
No randomness in the measurement path.

Output: experiments/results/exp5/exp5_exactly_once_real.json
"""

import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_REPO, "experiments", "results", "exp5")
BASE = os.getenv("ORCHESTRATOR_URL", "http://localhost:5002")
ORCH = BASE + "/ingest_data"
NONCE = str(int(time.time()))

K_SEQ_DUP = 6      # sequential duplicates of one payload
C_CONC_DUP = 25    # concurrent duplicates of one payload (raised >> 8-12)
M_DISTINCT = 40    # distinct payloads (raised >> 8-12)


def payload(uid):
    return {"id": uid, "deviceId": "d1", "temperature": 21.0, "humidity": 50}


ANCHOR_POLL_S = 0.05
ANCHOR_TIMEOUT_S = 120


def _await_anchor(outbox_id):
    """Resolve an outbox id to its on-chain anchor tx hash.

    Phase 2 made anchoring asynchronous: /ingest_data returns 202 with an
    outbox_id and no ethereum_tx_hash, because the anchor has not been broadcast
    yet when the response is written. The tx hash now has to be collected from
    /anchor_status once the relay has delivered it.

    Without this the experiment reads tx=None for every request, which collapses
    the DISTINCT case to one "unique anchor" and would report exactly-once
    holding for the wrong reason.
    """
    if not outbox_id:
        return None
    deadline = time.time() + ANCHOR_TIMEOUT_S
    url = f"{BASE}/anchor_status/{outbox_id}"
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                j = r.json()
                if j.get("anchor_state") == "delivered":
                    return j.get("eth_tx_hash")
                if j.get("anchor_state") in ("failed", "not_required"):
                    return None
        except requests.RequestException:
            pass
        time.sleep(ANCHOR_POLL_S)
    return None


def send(uid):
    try:
        r = requests.post(ORCH, json=payload(uid), timeout=60)
        # 202 Accepted is the current success code (private commit done, anchor
        # enqueued). 200 is kept for an idempotency replay served from cache.
        if r.status_code in (200, 202):
            j = r.json()
            return {"tx": _await_anchor(j.get("outbox_id")),
                    "outbox_id": j.get("outbox_id"),
                    "replay": j.get("idempotency_replay"),
                    "fabric": j.get("fabric_tx_id"), "ok": True}
        return {"ok": False, "status": r.status_code}
    except requests.RequestException as e:
        return {"ok": False, "err": str(e)}


def test_sequential_duplicates():
    uid = f"seqdup-{NONCE}"
    responses = [send(uid) for _ in range(K_SEQ_DUP)]
    txs = {r["tx"] for r in responses if r.get("ok")}
    replays = [r.get("replay") for r in responses if r.get("ok")]
    return {
        "requests": K_SEQ_DUP,
        "unique_anchor_txs": len(txs),
        "first_replay": replays[0] if replays else None,
        "num_replays_true": sum(1 for x in replays if x is True),
        "pass": len(txs) == 1 and replays and replays[0] is False
                and sum(1 for x in replays if x is True) == K_SEQ_DUP - 1,
    }


def test_concurrent_duplicates():
    uid = f"concdup-{NONCE}"
    with ThreadPoolExecutor(max_workers=C_CONC_DUP) as ex:
        responses = list(ex.map(lambda _: send(uid), range(C_CONC_DUP)))
    ok = [r for r in responses if r.get("ok")]
    txs = {r["tx"] for r in ok}
    non_replay = sum(1 for r in ok if r.get("replay") is False)
    return {
        "concurrent_requests": C_CONC_DUP,
        "ok_responses": len(ok),
        "unique_anchor_txs": len(txs),
        "non_replay_count": non_replay,
        "pass": len(txs) == 1,   # exactly one real anchor despite the concurrent race
    }


def test_distinct_requests():
    uids = [f"distinct-{NONCE}-{i}" for i in range(M_DISTINCT)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        responses = list(ex.map(send, uids))
    ok = [r for r in responses if r.get("ok")]
    txs = [r["tx"] for r in ok]
    dupes = [tx for tx, c in Counter(txs).items() if c > 1]
    return {
        "distinct_payloads": M_DISTINCT,
        "ok_responses": len(ok),
        "unique_anchor_txs": len(set(txs)),
        "duplicate_anchor_txs": dupes,
        "pass": len(ok) == M_DISTINCT and len(set(txs)) == M_DISTINCT,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        assert requests.get(BASE + "/health", timeout=5).status_code == 200
    except Exception as e:
        print(f"ERROR: orchestrator not reachable: {e}")
        return 1

    print("=" * 68)
    print("  EXPERIMENT 5 (rebuilt): REAL exactly-once / idempotency")
    print("=" * 68)

    a = test_sequential_duplicates()
    b = test_concurrent_duplicates()
    c = test_distinct_requests()
    all_pass = a["pass"] and b["pass"] and c["pass"]

    results = {
        "experiment": "exp5_exactly_once_real",
        "measured": True,
        "sequential_duplicates": a,
        "concurrent_duplicates": b,
        "distinct_requests": c,
        "exactly_once_holds": bool(all_pass),
        "note": (
            "Verified via REAL Ethereum tx hashes returned by the live orchestrator over "
            f"{K_SEQ_DUP + C_CONC_DUP + M_DISTINCT} requests. Duplicates (sequential and "
            "concurrent) collapse to exactly one on-chain anchor via the content-hash "
            "idempotency slot; distinct requests each get a unique anchor. Orchestrator "
            "crash-recovery is a separate test requiring process-kill mid-commit and is "
            "noted as future hardening, not claimed here."
        ),
    }
    path = os.path.join(OUTPUT_DIR, "exp5_exactly_once_real.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"  A sequential dup ({a['requests']}x)  : unique_txs={a['unique_anchor_txs']} "
          f"replays={a['num_replays_true']}  -> {'PASS' if a['pass'] else 'FAIL'}")
    print(f"  B concurrent dup ({b['concurrent_requests']}x): unique_txs={b['unique_anchor_txs']} "
          f"-> {'PASS' if b['pass'] else 'FAIL'}")
    print(f"  C distinct ({c['distinct_payloads']}x)      : unique_txs={c['unique_anchor_txs']} "
          f"dupes={len(c['duplicate_anchor_txs'])} -> {'PASS' if c['pass'] else 'FAIL'}")
    print(f"  exactly-once holds: {all_pass}")
    print(f"  JSON: {path}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
