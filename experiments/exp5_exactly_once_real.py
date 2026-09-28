#!/usr/bin/env python3
"""
Experiment 5 (rebuilt): Exactly-once semantics — REAL, against the live orchestrator.

Replaces the fabricated exp5_exactly_once.py, whose success/failure and crash events were
np.random draws and whose tests used only 8-12 requests (see PHASE0_FINDINGS.md).

  A. Sequential duplicates  : same payload sent K times -> exactly ONE anchor;
                              first response replay=false, the rest replay=true.
  B. Concurrent duplicates  : same payload fired C ways at once -> exactly ONE anchor.
  C. Distinct requests      : M distinct payloads -> M distinct anchors.

Revision WS0.5 (AUDIT_WS0 F4). The v1 pass conditions were len({tx}) == 1, which
also holds when every anchor timed out ({None}) or was a 'preexisting:' marker,
and the per-request hashes were not kept. Now:

  * a response only counts if its anchor resolves to a real 0x transaction hash;
  * the count that decides the test is taken from the contract's DataRegistered
    event logs, not from what the orchestrator or relay reports;
  * each event's dataHash must equal the commitment c returned at ingest;
  * every request is written to exp5_requests.jsonl.

No randomness in the measurement path.

Output: experiments/results/exp5/exp5_exactly_once_real.json (+ exp5_requests.jsonl)
"""

import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests
from web3 import Web3

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "orchestrator"))
import contract_registry  # noqa: E402
from commitment import onchain_id  # noqa: E402

# ORBIT_RESULTS_DIR lets v2 runs write outside the v1 working tree
# (experiments/results/ still holds the files RESULTS.json v1 was built from).
OUTPUT_DIR = os.path.join(os.getenv("ORBIT_RESULTS_DIR",
                                    os.path.join(_REPO, "experiments", "results")), "exp5")
ARTIFACT = os.path.join(_REPO, "blockchain", "setup", "ethereum", "build",
                        "contracts", "IoTDataRegistry.json")
BASE = os.getenv("ORCHESTRATOR_URL", "http://localhost:5002")
GANACHE_URL = os.getenv("GANACHE_URL", "http://127.0.0.1:8545")
ORCH = BASE + "/ingest_data"
NONCE = str(int(time.time()))

K_SEQ_DUP = 6      # sequential duplicates of one payload
C_CONC_DUP = 25    # concurrent duplicates of one payload (raised >> 8-12)
M_DISTINCT = 40    # distinct payloads (raised >> 8-12)

ANCHOR_POLL_S = 0.05
ANCHOR_TIMEOUT_S = 120
TX_HASH_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")

_rows = []


def payload(uid):
    # deviceId is PUBLIC under policy_engine (PUB-DEVICEID), so every payload
    # here routes HYBRID and must produce an anchor.
    return {"id": uid, "deviceId": "d1", "temperature": 21.0, "humidity": 50}


def _await_anchor(outbox_id):
    """Resolve an outbox id to its anchor state and tx hash via /anchor_status."""
    if not outbox_id:
        return {"anchor_state": "no_outbox_id", "tx": None}
    deadline = time.monotonic() + ANCHOR_TIMEOUT_S
    url = f"{BASE}/anchor_status/{outbox_id}"
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                j = r.json()
                st = j.get("anchor_state")
                if st == "delivered":
                    return {"anchor_state": st, "tx": j.get("eth_tx_hash")}
                if st in ("failed", "not_required"):
                    return {"anchor_state": st, "tx": None, "last_error": j.get("last_error")}
        except requests.RequestException:
            pass
        time.sleep(ANCHOR_POLL_S)
    return {"anchor_state": "timeout", "tx": None}


def send(test, uid):
    row = {"test": test, "uid": uid, "ok": False}
    try:
        r = requests.post(ORCH, json=payload(uid), timeout=60)
        row["status_code"] = r.status_code
        # 202 Accepted: private commit done, anchor enqueued. 200: idempotency replay.
        if r.status_code in (200, 202):
            j = r.json()
            row.update({"ok": True, "outbox_id": j.get("outbox_id"),
                        "replay": j.get("idempotency_replay"),
                        "replay_source": j.get("replay_source"),
                        "route": j.get("route"),
                        "fabric_tx_id": j.get("fabric_tx_id"),
                        "commitment": j.get("commitment")})
            row.update(_await_anchor(j.get("outbox_id")))
        else:
            row["error"] = r.text[:200]
    except requests.RequestException as e:
        row["error"] = str(e)
    row["real_tx"] = bool(row.get("tx") and TX_HASH_RE.match(str(row["tx"])))
    _rows.append(row)
    return row


