"""
fabric_client.py - REAL Hyperledger Fabric client for the orchestrator.

Replaces the previous `store_on_fabric()` stub (which returned a fabricated
`fabric_tx_<hash>` string and never touched Fabric - see PHASE0_FINDINGS.md).

This shells out to the Fabric `peer` CLI to submit/evaluate transactions against
the running network (channel `hiot`, chaincode `iot-data`). We use the CLI rather
than the Python Fabric SDK because that SDK was abandoned in this project due to
dependency issues; the CLI is the operator-standard, fully-real path and requires
no extra long-running service.

All paths/endpoints are configurable via environment variables so this works in
CI or a relocated network. Defaults match the WSL ext4 bring-up documented in
BRINGUP_STATUS.md.

Returns REAL transaction IDs parsed from the peer's commit event. On any failure
it returns None (the caller decides how to proceed) - it never fabricates an id.
"""

import json
import logging
import os
import re
import subprocess

logger = logging.getLogger("orchestrator.fabric")

# --- Configuration (env-overridable) ----------------------------------------
FABRIC_BIN      = os.getenv("FABRIC_BIN", "/root/fabric-clean/bin")
FABRIC_CFG_PATH = os.getenv("FABRIC_CFG_PATH", "/root/fabric-clean/config")
TN              = os.getenv("FABRIC_TEST_NETWORK", "/root/fabric-clean/test-network")
CHANNEL         = os.getenv("FABRIC_CHANNEL", "hiot")
CC_NAME         = os.getenv("FABRIC_CC_NAME", "iot-data")
ORDERER         = os.getenv("FABRIC_ORDERER", "localhost:7050")
ORDERER_HOST    = os.getenv("FABRIC_ORDERER_HOST", "orderer.example.com")
PEER1_ADDR      = os.getenv("FABRIC_PEER1_ADDR", "localhost:7051")
PEER2_ADDR      = os.getenv("FABRIC_PEER2_ADDR", "localhost:9051")
INVOKE_TIMEOUT  = int(os.getenv("FABRIC_INVOKE_TIMEOUT", "30"))

_ORG1 = f"{TN}/organizations/peerOrganizations/org1.example.com"
_ORG2 = f"{TN}/organizations/peerOrganizations/org2.example.com"
_ORDERER_CA = (f"{TN}/organizations/ordererOrganizations/example.com/orderers/"
               f"orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem")
_ORG1_TLS = f"{_ORG1}/peers/peer0.org1.example.com/tls/ca.crt"
_ORG2_TLS = f"{_ORG2}/peers/peer0.org2.example.com/tls/ca.crt"

_TXID_RE = re.compile(r"txid \[([a-f0-9]+)\] committed with status \(VALID\)")


def _peer_env():
    """Environment for peer CLI acting as the Org1 admin."""
    env = dict(os.environ)
    env["PATH"] = FABRIC_BIN + os.pathsep + env.get("PATH", "")
    env["FABRIC_CFG_PATH"] = FABRIC_CFG_PATH
    env["CORE_PEER_TLS_ENABLED"] = "true"
    env["CORE_PEER_LOCALMSPID"] = "Org1MSP"
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = _ORG1_TLS
    env["CORE_PEER_MSPCONFIGPATH"] = f"{_ORG1}/users/Admin@org1.example.com/msp"
    env["CORE_PEER_ADDRESS"] = PEER1_ADDR
    return env


def is_available():
    """Best-effort check that the peer binary and crypto material exist."""
    return os.path.exists(f"{FABRIC_BIN}/peer") and os.path.exists(_ORDERER_CA)


def store_iot_data(data_id, payload):
    """Submit StoreIoTData(data_id, payload) to Fabric. Returns the real txid on
    success, or None on failure. `payload` may be a dict or a JSON string; it is
    stored verbatim (full record, no field loss)."""
    payload_str = payload if isinstance(payload, str) else json.dumps(payload)
    args = json.dumps({"function": "StoreIoTData", "Args": [str(data_id), payload_str]})
    cmd = [
        f"{FABRIC_BIN}/peer", "chaincode", "invoke",
        "-o", ORDERER, "--ordererTLSHostnameOverride", ORDERER_HOST,
        "--tls", "--cafile", _ORDERER_CA,
        "-C", CHANNEL, "-n", CC_NAME,
        "--peerAddresses", PEER1_ADDR, "--tlsRootCertFiles", _ORG1_TLS,
        "--peerAddresses", PEER2_ADDR, "--tlsRootCertFiles", _ORG2_TLS,
        "-c", args, "--waitForEvent",
    ]
    try:
        res = subprocess.run(cmd, env=_peer_env(), capture_output=True,
                             text=True, timeout=INVOKE_TIMEOUT)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("Fabric invoke error: %s", e)
        return None

    out = (res.stdout or "") + (res.stderr or "")
    m = _TXID_RE.search(out)
    if res.returncode == 0 and m:
        txid = m.group(1)
        logger.info("Fabric StoreIoTData committed id=%s txid=%s", data_id, txid)
        return txid
    logger.error("Fabric invoke failed (rc=%s): %s", res.returncode, out[-600:])
    return None


def read_iot_data(data_id):
    """Evaluate ReadIoTData(data_id). Returns the stored record dict, or None."""
    args = json.dumps({"function": "ReadIoTData", "Args": [str(data_id)]})
    cmd = [f"{FABRIC_BIN}/peer", "chaincode", "query",
           "-C", CHANNEL, "-n", CC_NAME, "-c", args]
    try:
        res = subprocess.run(cmd, env=_peer_env(), capture_output=True,
                             text=True, timeout=INVOKE_TIMEOUT)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.error("Fabric query error: %s", e)
        return None
    if res.returncode != 0:
        logger.error("Fabric query failed: %s", (res.stderr or "")[-400:])
        return None
    try:
        return json.loads(res.stdout.strip())
    except json.JSONDecodeError:
        logger.error("Fabric query returned non-JSON: %s", res.stdout[:400])
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "selftest-1"
    tx = store_iot_data(rid, {"deviceId": "sensor_x", "temperature": 21.1,
                              "patientId": "P999", "note": "fabric_client self-test"})
    print("store txid:", tx)
    print("read back :", read_iot_data(rid))
