"""
anchoring.py - deliver one outbox row to the IoTDataRegistry contract.

Shared by the in-process relay (orchestrator.py, RELAY_MODE=inprocess), the
standalone relay process (relay_worker.py) and the synchronous-anchor baseline
(orchestrator ORCH_MODE=sync_anchor, WS4). Each relay sends from its own
account, which must be on the contract's relay allowlist (Auth(caller), Eq. 27).

On-chain call:  registerData(onchain_id(id), c, canon(m))
    _dataId    Keccak-256(utf-8 id): the idempotency key, not the payload's own
               `id` field. Before WS0.5 two different records sharing a payload
               `id` mapped to one slot, and the second was silently marked
               delivered against the first's commitment (AUDIT_WS0 F3).
    _dataHash  c = H(sigma), 0x-hex
    _metadata  canonical m, so h' = H(m) can be recomputed from the chain alone

Result: a dict {result, tx, status, gas_used, outcome}. `result` is what the
outbox records (tx hash, or "preexisting:<c>" when the slot already holds this
record's commitment); the rest describes the chain call for the WS3 attempt log.
"""

import json
import os
import threading

from eth_utils import keccak

from commitment import canon, onchain_id

RECEIPT_TIMEOUT_S = float(os.getenv("ANCHOR_RECEIPT_TIMEOUT_S", "120"))
# Pre-check getDataOwner before sending (default). WS3 `race` mode turns it off
# and sends with a fixed gas limit, so colliding relays really broadcast and the
# loser's transaction reverts on chain (measurable wasted gas). With the
# pre-check or gas estimation on, a duplicate is refused before it is sent.
PRECHECK = os.getenv("ANCHOR_PRECHECK", "1").lower() in ("1", "true", "yes")
FIXED_GAS = int(os.getenv("ANCHOR_FIXED_GAS", "0")) or None
# Test-only (WS3 safety experiment): anchor a modified commitment.
TAMPER = os.getenv("TEST_TAMPER", "").lower() in ("1", "true", "yes")

ZERO = "0x0000000000000000000000000000000000000000"
_nonce_locks = {}                     # one lock per sending account (sync mode threads)
_nonce_locks_guard = threading.Lock()


class AnchorConflict(RuntimeError):
    """The registry slot for this id holds a DIFFERENT commitment."""


def _existing(contract, data_id):
    """Return the on-chain dataHash for data_id, or None if the slot is empty."""
    if contract.functions.getDataOwner(data_id).call() == ZERO:
        return None
    rec = contract.functions.dataRecords(data_id).call()
    return rec[2]  # (id, owner, dataHash, metadata, registrationTime)


def _settle_existing(row, onchain_c, **info):
    if onchain_c == row["commitment"]:
        return dict({"result": "preexisting:" + row["commitment"],
                     "outcome": "preexisting"}, **info)
    raise AnchorConflict(
        f"registry slot for {row['id']} holds {onchain_c}, expected {row['commitment']}")


def _hex(h):
    s = h.hex() if hasattr(h, "hex") else str(h)
    return s if s.startswith("0x") else "0x" + s


def make_anchor_fn(web3, contract, account, hook=None):
    """Build anchor_fn(row) -> result dict for one sending account.

    `hook(name)` is called at fault-injection points (Outbox.crash_point)."""
    with _nonce_locks_guard:
        lock = _nonce_locks.setdefault(account, threading.Lock())

    def anchor(row):
        payload = json.loads(row["payload"]) if row["payload"] else {}
        m = payload.get("m")
        if m is None or not row.get("commitment"):
            raise RuntimeError(f"outbox row {row['id']} has no m/commitment; not a v2 row")
        data_id = onchain_id(row["id"])
        c = row["commitment"]
        if TAMPER:
            c = "0x" + keccak((c + "|tampered").encode()).hex()

        if PRECHECK:
            onchain_c = _existing(contract, data_id)
            if onchain_c is not None:
                return _settle_existing(row, onchain_c)

        tx = {"from": account}
        if FIXED_GAS:
            tx["gas"] = FIXED_GAS
        try:
            # One sender per account at a time: concurrent sends from one account
            # (sync_anchor request threads) would otherwise race on the nonce.
            with lock:
                tx_hash = contract.functions.registerData(
                    data_id, c, canon(m).decode("utf-8")).transact(tx)
        except Exception as e:
            # Ganache refuses a reverting call at send/estimate time with the reason.
            if "already registered" in str(e).lower():
                return _settle_existing(row, _existing(contract, data_id), outcome="refused_duplicate")
            raise
        if hook:
            hook("after_broadcast", row["id"])   # (a): sent, receipt not yet seen
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=RECEIPT_TIMEOUT_S)
        info = {"tx": _hex(receipt.transactionHash), "status": receipt.status,
                "gas_used": receipt.gasUsed}
        if receipt.status != 1:
            onchain_c = _existing(contract, data_id)
            if onchain_c is not None:
                r = _settle_existing(row, onchain_c, **info)
                r["outcome"] = "reverted_duplicate"
                return r
            raise RuntimeError(f"registerData reverted for {row['id']} (tx {info['tx']})")
        return dict({"result": info["tx"], "outcome": "delivered"}, **info)

    return anchor
