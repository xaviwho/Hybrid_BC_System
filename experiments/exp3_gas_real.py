#!/usr/bin/env python3
"""
Experiment 3 (Phase 2 rebuild): Ethereum anchoring gas cost — measured per batch size.

WHAT CHANGED AND WHY
--------------------
The previous version measured exactly ONE root transaction shape — a root over
64 leaves — and then produced all eight "batch size" rows by dividing that single
number by N. Seven of the eight rows were arithmetic on a root that did not
correspond to the batch it claimed to represent, and the 99.5%-at-N=200 headline
came from a 64-leaf root.

Now: for each N in {1,2,5,10,20,50,100,200} a real Merkle tree over N leaves is
built and its root is anchored in a real transaction, REPS times. gasUsed comes
from the receipt every time.

The division root_gas(N)/N is retained and is legitimate — one transaction
genuinely covers N records — but it is tagged `derived`, while the root gas it
divides is tagged `measured`.

Also recorded per N, because they were previously unstated assumptions:
  leaf count, tree depth, calldata size, proof size, and whether root gas is flat
  across N. Root gas being independent of N is the REASON batching works; if it
  is not flat, the 1/N model is wrong and the data will say so.

Output: experiments/results/exp3/exp3_gas_real.json
"""

import hashlib
import json
import os
import statistics
import sys
import time

from web3 import Web3

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "orchestrator"))
import contract_registry  # noqa: E402  — the SINGLE address-selection rule
OUTPUT_DIR = os.path.join(_REPO, "experiments", "results", "exp3")
CONTRACT_JSON = os.path.join(
    _REPO, "blockchain", "setup", "ethereum", "build", "contracts", "IoTDataRegistry.json")
GANACHE_URL = os.getenv("GANACHE_URL", "http://127.0.0.1:8545")

BATCH_SIZES = [1, 2, 5, 10, 20, 50, 100, 200]
REPS = 3          # >= 3 real transactions per batch size (spec, Change 3)
FLAT_TOLERANCE = 0.01   # root gas considered flat across N within 1%


def _record_metadata(i):
    """Realistic single-record public metadata JSON string."""
    return json.dumps({"deviceId": f"sensor_{i%50}", "ts": 1700000000 + i,
                       "loc": f"zone_{i%10}", "unit": "C"})


def _merkle(n, salt):
    """Real Merkle tree over n leaves. Returns (root_bytes, depth, proof_len).

    proof_len is the number of sibling hashes an inclusion proof carries, i.e.
    the tree depth — the verifier-side cost that batching trades against.
    """
    leaves = [hashlib.sha256(f"{salt}-{k}".encode()).digest() for k in range(n)]
    if not leaves:
        return b"\x00" * 32, 0, 0
    level, depth = leaves, 0
    while len(level) > 1:
        nxt = []
        for j in range(0, len(level), 2):
            a = level[j]
            b = level[j + 1] if j + 1 < len(level) else level[j]
            nxt.append(hashlib.sha256(a + b).digest())
        level = nxt
        depth += 1
    return level[0], depth, depth


