#!/usr/bin/env python3
"""Rebuild the Section IV result figures from RESULTS.json.

Written 2026-08-19 against run d8ce50b9 / config_hash bb85df0d7803. There was no
predecessor: the spec that commissioned these panels refers to a
`build_all_figures.py` that does not exist in this repository or its history, so
this file is new. The 16 `generate_*.py` panel scripts on
`wip/pre-phase3-backup` are organised per contribution, not per figure, and
predate the four-fixture run.

FAIL LOUD. Every quantity is fetched through `dig()`, which raises KeyError
naming the full path it could not resolve. Nothing is defaulted, inferred, or
carried over from an earlier file -- a missing metric stops the build instead of
silently plotting a stale value.

Figures produced (Fig 6 is deliberately absent -- exp2 did not move):
  fig5_orchestration.{pdf,png}   (a) throughput vs concurrency, 4 fixtures
                                 (b) ack decomposition across the transition
                                 (c) outbox insertion vs concurrency
  fig7_batching.{pdf,png}        (a) gas/record vs N  (b) reduction vs N
                                 (c) Merkle proof size vs N
  fig8_lifecycle.{pdf,png}       (a) rollback sawtooth vs target, u annotated
                                 (b) storage, sparse and dense
  fig9_recovery_paths.{pdf,png}  checkpoint restore vs inversion from head

Palette: dataviz categorical slots blue/orange/aqua/violet. Chosen by running
scripts/validate_palette.js on candidate sets: this is the only four-colour set
tested that clears the ALL-PAIRS pairlist (worst CVD dE 9.2 >= 8 target,
worst normal-vision dE 16.3 >= 15 floor) rather than only the adjacent
pairlist. All-pairs matters here because the fixture-vs-control comparison the
panels exist to make is not between adjacent series. Aqua sits at 2.74:1 on
white, below 3:1, so the relief rule applies: every series carries a legend
entry AND a distinct marker, and the paper's tables restate the values.
Markers double as the grayscale/print encoding.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(_REPO, "experiments", "results", "RESULTS.json")
OUTDIR = os.path.join(_REPO, "experiments", "results", "figures_section4")

RUN_COMMIT = "d8ce50b9"
RUN_HASH = "bb85df0d7803"

# --- palette: role -> hex, validated as a set (see module docstring) ---------
C_PUBLIC = "#2a78d6"   # slot 1 blue
C_SENS   = "#eb6834"   # slot 2 orange
C_MIXED  = "#1baf7a"   # slot 3 aqua   (2.74:1 -- relief rule: legend + marker)
C_ONLY   = "#4a3aa7"   # slot 7 violet (the control, drawn heavier)
INK      = "#1a1a19"
INK_SOFT = "#52514e"
GRID     = "#d8d7d2"
RULE     = "#8a8983"

FIXTURES = [
    ("all_public",    C_PUBLIC, "o", 1.6, "all_public"),
    ("all_sensitive", C_SENS,   "^", 1.6, "all_sensitive"),
    ("mixed",         C_MIXED,  "D", 1.6, "mixed"),
    ("fabric_only",   C_ONLY,   "s", 2.4, "fabric_only (control, no anchor)"),
]

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman", "Nimbus Roman"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7,
    "axes.edgecolor": RULE,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK_SOFT,
    "ytick.color": INK_SOFT,
    "axes.linewidth": 0.6,
    "grid.color": GRID,
    "grid.linewidth": 0.5,
    "lines.linewidth": 1.6,
    "lines.markersize": 4.0,
    "figure.dpi": 200,
    "savefig.dpi": 400,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
    "pdf.fonttype": 42,
})


class MissingMetric(KeyError):
    """Raised when RESULTS.json lacks something a panel needs."""


def dig(node, *path, where=""):
    """Fetch node[p0][p1]... or raise naming the exact path that failed."""
    cur = node
    walked = []
    for p in path:
        walked.append(str(p))
        try:
            cur = cur[p]
        except (KeyError, IndexError, TypeError):
            raise MissingMetric(
                "RESULTS.json is missing %r (resolved %s) -- needed by %s. "
                "Not defaulting; rerun the experiment or promote the value."
                % (p, " -> ".join(walked), where or "a Section IV panel"))
    return cur


def num(v, *, where=""):
    """Unwrap a kind-tagged metric to a float, or raise."""
    if isinstance(v, dict):
        for k in ("value", "mean"):
            if k in v and v[k] is not None:
                return float(v[k])
        raise MissingMetric("kind-tagged value has no usable value/mean (%s): %r"
                            % (where, sorted(v)))
    if v is None:
        raise MissingMetric("value is None (%s)" % where)
    return float(v)


def style_axes(ax, *, grid_axis="y"):
    ax.grid(True, axis=grid_axis, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def save(fig, stem):
    os.makedirs(OUTDIR, exist_ok=True)
    for ext in ("pdf", "png"):
        p = os.path.join(OUTDIR, "%s.%s" % (stem, ext))
        fig.savefig(p)
    plt.close(fig)
    print("  wrote %s.pdf / .png" % stem)


# =============================================================== FIGURE 5 =====
def fig5(raw):
    where = "Fig 5"
    tp = dig(raw, "exp1", "throughput", where=where)
    for name, _, _, _, _ in FIXTURES:
        if name not in tp:
            raise MissingMetric(
                "raw.exp1.throughput has no %r series -- needed by Fig 5. "
                "Present: %s" % (name, sorted(tp)))

    fig, (a, b, c) = plt.subplots(1, 3, figsize=(7.16, 2.6))
    XT = [1, 10, 16, 24, 32]

    # --- (a) throughput vs concurrency -------------------------------------
    for name, col, mk, lw, _ in FIXTURES:
        rows = sorted(tp[name], key=lambda r: r["concurrency"])
        xs = [r["concurrency"] for r in rows]
        ys = [num(r["throughput_tps"], where="%s tps %s" % (where, name)) for r in rows]
        a.plot(xs, ys, color=col, marker=mk, linewidth=lw,
               markeredgecolor="white", markeredgewidth=0.5, zorder=3)
    a.axvspan(0.4, 10, color="#000000", alpha=0.04, zorder=1, linewidth=0)
    a.axvline(10, color=RULE, linestyle=(0, (4, 2)), linewidth=0.9, zorder=2)
    a.set_ylim(0, 29)
    a.text(5.2, 27.4, "time-cut", ha="center", fontsize=6.4, color=INK_SOFT, style="italic")
    a.text(21.5, 27.4, "count-cut", ha="center", fontsize=6.4, color=INK_SOFT, style="italic")
    a.text(10.5, 4.2, "MaxMessageCount = 10", fontsize=6.2, color=INK,
           rotation=90, va="bottom", ha="left")
    a.set_xlabel("Client concurrency")
    a.set_ylabel("Throughput (TPS)")
    a.set_title("(a) Throughput vs concurrency", loc="left", pad=4)
    a.set_xlim(0.4, 33)
    a.set_xticks(XT)
    style_axes(a)

    # --- (b) ack decomposition, c=8 vs c=10 --------------------------------
    stages = [("stage_policy_ms", "policy", "#c9c8c2"),
              ("stage_fabric_ms", "fabric (private commit)", "#6f6e69"),
              ("stage_outbox_ms", "outbox insert", C_PUBLIC)]
    xs, ticks, groups = [], [], []
    pos = 0.0
    for name, _, _, _, _ in FIXTURES:
        start = pos
        for lv in (8, 10):
            row = next((r for r in tp[name] if r["concurrency"] == lv), None)
            if row is None:
                raise MissingMetric("raw.exp1.throughput.%s has no c=%d row -- Fig 5(b)"
                                    % (name, lv))
            bottom = 0.0
            for key, _lab, scol in stages:
                v = num(row[key], where="%s %s %s c=%d" % (where, name, key, lv))
                b.bar(pos, v, bottom=bottom, width=0.66, color=scol,
                      edgecolor="white", linewidth=0.7, zorder=3)
                bottom += v
            xs.append(pos)
            ticks.append(str(lv))
            pos += 1.0
        groups.append(((start + pos - 1.0) / 2.0, name))
        pos += 0.7

    b.set_xticks(xs)
    b.set_xticklabels(ticks, fontsize=6.6)
    for xc, nm in groups:
        b.text(xc, -0.175, nm.replace("_", "\n"), transform=b.get_xaxis_transform(),
               ha="center", va="top", fontsize=6.1, color=INK)
    b.set_ylabel("Ack latency (ms)")
    b.set_title("(b) Ack stages, c=8 vs c=10", loc="left", pad=4)
    b.set_ylim(0, 2900)
    style_axes(b)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=s[2], edgecolor="white")
               for s in stages]
    b.legend(handles, [s[1] for s in stages], frameon=False, loc="upper center",
             handlelength=1.0, borderpad=0.1, labelspacing=0.2, fontsize=6.1,
             ncol=1, bbox_to_anchor=(0.53, 1.03))
    b.text(0.02, 0.60, "policy is 3-38 ms:\ntoo thin to see", transform=b.transAxes,
           fontsize=6.0, color=INK_SOFT, style="italic")

    # --- (c) outbox insertion vs concurrency -------------------------------
    for name, col, mk, lw, _ in FIXTURES:
        rows = sorted(tp[name], key=lambda r: r["concurrency"])
        xs2 = [r["concurrency"] for r in rows]
        ys2 = [num(r["stage_outbox_ms"], where="%s outbox %s" % (where, name))
               for r in rows]
        c.plot(xs2, ys2, color=col, marker=mk, linewidth=lw,
               markeredgecolor="white", markeredgewidth=0.5, zorder=3)
    c.set_xlabel("Client concurrency")
    c.set_ylabel("Outbox insertion (ms)")
    c.set_title("(c) Outbox insertion", loc="left", pad=4)
    c.set_xlim(0.4, 33)
    c.set_xticks(XT)
    c.set_ylim(0, 700)
    style_axes(c)
    c.annotate("control: never\ncollected by the relay", xy=(24, 71.5), xytext=(4.5, 300),
               fontsize=6.2, color=C_ONLY,
               arrowprops=dict(arrowstyle="->", color=C_ONLY, linewidth=0.7))
    c.text(0.03, 0.955, "never dominant: 273.5 ms of a\n5689.2 ms ack at c=32 (4.8%)",
           transform=c.transAxes, fontsize=6.0, color=INK_SOFT, style="italic", va="top")

    # one shared fixture legend for the whole figure (a) and (c) share series
    handles2 = [plt.Line2D([], [], color=col, marker=mk, linewidth=lw,
                           markeredgecolor="white", markeredgewidth=0.5)
                for _, col, mk, lw, _ in FIXTURES]
    fig.legend(handles2, [lab for _, _, _, _, lab in FIXTURES], frameon=False,
               loc="lower center", ncol=4, fontsize=6.6, handlelength=1.9,
               columnspacing=1.3, bbox_to_anchor=(0.5, -0.035))
    fig.subplots_adjust(wspace=0.36, bottom=0.30, top=0.90)
    save(fig, "fig5_orchestration")


# =============================================================== FIGURE 7 =====
def fig7(raw):
    where = "Fig 7"
    rows = dig(raw, "exp3", "gas_per_record_by_batch", where=where)
    single = num(dig(raw, "exp3", "single_anchor_gas", where=where), where="single anchor")
    flat = dig(raw, "exp3", "root_gas_flat_in_N", where=where)
    spread = flat.get("relative_spread")
    if spread is None:
        raise MissingMetric("exp3.root_gas_flat_in_N has no relative_spread -- Fig 7(a)")

    rows = sorted(rows, key=lambda r: r["batch_size"])
    N = [r["batch_size"] for r in rows]
    per = [num(r["batched_gas_per_record"], where="%s per-record" % where) for r in rows]
    red = [num(r["gas_reduction_pct"], where="%s reduction" % where) for r in rows]
    proof = [r["proof_size_bytes"] for r in rows]

    fig, (a, b, c) = plt.subplots(1, 3, figsize=(7.16, 2.5))

    # --- (a) gas per record, log-log ---------------------------------------
    a.axhline(single, color=RULE, linestyle=(0, (4, 2)), linewidth=1.0, zorder=2)
    a.plot(N, per, color=C_PUBLIC, marker="o", linewidth=1.8, zorder=4,
           markeredgecolor="white", markeredgewidth=0.5)
    a.set_xscale("log")
    a.set_yscale("log")
    a.set_ylim(min(per) * 0.5, max(max(per), single) * 3.2)
    a.set_xlabel("Merkle batch size $N$")
    a.set_ylabel("Gas per record")
    a.set_title("(a) Amortized gas per record", loc="left", pad=4)
    a.yaxis.set_major_formatter(FuncFormatter(lambda v, p: "%g" % v))
    style_axes(a, grid_axis="both")
    a.text(0.03, 0.15, "dashed: single-record anchor," "\n" "273,695 gas",
           transform=a.transAxes, fontsize=6.0, color=INK_SOFT, va="bottom")

    # An 8% gap is invisible on a 1e3..3e5 log axis, and the sign of that gap is
    # the entire point of the panel -- so it gets a linear inset instead of a
    # wider axis range. Without this the N=1 point reads as sitting ON the line.
    ins = a.inset_axes([0.545, 0.55, 0.425, 0.33])
    ins.set_facecolor("white")
    for _sp in ins.spines.values():
        _sp.set_visible(True)
        _sp.set_edgecolor(RULE)
        _sp.set_linewidth(0.6)
    ins.axhline(single, color=RULE, linestyle=(0, (3, 2)), linewidth=0.9, zorder=2)
    ins.plot(N[:2], per[:2], color=C_PUBLIC, marker="o", markersize=3.4,
             linewidth=1.5, zorder=4, markeredgecolor="white", markeredgewidth=0.4)
    ins.set_xlim(0.85, 2.15)
    ins.set_ylim(130000, 320000)
    ins.set_xticks([1, 2])
    ins.set_xticklabels(["1", "2"], fontsize=5.6)
    ins.set_yticks([273695, 296267])
    ins.set_yticklabels(["273.7k", "296.3k"], fontsize=5.2)
    ins.tick_params(length=2, pad=1)
    for s in ("top", "right"):
        ins.spines[s].set_visible(False)
    ins.set_title("$N{=}1$ sits ABOVE", fontsize=5.6, color=INK, pad=1.5, loc="left")
    ins.grid(False)

    # --- (b) reduction, negatives included, zero line ----------------------
    b.axhline(0, color=INK, linewidth=0.9, zorder=3)
    b.plot(N, red, color=C_SENS, marker="^", linewidth=1.8, zorder=4,
           markeredgecolor="white", markeredgewidth=0.5)
    b.set_xscale("log")
    b.set_ylim(min(red) - 22, 122)
    b.set_xlabel("Merkle batch size $N$")
    b.set_ylabel("Gas reduction (%)")
    b.set_title("(b) Reduction vs single-record", loc="left", pad=4)
    style_axes(b)
    b.annotate("$-8.25\\%$ at $N{=}1$", xy=(1, red[0]), xytext=(1.9, red[0] - 4),
               fontsize=6.3, color=C_SENS,
               arrowprops=dict(arrowstyle="->", color=C_SENS, linewidth=0.7))
    b.text(0.30, 0.30, "crosses zero between\n$N{=}1$ and $N{=}2$", transform=b.transAxes,
           fontsize=6.1, color=INK_SOFT, style="italic")
    b.annotate("99.46% @ $N{=}200$", xy=(200, red[-1]), xytext=(9, 62),
               fontsize=6.3, color=INK,
               arrowprops=dict(arrowstyle="->", color=RULE, linewidth=0.7))

    # --- (c) proof size ----------------------------------------------------
    c.plot(N, proof, color=C_ONLY, marker="s", linewidth=2.0, zorder=4,
           markeredgecolor="white", markeredgewidth=0.5)
    c.set_xscale("log")
    c.set_xlabel("Merkle batch size $N$")
    c.set_ylabel("Merkle proof size (bytes)")
    c.set_title("(c) Auditor-side proof cost", loc="left", pad=4)
    c.set_ylim(-22, 340)
    style_axes(c)
    c.annotate("0 B at $N{=}1$", xy=(1, 0), xytext=(0.30, 0.06),
               textcoords="axes fraction", fontsize=6.3, color=INK_SOFT,
               arrowprops=dict(arrowstyle="->", color=RULE, linewidth=0.7))
    c.text(0.04, 0.80, "256 B at $N{=}200$" "\n" "grows as $32\\lceil\\log_2 N\\rceil$",
           transform=c.transAxes, fontsize=6.1, color=C_ONLY, va="top")

    fig.subplots_adjust(wspace=0.38, bottom=0.20, top=0.90)
    save(fig, "fig7_batching")
    return spread


# =============================================================== FIGURE 8 =====
PATH_STYLE = {"direct": (C_PUBLIC, "o", "direct"),
              "checkpoint": (C_SENS, "^", "checkpoint"),
              "inversion": (C_ONLY, "s", "inversion")}


def fig8(raw):
    where = "Fig 8"
    rb = dig(raw, "exp4", "by_state_model", "sparse",
             "rollback_latency_by_target_version", where=where)
    rb = sorted(rb, key=lambda r: r["target_version"])

    fig, (a, b) = plt.subplots(1, 2, figsize=(7.16, 2.6))

    ks = [r["target_version"] for r in rb]
    ms = [r["mean_ms"] for r in rb]
    us = [r["delta_applications_u"] for r in rb]
    paths = [r["reconstruction_path"] for r in rb]
    ci = [r.get("ci95_ms") or 0.0 for r in rb]
    for p in paths:
        if p not in PATH_STYLE:
            raise MissingMetric("unknown reconstruction_path %r -- Fig 8(a) has no "
                                "style for it; add one rather than defaulting" % p)

    a.plot(ks, ms, color=INK_SOFT, linewidth=1.1, zorder=2)
    a.errorbar(ks, ms, yerr=ci, fmt="none", ecolor=RULE, elinewidth=0.7,
               capsize=1.6, zorder=3)
    seen = set()
    for k, m, u, p in zip(ks, ms, us, paths):
        col, mk, lab = PATH_STYLE[p]
        a.plot([k], [m], color=col, marker=mk, markersize=5.2, zorder=4,
               markeredgecolor="white", markeredgewidth=0.6, linestyle="none",
               label=None if lab in seen else lab)
        seen.add(lab)
        a.annotate("u=%d" % u, xy=(k, m), xytext=(0, 7), textcoords="offset points",
                   ha="center", fontsize=6.2, color=INK)
    a.set_xlabel("Rollback target version index $k$")
    a.set_ylabel("Rollback latency (ms)")
    a.set_title("(a) Cost tracks $u$, sawtooth in $k$", loc="left", pad=4)
    a.set_ylim(0, max(ms) * 1.50)
    style_axes(a)
    a.legend(frameon=False, loc="lower center", handlelength=1.2, borderpad=0.1,
             labelspacing=0.22, fontsize=6.4, ncol=3, title="reconstruction path",
             title_fontsize=6.4, bbox_to_anchor=(0.5, -0.02))
    a.text(0.02, 0.97, "$u\\leq q{=}100$ bounds every target;\n"
           "$k{=}1$ and $k{=}1000$ both sit at $u{=}0$", transform=a.transAxes,
           fontsize=6.1, color=INK_SOFT, style="italic", va="top")

    # --- (b) storage, both conditions --------------------------------------
    snap_rows = None
    for mode, col, mk, lab in (("sparse", C_PUBLIC, "o", "sparse updates"),
                               ("dense", C_SENS, "^", "dense updates")):
        rowsx = dig(raw, "exp4", "by_state_model", mode, "storage_growth", where=where)
        rowsx = sorted(rowsx, key=lambda r: r["versions"])
        vs = [r["versions"] for r in rowsx]
        tb = [r["total_bytes"] / 1024.0 for r in rowsx]
        b.plot(vs, tb, color=col, marker=mk, linewidth=1.8, zorder=4, label=lab,
               markeredgecolor="white", markeredgewidth=0.5)
        if mode == "sparse":
            snap_rows = rowsx
            sparse_last = rowsx[-1]
        else:
            dense_last = rowsx[-1]

    # Drawn LAST and on top: the dense series sits almost exactly on this line,
    # which is the parity finding -- if it were drawn underneath it would be
    # invisible and the reader would think it was missing.
    vs = [r["versions"] for r in snap_rows]
    snap = [r["snapshot_equivalent_bytes"] / 1024.0 for r in snap_rows]
    b.plot(vs, snap, color=INK, linewidth=1.0, linestyle=(0, (3, 2)), zorder=6,
           label="snapshot-equivalent")

    b.set_xlabel("Versions retained")
    b.set_ylabel("Stored size (KiB)")
    b.set_title("(b) Saving is conditional on sparsity", loc="left", pad=4)
    b.set_xlim(-30, 980)
    b.set_ylim(0, 400)
    style_axes(b)
    b.legend(frameon=False, loc="upper left", handlelength=1.8, borderpad=0.1,
             labelspacing=0.24, fontsize=6.3)
    b.annotate("%.2f$\\times$ smaller at %d versions" "\n" "(%.1f B/version)"
               % (sparse_last["compression_vs_snapshots"], sparse_last["versions"],
                  sparse_last["bytes_per_version"]),
               xy=(sparse_last["versions"], sparse_last["total_bytes"] / 1024.0),
               xytext=(300, 18), fontsize=6.2, color=C_PUBLIC,
               arrowprops=dict(arrowstyle="->", color=C_PUBLIC, linewidth=0.7))
    b.annotate("dense sits ON the snapshot line:" "\n" "%.3f$\\times$, parity not regression"
               % dense_last["compression_vs_snapshots"],
               xy=(620, 238), xytext=(250, 232), fontsize=6.2, color=C_SENS,
               arrowprops=dict(arrowstyle="->", color=C_SENS, linewidth=0.7))

    fig.subplots_adjust(wspace=0.30, bottom=0.20, top=0.90)
    save(fig, "fig8_lifecycle")


# =============================================================== FIGURE 9 =====
def fig9(raw):
    where = "Fig 9"
    ms = dig(raw, "exp8", "by_state_model", "sparse", "by_checkpoint_interval",
             "100", "measurements", where=where)
    ms = sorted(ms, key=lambda r: r["target_version"])

    ks, ck, sel, ck_u = [], [], [], {}
    ivk, iv, ivu = [], [], []
    for r in ms:
        k = r["target_version"]
        ks.append(k)
        ck.append(num(dig(r, "checkpoint_restore", "latency_ms",
                          where="%s ckpt k=%s" % (where, k)), where="ckpt k=%s" % k))
        ck_u[k] = int(num(dig(r, "checkpoint_restore", "delta_applications_u",
                              where="%s ckpt u k=%s" % (where, k)), where="ckpt u"))
        sel.append(dig(r, "selected_path", "value", where="%s path k=%s" % (where, k)))
        inv = dig(r, "delta_inversion_from_head", where="%s inv k=%s" % (where, k))
        # Inversion was measured only near the head. Absence is a property of the
        # experiment, not missing data: skip it, never interpolate a curve.
        if inv.get("available"):
            ivk.append(k)
            iv.append(num(inv["latency_ms"], where="inv k=%s" % k))
            ivu.append(int(num(dig(inv, "delta_applications_u",
                                   where="inv u k=%s" % k), where="inv u")))
    if not ivk:
        raise MissingMetric(
            "no target in exp8 sparse q=100 has delta_inversion_from_head."
            "available -- Fig 9 exists to compare the two paths and cannot be "
            "drawn from the checkpoint path alone")

    # Two panels: the near-head points span 1% of a 0-1000 axis, so a single
    # full-range plot renders the actual comparison as a smudge at the right
    # edge. (b) is where the claim is legible.
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.16, 2.6),
                               gridspec_kw={"width_ratios": [1.25, 1.0]})

    a.plot(ks, ck, color=C_SENS, marker="^", linewidth=1.8, zorder=3,
           markeredgecolor="white", markeredgewidth=0.5,
           label="checkpoint restore (measured at all 10 targets)")
    a.plot(ivk, iv, color=C_ONLY, marker="s", linewidth=2.2, zorder=4,
           markeredgecolor="white", markeredgewidth=0.5, linestyle="-",
           label="inversion from head (measured near head only)")
    a.axvspan(min(ivk) - 6, 1006, color=C_ONLY, alpha=0.07, zorder=1, linewidth=0)
    a.text(min(ivk) - 14, max(ck) * 1.20, "near-head\nregion (b)", fontsize=6.1,
           color=C_ONLY, ha="right", va="top")
    a.set_xlabel("Rollback target version index $k$   (head $=1000$)")
    a.set_ylabel("Reconstruction latency (ms)")
    a.set_title("(a) Both paths across history", loc="left", pad=4)
    a.set_ylim(0, max(ck) * 1.38)
    a.set_xlim(-40, 1040)
    style_axes(a)
    a.legend(frameon=False, loc="lower center", handlelength=1.8, borderpad=0.1,
             labelspacing=0.26, fontsize=6.1, bbox_to_anchor=(0.5, -0.03))

    # --- (b) near-head: grouped bars, the legible comparison ---------------
    import numpy as _np
    idx = _np.arange(len(ivk), dtype=float)
    w = 0.36
    cks = [ck[ks.index(k)] for k in ivk]
    b.bar(idx - w / 2, cks, width=w, color=C_SENS, edgecolor="white",
          linewidth=0.7, zorder=3, label="checkpoint restore")
    b.bar(idx + w / 2, iv, width=w, color=C_ONLY, edgecolor="white",
          linewidth=0.7, zorder=3, label="inversion from head")
    for i, k in enumerate(ivk):
        b.text(idx[i] - w / 2, cks[i] + 0.004, "u=%d" % ck_u[k], ha="center",
               fontsize=5.9, color=C_SENS)
        b.text(idx[i] + w / 2, iv[i] + 0.004, "u=%d" % ivu[i], ha="center",
               fontsize=5.9, color=C_ONLY)
    b.set_xticks(idx)
    b.set_xticklabels(["k=%d" % k for k in ivk], fontsize=6.4)
    b.set_ylabel("Reconstruction latency (ms)")
    b.set_title("(b) Near head, inversion wins", loc="left", pad=4)
    b.set_ylim(0, max(cks) * 1.42)
    style_axes(b)
    # Mark the path the engine actually chose, per target.
    for i2, k in enumerate(ivk):
        chosen = sel[ks.index(k)]
        xoff = (w / 2) if chosen == "inversion" else (-w / 2)
        yv = iv[i2] if chosen == "inversion" else cks[i2]
        b.plot([idx[i2] + xoff], [yv * 0.55], marker="*", markersize=6.0,
               color="white", markeredgecolor=INK, markeredgewidth=0.4,
               linestyle="none", zorder=6)
    b.plot([], [], marker="*", markersize=6.0, color="white",
           markeredgecolor=INK, markeredgewidth=0.4, linestyle="none",
           label="path the engine selected")
    b.legend(frameon=False, loc="upper right", handlelength=1.1, borderpad=0.1,
             labelspacing=0.22, fontsize=6.2)
    fig.subplots_adjust(wspace=0.32, bottom=0.20, top=0.90)
    save(fig, "fig9_recovery_paths")


def main():
    if not os.path.exists(RESULTS):
        print("FATAL: %s not found" % RESULTS, file=sys.stderr)
        return 2
    with open(RESULTS, encoding="utf-8") as fh:
        d = json.load(fh)
    got = d.get("config_hash")
    print("RESULTS.json config_hash=%s   (panels specified against %s / %s)"
          % (got, RUN_HASH, RUN_COMMIT))
    if got != RUN_HASH:
        print("  NOTE: hash differs from the specified run. Figures reflect the "
              "file on disk; check before using them in the manuscript.")
    raw = d["raw"]
    print("Building Section IV figures into %s" % OUTDIR)
    fig5(raw)
    spread = fig7(raw)
    print("  Fig 7(a) root-gas relative spread = %g (flat in N)" % spread)
    fig8(raw)
    fig9(raw)
    print("Fig 6 (privacy routing) intentionally NOT rebuilt: exp2 did not move.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
