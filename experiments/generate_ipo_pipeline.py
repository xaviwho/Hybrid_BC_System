#!/usr/bin/env python3
"""HADC framework — IPO pipeline diagram generation."""

import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch

np.random.seed(42)

OUT = "experiments/results/methodology_figures"
os.makedirs(OUT, exist_ok=True)


def draw_ipo(fig, ax):
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_aspect('auto')
    ax.axis('off')

    # ---- Column definitions: white interiors, deep saturated borders ----
    col1 = dict(x=2,  w=22, ec='#0D47A1',
                head_fc='#0D47A1', head_tc='white', title='INPUTS')
    col2 = dict(x=29, w=42, ec='#4A148C',
                head_fc='#4A148C', head_tc='white',
                title='PROCESSING PIPELINE')
    col3 = dict(x=76, w=22, ec='#1B5E20',
                head_fc='#1B5E20', head_tc='white', title='OUTPUTS')

    BOX_Y_BOTTOM = 4
    BOX_Y_TOP = 96
    HEADER_H = 13    # bigger header band

    def draw_box(col):
        # Outer rounded box — WHITE interior with thick colored border
        outer = FancyBboxPatch(
            (col['x'], BOX_Y_BOTTOM),
            col['w'], BOX_Y_TOP - BOX_Y_BOTTOM,
            boxstyle='round,pad=0.4,rounding_size=2.0',
            linewidth=3.5, facecolor='white', edgecolor=col['ec'],
            zorder=2)
        ax.add_patch(outer)
        # Header band — solid dark color, white text, BIG
        header = FancyBboxPatch(
            (col['x'] + 0.3, BOX_Y_TOP - HEADER_H),
            col['w'] - 0.6, HEADER_H,
            boxstyle='round,pad=0.2,rounding_size=1.5',
            linewidth=0, facecolor=col['head_fc'], zorder=3)
        ax.add_patch(header)
        ax.text(col['x'] + col['w'] / 2, BOX_Y_TOP - HEADER_H / 2,
                col['title'], fontsize=20, color=col['head_tc'],
                ha='center', va='center', zorder=4, fontweight='bold')

    draw_box(col1)
    draw_box(col2)
    draw_box(col3)

    # ---------- INPUTS column items — tight vertical packing ----------
    # Inputs actually consumed by the measured experiments. See DATA_SOURCES.md.
    # REMOVED (Phase 2, Change 6): 'FlexSim Simulation Traces' — zero FlexSim
    # events ever entered the pipeline; no FlexSim file exists in the repo.
    # REMOVED: 'IIoT Operational (HAI, BATADAL, ICS-Flow)' — those CSVs are on
    # disk under sample-data/ but no canonical experiment reads them; the only
    # consumer is the superseded synthetic exp7_hadc_compression.py.
    # REMOVED: 'Failure Injection Events' — no fault-injection harness exists.
    inputs = [
        ('#FF6F00', 'IoT Telemetry Streams', '(synthetic, exp1)'),
        ('#2E7D32', 'DT State Updates', '(twin_manager, exp4/7/8)'),
        ('#1565C0', 'Curated Policy Records', '(13 cases, exp2)'),
    ]
    items_top = BOX_Y_TOP - HEADER_H - 5
    items_bot = BOX_Y_BOTTOM + 5
    ys = np.linspace(items_top, items_bot, len(inputs))

    for (color, label, sublabel), y in zip(inputs, ys):
        cx = col1['x'] + 2.5
        circ = Circle((cx, y), 1.8, facecolor=color, edgecolor='black',
                      linewidth=1.2, zorder=5)
        ax.add_patch(circ)
        ax.text(cx + 3, y + (1.6 if sublabel else 0),
                label, fontsize=13, color='#0D1B5E',
                ha='left', va='center', zorder=5, fontweight='bold')
        if sublabel:
            ax.text(cx + 3, y - 2.0, sublabel, fontsize=11,
                    color='#1A237E', ha='left', va='center',
                    zorder=5, fontweight='bold', style='italic')

    # ---------- PROCESS column stages — tight ----------
    stages = [
        ('#1565C0', 'Ingestion + ID',
         'id = H(x || t0)   [Eq.1]'),
        ('#E65100', 'ML Privacy Routing',
         'Route: Fabric or Ethereum'),
        ('#2E7D32', 'Concurrent Fabric Commit',
         'T_commit = endorse + order + validate   [Eq.5]'),
        ('#C62828', 'Merkle-Batched Anchoring',
         'R = MerkleRoot{h_i}   [Eq.3]'),
        ('#6A1B9A', 'HADC Delta Compression',
         'UCB1 policy pi_c per class   [Eq.14]'),
        ('#00838F', 'Checkpoint Versioning',
         'E[T_rb] = T_verify + u * T_delta   [Eq.11]'),
    ]

    s_top = BOX_Y_TOP - HEADER_H - 5
    s_bot = BOX_Y_BOTTOM + 4
    n_s = len(stages)
    ys_s = np.linspace(s_top, s_bot, n_s)
    row_gap = (s_top - s_bot) / (n_s - 1)

    for i, ((color, lbl, eq), y) in enumerate(zip(stages, ys_s)):
        bx = col2['x'] + 3
        # Number badge — bold border
        badge = Circle((bx, y), 2.6, facecolor=color, edgecolor='black',
                       linewidth=1.2, zorder=5)
        ax.add_patch(badge)
        ax.text(bx, y, str(i + 1), fontsize=15, color='white',
                ha='center', va='center', fontweight='bold', zorder=6)

        # Main label — BOLD
        ax.text(bx + 5, y + 1.7, lbl, fontsize=13, color='#0D1B5E',
                ha='left', va='center', zorder=5, fontweight='bold')
        # Equation reference — bold italic
        ax.text(bx + 5, y - 2.0, eq, fontsize=11, color='#37474F',
                ha='left', va='center', zorder=5,
                fontweight='bold', style='italic')

        # Separator between rows
        if i < n_s - 1:
            sep_y = y - row_gap / 2
            ax.plot([col2['x'] + 1.8, col2['x'] + col2['w'] - 1.8],
                    [sep_y, sep_y], color='#9C27B0', linewidth=1,
                    alpha=0.5, zorder=3)

    # ---------- OUTPUTS column items ----------
    outputs = [
        ('#2E7D32', 'Committed Fabric State'),
        ('#FF6F00', 'Ethereum Audit Anchors'),
        ('#6A1B9A', 'Compressed Delta Logs'),
        ('#1565C0', 'Recoverable Version Chain'),
        ('#C62828', 'Exactly-Once Guarantees'),
    ]
    ys_o = np.linspace(items_top, items_bot, len(outputs))
    for (color, lbl), y in zip(outputs, ys_o):
        cx = col3['x'] + 2.5
        circ = Circle((cx, y), 1.8, facecolor=color, edgecolor='black',
                      linewidth=1.2, zorder=5)
        ax.add_patch(circ)
        ax.text(cx + 3, y, lbl, fontsize=13, color='#0D3D14',
                ha='left', va='center', zorder=5, fontweight='bold')

    # ---------- Arrows ----------
    def draw_arrow(x_start, x_end, label):
        y_arrow = (BOX_Y_TOP + BOX_Y_BOTTOM) / 2 - 6
        # Thick dark arrow
        arrow = FancyArrowPatch(
            (x_start, y_arrow), (x_end, y_arrow),
            arrowstyle='-|>', mutation_scale=42,
            color='#263238', linewidth=5, zorder=3)
        ax.add_patch(arrow)
        # Label pill — placed clearly ABOVE the arrow
        cx = (x_start + x_end) / 2
        pill_w = 4.6
        pill_h = 8
        pill = FancyBboxPatch(
            (cx - pill_w / 2, y_arrow + 4), pill_w, pill_h,
            boxstyle='round,pad=0.2,rounding_size=0.8',
            linewidth=2, facecolor='white', edgecolor='#263238',
            zorder=5)
        ax.add_patch(pill)
        ax.text(cx, y_arrow + 8, label, fontsize=10,
                color='#263238', ha='center', va='center',
                zorder=6, fontweight='bold')

    draw_arrow(col1['x'] + col1['w'] + 0.3,
               col2['x'] - 0.3, 'state\ntransitions')
    draw_arrow(col2['x'] + col2['w'] + 0.3,
               col3['x'] - 0.3, 'verified\noutputs')


def main():
    print("=" * 60)
    print("  IPO Pipeline Figure Generation")
    print("=" * 60)

    fig, ax = plt.subplots(figsize=(16, 5.5))
    fig.patch.set_facecolor('white')
    draw_ipo(fig, ax)

    plt.tight_layout(pad=0.5)
    p_png = os.path.join(OUT, "fig_ipo_pipeline.png")
    p_pdf = os.path.join(OUT, "fig_ipo_pipeline.pdf")
    fig.savefig(p_png, dpi=300, bbox_inches='tight', facecolor='white')
    fig.savefig(p_pdf, bbox_inches='tight', facecolor='white')
    plt.close(fig)

    print(f"Saved: {p_png}")
    print(f"Saved: {p_pdf}")
    print("\nRun: python experiments/generate_ipo_pipeline.py")


if __name__ == '__main__':
    main()
