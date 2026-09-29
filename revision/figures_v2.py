#!/usr/bin/env python3
"""
WS8 figures for the revision, built ONLY from results/v2 (RESULTS.json and the
per-workstream summaries it indexes). Elsevier artwork widths: 90 mm single
column, 190 mm double. Every series carries colour + line style + marker, so the
figures read in grayscale. Colours: the dataviz reference categorical slots 1-4
(light), validated with scripts/validate_palette.js (all hard checks pass; the
sub-3:1 aqua/yellow slots are relieved by markers, legends and the tables).

A figure whose inputs are absent is skipped and named in the printed summary;
nothing is interpolated or drawn from placeholder data.

Output: results/v2/figures/<name>.{pdf,png}
"""
import glob
import json
import os
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(REPO, "results", "v2")
OUT = os.path.join(V2, "figures")
MM = 1 / 25.4
SINGLE, DOUBLE = 90 * MM, 190 * MM
INK, INK2, GRID, AXIS = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
STYLE = [("-", "o"), ("--", "s"), ("-.", "^"), (":", "D")]
FIXTURES = ["all_public", "all_sensitive", "mixed", "fabric_only"]
made, skipped = [], []

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 7, "axes.titlesize": 7.5, "axes.labelsize": 7,
    "legend.fontsize": 6.2, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.4,
    "lines.markersize": 3.6, "savefig.dpi": 300, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})


def load(p):
    return json.load(open(p)) if os.path.exists(p) else None


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"{name}.{ext}"))
    plt.close(fig)
    made.append(name)


def series(ax, i, x, y, err=None, label=None):
    ls, mk = STYLE[i % 4]
    ax.errorbar(x, y, yerr=err, color=SLOT[i % 4], ls=ls, marker=mk, label=label, capsize=1.5,
                elinewidth=0.6, markeredgecolor="white", markeredgewidth=0.4)


def cell(levels, key, stat="mean"):
    xs = sorted(levels, key=int)
    return ([int(c) for c in xs], [levels[c][key].get(stat) for c in xs],
            [levels[c][key].get("ci95_half") or 0 for c in xs])


# ---- Fig. 5 (updated): orchestration on the multi-VM testbed, WS2 base ----------
def fig_orchestration(ws2):
    base = (ws2 or {}).get("configs", {}).get("base")
    if not base:
        skipped.append("fig5_orchestration_v2 (WS2 base)"); return
    fig, (a, b) = plt.subplots(1, 2, figsize=(DOUBLE, 55 * MM))
    for i, cls in enumerate(FIXTURES):
        if cls not in base["fixtures"]:
            continue
        lv = base["fixtures"][cls]["levels"]
        x, y, e = cell(lv, "tps"); series(a, i, x, y, e, cls)
        x, y, e = cell(lv, "ack_mean"); series(b, i, x, y, e, cls)
    for ax in (a, b):
        ax.axvline(base["max_message_count"], color=INK2, lw=0.7, ls=(0, (4, 3)))
        ax.set_xlabel("client concurrency c")
    a.set_ylabel("throughput (tps)"); b.set_ylabel("acknowledgement latency (ms)")
    a.set_title("(a) throughput, mean ± 95% CI over repetitions", loc="left")
    b.set_title("(b) acknowledgement latency", loc="left")
    a.legend(frameon=False, ncol=2)
    save(fig, "fig5_orchestration_v2")


# ---- New: network-delay sweep ---------------------------------------------------
def fig_delay(ws2):
    cfgs = (ws2 or {}).get("configs", {})
    names = [n for n in ("base", "d10", "d25", "d50") if n in cfgs]
    if len(names) < 2:
        skipped.append("fig_delay_sweep (WS2 d10/d25/d50)"); return
    fig, (a, b) = plt.subplots(1, 2, figsize=(DOUBLE, 55 * MM))
    for i, n in enumerate(names):
        lv = cfgs[n]["fixtures"]["mixed"]["levels"]
        x, y, e = cell(lv, "ack_mean")
        series(a, i, x, y, e, f"+{2 * cfgs[n]['netem_one_way_ms']} ms RTT" if n != "base" else "Azure paths only")
    a.set_xlabel("client concurrency c"); a.set_ylabel("ack latency, mixed (ms)")
    a.set_title("(a) latency vs concurrency by added RTT", loc="left"); a.legend(frameon=False)
    fit = ws2.get("delay_fit", {})
    for i, cls in enumerate(("mixed", "fabric_only")):
        f = fit.get(cls)
        if not f:
            continue
        xs, ys = zip(*f["points_added_rtt_ms_vs_floor_ms"])
        series(b, i + 2, xs, ys, None, f"{cls}: slope {f['slope_round_trips']} RTT")
        b.plot([min(xs), max(xs)], [f["intercept_ms"] + f["slope_round_trips"] * x for x in (min(xs), max(xs))],
               color=SLOT[(i + 2) % 4], lw=0.8, alpha=0.6)
    b.set_xlabel("added round-trip time (ms)"); b.set_ylabel("floor: ack at c = 1 (ms)")
    b.set_title("(b) latency floor vs added RTT (least squares)", loc="left"); b.legend(frameon=False)
    save(fig, "fig_delay_sweep")


