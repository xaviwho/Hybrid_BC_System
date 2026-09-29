#!/usr/bin/env python3
"""
orbit_audit.py — independent auditor for OrBIT records (revision WS5).

Uses NO orchestrator code on the verification path. It re-implements the
commitment rules from the manuscript, reads the permissioned ledger through the
Fabric `peer` CLI and the public ledger through JSON-RPC, and checks, for each
record id:

  F   the record exists on Fabric; its envelope parses
  h   h' = Keccak-256(canon(m)) equals the h stored in the envelope        (Eq. 12)
  c   c' = Keccak-256(canon(<id, k, nu, tau, h'>)), with nu = the Fabric txid
      that created the record and tau = the envelope's t0            (Eqs. 20a/22)
  E   HYBRID: the registry slot keccak(id) holds dataHash == c'          (Eq. 20b)
  M   HYBRID: the registry's public metadata equals canon(m)
  1   HYBRID: exactly one DataRegistered event for the slot, carrying c'
  0   FABRIC_ONLY: nothing on chain for the slot

  canon(x) = JSON with sorted keys, separators (",", ":"), UTF-8, no NaN.

Commands
  records ID [ID ...]       audit the given idempotency ids
  all [--limit N]           audit every record on the ledger (Fabric ListRecords)
  proof LEAF ROOT PROOF     verify a Merkle inclusion proof (Eq. 13b); PROOF is JSON

Configuration (environment)
  AUDIT_PEER_BIN, AUDIT_FABRIC_CFG     peer binary dir and its config dir
  AUDIT_MSP_DIR, AUDIT_MSP_ID          identity used for read-only queries
  AUDIT_PEER_ADDR, AUDIT_PEER_TLS      peer to query and its TLS root cert
  AUDIT_CHANNEL (hiot), AUDIT_CC (iot-data)
  AUDIT_RPC                            Ethereum JSON-RPC URL
  AUDIT_REGISTRY, AUDIT_ABI            registry address and ABI JSON file (truffle artifact ok)

Output: a JSON report on stdout (or --out FILE); exit status 1 if any record fails.
"""
import argparse
import json
import os
import subprocess
import sys

from eth_utils import keccak
from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import merkle  # noqa: E402

ZERO = "0x0000000000000000000000000000000000000000"


# ---- the commitment rules, re-implemented from the manuscript ---------------

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def H(data):
    return "0x" + keccak(data).hex()


def slot(record_id):
    return keccak(record_id.encode("utf-8"))


# ---- ledgers -----------------------------------------------------------------