def test_sequential_duplicates():
    uid = f"seqdup-{NONCE}"
    rs = [send("A_sequential", uid) for _ in range(K_SEQ_DUP)]
    ok = [r for r in rs if r["ok"]]
    replays = [r.get("replay") for r in ok]
    return {
        "requests": K_SEQ_DUP, "ok_responses": len(ok),
        "all_real_tx": all(r["real_tx"] for r in ok) and len(ok) == K_SEQ_DUP,
        "unique_anchor_txs": len({r["tx"] for r in ok}),
        "unique_outbox_ids": sorted({r["outbox_id"] for r in ok}),
        "first_replay": replays[0] if replays else None,
        "num_replays_true": sum(1 for x in replays if x is True),
    }


def test_concurrent_duplicates():
    uid = f"concdup-{NONCE}"
    with ThreadPoolExecutor(max_workers=C_CONC_DUP) as ex:
        rs = list(ex.map(lambda _: send("B_concurrent", uid), range(C_CONC_DUP)))
    ok = [r for r in rs if r["ok"]]
    return {
        "concurrent_requests": C_CONC_DUP, "ok_responses": len(ok),
        "all_real_tx": all(r["real_tx"] for r in ok) and len(ok) == C_CONC_DUP,
        "unique_anchor_txs": len({r["tx"] for r in ok}),
        "unique_outbox_ids": sorted({r["outbox_id"] for r in ok}),
        "non_replay_count": sum(1 for r in ok if r.get("replay") is False),
    }


