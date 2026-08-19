# Superseded figures — pre-`d8ce50b9`

**Do not `\includegraphics` anything in this directory.** Every file here plots a
quantity that the run `d8ce50b9` / `config_hash bb85df0d7803` measured differently,
in several cases with the opposite sign or shape. They are kept, not deleted, so the
earlier state stays auditable and so `git log --follow` still works across the move.

Moved 2026-08-19. Filenames are flattened with `_` standing in for the original
`/`, so `contribution1_figures_fig1c_throughput_scaling.png` came from
`contribution1_figures/fig1c_throughput_scaling.png`.

## Replacements

| Superseded | Replaced by | Why it is wrong now |
|---|---|---|
| `exp1_throughput_curve`, `contribution1_figures_fig1c_throughput_scaling` | **Fig 5(a)** `figures_section4/fig5_orchestration` | 4 concurrency levels and 2 paths; no c=10 transition, and the transition is the result |
| `exp1_latency_breakdown`, `contribution1_figures_fig1b_stage_breakdown` | **Fig 5(b)** | Carries an "Ethereum anchor 106 ms" stage. Anchoring is off the acknowledgement path; it has no stage in ack latency |
| `exp1_latency_distribution`, `contribution1_figures_fig1a_latency_by_path` | **Fig 5(a)/(b)** | The public-vs-sensitive framing. Phase 2 made the private commit unconditional, so the 94.4 ms public path no longer exists |
| `exp3_gas_vs_batch`, `contribution_gas_figures_fig_gas_per_record` | **Fig 7(a)** | Took root-anchor gas to equal single-record gas, so N=1 sits *on* the baseline instead of above it |
| `contribution_gas_figures_fig_gas_reduction` | **Fig 7(b)** | Derived reduction as `1 - 1/N`, giving 0.03% at N=1 and round 90.00/95.00/99.50. Measured root gas is 296,267 — higher than the 273,695 baseline — so N=1 is **-8.25%** |
| `exp3_comparison_bar`, `exp3_cost_latency`, `contribution_gas_figures_fig_gas_panel` | **Fig 7(a)-(c)** | Composites built on the same superseded gas series |
| `exp4_rollback_latency`, `contribution3_figures_fig3a_rollback_latency` | **Fig 8(a)** | Monotonic 0.049 -> 0.112 ms. Actual behaviour is sawtooth, 0.104 -> 0.246 ms, tracking `u` not index |
| `exp4_storage_growth`, `contribution3_figures_fig3b_storage_growth` | **Fig 8(b)** | Single-condition, pre-dates the 4.01x sparse result; the prose it illustrated disclaimed any saving |
| `exp4_checkpoint_speedup` | **Fig 9** | Superseded by the measured checkpoint-vs-inversion comparison, incl. the near-head region |
| `contribution1_figures_fig_contribution1_panel`, `contribution3_figures_fig_contribution3_panel`, `tab_contribution1.tex`, `tab_contribution3.tex`, `tab_gas.tex` | Figs 5, 7, 8; Tables IV, VI, VII | Composite panels and tables containing the above |

`updated_results/` held a second copy of contributions 1, 3 and gas; both copies are
here, distinguishable by the `updated_results_` prefix.

## Deliberately NOT moved

- **`contribution3_figures/fig3c_exactly_once`** — Fig 8(c) survives unchanged.
  71 requests, 6 sequential / 25 concurrent / 40 distinct, still current.
- **`exp2/`, `contribution2_figures/`** — Fig 6 survives unchanged. exp2 did not
  move: 100% routing accuracy, zero leaks, 96.5% coverage (55/57), all confirmed
  against `RESULTS.json`.
- **`exp5/`** — exactly-once, unchanged.
- **`exp7/`, `contribution4_figures/`** — HADC / Contribution 4. exp7 reproduced
  6.25% and `heterogeneous_selection: true` on this host.
- **`methodology_figures/`** and its `icons/` — feed Figures 1-4, handled separately
  in the manuscript checklist.
- **`visual_metrics/`** — left in place as a judgement call, not an endorsement.
  It is supplementary rather than a Section IV panel, but two of its files
  (`metric_b_latency_distribution`, `contribution3_lifecycle_recovery`) do plot
  quantities this run changed. Review before using either.

## Current figures

`experiments/results/figures_section4/` — Figs 5, 7, 8, 9 plus `CAPTIONS.md`.
Rebuild with `python experiments/build_all_figures.py`, which reads `RESULTS.json`
only and raises rather than plotting a missing or stale value.
