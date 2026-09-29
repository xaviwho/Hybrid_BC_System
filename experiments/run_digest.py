"""
run_digest.py - the configuration a result was measured under, read from the
running system (revision WS0.5, AUDIT_WS0 F7).

v1's config hash was taken over hand-written strings in consolidate_results.py.
It covered no code commit, no contract bytecode, no orderer batch parameters and
no endorsement policy, and one of its strings ("chaincode iot-data seq2") was
wrong: the committed definition was sequence 1. Here every field is queried:

    code       git commit, branch, whether tracked source differs from it
    ethereum   chain id, client version, contract address AND runtime-code hash
               (a fresh deterministic Ganache puts every first deployment at the
               same address, so the address alone cannot tell v1 from v2),
               relay allowlist
    fabric     committed chaincode definition (version, sequence, endorsement
               policy), orderer type, consenter count and batch parameters from
               the channel config block, container images
    services   what /health of the orchestrator and policy service report
               (server, workers, threads, relay mode, read-back mode), live relays
    host       kernel, CPUs, memory, Python and key package versions

`config_hash` is SHA-256 over the canonical JSON of the stable fields; volatile
ones (block heights, pids, heartbeats) are recorded but not hashed.

Usage:  python experiments/run_digest.py [OUT_JSON]
"""

import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile

import requests
from web3 import Web3

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "orchestrator"))
import contract_registry  # noqa: E402
import fabric_client as fc  # noqa: E402

ARTIFACT = os.path.join(_REPO, "blockchain", "setup", "ethereum", "build",
                        "contracts", "IoTDataRegistry.json")
ORCH = os.getenv("ORCHESTRATOR_URL", "http://localhost:5002")
POLICY = os.getenv("POLICY_URL", "http://127.0.0.1:5011")
GANACHE_URL = os.getenv("GANACHE_URL", "http://127.0.0.1:8545")
RELAY_ACCOUNTS_CHECKED = 4
# Paths whose drift does not change what is measured (the npm tree differs
# between the Windows checkout and the WSL install; see AUDIT_WS0 §1).
DIRTY_IGNORE = ("blockchain/setup/ethereum/node_modules",)
VOLATILE = {("fabric", "channel_height"), ("services", "orchestrator_pid"),
            ("services", "relays_alive"), ("ethereum", "block_number")}
VOLATILE_SECTIONS = {"clock"}   # recorded, never hashed
# Multi-VM testbed (WS2+): Fabric containers live on other hosts, reached over
# SSH. Empty on the laptop, where everything is local.
DOCKER_HOSTS = [h for h in os.getenv("ORBIT_DOCKER_HOSTS", "").split(",") if h]
NET_HOSTS = [h for h in os.getenv("ORBIT_NET_HOSTS", "").split(",") if h]


def _run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:4])}... failed: {(r.stderr or r.stdout)[-400:]}")
    return r.stdout


def _on(host, cmd):
    """Run cmd (a list) locally (host None or "local") or on host over SSH."""
    if host in (None, "local"):
        return _run(cmd)
    import shlex
    return _run(["ssh", "-o", "BatchMode=yes", host, " ".join(shlex.quote(c) for c in cmd)])


def _docker(host, *args):
    return _on(host, (["sudo"] if host not in (None, "local") else []) + ["docker", *args])


def code():
    g = ["git", "-c", "safe.directory=*", "-C", _REPO]
    status = _run(g + ["status", "--porcelain", "--untracked-files=no"]).splitlines()
    dirty = [ln[3:] for ln in status if not ln[3:].startswith(DIRTY_IGNORE)]
    return {"commit": _run(g + ["rev-parse", "HEAD"]).strip(),
            "branch": _run(g + ["rev-parse", "--abbrev-ref", "HEAD"]).strip(),
            "dirty_tracked_files": dirty}


