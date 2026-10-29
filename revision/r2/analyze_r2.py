#!/usr/bin/env python3
"""
Round-2 summaries and figure, built ONLY from results/v2/raw/r2_orderer and
results/v2/raw/r2_congestion (orderer_outage.py, congestion.py).

  results/v2/r2_summary.json            per-metric mean, 95% CI half-width, n
  results/v2/figures/fig_r2.{pdf,png}   (a) orderer crash timeline (one rep):
                                        acks/s and outbox depth; (b) mu_relay vs
                                        block interval B, with the k/B prediction

The fee table multiplies the MEASURED gas per anchor by gas-price levels; the
prices are scenario inputs, not measurements, and are labelled as such.
"""
import glob
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import figures_v2 as F  # noqa: E402  (style, palette, save)

plt = F.plt
RAW = os.path.join(F.V2, "raw")
T975 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}
GWEI = [1, 10, 50, 100, 500]          # scenario gas prices (not measured)
BATCH_N = [1, 200]                    # direct anchor vs the paper's Merkle batch size


def agg(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    m = st.fmean(xs)
    h = T975.get(len(xs), 1.96) * st.stdev(xs) / len(xs) ** 0.5 if len(xs) > 1 else None
    return {"mean": round(m, 3), "ci95_half": round(h, 3) if h is not None else None,
            "min": min(xs), "max": max(xs), "n": len(xs)}


def orderer():
    reps = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(RAW, "r2_orderer", "rep*", "result.json")))]
    if not reps:
        return None
    g = lambda f: [f(r) for r in reps]  # noqa: E731
    return {
        "reps": len(reps), "c": reps[0]["c"], "relays": reps[0]["relays"],
        "outage_s": reps[0]["timeline_s"]["outage_requested"],
        "ok_per_s": {w: agg(g(lambda r: r["ingest_by_phase"][w]["ok_per_s"])) for w in ("pre", "outage", "post")},
        "failed": {w: agg(g(lambda r: r["ingest_by_phase"][w]["failed"])) for w in ("pre", "outage", "post")},
        "errors_outage": [r["ingest_by_phase"]["outage"]["errors"] for r in reps],
        "time_to_first_ack_after_restart_s": agg(g(lambda r: r["time_to_first_ack_after_restart_s"])),
        "queue_depth_at_kill": agg(g(lambda r: r["outbox"]["queue_depth_at_kill"])),
        "queue_depth_at_restart": agg(g(lambda r: r["outbox"]["queue_depth_at_restart"])),
        "anchors_delivered_during_outage": agg(g(lambda r: r["outbox"]["anchors_delivered_during_outage"])),
        "relay_rate_during_outage_per_s": agg(g(lambda r: r["outbox"]["relay_rate_during_outage_per_s"])),
        "ambiguous_failed_but_committed": sum(g(lambda r: r["ambiguous_failed_but_committed"])),
        "retries": sum(g(lambda r: r["retries"]["n"])),
        "retry_status": [r["retries"]["status"] for r in reps],
        "sweep_counts": [r["sweep"]["counts"] for r in reps],
        "repaired_orphans": sum(g(lambda r: r["sweep"]["repaired"])),
        "all_delivered": all(g(lambda r: r["all_delivered"])),
        "hybrid_records": sum(g(lambda r: r["hybrid_records_on_fabric"])),
        "anchors_on_chain": sum(g(lambda r: r["anchors_on_chain"])),
        "anchors_equal_records_all_reps": all(g(lambda r: r["anchors_equal_hybrid_records"])),
        "duplicate_anchors": sum(g(lambda r: r["duplicate_anchors"])),
    }