# ---- New: block-cutting sweep vs Eq. (8) -----------------------------------------
def fig_blockcut(ws2):
    cfgs = (ws2 or {}).get("configs", {})
    mm = [n for n in ("m5", "base", "m20") if n in cfgs]
    bt = [n for n in ("t05", "t1", "base") if n in cfgs]
    if len(mm) < 2 and len(bt) < 2:
        skipped.append("fig_blockcut_sweep (WS2 m5/m20/t05/t1)"); return
    fig, (a, b) = plt.subplots(1, 2, figsize=(DOUBLE, 55 * MM))
    for i, n in enumerate(mm):
        lv = cfgs[n]["fixtures"]["fabric_only"]["levels"]
        x, y, e = cell(lv, "ack_mean")
        mmc = cfgs[n]["max_message_count"]
        series(a, i, x, y, e, f"MaxMessageCount {mmc}")
        a.axvline(mmc, color=SLOT[i], lw=0.7, ls=(0, (4, 3)))
    a.set_xlabel("client concurrency c"); a.set_ylabel("ack latency, fabric_only (ms)")
    a.set_title("(a) transition at c = MaxMessageCount (dashed: prediction)", loc="left")
    a.legend(frameon=False)
    for i, cls in enumerate(("mixed", "fabric_only")):
        pts = sorted((cfgs[n]["batch_timeout_s"] * 1000, cfgs[n]["fixtures"][cls]["floor_ack_ms_c1"]) for n in bt)
        if pts:
            series(b, i + 2, [p[0] for p in pts], [p[1] for p in pts], None, cls)
    lim = [0, 2100]
    b.plot(lim, lim, color=INK2, lw=0.7, ls=(0, (1, 2)), label="floor = BatchTimeout")
    b.set_xlabel("BatchTimeout (ms)"); b.set_ylabel("floor: ack at c = 1 (ms)")
    b.set_title("(b) sub-threshold floor tracks BatchTimeout", loc="left"); b.legend(frameon=False)
    save(fig, "fig_blockcut_sweep")


# ---- New: mu_relay vs k -------------------------------------------------------------
def fig_mu(results):
    ms = {m["metric"]: m for m in (results or {}).get("metrics", []) if m["metric"].startswith("ws3_mu_relay_")}
    if not ms:
        skipped.append("fig_mu_relay (WS3 drain)"); return
    fig, ax = plt.subplots(figsize=(SINGLE, 55 * MM))
    i = 0
    for coord in ("lease", "race"):
        for k in (1, 2, 3):
            pts = sorted((float(m.split("lambda")[1]), v["value"], v.get("ci95_half") or 0)
                         for m, v in ms.items() if f"_k{k}_{coord}_" in m)
            if pts:
                series(ax, i, [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts], f"k={k} {coord}")
                i += 1
    ax.set_xlabel("offered rate λ (rows/s)"); ax.set_ylabel("μ_relay while backlogged (anchors/s)")
    ax.set_title("Relay drain rate vs offered load", loc="left"); ax.legend(frameon=False, ncol=2)
    save(fig, "fig_mu_relay")