class Fabric:
    def __init__(self):
        e = os.environ
        self.bin = os.path.join(e["AUDIT_PEER_BIN"], "peer")
        self.env = dict(e, FABRIC_CFG_PATH=e["AUDIT_FABRIC_CFG"], CORE_PEER_TLS_ENABLED="true",
                        CORE_PEER_LOCALMSPID=e["AUDIT_MSP_ID"], CORE_PEER_MSPCONFIGPATH=e["AUDIT_MSP_DIR"],
                        CORE_PEER_ADDRESS=e["AUDIT_PEER_ADDR"], CORE_PEER_TLS_ROOTCERT_FILE=e["AUDIT_PEER_TLS"])
        self.channel = e.get("AUDIT_CHANNEL", "hiot")
        self.cc = e.get("AUDIT_CC", "iot-data")

    def _query(self, fn, *args):
        a = json.dumps({"function": fn, "Args": [str(x) for x in args]})
        r = subprocess.run([self.bin, "chaincode", "query", "-C", self.channel, "-n", self.cc, "-c", a],
                           env=self.env, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None, (r.stderr or "")[-300:]
        return json.loads(r.stdout.strip()), None

    def read(self, key):
        return self._query("ReadIoTData", key)

    def list_all(self, page=200, limit=None):
        bookmark, n = "", 0
        while True:
            pg, err = self._query("ListRecords", page, bookmark)
            if err:
                raise RuntimeError(f"ListRecords failed: {err}")
            for r in pg["records"]:
                yield r
                n += 1
                if limit and n >= limit:
                    return
            if not pg["records"] or not pg.get("bookmark"):
                return
            bookmark = pg["bookmark"]


class Chain:
    def __init__(self, from_block=0):
        e = os.environ
        self.w3 = Web3(Web3.HTTPProvider(e["AUDIT_RPC"], request_kwargs={"timeout": 300}))
        abi = json.load(open(e["AUDIT_ABI"]))
        abi = abi["abi"] if isinstance(abi, dict) else abi
        self.c = self.w3.eth.contract(address=Web3.to_checksum_address(e["AUDIT_REGISTRY"]), abi=abi)
        self.from_block = from_block
        self._events = None

    def record(self, record_id):
        s = slot(record_id)
        if self.c.functions.getDataOwner(s).call() == ZERO:
            return None
        rec = self.c.functions.dataRecords(s).call()
        return {"owner": rec[1], "dataHash": rec[2], "metadata": rec[3], "time": rec[4]}

    def events(self):
        """DataRegistered events since from_block, grouped by slot (fetched once).

        A full scan from block 0 stalls a node holding ~1e5 anchors for seconds;
        callers that know when the audited records were created pass --from-block.
        The event-count check then covers that window; the storage checks (E, c, M)
        read the slot directly and are unaffected by the window."""
        if self._events is None:
            self._events = {}
            for ev in self.c.events.DataRegistered().get_logs(from_block=self.from_block):
                self._events.setdefault(bytes(ev["args"]["id"]), []).append(
                    {"dataHash": ev["args"]["dataHash"], "block": ev["blockNumber"],
                     "tx": "0x" + bytes(ev["transactionHash"]).hex()})
        return self._events


# ---- the audit -----------------------------------------------------------------

def audit_one(key, fab, chain, fabric_rec=None):
    out = {"id": key, "checks": {}, "reasons": []}
    ck = out["checks"]
    if fabric_rec is None:
        fabric_rec, err = fab.read(key)
        if err:
            out["reasons"].append(f"fabric: {err.strip()[:120]}")
    ck["F_exists"] = bool(fabric_rec and fabric_rec.get("envelope"))
    if not ck["F_exists"]:
        out["pass"] = False
        return out
    env = json.loads(fabric_rec["envelope"])
    route, m = env.get("route"), env.get("m")
    out["route"] = route
    rec = chain.record(env["id"])
    evs = chain.events().get(slot(env["id"]), [])
    if route == "HYBRID":
        h1 = H(canon(m))
        ck["h_matches"] = h1 == env.get("h")
        sigma = {"id": env["id"], "k": key, "nu": fabric_rec["txid"], "tau": env["t0_us"], "h": h1}
        c1 = H(canon(sigma))
        out["c_recomputed"] = c1
        ck["E_on_chain"] = rec is not None
        ck["c_matches"] = bool(rec) and rec["dataHash"] == c1
        ck["M_metadata_matches"] = bool(rec) and rec["metadata"] == canon(m).decode("utf-8")
        ck["one_event"] = len(evs) == 1 and evs[0]["dataHash"] == c1
        if rec and rec["dataHash"] != c1:
            out["reasons"].append(f"TAMPER: chain holds {rec['dataHash']}, recomputed {c1}")
        if not rec:
            out["reasons"].append("MISSING: no anchor on chain")
        if len(evs) > 1:
            out["reasons"].append(f"DUPLICATE: {len(evs)} events")
    else:
        ck["nothing_on_chain"] = rec is None and not evs
    out["pass"] = all(ck.values())
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out")
    ap.add_argument("--from-block", type=int, default=0,
                    help="first block of the DataRegistered event window (default 0 = whole chain)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("records"); r.add_argument("ids", nargs="+")
    a = sub.add_parser("all"); a.add_argument("--limit", type=int)
    p = sub.add_parser("proof"); p.add_argument("leaf"); p.add_argument("root"); p.add_argument("proof")
    args = ap.parse_args(argv)

    if args.cmd == "proof":
        ok = merkle.verify(args.leaf, [tuple(x) for x in json.loads(args.proof)], args.root)
        report = {"command": "proof", "pass": ok}
    else:
        fab, chain = Fabric(), Chain(args.from_block)
        if args.cmd == "records":
            results = [audit_one(k, fab, chain) for k in args.ids]
        else:
            results = [audit_one(rec["key"], fab, chain, rec) for rec in fab.list_all(limit=args.limit)]
        report = {
            "command": args.cmd, "audited": len(results),
            "passed": sum(1 for x in results if x["pass"]),
            "failed": [x["id"] for x in results if not x["pass"]],
            "by_reason": {k: sum(1 for x in results for rsn in x["reasons"] if rsn.startswith(k))
                          for k in ("TAMPER", "MISSING", "DUPLICATE")},
            "registry": os.environ["AUDIT_REGISTRY"], "rpc": os.environ["AUDIT_RPC"],
            "event_window_from_block": args.from_block,
            "results": results,
        }
        report["pass"] = not report["failed"]
    s = json.dumps(report, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(s)
        print(json.dumps({k: v for k, v in report.items() if k != "results"}))
    else:
        print(s)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