def congestion():
    out, gas = {}, []
    for p in sorted(glob.glob(os.path.join(RAW, "r2_congestion", "B*", "k*", "rep*", "result.json"))):
        r = json.load(open(p))
        cell = out.setdefault(f"B{r['block_time_set_s']:g}", {}).setdefault(f"k{r['k']}", [])
        cell.append(r)
        if r["gas_used_per_anchor"]["mean"]:
            gas.append(r["gas_used_per_anchor"]["mean"])
    if not out:
        return None
    summ = {}
    for b, ks in out.items():
        for k, rs in ks.items():
            summ.setdefault(b, {})[k] = {
                "mu_relay_backlogged": agg([r["mu_relay_backlogged"] for r in rs]),
                "delivered_rate_overall": agg([r["delivered_rate_overall"] for r in rs]),
                "predicted_mu_k_over_B": rs[0]["predicted_mu"],
                "observed_block_interval_s": agg([r["observed_block_interval_s"] for r in rs]),
                "t_queue_p95_ms": agg([r["t_queue_ms"]["p95"] for r in rs]),
                "all_delivered": all(r["all_delivered"] for r in rs),
                "duplicates": sum(r["events"]["ids_with_many"] for r in rs),
                "reverted_txs": sum(r["chain"]["reverted_txs"] for r in rs),
            }
    g = st.fmean(gas) if gas else None
    fees = None
    if g:
        fees = {"gas_per_anchor_measured": round(g, 1), "gas_price_gwei_scenarios": GWEI,
                "eth_per_record": {f"N={n}": {str(p): round(g * p * 1e-9 / n, 9) for p in GWEI} for n in BATCH_N},
                "note": "gas measured from receipts; gas prices are scenario inputs; Merkle root gas ~= direct gas "
                        "(Table gas), so the N=200 row divides the root cost by N"}
    return {"cells": summ, "fees": fees}


def figure(od, cg):
    fig, (a, b) = plt.subplots(1, 2, figsize=(F.DOUBLE, 2.3))
    p = os.path.join(RAW, "r2_orderer", "rep1")
    if od and os.path.exists(os.path.join(p, "samples.json")):
        s = json.load(open(os.path.join(p, "samples.json")))
        rq = [json.loads(x) for x in open(os.path.join(p, "requests.jsonl"))]
        t0 = min(r["t_submit_rel"] for r in rq)
        bins = {}
        for r in rq:
            if r.get("status") in (200, 202):
                bins[int(r["t_return_rel"] - t0) // 5] = bins.get(int(r["t_return_rel"] - t0) // 5, 0) + 1
        xs = sorted(bins)
        a.step([x * 5 + t0 for x in xs], [bins[x] / 5 for x in xs], where="post", color=F.SLOT[0],
               label="ingest acks/s (5 s bins)")
        a2 = a.twinx()
        a2.plot([x[0] for x in s["samples"]], [x[1] for x in s["samples"]], color=F.SLOT[1], ls="--",
                label="outbox pending rows")
        a2.set_ylabel("pending anchors", color=F.INK2)
        a2.spines["right"].set_visible(True)
        a2.grid(False)
        a.axvspan(0, s["t_restart"], color=F.GRID, alpha=0.7, lw=0)
        a.text(s["t_restart"] / 2, a.get_ylim()[1] * 0.92, "orderer down", ha="center", fontsize=6, color=F.INK2)
        a.set_xlabel("time relative to orderer crash (s)")
        a.set_ylabel("acks/s")
        h1, l1 = a.get_legend_handles_labels()
        h2, l2 = a2.get_legend_handles_labels()
        a.legend(h1 + h2, l1 + l2, loc="lower left", frameon=False)
        a.set_title("(a) Orderer crash: ingestion stops, relay drains backlog")
    if cg:
        for i, k in enumerate(("k1", "k2", "k3")):
            pts = sorted((float(bk[1:]), v[k]["mu_relay_backlogged"]) for bk, v in cg["cells"].items() if k in v)
            pts = [(x, m) for x, m in pts if m.get("n")]
            if not pts:
                continue
            F.series(b, i, [x for x, _ in pts], [m["mean"] for _, m in pts],
                     [m.get("ci95_half") or 0 for _, m in pts], label=f"k={k[1]} measured")
            xs = [x for x, _ in pts]
            b.plot(xs, [int(k[1]) / x for x in xs], color=F.SLOT[i], lw=0.7, ls=":", alpha=0.8)
        b.plot([], [], color=F.INK2, ls=":", lw=0.7, label="k/B prediction")
        b.set_xlabel("block interval B (s)")
        b.set_ylabel(r"$\mu_{\mathrm{relay}}$ (anchors/s)")
        b.set_yscale("log")
        b.legend(frameon=False)
        b.set_title("(b) Inclusion delay bounds relay throughput")
    F.save(fig, "fig_r2")


def main():
    od, cg = orderer(), congestion()
    out = {"orderer_crash": od, "congestion": cg}
    with open(os.path.join(F.V2, "r2_summary.json"), "w") as f:
        json.dump(out, f, indent=1)
    figure(od, cg)
    print(json.dumps(out, indent=1)[:6000])


if __name__ == "__main__":
    main()
