"""
anchoring.py - deliver one outbox row to the IoTDataRegistry contract.

Shared by the in-process relay (orchestrator.py, RELAY_MODE=inprocess) and the
standalone relay process (relay_worker.py). Each relay sends from its own
account, which must be on the contract's relay allowlist (Auth(caller), Eq. 27).

On-chain call:  registerData(onchain_id(id), c, canon(m))
    _dataId    Keccak-256(utf-8 id): the idempotency key, not the payload's own
               `id` field. Before WS0.5 two different records sharing a payload
               `id` mapped to one slot, and the second was silently marked
               delivered against the first's commitment (AUDIT_WS0 F3).
    _dataHash  c = H(sigma), 0x-hex
    _metadata  canonical m, so h' = H(m) can be recomputed from the chain alone
"""

import json
import os

from commitment import canon, onchain_id

RECEIPT_TIMEOUT_S = float(os.getenv("ANCHOR_RECEIPT_TIMEOUT_S", "120"))
# Pre-check getDataOwner before sending. On (default) keeps duplicate reverts
# rare; WS3's `race` coordination mode turns it off so collisions resolve on chain.
PRECHECK = os.getenv("ANCHOR_PRECHECK", "1").lower() in ("1", "true", "yes")

ZERO = "0x0000000000000000000000000000000000000000"


class AnchorConflict(RuntimeError):
    """The registry slot for this id holds a DIFFERENT commitment."""


def _existing(contract, data_id):
    """Return the on-chain dataHash for data_id, or None if the slot is empty."""
    if contract.functions.getDataOwner(data_id).call() == ZERO:
        return None
    rec = contract.functions.dataRecords(data_id).call()
    return rec[2]  # (id, owner, dataHash, metadata, registrationTime)


def _settle_existing(row, onchain_c):
    if onchain_c == row["commitment"]:
        return "preexisting:" + row["commitment"]
    raise AnchorConflict(
        f"registry slot for {row['id']} holds {onchain_c}, expected {row['commitment']}")


def make_anchor_fn(web3, contract, account):
    """Build anchor_fn(row) -> tx hash (or 'preexisting:<c>') for one account."""

    def anchor(row):
        payload = json.loads(row["payload"]) if row["payload"] else {}
        m = payload.get("m")
        if m is None or not row.get("commitment"):
            raise RuntimeError(f"outbox row {row['id']} has no m/commitment; not a v2 row")
        data_id = onchain_id(row["id"])

        if PRECHECK:
            onchain_c = _existing(contract, data_id)
            if onchain_c is not None:
                return _settle_existing(row, onchain_c)

        try:
            tx_hash = contract.functions.registerData(
                data_id, row["commitment"], canon(m).decode("utf-8"),
            ).transact({"from": account})
        except Exception as e:
            # Ganache rejects a reverting transaction at send time with the reason.
            if "already registered" in str(e).lower():
                return _settle_existing(row, _existing(contract, data_id))
            raise
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=RECEIPT_TIMEOUT_S)
        if receipt.status != 1:
            onchain_c = _existing(contract, data_id)
            if onchain_c is not None:
                return _settle_existing(row, onchain_c)
            raise RuntimeError(f"registerData reverted for {row['id']} "
                               f"(tx {receipt.transactionHash.hex()})")
        return receipt.transactionHash.hex()

    return anchor
