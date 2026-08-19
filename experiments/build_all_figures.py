#!/usr/bin/env python3
"""Section IV figures for IEEE IoT-J. Rebuilt 2026-08-19 (v2).

Target: single-column, 88.9 mm (3.5 in). Panels stack vertically.

House rules, applied uniformly:
  * NOTHING inside the axes except data, axis labels, tick labels and a legend.
    Every value, threshold and interpretation lives in CAPTIONS.md. The previous
    revision pushed prose into the panels -- three italic notes, eight arrow
    callouts, a rotated gridline label -- which read as slide annotation, not a
    journal figure.
  * Grayscale-safe by construction: every series carries colour AND line style
    AND marker, so identity survives with no colour at all. Bar fills are
    separated by luminance, not hue.
  * Thin marks: 1.0 pt lines, 3.2 pt markers, 0.5 pt spines. Sized for print at
    88.9 mm, not for screen.
  * No mathtext backslashes anywhere in this file, deliberately: LaTeX escapes in
    non-raw strings silently corrupted labels in the previous revision
    (\times rendered as a tab). Symbols that need typesetting live in the caption.

Structural changes from v1, not restyling:
  * Fig 5(b) is GROUPED bars on a log y-axis, not stacked. A 3 ms policy stage
    against a 2300 ms fabric stage cannot be seen in a stack; on log axes all
    three stages are legible, which is the point of the panel.
  * Fig 9 drops its full-range panel. It duplicated Fig 8(a) and its near-head
    region was a 1%-wide shaded sliver. Fig 9 is now the near-head comparison
    alone, which is the result.

Data source: RESULTS.json only. dig() raises naming the path it could not
resolve; nothing is defaulted.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(_REPO, "experiments", "results", "RESULTS.json")
OUTDIR = os.path.join(_REPO, "experiments", "results", "figures_section4")

RUN_COMMIT = "d8ce50b9"
RUN_HASH = "bb85df0d7803"

COL = 3.5                      # IEEE single column, inches

INK = "#111111"
INK_SOFT = "#555555"
GRID = "#dddddd"
RULE = "#888888"

# colour + style + marker: any one of the three identifies the series
FIXTURES = [
    ("all_public",    "#2a78d6", "o", "-"),
    ("all_sensitive", "#eb6834", "^", "--"),
    ("mixed",         "#1baf7a", "D", "-."),
    ("fabric_only",   "#4a3aa7", "s", ":"),
]
# stage fills separated by luminance so they survive grayscale
STAGE_FILL = {"policy": "#e8e8e6", "fabric": "#9a9a95", "outbox": "#3c3c39"}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman", "Nimbus Roman"],
    "font.size": 7,
    "axes.labelsize": 7,
    "axes.titlesize": 7,
    "xtick.labelsize": 6.2,
    "ytick.labelsize": 6.2,
    "legend.fontsize": 6.0,
    "axes.edgecolor": RULE,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK_SOFT,
    "ytick.color": INK_SOFT,
    "axes.linewidth": 0.5,
    "grid.color": GRID,
    "grid.linewidth": 0.4,
    "lines.linewidth": 1.0,
    "lines.markersize": 3.2,
    "xtick.major.width": 0.5,
    "ytick.major.width": 0.5,
    "xtick.major.size": 2.2,
    "ytick.major.size": 2.2,
    "figure.dpi": 200,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.015,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


class MissingMetric(KeyError):
    """RESULTS.json lacks something a panel needs."""


def dig(node, *path, where=""):
    cur, walked = node, []
    for p in path:
        walked.append(str(p))
        try:
            cur = cur[p]
        except (KeyError, IndexError, TypeError):
            raise MissingMetric(
                "RESULTS.json is missing %r (resolved %s) -- needed by %s. "
                "Not defaulting." % (p, " -> ".join(walked), where or "a panel"))
    return cur


def num(v, *, where=""):
    if isinstance(v, dict):
        for k in ("value", "mean"):
            if k in v and v[k] is not None:
                return float(v[k])
        raise MissingMetric("no usable value/mean (%s)" % where)
    if v is None:
        raise MissingMetric("value is None (%s)" % where)
    return float(v)


def axes_style(ax, grid_axis="y"):
    ax.grid(True, axis=grid_axis, zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def panel_tag(ax, tag):
    """(a)/(b)/(c) above the axes, left-aligned. The only text we allow."""
    ax.set_title(tag, loc="left", pad=3, fontsize=7, color=INK)


def save(fig, stem):
    os.makedirs(OUTDIR, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUTDIR, "%s.%s" % (stem, ext)))
    plt.close(fig)
    print("  wrote %s.pdf / .png" % stem)


# =============================================================== FIGURE 5 =====
def fig5(raw):
    where = "Fig 5"
    tp = dig(raw, "exp1", "throughput", where=where)
    for name, _, _, _ in FIXTURES:
        if name not in tp:
            raise MissingMetric("raw.exp1.throughput has no %r -- Fig 5. Present: %s"
                                % (name, sorted(tp)))

    fig, (a, b, c) = plt.subplots(3, 1, figsize=(COL, 5.35),
                                  gridspec_kw={"height_ratios": [1.0, 0.82, 1.0]})
    XT = [1, 8, 16, 24, 32]

    # --- (a) throughput -----------------------------------------------------
    for name, col, mk, ls in FIXTURES:
        rows = sorted(tp[name], key=lambda r: r["concurrency"])
        a.plot([r["concurrency"] for r in rows],
               [num(r["throughput_tps"], where=where) for r in rows],
               color=col, marker=mk, linestyle=ls, label=name,
               markeredgecolor="white", markeredgewidth=0.35, zorder=3)
    a.axvline(10, color=RULE, linestyle=(0, (2.5, 2)), linewidth=0.6, zorder=2)
    a.set_xlabel("Client concurrency")
    a.set_ylabel("Throughput (TPS)")
    a.set_xlim(0, 33.5)
    a.set_xticks(XT)
    a.set_ylim(0, 27)
    panel_tag(a, "(a)")
    axes_style(a)
    a.legend(frameon=False, loc="upper left", handlelength=2.2, borderpad=0.0,
             labelspacing=0.18, handletextpad=0.5, borderaxespad=0.2)

    # --- (b) stage decomposition, grouped on log y --------------------------
    # Grouped, not stacked: the policy stage is three orders of magnitude below
    # the fabric stage, so a stack hides it entirely.
    stages = ("policy", "fabric", "outbox")
    keys = {"policy": "stage_policy_ms", "fabric": "stage_fabric_ms",
            "outbox": "stage_outbox_ms"}
    levels = (8, 10)
    w = 0.28
    for gi, lv in enumerate(levels):
        row = next((r for r in tp["mixed"] if r["concurrency"] == lv), None)
        if row is None:
            raise MissingMetric("no c=%d row for mixed -- Fig 5(b)" % lv)
        for si, st in enumerate(stages):
            v = num(row[keys[st]], where="%s %s c=%d" % (where, st, lv))
            b.bar(gi + (si - 1) * w, v, width=w, color=STAGE_FILL[st],
                  edgecolor=INK, linewidth=0.4, zorder=3,
                  label=st if gi == 0 else None)
    b.set_yscale("log")
    b.set_xticks(list(range(len(levels))))
    b.set_xticklabels(["c = %d" % lv for lv in levels])
    b.set_xlim(-0.55, 1.55)
    b.set_ylabel("Stage latency (ms)")
    b.set_ylim(1, 14000)
    panel_tag(b, "(b)")
    axes_style(b)
    b.yaxis.set_major_formatter(FuncFormatter(lambda v, p: "%g" % v))
    b.legend(frameon=False, loc="upper center", handlelength=1.1, borderpad=0.0,
             labelspacing=0.18, handletextpad=0.4, borderaxespad=0.15, ncol=3,
             columnspacing=0.8)

    # --- (c) outbox insertion ----------------------------------------------
    for name, col, mk, ls in FIXTURES:
        rows = sorted(tp[name], key=lambda r: r["concurrency"])
        c.plot([r["concurrency"] for r in rows],
               [num(r["stage_outbox_ms"], where=where) for r in rows],
               color=col, marker=mk, linestyle=ls, label=name,
               markeredgecolor="white", markeredgewidth=0.35, zorder=3)
    c.set_xlabel("Client concurrency")
    c.set_ylabel("Outbox insertion (ms)")
    c.set_xlim(0, 33.5)
    c.set_xticks(XT)
    c.set_ylim(0, 640)
    panel_tag(c, "(c)")
    axes_style(c)
    c.legend(frameon=False, loc="upper left", handlelength=2.2, borderpad=0.0,
             labelspacing=0.18, handletextpad=0.5, borderaxespad=0.2)

    fig.subplots_adjust(hspace=0.52)
    save(fig, "fig5_orchestration")


# =============================================================== FIGURE 7 =====
def fig7(raw):
    where = "Fig 7"
    rows = dig(raw, "exp3", "gas_per_record_by_batch", where=where)
    single = num(dig(raw, "exp3", "single_anchor_gas", where=where), where="single")
    flat = dig(raw, "exp3", "root_gas_flat_in_N", where=where)
    spread = flat.get("relative_spread")
    if spread is None:
        raise MissingMetric("exp3.root_gas_flat_in_N lacks relative_spread -- Fig 7")

    rows = sorted(rows, key=lambda r: r["batch_size"])
    N = [r["batch_size"] for r in rows]
    per = [num(r["batched_gas_per_record"], where=where) for r in rows]
    red = [num(r["gas_reduction_pct"], where=where) for r in rows]
    proof = [r["proof_size_bytes"] for r in rows]

    fig, (a, b, c) = plt.subplots(3, 1, figsize=(COL, 5.55))

    # (a) The dashed baseline is the single-record anchor. The N=1 point lying
    # ABOVE it is the panel's claim; the sign is quantified in (b) and stated in
    # the caption, so no inset or callout is needed here.
    a.axhline(single, color=RULE, linestyle=(0, (2.5, 2)), linewidth=0.7, zorder=2)
    a.plot(N, per, color="#2a78d6", marker="o", linestyle="-", zorder=4,
           markeredgecolor="white", markeredgewidth=0.35)
    a.set_xscale("log")
    a.set_yscale("log")
    a.set_ylim(1000, 700000)
    a.set_xlabel("Merkle batch size $N$")
    a.set_ylabel("Gas per record")
    a.yaxis.set_major_formatter(FuncFormatter(lambda v, p: "%g" % v))
    panel_tag(a, "(a)")
    axes_style(a, grid_axis="both")

    # (b) carries the sign: negative at N=1, crossing zero before N=2.
    b.axhline(0, color=INK, linewidth=0.6, zorder=3)
    b.plot(N, red, color="#eb6834", marker="^", linestyle="--", zorder=4,
           markeredgecolor="white", markeredgewidth=0.35)
    b.set_xscale("log")
    b.set_ylim(-20, 112)
    b.set_xlabel("Merkle batch size $N$")
    b.set_ylabel("Gas reduction (%)")
    panel_tag(b, "(b)")
    axes_style(b)

    # (c) auditor-side cost, the counterweight to (a).
    c.plot(N, proof, color="#4a3aa7", marker="s", linestyle=":", zorder=4,
           markeredgecolor="white", markeredgewidth=0.35)
    c.set_xscale("log")
    c.set_ylim(-14, 288)
    c.set_xlabel("Merkle batch size $N$")
    c.set_ylabel("Proof size (bytes)")
    panel_tag(c, "(c)")
    axes_style(c)

    fig.subplots_adjust(hspace=0.55)
    save(fig, "fig7_batching")
    return spread


# =============================================================== FIGURE 8 =====
PATH_STYLE = {"direct":     ("#2a78d6", "o"),
              "checkpoint": ("#eb6834", "^"),
              "inversion":  ("#4a3aa7", "s")}


def fig8(raw):
    where = "Fig 8"
    rb = dig(raw, "exp4", "by_state_model", "sparse",
             "rollback_latency_by_target_version", where=where)
    rb = sorted(rb, key=lambda r: r["target_version"])
    for r in rb:
        if r["reconstruction_path"] not in PATH_STYLE:
            raise MissingMetric("no style for reconstruction_path %r -- Fig 8(a)"
                                % r["reconstruction_path"])

    fig, (a, b) = plt.subplots(2, 1, figsize=(COL, 3.9))

    ks = [r["target_version"] for r in rb]
    ms = [r["mean_ms"] for r in rb]
    ci = [r.get("ci95_ms") or 0.0 for r in rb]

    # The sawtooth is the claim. u per point is listed in the caption rather than
    # printed on seven markers.
    a.plot(ks, ms, color=INK_SOFT, linewidth=0.8, linestyle="-", zorder=2)
    a.errorbar(ks, ms, yerr=ci, fmt="none", ecolor=RULE, elinewidth=0.5,
               capsize=1.2, zorder=3)
    seen = set()
    for r in rb:
        col, mk = PATH_STYLE[r["reconstruction_path"]]
        lab = r["reconstruction_path"]
        a.plot([r["target_version"]], [r["mean_ms"]], color=col, marker=mk,
               linestyle="none", markersize=3.6, markeredgecolor="white",
               markeredgewidth=0.4, zorder=4,
               label=None if lab in seen else lab)
        seen.add(lab)
    a.set_xlabel("Rollback target version index $k$")
    a.set_ylabel("Rollback latency (ms)")
    a.set_ylim(0, 0.30)
    a.set_xlim(-40, 1040)
    panel_tag(a, "(a)")
    axes_style(a)
    a.legend(frameon=False, loc="lower right", handlelength=1.0, borderpad=0.0,
             labelspacing=0.18, handletextpad=0.5, borderaxespad=0.2, ncol=3,
             columnspacing=0.8)

    # (b) both conditions plus the snapshot baseline. Dense lies on the baseline;
    # the baseline is drawn last so it stays visible.
    snap_rows = None
    for mode, col, mk, ls in (("sparse", "#2a78d6", "o", "-"),
                              ("dense", "#eb6834", "^", "--")):
        rowsx = sorted(dig(raw, "exp4", "by_state_model", mode, "storage_growth",
                           where=where), key=lambda r: r["versions"])
        b.plot([r["versions"] for r in rowsx],
               [r["total_bytes"] / 1024.0 for r in rowsx],
               color=col, marker=mk, linestyle=ls, label=mode,
               markeredgecolor="white", markeredgewidth=0.35, zorder=4)
        if mode == "sparse":
            snap_rows = rowsx
    b.plot([r["versions"] for r in snap_rows],
           [r["snapshot_equivalent_bytes"] / 1024.0 for r in snap_rows],
           color=INK, linewidth=0.7, linestyle=(0, (2.5, 2)), zorder=6,
           label="snapshot-equivalent")
    b.set_xlabel("Versions retained")
    b.set_ylabel("Stored size (KiB)")
    b.set_xlim(-25, 840)
    b.set_ylim(0, 340)
    panel_tag(b, "(b)")
    axes_style(b)
    b.legend(frameon=False, loc="upper left", handlelength=2.2, borderpad=0.0,
             labelspacing=0.18, handletextpad=0.5, borderaxespad=0.2)

    fig.subplots_adjust(hspace=0.60)
    save(fig, "fig8_lifecycle")


# =============================================================== FIGURE 9 =====
def fig9(raw):
    """Near-head comparison only.

    v1 had a full-range panel (a) as well; it duplicated Fig 8(a)'s sawtooth and
    reduced the actual comparison to four points inside 1% of the x-range. The
    near-head region IS the result, so it is the whole figure.
    """
    where = "Fig 9"
    ms = sorted(dig(raw, "exp8", "by_state_model", "sparse",
                    "by_checkpoint_interval", "100", "measurements", where=where),
                key=lambda r: r["target_version"])

    ks, ck, iv = [], [], []
    for r in ms:
        inv = dig(r, "delta_inversion_from_head", where=where)
        # Inversion was measured only near the head; absence is a property of the
        # experiment, so those targets are simply not in this figure.
        if not inv.get("available"):
            continue
        k = r["target_version"]
        ks.append(k)
        ck.append(num(dig(r, "checkpoint_restore", "latency_ms", where=where),
                      where="ckpt k=%s" % k))
        iv.append(num(inv["latency_ms"], where="inv k=%s" % k))
    if not ks:
        raise MissingMetric("no target has delta_inversion_from_head.available -- "
                            "Fig 9 compares two paths and cannot be drawn from one")

    fig, ax = plt.subplots(figsize=(COL, 2.15))
    idx = list(range(len(ks)))
    w = 0.34
    ax.bar([i - w / 2 for i in idx], ck, width=w, color=STAGE_FILL["policy"],
           edgecolor=INK, linewidth=0.45, zorder=3, label="checkpoint restore")
    ax.bar([i + w / 2 for i in idx], iv, width=w, color=STAGE_FILL["fabric"],
           edgecolor=INK, linewidth=0.45, zorder=3, label="inversion from head")
    ax.set_xticks(idx)
    ax.set_xticklabels(["%d" % k for k in ks])
    ax.set_xlabel("Rollback target version index $k$")
    ax.set_ylabel("Reconstruction (ms)")
    ax.set_ylim(0, max(ck) * 1.32)
    axes_style(ax)
    ax.legend(frameon=False, loc="upper left", handlelength=1.1, borderpad=0.0,
              labelspacing=0.18, handletextpad=0.5, borderaxespad=0.2)
    save(fig, "fig9_recovery_paths")


def main():
    if not os.path.exists(RESULTS):
        print("FATAL: %s not found" % RESULTS, file=sys.stderr)
        return 2
    with open(RESULTS, encoding="utf-8") as fh:
        d = json.load(fh)
    got = d.get("config_hash")
    print("RESULTS.json config_hash=%s   (expected %s / %s)"
          % (got, RUN_HASH, RUN_COMMIT))
    if got != RUN_HASH:
        print("  NOTE: hash differs from the run these panels were specified "
              "against. Figures reflect the file on disk.")
    raw = d["raw"]
    print("Building single-column Section IV figures into %s" % OUTDIR)
    fig5(raw)
    spread = fig7(raw)
    print("  Fig 7(a) root-gas relative spread = %g" % spread)
    fig8(raw)
    fig9(raw)
    print("Fig 6 (privacy routing) not rebuilt: exp2 did not move.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
