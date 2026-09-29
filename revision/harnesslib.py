"""Shared helpers for the WS3/WS5 harnesses (run on the measurement host).

Environment as for the orchestrator (OUTBOX_DB, GANACHE_URL, FABRIC_*); service
control through scripts/orbit_v2.sh with ORBIT_ENV honoured.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from web3 import Web3

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "orchestrator"))
sys.path.insert(0, os.path.join(REPO, "experiments"))
import commitment as cm  # noqa: E402
import contract_registry  # noqa: E402

ORCH = os.getenv("ORCHESTRATOR_URL", "http://127.0.0.1:5002")
ARTIFACT = os.path.join(REPO, "blockchain", "setup", "ethereum", "build", "contracts",
                        "IoTDataRegistry.json")
PY = sys.executable
CTL = os.path.join(REPO, "scripts", "orbit_v2.sh")


def sh(cmd, env=None, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"{cmd!r} failed: {r.stderr[-500:] or r.stdout[-500:]}")
    return r.stdout


def chain():
    w3 = Web3(Web3.HTTPProvider(os.environ["GANACHE_URL"]))
    res = contract_registry.resolve(ARTIFACT, w3=w3, require_code=True)
    return w3, w3.eth.contract(address=res["address"], abi=res["abi"]), res["address"]


def services(profile="prod", extra_env=None):
    """(Re)start policy + orchestrator with NO relay (RELAY_MODE=external)."""
    env = dict(os.environ, SERVER_PROFILE=profile, **(extra_env or {}))
    sh(f"{CTL} stop", env=env, check=False)
    sh(f"{CTL} services", env=env)
    wait_health()


def wait_health(timeout=90):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if requests.get(ORCH + "/health", timeout=3).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.3)
    raise RuntimeError("orchestrator not healthy")


class Relays:
    """k relay processes, relay-i on eth.accounts[i]."""

    def __init__(self, k, coord, logdir, lease_s=10, per_relay_env=None, race_gas=400000):
        self.procs = {}
        os.makedirs(logdir, exist_ok=True)
        for i in range(1, k + 1):
            env = dict(os.environ, RELAY_ID=f"relay-{i}", RELAY_ACCOUNT_INDEX=str(i),
                       RELAY_COORD=coord, RELAY_LEASE_S=str(lease_s), RELAY_POLL_S="0.05")
            if coord == "race":
                env.update(ANCHOR_PRECHECK="0", ANCHOR_FIXED_GAS=str(race_gas))
            env.update((per_relay_env or {}).get(i, {}))
            log = open(os.path.join(logdir, f"relay-{i}.log"), "w")
            self.procs[i] = subprocess.Popen([PY, os.path.join(REPO, "orchestrator", "relay_worker.py")],
                                             env=env, stdout=log, stderr=subprocess.STDOUT,
                                             start_new_session=True)
        time.sleep(3)
        dead = [i for i, p in self.procs.items() if p.poll() is not None]
        if dead:
            raise RuntimeError(f"relays {dead} exited at start; see {logdir}")

    def kill(self, i, sig=signal.SIGKILL):
        self.procs[i].send_signal(sig)

    def stop(self):
        for p in self.procs.values():
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in self.procs.values():
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()


def submit_hybrid(prefix, n, concurrency=6):
    """n HYBRID records (exp1 'mixed' fixture) through the orchestrator."""
    from exp1_latency_real import payload

    def one(i):
        x = payload("mixed", i)
        x["id"] = f"{prefix}-{i}"
        r = requests.post(ORCH + "/ingest_data", json=x, timeout=120)
        j = r.json()
        return {"i": i, "status": r.status_code, "outbox_id": j.get("outbox_id"),
                "commitment": j.get("commitment"), "route": j.get("route")}
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        return list(ex.map(one, range(n)))


def outbox_rows(ob, ids):
    return {i: ob.get(i) for i in ids}


def wait_delivered(ob, ids, timeout=600, poll=0.2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        rows = [ob.get(i) for i in ids]
        if all(r and r["state"] == "delivered" for r in rows):
            return True
        time.sleep(poll)
    return False


def events_for(contract, ids, from_block):
    """DataRegistered events per id (from the contract's logs, not relay logs)."""
    want = {bytes(cm.onchain_id(i)): i for i in ids}
    out = {i: [] for i in ids}
    for ev in contract.events.DataRegistered().get_logs(from_block=from_block):
        k = bytes(ev["args"]["id"])
        if k in want:
            out[want[k]].append({"dataHash": ev["args"]["dataHash"], "block": ev["blockNumber"]})
    return out


def chain_reverts(w3, address, from_block, to_block):
    """Registry transactions that REVERTED on chain in the block window: count, gas."""
    n, gas, addr = 0, 0, address.lower()
    for b in range(from_block, to_block + 1):
        blk = w3.eth.get_block(b, full_transactions=True)
        for tx in blk.transactions:
            if (tx["to"] or "").lower() != addr:
                continue
            rc = w3.eth.get_transaction_receipt(tx["hash"])
            if rc.status == 0:
                n += 1
                gas += rc.gasUsed
    return {"reverted_txs": n, "gas_wasted": gas, "blocks": [from_block, to_block]}


class Sampler(threading.Thread):
    """Samples queue depth and delivered count for a prefix every `period` s."""

    def __init__(self, ob, prefix, period=0.5):
        super().__init__(daemon=True)
        self.ob, self.prefix, self.period = ob, prefix, period
        self.samples, self._halt = [], threading.Event()

    def run(self):
        like = self.prefix + "-%"          # synthetic drain rows: id = <prefix>-<i>
        from outbox import Outbox
        mine = Outbox(self.ob.db_path)     # own connection (sqlite is per-thread)
        while not self._halt.is_set():
            r = mine._conn().execute(
                "SELECT SUM(state='pending'), SUM(state='delivered') FROM outbox WHERE id LIKE ?",
                (like,)).fetchone()
            self.samples.append([round(time.monotonic(), 3), r[0] or 0, r[1] or 0])
            self._halt.wait(self.period)

    def stop(self):
        self._halt.set()
        self.join(5)


def audit_env():
    """Environment for tools/auditor/orbit_audit.py (Org2 identity, Org2 peer)."""
    tn = os.environ.get("FABRIC_TEST_NETWORK")
    o2 = f"{tn}/organizations/peerOrganizations/org2.example.com"
    w3, c, addr = chain()
    return dict(os.environ,
                AUDIT_PEER_BIN=os.environ["FABRIC_BIN"], AUDIT_FABRIC_CFG=os.environ["FABRIC_CFG_PATH"],
                AUDIT_MSP_ID="Org2MSP", AUDIT_MSP_DIR=f"{o2}/users/Admin@org2.example.com/msp",
                AUDIT_PEER_ADDR=os.getenv("FABRIC_PEER2_ADDR", "localhost:9051"),
                AUDIT_PEER_TLS=f"{o2}/peers/peer0.org2.example.com/tls/ca.crt",
                AUDIT_RPC=os.environ["GANACHE_URL"], AUDIT_REGISTRY=addr, AUDIT_ABI=ARTIFACT)


def _run_tool(cmd, env, out):
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    with open(out + ".stderr", "w") as f:
        f.write(r.stderr)
    return json.load(open(out)) if os.path.exists(out) else {"error": r.stderr[-800:], "rc": r.returncode}


def run_auditor(ids, out, from_block=0):
    return _run_tool([PY, os.path.join(REPO, "tools", "auditor", "orbit_audit.py"), "--out", out,
                      "--from-block", str(from_block), "records", *ids], audit_env(), out)


def run_reconcile(prefix, out, repair=False):
    return _run_tool([PY, os.path.join(REPO, "tools", "reconcile.py"), "--prefix", prefix,
                      "--out", out] + (["--repair"] if repair else []), os.environ, out)