def test_distinct_requests():
    uids = [f"distinct-{NONCE}-{i}" for i in range(M_DISTINCT)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        rs = list(ex.map(lambda u: send("C_distinct", u), uids))
    ok = [r for r in rs if r["ok"]]
    txs = [r["tx"] for r in ok]
    return {
        "distinct_payloads": M_DISTINCT, "ok_responses": len(ok),
        "all_real_tx": all(r["real_tx"] for r in ok) and len(ok) == M_DISTINCT,
        "unique_anchor_txs": len(set(txs)),
        "duplicate_anchor_txs": [tx for tx, n in Counter(txs).items() if n > 1],
        "unique_outbox_ids": sorted({r["outbox_id"] for r in ok}),
    }


def chain_events(contract, from_block):
    """DataRegistered events since from_block, grouped by bytes32 id (hex)."""
    by_id = defaultdict(list)
    for ev in contract.events.DataRegistered().get_logs(from_block=from_block):
        by_id["0x" + bytes(ev["args"]["id"]).hex()].append({
            "dataHash": ev["args"]["dataHash"], "tx": ev["transactionHash"].hex(),
            "block": ev["blockNumber"]})
    return by_id


def verify_on_chain(result, expected_ids, events):
    """Exactly one event per expected outbox id, carrying the ingest commitment."""
    commit_of = {r["outbox_id"]: r.get("commitment") for r in _rows if r.get("outbox_id")}
    per_id = {}
    for oid in expected_ids:
        evs = events.get("0x" + onchain_id(oid).hex(), [])
        per_id[oid] = {"events": len(evs),
                       "commitment_matches": len(evs) == 1 and evs[0]["dataHash"] == commit_of.get(oid)}
    result["on_chain"] = {
        "events_per_id": {k: v["events"] for k, v in per_id.items()},
        "all_exactly_one": all(v["events"] == 1 for v in per_id.values()),
        "all_commitments_match": all(v["commitment_matches"] for v in per_id.values()),
        "total_events": sum(v["events"] for v in per_id.values()),
    }
    return result


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        _h = requests.get(BASE + "/health", timeout=5)
        assert _h.status_code == 200
        health = _h.json()
    except Exception as e:
        print(f"ERROR: orchestrator not reachable: {e}")
        return 1
    w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
    res = contract_registry.resolve(ARTIFACT, w3=w3, require_code=True)
    if res["address"].lower() != str(health.get("contract_addr")).lower():
        print(f"ERROR: orchestrator anchors to {health.get('contract_addr')}, "
              f"artifact resolves {res['address']}")
        return 1
    contract = w3.eth.contract(address=res["address"], abi=res["abi"])
    start_block = w3.eth.block_number + 1

    print("=" * 68)
    print("  EXPERIMENT 5 (rebuilt): REAL exactly-once / idempotency")
    print("=" * 68)

    a = test_sequential_duplicates()
    b = test_concurrent_duplicates()
    c = test_distinct_requests()
    events = chain_events(contract, start_block)
    end_block = w3.eth.block_number
    verify_on_chain(a, a["unique_outbox_ids"], events)
    verify_on_chain(b, b["unique_outbox_ids"], events)
    verify_on_chain(c, c["unique_outbox_ids"], events)

    a["pass"] = (a["all_real_tx"] and a["unique_anchor_txs"] == 1
                 and len(a["unique_outbox_ids"]) == 1 and a["first_replay"] is False
                 and a["num_replays_true"] == K_SEQ_DUP - 1
                 and a["on_chain"]["all_exactly_one"] and a["on_chain"]["all_commitments_match"])
    b["pass"] = (b["all_real_tx"] and b["unique_anchor_txs"] == 1
                 and len(b["unique_outbox_ids"]) == 1 and b["non_replay_count"] == 1
                 and b["on_chain"]["all_exactly_one"] and b["on_chain"]["all_commitments_match"])
    c["pass"] = (c["all_real_tx"] and c["unique_anchor_txs"] == M_DISTINCT
                 and len(c["unique_outbox_ids"]) == M_DISTINCT
                 and c["on_chain"]["all_exactly_one"] and c["on_chain"]["all_commitments_match"])
    all_pass = a["pass"] and b["pass"] and c["pass"]
    # Every DataRegistered event in the window must belong to one of our ids;
    # anything else means another writer was active during the run.
    ours = {"0x" + onchain_id(o).hex() for t in (a, b, c) for o in t["unique_outbox_ids"]}
    foreign = sorted(set(events) - ours)

    rows_path = os.path.join(OUTPUT_DIR, "exp5_requests.jsonl")
    with open(rows_path, "w") as f:
        for r in _rows:
            f.write(json.dumps(r) + "\n")

    results = {
        "experiment": "exp5_exactly_once_real",
        "schema_version": 3,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "measured": True,
        "provenance": {
            "architecture": ("async: 202 after private commit, anchor delivered by "
                             "the outbox relay; counts taken from DataRegistered "
                             "event logs"),
            "contract_addr": health.get("contract_addr"),
            "chain_id": health.get("chain_id"),
            "network_id": health.get("network_id"),
            "outbox_db": health.get("outbox_db"),
            "orchestrator_health": health,
            "block_window": [start_block, end_block],
            "per_request_rows": os.path.relpath(rows_path, _REPO),
        },
        "sequential_duplicates": a,
        "concurrent_duplicates": b,
        "distinct_requests": c,
        "foreign_events_in_window": foreign,
        "exactly_once_holds": bool(all_pass and not foreign),
        "note": (
            f"{K_SEQ_DUP + C_CONC_DUP + M_DISTINCT} requests. Pass requires real tx "
            "hashes for every response AND exactly one DataRegistered event per "
            "idempotency key whose dataHash equals the commitment returned at "
            "ingest. Orchestrator crash-recovery is tested separately (WS5)."
        ),
    }
    path = os.path.join(OUTPUT_DIR, "exp5_exactly_once_real.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)

    for label, t, n in (("A sequential dup", a, K_SEQ_DUP), ("B concurrent dup", b, C_CONC_DUP),
                        ("C distinct      ", c, M_DISTINCT)):
        print(f"  {label} ({n:>2}x): real_tx={t['all_real_tx']} unique_txs={t['unique_anchor_txs']} "
              f"events={t['on_chain']['total_events']} commit_match="
              f"{t['on_chain']['all_commitments_match']} -> {'PASS' if t['pass'] else 'FAIL'}")
    print(f"  foreign events in window: {len(foreign)}")
    print(f"  exactly-once holds: {results['exactly_once_holds']}")
    print(f"  JSON: {path}")
    return 0 if results["exactly_once_holds"] else 1


if __name__ == "__main__":
    sys.exit(main())
