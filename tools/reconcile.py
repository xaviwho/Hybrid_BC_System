#!/usr/bin/env python3
"""
reconcile.py — the reconciliation sweep (revision WS5).

The relational difference between what the permissioned ledger holds and what
the outbox and the public registry say, record by record:

  orphan     HYBRID on Fabric, no outbox row: the orchestrator died between the
             Fabric commit and the outbox transaction (the documented window).
  withheld   outbox row marked delivered, but no anchor in the registry slot
             (a relay reported success and never sent; WS3 withholding relay).
  tampered   registry slot holds a commitment other than c' rebuilt from Fabric.
  pending    outbox row still pending (in flight; not an error).
  failed     outbox row gave up after max attempts.
  ok         anchored with the right commitment.

--repair:
  orphan   -> rebuild sigma and c from the Fabric record and enqueue the row
              (same fields the orchestrator would have written); a relay anchors it.
  withheld -> reset the row to pending, so an honest relay re-anchors it.
  tampered -> reported only: the registry's uniqueness revert makes the slot
              immutable, which is exactly what lets an auditor prove the tamper.

Usage: reconcile.py [--repair] [--prefix P] [--out FILE]
  --prefix restricts to payloads whose x.id starts with P (one experiment's records).
Environment: as for the orchestrator (OUTBOX_DB, FABRIC_*, GANACHE_URL).
"""
import argparse
import collections
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "orchestrator"))
from web3 import Web3  # noqa: E402

import commitment as cm  # noqa: E402
import contract_registry  # noqa: E402
import fabric_client  # noqa: E402
from outbox import Outbox, STATE_DELIVERED, STATE_FAILED, STATE_PENDING  # noqa: E402

ARTIFACT = os.path.join(REPO, "blockchain", "setup", "ethereum", "build", "contracts",
                        "IoTDataRegistry.json")
ZERO = "0x0000000000000000000000000000000000000000"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--out")
    args = ap.parse_args()

    ob = Outbox(os.environ["OUTBOX_DB"])
    w3 = Web3(Web3.HTTPProvider(os.getenv("GANACHE_URL", "http://127.0.0.1:8545")))
    res = contract_registry.resolve(ARTIFACT, w3=w3, require_code=True)
    reg = w3.eth.contract(address=res["address"], abi=res["abi"])

    t0 = time.monotonic()
    rows, counts = [], collections.Counter()
    for rec in fabric_client.iter_records():
        if not rec.get("envelope"):
            continue
        env = json.loads(rec["envelope"])
        if args.prefix and not str((env.get("x") or {}).get("id", "")).startswith(args.prefix):
            continue
        if env.get("route") != "HYBRID":
            counts["fabric_only"] += 1
            continue
        key = rec["key"]
        sigma = cm.make_sigma(env["id"], key, rec["txid"], env["t0_us"], cm.metadata_hash(env["m"]))
        c = cm.commitment(sigma)
        slot = cm.onchain_id(env["id"])
        onchain = None
        if reg.functions.getDataOwner(slot).call() != ZERO:
            onchain = reg.functions.dataRecords(slot).call()[2]
        row = ob.get(env["id"])
        if row is None:
            state = "orphan"
        elif onchain is not None and onchain != c:
            state = "tampered"
        elif row["state"] == STATE_DELIVERED and onchain is None:
            state = "withheld"
        elif row["state"] == STATE_PENDING:
            state = "pending"
        elif row["state"] == STATE_FAILED:
            state = "failed"
        else:
            state = "ok" if onchain == c else "unknown"
        counts[state] += 1
        entry = {"id": env["id"], "state": state, "c": c, "onchain": onchain}
        if args.repair and state == "orphan":
            ob.commit_and_enqueue(
                record_id=env["id"], commitment=c, fabric_tx_id=rec["txid"],
                twin_key=(env.get("x") or {}).get("id"), version=(env.get("x") or {}).get("version"),
                tau=env.get("sensitivity"),
                payload={"data_id": (env.get("x") or {}).get("id"), "m": env["m"]},
                anchor_required=True, sigma=cm.canon(sigma).decode("utf-8"))
            entry["repair"] = "enqueued"
        elif args.repair and state == "withheld":
            with ob._conn() as conn:
                conn.execute("UPDATE outbox SET state=?, eth_tx_hash=NULL, attempts=0,"
                             " next_attempt_at=0, lease_until_mono=NULL, delivered_by=NULL"
                             " WHERE id=? AND state=?", (STATE_PENDING, env["id"], STATE_DELIVERED))
            entry["repair"] = "reset_to_pending"
        if state != "ok":
            rows.append(entry)
    report = {"prefix": args.prefix, "repair": args.repair, "counts": dict(counts),
              "sweep_s": round(time.monotonic() - t0, 2), "registry": res["address"],
              "gaps": rows}
    s = json.dumps(report, indent=1)
    if args.out:
        open(args.out, "w").write(s)
    print(json.dumps({k: v for k, v in report.items() if k != "gaps"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
