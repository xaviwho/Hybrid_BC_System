# Section IV figure captions — IEEE IoT-J single-column

Run `d8ce50b9`, `config_hash bb85df0d7803`. Built by `experiments/build_all_figures.py`
from `RESULTS.json` only.

**Format.** 88.9 mm (3.5 in) single-column, panels stacked. Every series carries
colour **and** line style **and** marker, so the figures read in grayscale. Nothing
appears inside the axes except data, axis labels, tick labels and a legend — which
means these captions are load-bearing and must ship with the figures.

Retired as false: *"increasing monotonically"*, *"99.5%"*, *"sub-millisecond but not
constant-time"*, *"linear storage (~592 B/ver)"*, *"Ethereum anchor 106.0 ms (5%)"*.

---

## Fig. 5 — Hybrid orchestration under concurrency

> **Fig. 5. Orchestration behaviour across four record fixtures.** **(a)** Throughput
> against client concurrency. The dashed vertical rule marks `c = 10`, the orderer's
> `BatchSize.MaxMessageCount`. Below it every transaction waits out
> `BatchTimeout = 2 s`; at and above it a block fills on message count before the
> timer expires, and acknowledgement latency falls from ~2.3 s to ~0.6 s. Because
> the harness holds exactly `c` requests in flight, the threshold is the message
> count itself and carries no dependence on latency. `fabric_only` commits privately
> and enqueues no public anchor: it is the control, and the only fixture that stays
> stable above the transition, peaking at 25.1 TPS against 20.4 (`all_sensitive`),
> 15.3 (`mixed`) and 10.1 (`all_public`). **(b)** Per-stage latency for the `mixed`
> fixture either side of the transition, on a logarithmic axis. Grouped rather than
> stacked, and logarithmic, because the policy stage is three orders of magnitude
> below the private commit and vanishes in a linear stack. The private commit falls
> 2229 ms to 626 ms and accounts for the entire drop; policy holds an 8–14 ms band
> (3–38 ms across all fixtures and levels, under 1.5% of acknowledgement latency)
> and outbox insertion rises slightly, 99 ms to 117 ms. No anchoring stage appears:
> anchoring is asynchronous, delivered by the relay after the 202 response, and is
> absent from acknowledgement latency by construction. **(c)** Outbox insertion
> against concurrency. Insertion cost rises with load in every fixture, but
> `fabric_only` holds 53–92 ms where the anchoring fixtures reach 450–585 ms,
> isolating relay contention on the single SQLite writer as the mechanism.
> Insertion is never dominant: at `c = 32` for `all_public` it is 273.5 ms of a
> 5689.2 ms acknowledgement, 4.8%.
> Above `c = 16` the anchoring fixtures vary by 2–3x between runs at 50 requests per
> level; read those points as curve shape, not as point estimates. `fabric_only`
> shows no comparable variance.

## Fig. 6 — Deterministic privacy routing

> Unchanged. exp2 did not move: 100% routing accuracy, zero sensitive-field leakage,
> 96.5% explicit field coverage (55/57), all reconfirmed against `RESULTS.json`.
> Existing panels and caption remain correct.

## Fig. 7 — Merkle batching economics

> **Fig. 7. Anchoring cost against Merkle batch size, measured on-chain from
> `gasUsed` receipts.** **(a)** Amortized gas per record, log–log. The dashed
> horizontal line is the measured single-record anchor, 273,695 gas. The `N = 1`
> point lies **above** it, at 296,267 gas: a one-leaf tree pays the root-anchor
> overhead with nothing to amortize it against. Root-anchor cost is flat in `N`
> (relative spread 3 x 10^-5, 296,267 gas) because only the 32-byte root reaches
> the chain, which is why per-record cost falls as 1/N. **(b)** Reduction relative
> to the single-record anchor, with the zero line drawn. The curve begins
> **negative** at −8.25% and crosses zero between `N = 1` and `N = 2`; batching is
> a net loss below two leaves. It reaches 45.88% at `N = 2`, 89.18% at `N = 10`,
> 98.92% at `N = 100` and **99.46% at `N = 200`** — the figure to quote, replacing
> the previously reported 99.5%. **(c)** Merkle proof size, the cost borne by a
> verifying auditor: 0 B at `N = 1` rising to 256 B at `N = 200`, growing as
> 32*ceil(log2 N). Operator cost falls as 1/N while auditor cost grows
> logarithmically; that opposition, not any on-chain limit, is what bounds a useful
> batch size.

## Fig. 8 — Twin lifecycle

