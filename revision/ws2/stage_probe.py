#!/usr/bin/env python3
"""
WS2 endorsement-stage probe: split the Fabric commit path under AND(Org1,Org2)
with the same peer CLI the orchestrator uses, from the orchestrator host.

  spawn         `peer version`: CLI process start-up only (no network)
  query_org1    one proposal to peer0.org1 (evaluate; one endorsement RTT + TLS setup)
  query_org2    one proposal to peer0.org2
  endorse_submit  invoke WITHOUT --waitForEvent: both endorsements + orderer
                broadcast acknowledgement (the CLI returns once the orderer accepts)
  full          invoke WITH --waitForEvent: the orchestrator's call (endorse,
                order, block cut, validate, commit, event)

Derived: order_commit = full - endorse_submit (block cutting + delivery +
validation + commit + event), reported per sample pair and as a mean difference.
Samples are sequential (c = 1), so full includes BatchTimeout at MMC > 1.
Output JSON: per-variant n/mean/median/p95/CI (ms, monotonic clock).
"""
import json
import math
import os
import statistics as st
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                "orchestrator"))
import fabric_client as fc  # noqa: E402

N = int(os.getenv("PROBE_N", "50"))


def run(cmd, env):
    t0 = time.monotonic()
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    dt = (time.monotonic() - t0) * 1000
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-300:])
    return dt


def org_env(org):
    env = fc._peer_env()
    if org == 2:
        o2 = f"{fc.TN}/organizations/peerOrganizations/org2.example.com"
        env.update(CORE_PEER_LOCALMSPID="Org2MSP", CORE_PEER_ADDRESS=fc.PEER2_ADDR,
                   CORE_PEER_TLS_ROOTCERT_FILE=fc._ORG2_TLS,
                   CORE_PEER_MSPCONFIGPATH=f"{o2}/users/Admin@org2.example.com/msp")
    return env


def invoke(key, wait):
    args = json.dumps({"function": "StoreIoTData", "Args": [key, json.dumps({"probe": key})]})
    cmd = [f"{fc.FABRIC_BIN}/peer", "chaincode", "invoke", "-o", fc.ORDERER,
           "--ordererTLSHostnameOverride", fc.ORDERER_HOST, "--tls", "--cafile", fc._ORDERER_CA,
           "-C", fc.CHANNEL, "-n", fc.CC_NAME,
           "--peerAddresses", fc.PEER1_ADDR, "--tlsRootCertFiles", fc._ORG1_TLS,
           "--peerAddresses", fc.PEER2_ADDR, "--tlsRootCertFiles", fc._ORG2_TLS, "-c", args]
    return cmd + (["--waitForEvent"] if wait else [])


def query(key):
    return [f"{fc.FABRIC_BIN}/peer", "chaincode", "query", "-C", fc.CHANNEL, "-n", fc.CC_NAME,
            "-c", json.dumps({"function": "ReadIoTData", "Args": [key]})]


def stats(xs):
    xs = sorted(xs)
    n, m = len(xs), st.fmean(xs)
    sd = st.stdev(xs) if n > 1 else 0
    return {"n": n, "mean": round(m, 2), "median": round(st.median(xs), 2),
            "p95": round(xs[min(n - 1, math.ceil(0.95 * n) - 1)], 2),
            "ci95_half": round(1.96 * sd / math.sqrt(n), 2)}


def main(out):
    tag = f"probe-{int(time.time())}"
    seed = f"{tag}-seed"
    run(invoke(seed, True), fc._peer_env())          # a key both queries can read
    res = {k: [] for k in ("spawn", "query_org1", "query_org2", "endorse_submit", "full")}
    diffs = []
    for i in range(N):
        res["spawn"].append(run([f"{fc.FABRIC_BIN}/peer", "version"], fc._peer_env()))
        res["query_org1"].append(run(query(seed), org_env(1)))
        res["query_org2"].append(run(query(seed), org_env(2)))
        a = run(invoke(f"{tag}-ns-{i}", False), fc._peer_env())
        b = run(invoke(f"{tag}-w-{i}", True), fc._peer_env())
        res["endorse_submit"].append(a)
        res["full"].append(b)
        diffs.append(b - a)
    report = {"tag": tag, "N": N, "clock": "monotonic", "orderer": fc.ORDERER,
              "peers": [fc.PEER1_ADDR, fc.PEER2_ADDR], "policy": "AND(Org1,Org2)",
              "variants_ms": {k: stats(v) for k, v in res.items()},
              "order_commit_ms": dict(stats(diffs), kind="derived",
                                      derivation="full - endorse_submit, paired per iteration"),
              "raw_ms": res}
    with open(out, "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({k: v for k, v in report.items() if k != "raw_ms"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
