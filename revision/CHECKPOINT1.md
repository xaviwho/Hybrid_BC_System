# Checkpoint 1 — WS1: development vs production application server

**Design.** Single host (the v1 laptop, WSL2, 4 cores) and one v2 deployment
(WS0.5). The comparison is:

- `dev`: Werkzeug, as in v1.
- `prod`: gunicorn gthread; the orchestrator runs 1 worker × 64 threads, the
  policy service 2 × 32 (`config/orbit_v2_server.env`).

Each run covers 4 fixtures × 11 concurrency levels. Each level sends the
smallest multiple of c that is ≥ 200 requests, after 2 warm-up rounds at c.
There are 5 repetitions per profile. The order alternates per repetition
(dev,prod | prod,dev | …), so each repetition yields a back-to-back pair.
Commit `a0f9d1e7`. The digest config hashes are `8d0891d91160` (dev) and
`c9d23c394ef7` (prod), which differ only in the server fields.

Harness: `revision/ws1/run_ws1.sh`. Analysis: `revision/ws1/analyze_ws1.py`.
Summary: `results/v2/ws1/ws1_summary.json`.
Raw rows: `results/v2/raw/ws1/<profile>/rep<k>/exp1/exp1_requests.jsonl`.

## Result

**Replacing Werkzeug with gunicorn has no measurable effect on this host.**

- **Below the block-cutting threshold (c ≤ 8):** the paired prod/dev TPS ratio
  is 0.967–1.004 across all fixtures, and every 95 % CI contains 1. Latency
  there is BatchTimeout-bound: ack is 2.2–2.5 s whatever the server.
- **At and above the threshold (c ≥ 10):** no ratio differs from 1 at 95 %. The
  point estimates for the anchoring fixtures lean slightly below 1 at c = 12–20
  (0.80–0.92), but with CI half-widths of 0.16–0.69.
- **Reconciliation gate:** 0 failures in 440 level-runs.

The server is not the bottleneck. Every request spawns two `peer` CLI
subprocesses (the invoke, and the Alg. 1 read-back); every HYBRID record adds
a relay transaction and SQLite writes. All of it shares 4 cores.

The spread above the threshold points the same way. For `fabric_only`, which
has no relay and no anchors, the rep-to-rep CI is ±5–7 % at c = 10–12. For the
three anchoring fixtures it is ±15–50 % at the same levels. So relay activity
competing for the same host, not the web server, is what makes throughput
above the threshold irreproducible on one machine. The manuscript already says
so qualitatively (§IV summary); these runs quantify it. Per-fixture tables are
in `ws1_summary.json`: mean, median, SD and 95 % t-CI over repetitions, for TPS
(gated and steady-state), ack mean, p50 and p95, and the invoke and read-back
stages.

## Caveats that travel with these numbers

1. **Clock.** All durations are on WSL `CLOCK_MONOTONIC`.
   - Against the Windows host, it ran at **0.912–0.956** per run (mean of the
     pre and post calibrations). `ws1_summary.json` carries both raw and
     host-corrected values.
   - Against NTP, checked on 2026-09-29 (`revision/ws1/clock_vs_ntp_2026-09-29.json`),
     WSL monotonic ran at **0.907** and the Windows host at **0.980**. Neither
     local clock is a UTC reference. Absolute laptop latencies are therefore
     low by roughly 5–12 %, and laptop TPS high by the same.
   - The dev/prod **ratios** are unaffected to first order: both runs of a pair
     are back to back, and their clock rates differ by ≤ 0.023.
   - This is why every later measurement moves to Azure, where the VM clocks
     are NTP-disciplined to within microseconds.
2. **Two runs were rebuilt:** `dev rep3` and `prod rep5`.
   - All 44 levels completed and every per-request row was written. The
     end-of-run digest then timed out on `/outbox_stats`, whose full-table
     scans had grown slow with ~100k outbox rows. So no summary JSON and no
     digest were written.
   - Their aggregates are rebuilt from the rows with exp1's own functions.
     Wall time per level is the monotonic span from first submit to last
     return (`analyze_ws1.py:rebuild`).
   - Their configuration equals their neighbours': same commit, same launcher,
     and `/health` is recorded in `harness.log`. But it was not captured by a
     digest, and they are marked `reconstructed`.
   - The query is fixed (covering index, windowed delivery rate, a separate
     `/outbox_depth` probe). The digest now retries with a 60 s timeout.
3. **v1 vs v2 on this host.** v2 peaks lower than v1 (for example
   `fabric_only` at c = 10: 17.6 TPS in v2 against 22.5 in v1). v2 adds the
   Fabric read-back on the acknowledgement path, about 180 ms at c = 10, and
   stores the full envelope. v1 measured one run of 50 requests per level.
   Both runs used the same drifting clock.

## Status

WS1 done on the single host.

The multi-host counterpart (WS2) runs on the Azure testbed. It will be the
basis for v2's absolute latency and throughput figures, because only there are
the clocks trustworthy.
