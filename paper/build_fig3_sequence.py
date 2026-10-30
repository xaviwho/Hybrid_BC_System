"""Redraw Fig. 3 (orchestration sequence) as a vector figure with larger, bolder text.

Every label, arrow and direction follows images/Fig 3.png verbatim; long header
names are only wrapped onto two lines. Icons are cropped from
images/orchestra_v2.png (the higher-resolution earlier render).
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.offsetbox import AnnotationBbox, OffsetImage  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

SRC, OUT = sys.argv[1], sys.argv[2]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.weight": "bold", "pdf.fonttype": 42})

INK = "#000000"
LAV, LAV_E = "#efe6fd", "#8a5ad8"
LANES = [  # name, subtitle, fill, edge, icon crop box in orchestra_v2.png
    ("IoT Device", "", LAV, LAV_E, (22, 38, 76, 100)),
    ("ORBIT\nOrchestrator", "(API + Control\nPlane)", "#d8edff", "#2b8ae0", (355, 20, 407, 72)),
    ("Policy Engine", "(Deterministic,\nHIPAA/GDPR/PCI)", "#fff0b8", "#e0a800", (612, 24, 668, 82)),
    ("Fabric\n(Private Ledger)", "(World State +\nPDC + Outbox)", LAV, LAV_E, (955, 16, 1004, 70)),
    ("Relay Worker", "(Outbox\nConsumer)", "#d9f7d9", "#2fae4a", (1226, 8, 1286, 68)),
    ("Ethereum\n(Public Anchor)", "(Registry\nContract)", LAV, LAV_E, (1493, 8, 1537, 70)),
]
X = [8.6 + 16.56 * i for i in range(6)]
DEV, ORC, POL, FAB, REL, ETH = range(6)
BOX_W, HEAD_H = 15.4, 15.0
YMAX = 120.5
TOP, BOTTOM_HEAD = 0.5, 105.0
LW = 2.0

src = Image.open(SRC).convert("RGBA")


def icon(box):
    im = np.asarray(src.crop(box)).copy()
    im[im[..., :3].min(axis=2) > 222, 3] = 0
    return im


fig = plt.figure(figsize=(7.6, 8.4))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100)
ax.set_ylim(YMAX, 0)
ax.axis("off")


def header(y0):
    for (name, sub, fill, edge, crop), x in zip(LANES, X):
        ax.add_patch(FancyBboxPatch((x - BOX_W / 2, y0), BOX_W, HEAD_H,
                                    boxstyle="round,pad=0,rounding_size=1.0",
                                    fc=fill, ec=edge, lw=2.0, zorder=3))
        ax.add_artist(AnnotationBbox(OffsetImage(icon(crop), zoom=0.40), (x, y0 + 3.6),
                                     frameon=False, zorder=4))
        ax.text(x, y0 + 7.0, name, ha="center", va="top", fontsize=8.6, color=INK,
                linespacing=1.05, zorder=4)
        if sub:
            ax.text(x, y0 + 7.0 + 2.25 * (name.count("\n") + 1) + 0.4, sub, ha="center", va="top",
                    fontsize=7.0, color="#222222", linespacing=1.05, zorder=4)


header(TOP)
header(BOTTOM_HEAD)
for x in X:
    ax.plot([x, x], [TOP + HEAD_H, BOTTOM_HEAD], color="#7a7a7a", lw=1.3, ls=(0, (4, 3)), zorder=1)


def arrow(x0, y0, x1, y1, dashed=False, both=False):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="<|-|>" if both else "-|>", color=INK, lw=LW,
                                ls=(0, (3.5, 2)) if dashed else "-", mutation_scale=14,
                                shrinkA=0, shrinkB=0), zorder=5)


BG = "white"


def msg(y, a, b, label, dashed=False, both=False, right=False):
    arrow(X[a], y, X[b], y, dashed, both)
    tx = max(X[a], X[b]) - 1.2 if right else min(X[a], X[b]) + 1.2
    ax.text(tx, y - 0.8, label, ha="right" if right else "left", va="bottom", fontsize=8.6,
            color=INK, linespacing=1.1, zorder=6,
            bbox=dict(fc=BG, ec="none", pad=0.6))


def frame(x0, y0, x1, y1, tag, guard, fill, edge):
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=fill, ec=edge, lw=2.0, zorder=0.5))
    tw = 2.6 + 1.5 * len(tag)
    ax.add_patch(Polygon([(x0, y0), (x0 + tw + 1.4, y0), (x0 + tw + 1.4, y0 + 2.0), (x0 + tw, y0 + 3.4),
                          (x0, y0 + 3.4)], closed=True, fc="white", ec=edge, lw=1.6, zorder=0.6))
    ax.text(x0 + 1.1, y0 + 1.75, tag, ha="left", va="center", fontsize=9.5, color=INK, zorder=6)
    ax.text(x0 + tw + 2.6, y0 + 1.75, guard, ha="left", va="center", fontsize=8.6, color=INK, zorder=6)


# ---- messages, top to bottom (as in Fig 3.png) -------------------------------------
msg(21.5, DEV, ORC, "(1) POST /telemetry (payload x, t0)")
xo = X[ORC]
ax.plot([xo, xo + 3.0, xo + 3.0], [24.2, 24.2, 28.0], color=INK, lw=LW, zorder=5)
arrow(xo + 3.0, 28.0, xo, 28.0)
ax.text(xo + 4.2, 26.1, "(1a) Id = H(x || t0)\nValidate schema", ha="left", va="center",
        fontsize=8.6, color=INK, linespacing=1.1, zorder=6, bbox=dict(fc="white", ec="none", pad=0.6))
msg(32.5, ORC, FAB, "(1b) Check dedupId", both=True)

frame(1.0, 35.0, 99.0, 103.0, "alt", "[Id already committed]", "#e6f3fd", "#2b8ae0")
BG = "#e6f3fd"
msg(41.0, FAB, ORC, "prior_result (txid_fab_anchor_id/h)", dashed=True)
msg(45.5, ORC, DEV, "(2) 202 Accepted (cached result)")
ax.plot([1.0, 99.0], [48.0, 48.0], color="#2b8ae0", lw=1.5, ls=(0, (5, 3)), zorder=0.7)
ax.text(2.0, 50.3, "[new request]", ha="left", va="center", fontsize=8.6, color=INK, zorder=6)

msg(54.5, ORC, POL, "(3) Evaluate policy(x)")
msg(59.0, POL, ORC, "(4) per-field sensitivity + basis")
msg(68.0, ORC, FAB, "(5) Commit private state\nAND append outbox event\n(atomic txn)")
msg(72.5, FAB, ORC, "(6) FabricTxID + commitment h")
msg(77.0, ORC, DEV, "(7) 202 Accepted (ack after Fabric commit)")

frame(X[FAB] - 4.0, 74.5, 98.0, 93.0, "par", "[Async anchoring]", "#e9e9fd", "#6c6cdc")
BG = "#e9e9fd"
msg(80.5, REL, FAB, "(8) Read outbox event")
msg(84.0, REL, ETH, "(9) registerData(id, h, metadata)", right=True)
msg(87.5, ETH, REL, "(10) tx_hash", dashed=True, right=True)
msg(91.0, REL, FAB, "(11) Mark outbox delivered")
BG = "#e6f3fd"
msg(96.0, REL, ETH, "(12) Observe confirmations", right=True)
msg(99.0, ETH, REL, "(13) confirmed(z blocks)", dashed=True, right=True)
msg(102.0, REL, ORC, "(14) Optional notify: anchor confirmed")

fig.savefig(OUT + ".pdf")
fig.savefig(OUT + ".png", dpi=220)
print("ok")
