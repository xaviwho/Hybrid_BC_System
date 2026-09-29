"""
relay_worker.py - one outbox relay as its own OS process (revision WS0.5).

The v1 relay was a thread inside the orchestrator process, started at import.
That tied relay count to web-server worker count and made a relay crash
indistinguishable from a server crash (AUDIT_WS0 F6). Here each relay is a
process with its own Ethereum account, so WS1 can serve the orchestrator from
gunicorn and WS3 can run and kill k relays independently.

Environment:
    OUTBOX_DB            path to the shared outbox (ext4; WAL is enforced)
    GANACHE_URL          JSON-RPC endpoint (default http://127.0.0.1:8545)
    RELAY_ID             identifier recorded on delivered rows (default relay-<idx>)
    RELAY_ACCOUNT_INDEX  index into eth.accounts; must be allowlisted (default 0)
    RELAY_POLL_S         poll interval (default outbox.POLL_INTERVAL_S)
    RELAY_LEASE_S        claim lease (default outbox.LEASE_S)
    RELAY_COORD          lease (default) | race   (WS3; see Outbox)

Test-only fault injection (WS3), never set in measurement runs of other WSs:
    TEST_CRASH_HOOK      after_broadcast | after_receipt | mid_poll
    TEST_CRASH_AFTER     deliveries before the hook fires (default 0)
    TEST_TAMPER=1        anchor a modified commitment (anchoring.py)
    TEST_WITHHOLD=1      mark rows delivered without anchoring them

Exits non-zero if the chain, the contract, or the allowlist check fails.
"""

from eth_utils import keccak

import os
import signal
import sys
import time

from web3 import Web3

import contract_registry
from anchoring import make_anchor_fn
from outbox import LEASE_S, POLL_INTERVAL_S, Outbox

ARTIFACT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "blockchain", "setup", "ethereum",
    "build", "contracts", "IoTDataRegistry.json"))


def main():
    db = os.environ.get("OUTBOX_DB")
    if not db:
        raise SystemExit("FATAL: OUTBOX_DB is not set")
    url = os.getenv("GANACHE_URL", "http://127.0.0.1:8545")
    idx = int(os.getenv("RELAY_ACCOUNT_INDEX", "0"))
    relay_id = os.getenv("RELAY_ID", f"relay-{idx}")

    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 120}))
    for _ in range(60):                  # a node busy with a large log query can stall briefly
        if w3.is_connected():
            break
        time.sleep(1)
    else:
        raise SystemExit(f"FATAL: cannot reach {url}")
    res = contract_registry.resolve(ARTIFACT, w3=w3, require_code=True)
    contract = w3.eth.contract(address=res["address"], abi=res["abi"])
    account = w3.eth.accounts[idx]
    if not contract.functions.isRelay(account).call():
        raise SystemExit(f"FATAL: account {idx} ({account}) is not on the relay "
                         f"allowlist of {res['address']}")

    ob = Outbox(db, poll_interval_s=float(os.getenv("RELAY_POLL_S", POLL_INTERVAL_S)),
                lease_s=float(os.getenv("RELAY_LEASE_S", LEASE_S)),
                relay_id=relay_id, relay_account=account,
                coord=os.getenv("RELAY_COORD", "lease"))
    anchor = make_anchor_fn(w3, contract, account, hook=ob.crash_point)
    if os.getenv("TEST_WITHHOLD", "").lower() in ("1", "true", "yes"):
        # A withholding relay: reports success with a plausible hash and never
        # sends anything. Only the reconciliation sweep (WS5) can notice.
        def anchor(row):  # noqa: F811
            return {"result": "0x" + keccak(("withheld|" + row["id"]).encode()).hex(),
                    "outcome": "withheld"}
    ob.anchor_fn = anchor

    def stop(signum, _frame):
        print(f"[{relay_id}] signal {signum}, stopping", flush=True)
        ob._stop.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    tests = {k: os.environ[k] for k in ("TEST_CRASH_HOOK", "TEST_CRASH_AFTER", "TEST_TAMPER",
                                        "TEST_WITHHOLD", "ANCHOR_PRECHECK", "ANCHOR_FIXED_GAS")
             if os.getenv(k)}
    print(f"[{relay_id}] pid {os.getpid()} account {account} contract {res['address']} "
          f"db {db} coord {ob.coord} lease {ob.lease_s}s {tests or ''}", flush=True)
    ob.run_relay()
    return 0


if __name__ == "__main__":
    sys.exit(main())