> **Fig. 8. Rollback cost and storage under the delta-plus-checkpoint model,
> checkpoint interval `q = 100`, sparse updates.** **(a)** Rollback latency against
> target version index. Cost is **not** monotonic in `k`: it is sawtooth, tracking
> the number of delta applications `u` rather than the distance travelled. For
> `k = 1, 50, 100, 250, 500, 750, 1000` the measured `u` is
> **0, 49, 99, 49, 99, 49, 0** and latency is 0.104, 0.176, 0.225, 0.175, 0.246,
> 0.184, 0.120 ms — the correlation is with `u`, not with `k`, and `u` is bounded by
> the checkpoint interval, `u <= q = 100`. The extremes are the trap: `k = 1` and
> `k = 1000` both land on `u = 0`, so a first-versus-last probe measures almost
> nothing and would license a false constant-time claim. Marker shape and colour
> give the path the engine selected — direct, checkpoint, or inversion from head.
> Error bars are 95% CI over 100 repetitions. **(b)** Stored size against retained
> versions for both update conditions, with the snapshot-equivalent baseline dashed.
> Under sparse updates storage is **4.01x smaller at 800 versions, 95.9 B per
> version**. Under dense updates the series lies **on** the baseline at 0.996x —
> parity, not a regression, because the `min(delta, snapshot)` fallback declines to
> store a delta larger than the snapshot it would replace. The saving is therefore
> conditional on update sparsity, and the fallback is what bounds the downside.
> **(c)** Exactly-once (unchanged): 71 requests — 6 sequential duplicates, 25
> concurrent duplicates, 40 distinct — one anchoring transaction per idempotency
> key, no duplicates, no lost commits.

## Fig. 9 — Recovery path selection (new)

> **Fig. 9. Checkpoint restore against inversion from head, `q = 100`, sparse
> updates, near-head targets.** At every near-head target inversion costs roughly
> half of checkpoint restore: 0.061 vs 0.124 ms at `k = 990`, 0.058 vs 0.129 at
> `k = 995`, 0.048 vs 0.134 at `k = 999`, 0.047 vs 0.134 at `k = 1000`. The reason
> is the delta count: inversion walks back from head applying `u = 11, 6, 2, 1`
> deltas where the checkpoint path walks forward from the preceding checkpoint
> applying `u = 89, 94, 98, 99`. The engine selected inversion at all four targets,
> which are 4 of the 10 measured, so the second path is not a corner case and
> Eq. (34) is load-bearing rather than vestigial. Only the near-head region appears
> because inversion from head was measured only there; the remaining six targets
> have `delta_inversion_from_head.available = false` and are omitted rather than
> interpolated. The full-range sawtooth is Fig. 8(a).

---

# Manuscript-side consequences

Checked against `Completed_Result_Enhanced_OrBiT__…__Copy_.pdf` (16 pp., Section IV
at pp. 12–15). The figures above are correct as drawn; these are the prose and
table edits the same run implies, which the figure spec did not cover.

| Item | Manuscript says | Run `d8ce50b9` says |
|---|---|---|
| Table IV | Public path 94.4 ms / 2.97 TPS; Sensitive 2247 ms / 1.65 TPS | **Structurally obsolete.** Phase 2 made the private commit unconditional, so no fast public path exists; every fixture is ~2.2 s at c=1. Four fixtures, not two paths |
| Table VI | N=1 → 273,623.0 gas, 0.03% | N=1 → 296,267 gas, **−8.25%** |
| Table VI | 99.50% at N=200, "the single figure that should be quoted" | **99.46%** |
| Table VII | 0.0493 → 0.1123 ms, monotonic | 0.104 → 0.246 ms, **sawtooth in k, tracking u** |
| Table VII caption | "scales with the target's position in history" | scales with **u**, bounded by `u ≤ q` |
| §IV-D prose | "we report **no** storage reduction from delta encoding" | **4.01× measured** under sparse updates; parity under dense |
| §IV-E summary | "sustained throughput is a few transactions per second" | **25.1 TPS** (`fabric_only`), 20.4 (`all_sensitive`) |
| §IV-E summary | "bounded, **index-dependent** cost" | **u-dependent**; index is the wrong variable |
| §IV-A prose | "public anchoring (106 ms)" as a latency stage | anchoring is off the acknowledgement path; it has no stage in ack latency |
| Fig. 6 / Table V | 100% accuracy, 0 leaks, 96.5% (55/57) | **Unchanged — confirmed against RESULTS.json** |

**Why Table VI's sign flipped.** The old values are exact `273,623/N` multiples,
so the old method took root-anchor gas to equal single-record gas and derived
reduction as `1 − 1/N` — which is why 90.00% / 95.00% / 99.50% are round. The
current run measures root gas independently: 296,267, flat in `N` to 3 × 10⁻⁵, and
**higher** than the 273,695 single-record anchor. Hence a real loss at `N = 1`. The
change is methodological, not noise.

**The storage claim needs writing, not correcting.** §IV-D currently disclaims a
saving. Fig. 8(b) now measures 4.01× at 800 versions, conditional on sparsity, with
dense updates at parity because `min(delta, snapshot)` declines a delta larger than
the snapshot it replaces. That is a Contribution 3 result the paper does not yet
claim.