def ethereum():
    w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
    res = contract_registry.resolve(ARTIFACT, w3=w3, require_code=True)
    contract = w3.eth.contract(address=res["address"], abi=res["abi"])
    code_bytes = w3.eth.get_code(res["address"])
    accounts = w3.eth.accounts[:RELAY_ACCOUNTS_CHECKED]
    allow = {}
    if any(f.get("name") == "isRelay" for f in res["abi"]):
        allow = {a: contract.functions.isRelay(a).call() for a in accounts}
    latest = w3.eth.get_block("latest")
    return {"chain_id": w3.eth.chain_id,
            "client_version": w3.client_version,
            "contract_address": res["address"],
            "contract_code_keccak": "0x" + Web3.keccak(code_bytes).hex().removeprefix("0x"),
            "contract_code_bytes": len(code_bytes),
            "relay_allowlist": allow,
            "block_gas_limit": latest["gasLimit"],
            "block_number": latest["number"]}


def _orderer_args():
    return ["-o", fc.ORDERER, "--ordererTLSHostnameOverride", fc.ORDERER_HOST,
            "--tls", "--cafile", fc._ORDERER_CA]


def fabric():
    env = fc._peer_env()
    peer = f"{fc.FABRIC_BIN}/peer"
    info = _run([peer, "channel", "getinfo", "-c", fc.CHANNEL], env=env)
    height = json.loads(info[info.index("{"):])["height"]

    cc = json.loads(_run([peer, "lifecycle", "chaincode", "querycommitted",
                          "-C", fc.CHANNEL, "-n", fc.CC_NAME, "-O", "json"], env=env))
    vp = base64.b64decode(cc.get("validation_parameter", "")).decode("latin-1")

    with tempfile.TemporaryDirectory() as td:
        blk = os.path.join(td, "config.pb")
        _run([peer, "channel", "fetch", "config", blk, "-c", fc.CHANNEL] + _orderer_args(),
             env=env)
        cfg = json.loads(_run([f"{fc.FABRIC_BIN}/configtxlator", "proto_decode",
                               "--input", blk, "--type", "common.Block"]))
    ch = cfg["data"]["data"][0]["payload"]["data"]["config"]["channel_group"]
    ov = ch["groups"]["Orderer"]["values"]
    ctype = ov["ConsensusType"]["value"]
    consenters = (ctype.get("metadata") or {}).get("consenters") or []
    # Tags are not versions: on this host `fabric-peer:latest` happens to be the
    # 2.5.0 image while `fabric-ccenv:2.5` (the chaincode builder) is 2.5.12.
    # Record image ids and the binaries' own version strings.
    images, where = {}, {}
    for host in (DOCKER_HOSTS or [None]):
        for line in _docker(host, "ps", "--format", "{{.Names}}|{{.Image}}").split():
            name, tag = line.split("|", 1)
            if "hyperledger" in tag or "couchdb" in tag:
                iid = _docker(host, "inspect", "-f", "{{.Image}}", name).strip()
                images[name] = f"{tag}@{iid[:19]}" + (f" on {host}" if host else "")
                where[name] = host

    def binver(container, binary):
        out = _docker(where.get(container), "exec", container, binary, "version")
        return next((ln.split(":", 1)[1].strip() for ln in out.splitlines()
                     if ln.strip().startswith("Version:")), None)
    versions = {"peer": binver("peer0.org1.example.com", "peer"),
                "orderer": binver("orderer.example.com", "orderer")}
    return {"channel": fc.CHANNEL,
            "binary_versions": versions,
            "chaincode": {"name": fc.CC_NAME, "version": cc.get("version"),
                          "sequence": cc.get("sequence"),
                          "validation_parameter_b64": cc.get("validation_parameter"),
                          "endorsement_policy_printable": "".join(
                              ch_ if 32 <= ord(ch_) < 127 else "." for ch_ in vp),
                          "approvals": cc.get("approvals")},
            "orderer": {"type": ctype.get("type"),
                        "consenters": len(consenters),
                        "batch_timeout": ov["BatchTimeout"]["value"]["timeout"],
                        "max_message_count": ov["BatchSize"]["value"]["max_message_count"],
                        "absolute_max_bytes": ov["BatchSize"]["value"]["absolute_max_bytes"],
                        "preferred_max_bytes": ov["BatchSize"]["value"]["preferred_max_bytes"]},
            "images": images,
            "channel_height": height}


