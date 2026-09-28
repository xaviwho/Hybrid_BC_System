"""
WS0.5 acceptance: every record verified from the two ledgers, not from the
orchestrator's own responses.

For each submitted record (the four exp1 fixtures, plus the v1 key-collision
case and a duplicate retry):

  Fabric  (peer CLI query, Org1 peer)
    F1  the record exists under key = idempotency key
    F2  envelope.x equals the submitted payload (full record, sensitive fields kept)
    F3  envelope.m contains no field the fixtures mark sensitive
    F4  h' = keccak(canon(m)) equals envelope.h
  Chain   (contract storage + DataRegistered logs)
    C1  HYBRID: dataRecords(keccak(id)).dataHash == c' = keccak(canon(sigma')),
        sigma' = <id, k, nu=record.txid, tau=envelope.t0_us, h'> rebuilt from Fabric
    C2  HYBRID: dataRecords(...).metadata == canon(m)
    C3  HYBRID: exactly one DataRegistered event for the id
    C4  FABRIC_ONLY: no registry entry, no event
  Collision (AUDIT_WS0 F3): two different payloads sharing one `id` field get two
    registry entries, each with its own correct commitment.
  Retry: re-sending a payload is a replay and adds no event.

Uses orchestrator/commitment.py for canon/keccak and fabric_client for the query.
The standalone auditor of WS5 will not.

Usage: python revision/ws05/verify_e2e.py OUT_JSON
"""
import json
import os
import sys
import time

import requests
from web3 import Web3

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "orchestrator"))
sys.path.insert(0, os.path.join(REPO, "experiments"))
import commitment as cm  # noqa: E402
import contract_registry  # noqa: E402
import fabric_client  # noqa: E402
from exp1_latency_real import payload as fixture  # noqa: E402

BASE = os.getenv("ORCHESTRATOR_URL", "http://localhost:5002")
ARTIFACT = os.path.join(REPO, "blockchain", "setup", "ethereum", "build",
                        "contracts", "IoTDataRegistry.json")
SENSITIVE = {"patientId", "diagnosis", "ssn", "homeAddress"}
PER_CLASS = 3
TAG = f"ws05-{int(time.time())}"

w3 = Web3(Web3.HTTPProvider(os.getenv("GANACHE_URL", "http://127.0.0.1:8545")))
res = contract_registry.resolve(ARTIFACT, w3=w3, require_code=True)
contract = w3.eth.contract(address=res["address"], abi=res["abi"])
start_block = w3.eth.block_number + 1


def submit(x):
    r = requests.post(BASE + "/ingest_data", json=x, timeout=60)
    j = r.json()
    j["_status"] = r.status_code
    return j


def await_anchor(oid, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        j = requests.get(f"{BASE}/anchor_status/{oid}", timeout=10).json()
        if j.get("anchor_state") in ("delivered", "failed", "not_required"):
            return j
        time.sleep(0.1)
    return {"anchor_state": "timeout"}


def events_for(oid):
    return [e for e in contract.events.DataRegistered().get_logs(from_block=start_block)
            if bytes(e["args"]["id"]) == cm.onchain_id(oid)]


def verify(x, resp):
    key = resp.get("fabric_key")
    out = {"status": resp["_status"], "route": resp.get("route"), "key": key}
    rec = fabric_client.read_iot_data(key)
    out["F1_exists"] = bool(rec)
    if not rec:
        return out
    env = json.loads(rec["envelope"])
    m = env.get("m")
    out["F2_full_payload"] = cm.canon(env["x"]) == cm.canon(x)
    out["F3_no_sensitive_in_m"] = not (set(m or {}) & SENSITIVE)
    h1 = cm.metadata_hash(m) if m else None
    out["F4_h_matches"] = h1 == env.get("h")
    onchain = contract.functions.dataRecords(cm.onchain_id(key)).call()
    evs = events_for(key)
    if env["route"] == "HYBRID":
        sigma = cm.make_sigma(key, key, rec["txid"], env["t0_us"], h1)
        c1 = cm.commitment(sigma)
        out["C1_commitment_matches"] = onchain[2] == c1
        out["C2_metadata_matches"] = onchain[3] == cm.canon(m).decode("utf-8")
        out["C3_one_event"] = len(evs) == 1
        out["c"] = c1
    else:
        out["C4_nothing_on_chain"] = onchain[1] == "0x0000000000000000000000000000000000000000" and not evs
    checks = [v for k, v in out.items() if k[:2] in ("F1", "F2", "F3", "F4", "C1", "C2", "C3", "C4")]
    out["pass"] = all(checks)
    return out


def main(out_path):
    results = {"tag": TAG, "contract": res["address"], "records": []}
    subs = []
    for cls in ("all_public", "all_sensitive", "mixed", "fabric_only"):
        for i in range(PER_CLASS):
            x = fixture(cls, i)
            x["id"] = f"{TAG}-{cls}-{i}"
            subs.append((cls, x, submit(x)))
    # AUDIT_WS0 F3: same `id` field, different content.
    for n, temp in enumerate((30.0, 31.0)):
        x = {"id": f"{TAG}-shared-id", "deviceId": "d9", "temperature": temp}
        subs.append((f"collision-{n}", x, submit(x)))
    for cls, x, r in subs:
        if r.get("anchor_state") == "pending":
            await_anchor(r["outbox_id"])
    time.sleep(1)
    for cls, x, r in subs:
        v = verify(x, r)
        v["fixture"] = cls
        results["records"].append(v)

    col = [v for v in results["records"] if v["fixture"].startswith("collision")]
    results["collision_two_distinct_entries"] = (
        len({v["key"] for v in col}) == 2 and all(v.get("pass") for v in col))

    # Retry: re-send the first mixed record; must be a replay, no new event.
    cls, x, r = next(s for s in subs if s[0] == "mixed")
    before = len(events_for(r["fabric_key"]))
    again = submit(x)
    time.sleep(2)
    results["retry"] = {"status": again["_status"], "replay": again.get("idempotency_replay"),
                        "events_before": before, "events_after": len(events_for(r["fabric_key"]))}
    results["retry"]["pass"] = (again.get("idempotency_replay") is True
                                and results["retry"]["events_after"] == 1)

    results["all_pass"] = (all(v.get("pass") for v in results["records"])
                           and results["collision_two_distinct_entries"]
                           and results["retry"]["pass"])
    with open(out_path, "w") as f:
        json.dump(results, f, indent=1)
    for v in results["records"]:
        flags = " ".join(f"{k.split('_')[0]}={'ok' if val else 'FAIL'}" for k, val in v.items()
                         if k[:2] in ("F1", "F2", "F3", "F4", "C1", "C2", "C3", "C4"))
        print(f"{v['fixture']:>14} {v['route']:<12} {flags}  -> {'PASS' if v.get('pass') else 'FAIL'}")
    print("collision -> two distinct entries:", results["collision_two_distinct_entries"])
    print("retry:", results["retry"])
    print("ALL PASS:", results["all_pass"])
    return 0 if results["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
