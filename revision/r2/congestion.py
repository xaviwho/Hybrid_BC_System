#!/usr/bin/env python3
"""
R2-2 — relay throughput when public-chain inclusion slows down (congestion).

Reviewer (round 2): "address how [~4 anchors/s] scales if public gas costs spike
or if Ethereum blocks experience congestion". Gas price changes the cost of an
anchor, not its gas or the relay's pacing; what bounds relay throughput is the
time an anchor waits for inclusion. This run emulates slow inclusion on the
SAME Ganache chain and registry by restarting it with --miner.blockTime B
(ganache_mode.sh, run beforehand), then drains a burst of N synthetic outbox
rows with k lease relays exactly as WS3's drain part does.

Prediction: each lease relay holds one transaction in flight until its receipt,
so mu_relay ~= k / E[inclusion wait] ~= k / B once B dominates the per-anchor
service time (WS3, instamine: 1/mu ~= 0.25-0.5 s).

Output: <out>/B<B>/k<k>/rep<r>/result.json (drain_run fields + observed block
interval and gas used per anchor).
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ws3"))
import harnesslib as H  # noqa: E402
from outbox import Outbox  # noqa: E402
from run_ws3 import drain_run  # noqa: E402


def block_interval(w3, b0, b1):
    """Mean timestamp gap between consecutive blocks in [b0, b1] (s)."""
    if b1 - b0 < 2:
        return None
    ts = [w3.eth.get_block(b)["timestamp"] for b in range(b0, b1 + 1)]
    return round((ts[-1] - ts[0]) / (len(ts) - 1), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block-time", type=float, required=True, help="Ganache --miner.blockTime in force (0 = instamine)")
    ap.add_argument("--k", default="1,2,3")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--n", type=int, default=20, help="burst size (rows)")
    ap.add_argument("--out", default=os.path.join(H.REPO, "results", "v2", "raw", "r2_congestion"))
    a = ap.parse_args()
    ob = Outbox(os.environ["OUTBOX_DB"])
    w3, _, _ = H.chain()
    H.services("prod")
    for rep in range(1, a.reps + 1):
        for k in [int(x) for x in a.k.split(",")]:
            d = os.path.join(a.out, f"B{a.block_time:g}", f"k{k}", f"rep{rep}")
            if os.path.exists(os.path.join(d, "result.json")):
                continue
            os.makedirs(d, exist_ok=True)
            tag = f"r2cg-B{a.block_time:g}-k{k}-r{rep}-{int(time.time())}"
            b0 = w3.eth.block_number
            # burst: n rows enqueued over 1/20 s each (lam = n rows/s for 1 s)
            res = drain_run(ob, k, "lease", float(a.n), 1.0, d, tag)
            b1 = w3.eth.block_number
            gas = [g for (g,) in ob._conn().execute(
                "SELECT gas_used FROM relay_attempts WHERE row_id LIKE ? AND tx_status=1 AND gas_used > 0",
                (tag + "-%",))]
            res.update(block_time_set_s=a.block_time, observed_block_interval_s=block_interval(w3, b0 + 1, b1),
                       predicted_mu=round(k / a.block_time, 3) if a.block_time > 0 else None,
                       gas_used_per_anchor={"n": len(gas), "mean": round(sum(gas) / len(gas), 1) if gas else None,
                                            "min": min(gas, default=None), "max": max(gas, default=None)},
                       rep=rep, tag=tag)
            with open(os.path.join(d, "result.json"), "w") as f:
                json.dump(res, f, indent=1)
            print(json.dumps({x: res.get(x) for x in ("k", "rep", "block_time_set_s", "observed_block_interval_s",
                                                      "mu_relay_backlogged", "delivered_rate_overall", "predicted_mu",
                                                      "all_delivered", "events")}), flush=True)


if __name__ == "__main__":
    main()
