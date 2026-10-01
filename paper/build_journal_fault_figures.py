#!/usr/bin/env python3
"""Build publication-quality Figures 8 and 9 from consolidated v2 metrics."""

import argparse
import json
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


MM = 1 / 25.4
DOUBLE = 190 * MM
COLORS = {1: "#0072B2", 2: "#D55E00", 3: "#009E73"}
MARKERS = {1: "o", 2: "s", 3: "^"}
FAULTS = ["after_broadcast", "after_receipt", "mid_poll", "sigkill"]
FAULT_LABELS = ["After\nbroadcast", "After\nreceipt", "Mid-poll", "SIGKILL"]


def configure_style():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.titlesize": 8.5,
            "axes.labelsize": 8,
            "legend.fontsize": 7.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": "#D9D9D9",
            "grid.linewidth": 0.55,
            "axes.axisbelow": True,
            "lines.linewidth": 1.6,
            "lines.markersize": 4.5,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def load_metrics(path):
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return {entry["metric"]: entry for entry in payload["metrics"]}


def save(fig, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    for extension in ("pdf", "png"):
        fig.savefig(os.path.join(outdir, f"{name}.{extension}"), dpi=400)
    plt.close(fig)


def relay_figure(metrics, outdir):
    pattern = re.compile(r"ws3_mu_relay_k([123])_(lease|race)_lambda([0-9.]+)$")
    parsed = []
    for key, entry in metrics.items():
        match = pattern.fullmatch(key)
        if match:
            parsed.append(
                (
                    int(match.group(1)),
                    match.group(2),
                    float(match.group(3)),
                    float(entry["value"]),
                    float(entry.get("ci95_half") or 0),
                )
            )

    fig, axes = plt.subplots(1, 2, figsize=(DOUBLE, 68 * MM), sharey=True)
    for ax, mode in zip(axes, ("lease", "race")):
        for workers in (1, 2, 3):
            points = sorted(row for row in parsed if row[0] == workers and row[1] == mode)
            if not points:
                continue
            x = [row[2] for row in points]
            y = [row[3] for row in points]
            err = [row[4] for row in points]
            ax.errorbar(
                x,
                y,
                yerr=err,
                color=COLORS[workers],
                marker=MARKERS[workers],
                linestyle="-",
                capsize=2.5,
                elinewidth=0.8,
                markeredgecolor="white",
                markeredgewidth=0.45,
                label=f"$k={workers}$",
            )
        ax.set_title(f"({'a' if mode == 'lease' else 'b'}) {mode.capitalize()} coordination", loc="left")
        ax.set_xlabel(r"Offered rate $\lambda$ (rows s$^{-1}$)")
        if mode == "lease":
            ax.set_xlim(1.3, 16.7)
            ax.set_xticks([2, 4, 8, 16])
        else:
            ax.set_xlim(7.3, 16.7)
            ax.set_xticks([8, 16])
        ax.set_ylim(1.5, 6.4)
    axes[0].set_ylabel(r"Drain rate $\mu_{\mathrm{relay}}$ (anchors s$^{-1}$)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Relays", frameon=False, ncol=3,
               loc="lower center", bbox_to_anchor=(0.5, -0.01))
    fig.subplots_adjust(wspace=0.12, bottom=0.25)
    save(fig, outdir, "fig_mu_relay")


def fault_figure(metrics, outdir):
    fig, (left, right) = plt.subplots(1, 2, figsize=(DOUBLE, 67 * MM))
    x = np.arange(len(FAULTS))
    offsets = [-0.27, -0.09, 0.09, 0.27]
    series = [(2, "lease"), (2, "race"), (3, "lease"), (3, "race")]
    linestyles = {"lease": "-", "race": "--"}

    for offset, (workers, mode) in zip(offsets, series):
        values, errors = [], []
        for fault in FAULTS:
            entry = metrics[f"ws3_fault_k{workers}_{mode}_{fault}_time_to_recovery_s"]
            values.append(float(entry["value"]))
            errors.append(float(entry.get("ci95_half") or 0))
        left.errorbar(
            x + offset,
            values,
            yerr=errors,
            color=COLORS[workers],
            marker=MARKERS[workers],
            linestyle=linestyles[mode],
            capsize=2.4,
            elinewidth=0.8,
            markerfacecolor="white" if mode == "race" else COLORS[workers],
            markeredgewidth=0.9,
            label=f"$k={workers}$, {mode}",
        )

    left.set_title("(a) Recovery after relay crash", loc="left")
    left.set_ylabel("End-to-end recovery time (s)")
    left.set_xticks(x, FAULT_LABELS)
    left.set_ylim(4, 31)
    left.legend(frameon=False, ncol=2, loc="lower left")

    width = 0.34
    for index, workers in enumerate((2, 3)):
        values = [
            float(metrics[f"ws3_fault_k{workers}_race_{fault}_reverted_txs"]["value"])
            for fault in FAULTS
        ]
        right.bar(
            x + (index - 0.5) * width,
            values,
            width=width,
            color=COLORS[workers],
            edgecolor="white",
            linewidth=0.7,
            label=f"$k={workers}$ race",
        )
    right.axhline(0, color="#555555", linewidth=0.7)
    right.set_title("(b) Cost of uncoordinated race mode", loc="left")
    right.set_ylabel("Reverted transactions (count)")
    right.set_xticks(x, FAULT_LABELS)
    right.legend(frameon=False, loc="upper left")

    fig.subplots_adjust(wspace=0.24)
    save(fig, outdir, "fig_fault_injection")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True, help="Path to results/v2/RESULTS.json")
    parser.add_argument("--outdir", required=True, help="Directory for PDF and PNG outputs")
    args = parser.parse_args()
    configure_style()
    metrics = load_metrics(args.results)
    relay_figure(metrics, args.outdir)
    fault_figure(metrics, args.outdir)


if __name__ == "__main__":
    main()