# ---- New: fault-injection summary ---------------------------------------------------
def fig_fault(results):
    ms = {m["metric"]: m["value"] for m in (results or {}).get("metrics", []) if m["metric"].startswith("ws3_fault_")}
    ttr = {m: v for m, v in ms.items() if m.endswith("_time_to_recovery_s")}
    if not ttr:
        skipped.append("fig_fault_injection (WS3 fault)"); return
    labels = sorted({m[len("ws3_fault_"):-len("_time_to_recovery_s")] for m in ttr})
    fig, ax = plt.subplots(figsize=(DOUBLE, 60 * MM))
    xs = range(len(labels))
    ax.bar(xs, [ttr[f"ws3_fault_{l}_time_to_recovery_s"] for l in labels], color=SLOT[0], width=0.6,
           edgecolor="white", linewidth=0.8)
    for x, l in zip(xs, labels):
        dup = ms.get(f"ws3_fault_{l}_duplicate_anchors")
        ok = ms.get(f"ws3_fault_{l}_anchors_equal_records")
        ax.annotate(f"dup {dup}\n{'=' if ok else '≠'} records", (x, ttr[f'ws3_fault_{l}_time_to_recovery_s']),
                    ha="center", va="bottom", fontsize=5.5, color=INK2, xytext=(0, 2), textcoords="offset points")
    ax.set_xticks(list(xs)); ax.set_xticklabels([l.replace("_", "\n", 2) for l in labels], fontsize=5.5)
    ax.set_ylabel("time to recovery after crash (s)")
    ax.set_title("Fault injection: recovery time; duplicate anchors and anchor/record equality from event logs", loc="left")
    save(fig, "fig_fault_injection")


# ---- New: sync vs async -------------------------------------------------------------
def fig_sync(results):
    ms = {m["metric"]: m for m in (results or {}).get("metrics", []) if m["metric"].startswith("ws4_")}
    if not ms:
        skipped.append("fig_sync_vs_async (WS4)"); return
    fig, (a, b) = plt.subplots(1, 2, figsize=(DOUBLE, 55 * MM))
    for i, label in enumerate(("sync_anchor", "async_outbox", "fabric_only")):
        for ax, q in ((a, "ack_ms"), (b, "tps")):
            pts = sorted((int(m.split("_c")[1].split("_")[0]), v["value"], v.get("ci95_half") or 0)
                         for m, v in ms.items() if m.startswith(f"ws4_{label}_c") and m.endswith(q))
            if pts:
                series(ax, i, [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts], label)
    a.set_ylabel("acknowledgement latency (ms)"); b.set_ylabel("throughput (tps)")
    for ax in (a, b):
        ax.set_xlabel("client concurrency c")
    a.set_title("(a) T_ack", loc="left"); b.set_title("(b) throughput", loc="left"); a.legend(frameon=False)
    save(fig, "fig_sync_vs_async")


# ---- Fig. 7 (updated): Merkle batching from WS7 ------------------------------------
def fig_batching(results):
    ms = {m["metric"]: m["value"] for m in (results or {}).get("metrics", [])}
    ns = sorted(int(k.split("_N")[1]) for k in ms if k.startswith("gas_reduction_N"))
    if not ns or "gas_per_record_single" not in ms:
        skipped.append("fig7_batching_v2 (WS7 exp3)"); return
    fig, (a, b) = plt.subplots(1, 2, figsize=(DOUBLE, 55 * MM))
    series(a, 0, ns, [ms[f"gas_root_anchor_N{n}"] / n for n in ns], None, "root anchor / N")
    a.axhline(ms["gas_per_record_single"], color=INK2, lw=0.7, ls=(0, (4, 3)), label="single-record anchor")
    a.set_xscale("log"); a.set_yscale("log")
    a.set_xlabel("batch size N"); a.set_ylabel("gas per record"); a.legend(frameon=False)
    a.set_title("(a) amortised gas per record", loc="left")
    series(b, 1, ns, [ms[f"gas_reduction_N{n}"] for n in ns], None, "reduction vs single")
    b.axhline(0, color=AXIS, lw=0.7)
    b.set_xscale("log"); b.set_xlabel("batch size N"); b.set_ylabel("reduction (%)")
    b.set_title("(b) reduction relative to single-record anchoring", loc="left")
    save(fig, "fig7_batching_v2")


def main():
    results = load(os.path.join(V2, "RESULTS.json"))
    ws2 = load(os.path.join(V2, "ws2", "ws2_summary.json"))
    fig_orchestration(ws2); fig_delay(ws2); fig_blockcut(ws2)
    fig_mu(results); fig_fault(results); fig_sync(results); fig_batching(results)
    print("made:", made)
    print("skipped (inputs absent):", skipped)


if __name__ == "__main__":
    main()