def _stats(xs):
    if not xs:
        return {"n": 0}
    return {
        "n": len(xs),
        "mean": round(statistics.fmean(xs), 1),
        "min": min(xs),
        "max": max(xs),
        "stdev": round(statistics.pstdev(xs), 3) if len(xs) > 1 else 0.0,
        "samples": xs,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
    if not w3.is_connected():
        print(f"ERROR: cannot reach Ganache at {GANACHE_URL}. Start it first.")
        print("Nothing written — a missing number is recoverable, a fabricated one is not.")
        return 1
    # Same resolver as the orchestrator. If these two ever disagree, exp3 measures
    # gas on one contract while exp1/exp5 anchor to another within a single run.
    try:
        res = contract_registry.resolve(CONTRACT_JSON, w3=w3, require_code=True)
    except contract_registry.ContractResolutionError as e:
        print(f"ERROR: {e}")
        print("Nothing written — a missing number is recoverable, a fabricated one is not.")
        return 1
    addr = res["address"]
    c = w3.eth.contract(address=addr, abi=res["abi"])
    acct = w3.eth.accounts[0]
    w3.eth.default_account = acct
    run_salt = f"{os.getpid()}-{int(time.time())}"

    print("=" * 72)
    print("  EXPERIMENT 3 (Phase 2): measured gas per REAL N-leaf Merkle root")
    print(f"  chain_id={w3.eth.chain_id}  contract={addr}")
    print("=" * 72)

    tx_hashes = []

    def anchor(data_id_str, dhash, metadata_str):
        did = hashlib.sha256(data_id_str.encode()).digest()
        txh = c.functions.registerData(did, dhash, metadata_str).transact()
        rcpt = w3.eth.wait_for_transaction_receipt(txh)
        tx_hashes.append(rcpt.transactionHash.hex())
        return rcpt.gasUsed, rcpt.transactionHash.hex()

    # --- Baseline: single-record anchoring, one tx per record ---
    single_gas, single_txs = [], []
    for i in range(REPS):
        md = _record_metadata(i)
        g, h = anchor(f"single-{run_salt}-{i}", hashlib.sha256(md.encode()).hexdigest(), md)
        single_gas.append(g)
        single_txs.append(h)
    single_avg = statistics.fmean(single_gas)
    print(f"  single-record: {single_avg:.0f} gas  samples={single_gas}")

    # --- Per-N: REAL N-leaf root, REPS real transactions each ---
    curve = []
    for n in BATCH_SIZES:
        gas_samples, txs = [], []
        root_hex = depth = proof_len = None
        for r in range(REPS):
            root, depth, proof_len = _merkle(n, f"{run_salt}-N{n}-r{r}")
            root_hex = "0x" + root.hex()
            g, h = anchor(f"root-{run_salt}-N{n}-r{r}", root_hex, root_hex)
            gas_samples.append(g)
            txs.append(h)
        root_stats = _stats(gas_samples)
        root_mean = root_stats["mean"]
        per_record = root_mean / n
        reduction = 100.0 * (1 - per_record / single_avg)
        curve.append({
            "batch_size": n,
            "leaf_count": n,
            "tree_depth": depth,
            "proof_len_hashes": proof_len,
            "proof_size_bytes": proof_len * 32,
            "calldata_bytes": len(root_hex.encode()),
            "root_anchor_gas": {"kind": "measured", **root_stats},
            "batched_gas_per_record": {
                "kind": "derived",
                "value": round(per_record, 1),
                "derivation": f"measured_root_gas(N={n}).mean / {n}",
            },
            "gas_reduction_pct": {
                "kind": "derived",
                "value": round(reduction, 2),
                "derivation": f"100 * (1 - batched_gas_per_record / measured_single_gas)",
            },
            "tx_hashes": txs,
        })
        print(f"   N={n:>4}: root {root_mean:>9.1f} gas (depth {depth}, "
              f"proof {proof_len*32} B) -> {per_record:>9.1f} gas/record  "
              f"({reduction:.2f}% reduction)")

    # --- Is root gas actually flat in N? The 1/N model depends on it. ---
    root_means = [row["root_anchor_gas"]["mean"] for row in curve]
    spread = (max(root_means) - min(root_means)) / statistics.fmean(root_means)
    flat = spread <= FLAT_TOLERANCE

    results = {
        "experiment": "exp3_gas_real",
        "schema_version": 2,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": {
            "data_source": "real transactions against deployed IoTDataRegistry",
            "chain_id": w3.eth.chain_id,
            "contract_address": addr,
            "reps_per_batch_size": REPS,
            "batch_sizes": BATCH_SIZES,
            "total_transactions": len(tx_hashes),
            "all_tx_hashes": tx_hashes,
        },
        "single_anchor_gas": {"kind": "measured", **_stats(single_gas),
                              "tx_hashes": single_txs,
                              "note": ("zero variance is expected: registerData writes a "
                                       "fixed-size struct and the metadata string is the "
                                       "same length for every single-record sample")},
        "gas_per_record_by_batch": curve,
        "root_gas_flat_in_N": {
            "kind": "measured",
            "value": flat,
            "relative_spread": round(spread, 5),
            "tolerance": FLAT_TOLERANCE,
            "note": ("Root gas is independent of N because only the 32-byte root is "
                     "stored on chain — this is WHY batching works, and it is now "
                     "measured rather than assumed."
                     if flat else
                     "Root gas is NOT flat across N; the 1/N amortization model does "
                     "not hold as stated and must be re-derived from these numbers."),
        },
        "max_reduction_pct": curve[-1]["gas_reduction_pct"],
    }
    path = os.path.join(OUTPUT_DIR, "exp3_gas_real.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n  root gas flat across N: {flat} (relative spread {spread:.5f})")
    print(f"  total real transactions: {len(tx_hashes)}")
    print(f"  JSON: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