def _get_json(url, attempts=3, timeout=60):
    """GET with retries. The end-of-run digest follows a sweep that leaves a
    relay backlog; a single 10 s attempt failed 2 of 10 WS1 runs."""
    last = None
    for _ in range(attempts):
        try:
            return requests.get(url, timeout=timeout).json()
        except requests.RequestException as e:
            last = e
    raise RuntimeError(f"digest: {url} unreachable after {attempts} attempts: {last}")


def services():
    h = _get_json(ORCH + "/health")
    st = _get_json(ORCH + "/outbox_stats")
    p = _get_json(POLICY + "/health")
    return {"orchestrator": {k: h.get(k) for k in (
                "server", "server_profile", "server_mode", "server_workers", "server_threads",
                "relay_mode", "fabric_readback", "commitment_scheme", "outbox_db",
                "contract_addr")},
            "orchestrator_pid": h.get("pid"),
            "relays": sorted({(r["relay_id"], r["account"]) for r in st.get("relays", [])}),
            "relays_alive": st.get("relays_alive"),
            "policy": {k: p.get(k) for k in sorted(p) if k != "status"}}


def host():
    def ver(mod):
        try:
            return __import__(mod).__version__
        except Exception:
            try:
                from importlib.metadata import version
                return version(mod)
            except Exception:
                return None
    mem = None
    try:
        with open("/proc/meminfo") as f:
            mem = int(f.readline().split()[1]) // 1024
    except OSError:
        pass
    return {"kernel": platform.release(), "cpus": os.cpu_count(), "mem_mb": mem,
            "python": platform.python_version(),
            "packages": {m: ver(m) for m in ("web3", "flask", "flask_socketio",
                                             "gunicorn", "requests")}}


IMDS = ("curl -s -m 3 -H Metadata:true 'http://169.254.169.254/metadata/instance/compute"
        "?api-version=2021-02-01&format=json' | jq -c '{vmSize, location, zone}' || echo null")


def network():
    """Per-host shaping and placement. `tc` state is hashed, so a netem delay
    (WS2 delay sweep) is part of the configuration it was measured under."""
    out = {"topology_mode": os.getenv("ORBIT_TOPOLOGY", "single_host"), "hosts": {}}
    for h in (NET_HOSTS or [None]):
        key = h or "local"
        tc = _on(h, ["sh", "-c", "tc qdisc show dev eth0; tc filter show dev eth0 | grep -E 'match|flowid' || true"])
        vm = _on(h, ["sh", "-c", IMDS]).strip()
        out["hosts"][key] = {"tc": [ln.strip() for ln in tc.splitlines() if ln.strip()],
                             "vm": json.loads(vm) if vm.startswith("{") else None}
    return out


def clock():
    """NTP state per host (recorded, not hashed)."""
    out = {}
    for h in (NET_HOSTS or [None]):
        try:
            t = _on(h, ["sh", "-c", "chronyc tracking | grep -E 'System time|Frequency|Leap status'"])
            out[h or "local"] = [ln.strip() for ln in t.splitlines()]
        except Exception as e:  # the laptop has no chrony
            out[h or "local"] = f"unavailable: {e.__class__.__name__}"
    return out


def _stable(d):
    return {sec: ({k: v for k, v in val.items() if (sec, k) not in VOLATILE}
                  if isinstance(val, dict) else val)
            for sec, val in d.items() if sec not in VOLATILE_SECTIONS}


def collect():
    d = {"code": code(), "ethereum": ethereum(), "fabric": fabric(),
         "services": services(), "host": host(), "network": network(), "clock": clock()}
    blob = json.dumps(_stable(d), sort_keys=True, separators=(",", ":"), default=list)
    d["config_hash"] = hashlib.sha256(blob.encode()).hexdigest()[:12]
    d["config_hash_covers"] = "all fields except " + ", ".join(
        f"{s}.{k}" for s, k in sorted(VOLATILE))
    return d


if __name__ == "__main__":
    out = collect()
    s = json.dumps(out, indent=1, default=list)
    print(s)
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w") as f:
            f.write(s)
