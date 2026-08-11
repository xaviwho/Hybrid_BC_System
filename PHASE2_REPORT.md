# OrBIT Phase 2 — Execution Report

**Scope.** Implementation of `PHASE2_REBUILD_SPEC.md` (Changes 1–6, RESULTS.json v2).
**Outcome.** All six changes implemented. Offline experiments re-run with real data.
Three stack-dependent experiments rebuilt but not re-run — the stack was down.
**Manuscript.** Untouched, per spec.

---

## 0. Blocking constraint discovered at the start

The measurement stack is not running on this host:

| Service | Port | State |
|---------|------|-------|
| Orchestrator | 5002 | closed |
| Ganache | 8545 | closed |
| Policy engine | 5011 | closed |
| (port 5001) | 5001 | open, but an **unrelated** container — returns `404 page not found` on `/` and `/health` |

Running Docker containers are `protchainapi`, `protchain-db`, `ipfs`, `bioapi` — a
different project. No Fabric, no Ganache, no policy engine.

Consequence for execution-order step 6 (full rerun):

| Experiment | Depends on | Status |
|------------|-----------|--------|
| exp4 lifecycle | nothing (in-process `twin_manager`) | **RE-RUN, real data** |
| exp7 HADC | nothing (in-process `twin_manager`) | **RE-RUN, real data** |
| exp8 recovery | nothing (in-process `twin_manager`) | **RE-RUN, real data (new)** |
| exp1 latency/throughput | orchestrator + policy + Fabric + Ganache | code rebuilt, **not re-run** |
| exp3 gas | Ganache + deployed contract | code rebuilt, **not re-run** |
| exp5 exactly-once | orchestrator + Fabric + Ganache | unchanged, **not re-run** |

Nothing was fabricated to fill the gap. `RESULTS.json` lists exp1 and exp3 in
`not_measured` with reasons.

---

## 1. Change 2 — every record commits to Fabric ✅

**File:** `orchestrator/orchestrator.py:293`

The `if data_sensitivity == 'sensitive':` guard is removed. The private commit is
now unconditional, per Algorithm 1 line 21 / Eq (4) / Section III-C.

Two consequential follow-ons that were not in the spec but were forced by it:

1. **Fabric failure is now fatal (HTTP 502).** The old code printed
   `"Warning: Failed to store on Fabric, continuing with Ethereum registration"`
   and anchored anyway. That publishes a commitment `H(m)` for a record that does
   not exist at rest — strictly worse than an error. It now releases the
   idempotency slot and returns 502 with `"record not persisted, nothing anchored"`.

2. **Fixed a blocker the removal exposed.** The handler rejected any response with
   empty `shareable_data` as a 500 (`"Invalid or incomplete response from privacy
   filter"`). Under "always commit," that is precisely the all-sensitive record —
   nothing publishable. It now commits privately and produces no anchor.

**Acceptance criteria:** `fabric_invoked == true` for 100% of records — verifiable
only against the live stack (exp1 records the flag per request). A record with no
publishable fields produces no outbox row — **verified offline**, test [4].

---

## 2. Change 1 — transactional outbox + relay worker ✅

**Files:** new `orchestrator/outbox.py`, new `tests/test_outbox_relay.py`,
`orchestrator/orchestrator.py` (handler + module init).

### What was built

- **Durable store.** SQLite, WAL journal, `synchronous=FULL`, per-thread
  connections, `busy_timeout=5000`. Two tables: `outbox` (spec schema plus
  `last_error`, `next_attempt_at`, `payload`) and `dedup` for `D[id]`.
- **Atomic commit+enqueue.** `commit_and_enqueue()` writes the dedup record and
  the outbox row in **one** SQLite transaction, after the Fabric commit returns.
- **Relay worker.** Daemon thread, 100 ms poll (`POLL_INTERVAL_S`), claims one due
  row at a time inside a transaction, exponential backoff
  (`BACKOFF_BASE_S=0.5`, cap 30 s), `MAX_ATTEMPTS=5` then `failed`.
- **Response boundary.** Handler returns **202 Accepted** after the enqueue.
- **New endpoints.** `GET /anchor_status/<id>` (completion latency probe),
  `GET /outbox_stats` (queue depths, relay liveness, reconciliation set size).

### Acceptance criteria

| Criterion | Result |
|-----------|--------|
| No `wait_for_transaction_receipt` in the request handler | **PASS** — sole occurrence is line 160, inside `_anchor_row`, on the relay thread. Handler spans lines 269–431. |
| Response latency ≈ policy + fabric, anchor excluded | **PASS by construction**; magnitude needs the live stack |
| `pending → delivered`, `delivered_at > created_at`, gap ≈ anchor duration | **PASS** — test [1], gap 54.2 ms against a 50 ms stub anchor |
| Kill between commit and anchor; restart drains, exactly one anchor | **PASS** — test [3] |
| Same payload twice → one Fabric write, one outbox row, one anchor | **PASS** — test [2], after a fix (below) |

### Test results — 21/21 passing

```
[1] pending -> delivered .................. 6/6 PASS
[2] duplicate submission .................. 2/2 PASS
[3] crash recovery ........................ 3/3 PASS
[4] all-sensitive: no outbox row .......... 4/4 PASS
[5] retry, backoff, permanent failure ..... 5/5 PASS
[6] enqueue does not block on anchor ...... 1/1 PASS  (0.51 ms vs 50 ms)
```

Run offline with a stubbed chain: the outbox's own guarantees are isolated from
chain behaviour. Chain-side exactly-once is exp5's job, against Ganache.

### Two real defects the tests caught

**(a) `deliver()` re-anchored an already-delivered row.** Test [2] failed on the
first run: `calls=2` for one record. The relay loop only claims `pending` rows, so
the loop was safe, but `deliver()` itself had no guard — a replayed delivery
(second worker, manual retry, re-read of a claimed row) produced a **second
anchor**, breaking exactly-once at the application layer. Fixed with a state
re-check plus a conditional `UPDATE ... WHERE id=? AND state='pending'`.

**(b) A worse one in the recovery path, found by reading the contract.**
`IoTDataRegistry.registerData` contains:

```solidity
require(dataOwners[_dataId] == address(0), "Data ID already registered");
```

It **reverts** on a duplicate `_dataId`. So a crash after broadcasting the anchor
but before recording the receipt would make the retry revert — and the relay would
have counted that as a delivery failure, retried to exhaustion, and marked a
**successfully anchored** row as `failed`. `_anchor_row` now pre-checks
`getDataOwner()` and treats an existing record as idempotent success, and also
catches the revert string as a fallback.

**This is a paper-relevant mechanism, not just a bug fix.** At-least-once relay
delivery **plus** on-chain uniqueness is what produces the exactly-once *effect*.
The outbox primary key alone does not survive a crash between broadcast and
commit. Section III-E should state both halves.

### Honest limits, as spec §1b requires

Fabric and SQLite cannot share a transaction. The ordering is: Fabric commit →
(outbox row + dedup record in one SQLite transaction) → 202. A crash in that
window leaves a record committed privately and never anchored.
`Outbox.find_unanchored()` returns exactly that set (`dedup LEFT JOIN outbox`)
for a reconciliation sweep. **No atomicity across the two ledgers is claimed.**

### Naming mismatch for the manuscript

The spec specifies `registerAnchor(id, h)`. **No such function exists on chain.**
The deployed ABI is `registerData(bytes32 _dataId, string _dataHash, string
_metadata)`. The outbox is chain-agnostic (anchor call injected as `anchor_fn`),
but the spec and the manuscript must be reconciled with the ABI.

---

## 3. Change 4 — throughput harness ✅

**File:** `experiments/exp1_latency_real.py` (rewritten)

### New measurement axes (forced by Change 2)

The public-vs-sensitive latency split dissolved. Now measured:

| Axis | Meaning |
|------|---------|
| `ack_latency_ms` | t0 → 202 Accepted. Client-visible headline. |
| `completion_latency_ms` | t0 → anchor delivered, via `/anchor_status` polling |

across **three** record classes: `all_public`, `all_sensitive`, **`mixed`** — the
realistic case, never previously measured.

### The four fixes

1. **`requests.Session` per worker thread**, `HTTPAdapter(pool_maxsize=64)`.
   Previously a new TCP connection per request, no keep-alive.
2. **Server-side data captured** — `timing_ms.*`, `fabric_invoked`,
   `anchor_enqueued`, `anchor_state`, `outbox_id`.
3. **Per-request JSONL** at `results/exp1/exp1_requests.jsonl`:
   `{concurrency, class, rtt_ms, policy_ms, fabric_ms, outbox_ms, ack_ms,
   fabric_invoked, ok, t_submit, t_return}`. This closes **F5** — p95 of
   acknowledgement latency is now derivable.
4. **Concurrency {1,2,4,8,16,32}, N=50/level, n=200/class**, warm-up 20 discarded,
   sweep stops on first error level with the reason recorded. Saturation is
   *read from the curve*; if not reached, `saturation_reached: false` and the
   highest level tested is stated explicitly.

### The reconciliation gate — verified against the historical failure

`observed_tps ≈ concurrency / mean_ack_latency_s`, tolerance ±25%. Replayed
against the F4 data that went undetected for months:

| c | recorded TPS | expected TPS | rel. error | verdict |
|---|-------------:|-------------:|-----------:|---------|
| 1 | 0.442 | 10.588 | 0.958 | **FAIL** |
| 2 | 0.872 | 21.176 | 0.959 | **FAIL** |
| 4 | 1.653 | 42.352 | 0.961 | **FAIL** |
| 8 | 2.974 | 84.704 | 0.965 | **FAIL** |

Control, internally consistent data (2247 ms path): rel. error **0.000** at
c ∈ {1,2,4}, all pass.

On failure the run writes `exp1_latency_real.FAILED.json` containing the
discrepancy, records `not_measured` for throughput, prints the deltas, and exits
**2**. No throughput number reaches `RESULTS.json`.

Also verified: with the stack down the harness prints
*"Nothing was written — a missing number is recoverable, a fabricated one is not"*
and exits 1.

---

## 4. Change 3 — real N-leaf Merkle roots ✅

**File:** `experiments/exp3_gas_real.py` (rewritten)

`_merkle_root(64, ...)` replaced by a real N-leaf tree per
N ∈ {1,2,5,10,20,50,100,200}, `REPS = 3` real transactions each.

- **27 distinct transactions** (3 single-record + 8 × 3 root) ≥ the 24 required.
  Every `tx_hash` recorded in `provenance.all_tx_hashes`.
- `root_anchor_gas` → `kind: measured`; `batched_gas_per_record` → `kind: derived`
  with `derivation: "measured_root_gas(N=…).mean / N"`.
- **Now recorded per N:** leaf count, tree depth, proof length, proof size in
  bytes, calldata size. Verified offline: N=200 → depth 8, 256 B proof;
  N=1 → depth 0.
- **Root-gas flatness is now tested, not assumed** (`root_gas_flat_in_N`, 1%
  tolerance). If root gas is flat, the note states this is *why* batching works;
  if not, it states the 1/N model does not hold and must be re-derived.
- The zero-variance single-record gas (273,695 × 5) is now explained in-file
  rather than left looking like a coincidence.

**The 99.5% @ N=200 headline must be recomputed from the measured 200-leaf root.**
Until then it is withheld.

---

## 5. Change 5 — checkpoint vs delta inversion ✅ (new, re-run, real data)

**File:** `experiments/exp8_recovery_strategy.py` (new)

### Finding: the spec's premise is false

> "Algorithm 2 already branches both ways, so the machinery exists."

**It does not.** `orchestrator/twin_manager.py` stores a **full snapshot per
version** (`TwinVersion.state` is a deep copy; `rollback_to_version` is a linear
scan plus `deepcopy`). There is no checkpoint interval, no delta store, and no
inverse-delta application anywhere in the codebase.

Both strategies are therefore implemented **in the experiment**, over the real
version history produced by `twin_manager`. Deltas and timings are real. The
`provenance.implementation_note` states this in the results file.
**The manuscript must not describe Algorithm 2's branching as implemented in the
production twin manager.**

### Setup

1,001 real versions (head n=1000), 7 targets × 3 checkpoint intervals = 21 points,
100 reps each, warm-up 20, two state-evolution models. **Every reconstruction is
verified against the stored snapshot before timing** — a mismatch aborts the run.

### Result 1 — Eq (36) is a bound, not an equality

| Form | dense | sparse |
|------|------:|-------:|
| `u == min{n−k, q}` (as written) | **3/21** | **3/21** |
| `u ≤ min{n−k, q}` | **21/21** | **21/21** |
| `u == min{n−k, k mod q}` | **21/21** | **21/21** |

Checkpoint restore costs `k mod q` delta applications, **not** `q`. `q` is the
supremum over k, attained only in the worst case. The three passing points are
k = n = 1000, where both sides are 0.

Measured at q=100 (sparse model):

| k | ckpt ms | invert ms | u_ckpt | u_invert | u_opt | Eq(36) | exact |
|---|--------:|----------:|-------:|---------:|------:|-------:|------:|
| 1 | 0.0121 | 0.3289 | 1 | 999 | 1 | 100 | 1 |
| 50 | 0.0268 | 0.3146 | 50 | 950 | 50 | 100 | 50 |
| 100 | 0.0118 | 0.2971 | 0 | 900 | 0 | 100 | 0 |
| 250 | 0.0264 | 0.2516 | 50 | 750 | 50 | 100 | 50 |
| 500 | 0.0118 | 0.1770 | 0 | 500 | 0 | 100 | 0 |
| 750 | 0.0276 | 0.0890 | 50 | 250 | 50 | 100 | 50 |
| 1000 | 0.0118 | 0.0119 | 0 | 0 | 0 | 0 | 0 |

**Recommendation:** state Eq (36) as `u ≤ min{n−k, q}`, or replace it with the
exact form `u = min{n−k, k mod q}`. Contribution 3 moves from asserted to
validated either way.

### Result 2 — the III-K storage comparison was vacuous as configured

| State model | fields changed / version | snapshots | forward deltas | ratio |
|-------------|-------------------------:|----------:|---------------:|------:|
| dense (exp4's generator) | 20.0 / 20 | 425,970 B | 425,620 B | **1.001×** |
| sparse (2 of 20, realistic IIoT) | 1.991 / 20 | 425,440 B | 42,383 B | **10.038×** |

exp4's state generator changes **every field every version**, so a delta *is* a
full snapshot and delta encoding saves nothing **by construction**. Any
checkpoint-vs-delta comparison run on that generator is predetermined. Under a
sparse model — a few telemetry channels moving at a time, which is what IIoT
looks like — deltas are **10× smaller**.

Checkpoint restore also beats inversion-from-head by **10–30×** in latency at
most targets, and the two converge only at k = n.

---

## 6. Change 6 — FlexSim removal and data-source inventory ✅

**Files:** new `experiments/DATA_SOURCES.md`; `experiments/generate_ipo_pipeline.py:67`.

**Zero FlexSim events were ever consumed end-to-end.** No FlexSim file exists in
the repository. The "FlexSim Simulation Traces" input box is removed. FlexSim is
not being added — the real provenance (twin_manager deltas) is better.

**Two further boxes were removed, beyond the spec.** Justification:

- **`IIoT Operational (HAI, BATADAL, ICS-Flow)`** — the CSVs *do* exist
  (`HAI_train1.csv` alone is 216,001 rows / 115 MiB), but **no canonical
  experiment reads them**. The only consumers are the superseded synthetic
  `exp7_hadc_compression.py` and two diagram generators.
- **`Failure Injection Events`** — no fault-injection harness exists.

**Nothing in the canonical set loads from a file.** Every input is generated
deterministically at run time. That is defensible and should simply be stated;
what is not acceptable is naming those datasets as inputs to results they did not
produce. Sections III-H and III-M need rewriting against `DATA_SOURCES.md`.

---

## 7. RESULTS.json v2 ✅

**File:** `experiments/consolidate_results.py` (rewritten)

`kind` ∈ {`measured`, `derived`, `modeled`} is **mandatory** on every metric and
validated at build time:

- invalid or missing `kind` → error
- `derived` without a `derivation` → error
- `modeled` without a `formula` → error
- a `None` value → error ("omit it or list it in `not_measured`")

Any violation prints the list, **writes nothing**, and exits non-zero.

### Current build

```
21 metrics — measured 6, derived 15, modeled 0
config_hash = 3fa584dfbfc2
not_measured:
  exp1 — file predates Phase 2 (schema_version != 2): retired public-vs-sensitive
         split, carries the F4 throughput discrepancy. Rerun required.
  exp3 — file predates Phase 2: 7 of 8 batch rows were division on a fixed
         64-leaf root. Rerun required.
```

The figure pipeline now **fails loudly** rather than plotting stale numbers:
`build_all_figures.py` raises `KeyError: metric 'gas_reduction_batch200' not in
RESULTS.json` and lists what is available. Withheld numbers cannot be rendered.

### exp4 storage repetitions raised (1 → 5)

`STORAGE_REPS = 5`. Re-run result: **stdev = 0.0 at every one of the 7 points**
(542 / 5,761 / 29,681 / 59,832 / 120,232 / 245,032 / 494,632 B). The construction
is deterministic, so zero spread is expected — but that is now *demonstrated*
rather than assumed, which one construction per point could not do.

Other exp4 values re-confirmed: 591.7 B/version; update latency 0.0305 ms (n=200);
rollback 0.0451 → 0.1464 ms, a **3.24×** span across target index — still not O(1).

---

## 8. Findings requiring a decision

### F-A. Contribution 4 does not reproduce across environments

exp7 re-run here (Windows 11, Python 3.12.10, zlib 1.3.1) vs the published run
(WSL2, versions unrecorded):

| | published | Phase 2 re-run |
|---|---:|---:|
| uniform ratio | 11.591× | 11.536× |
| HADC ratio | 12.099× | 12.304× |
| **HADC saving** | **4.2%** | **6.25%** |
| **heterogeneous_selection** | **false** | **true** |
| codecs selected | all zlib-9 | zlib-6 (agv) + zlib-9 |

Per class:

| class | raw B | uniform (pub) | uniform (new) | HADC (pub) | HADC (new) |
|-------|------:|--------------:|--------------:|-----------:|-----------:|
| machine | 24,189 | 1,761 | 1,728 | 1,618 | 1,618 |
| conveyor | 24,087 | 1,674 | 1,680 | 1,569 | 1,569 |
| sensor | 24,249 | 1,355 | **1,642** | 1,322 | 1,322 |
| agv | 27,362 | 3,828 | 3,609 | 3,747 | **3,609** |

**Raw delta bytes are byte-identical** — the twin_manager delta derivation
reproduces exactly. **zlib-9 outputs are byte-identical.** What moved is
**zlib-6**, by up to **21%** (sensor). Since the headline is the ratio of a
zlib-9 result to a zlib-6 baseline, the number is a function of the zlib build,
not of the method. And agv now prefers zlib-6, so the published caveat — *"all
classes chose zlib-9, so there is no structural heterogeneity"* — is **false**
in this environment and cannot be stated as a finding.

**Do not cite the 4.2% figure or the all-zlib-9 caveat until the environment is
pinned.** Both runs are preserved side by side in
`experiments/results/exp7/exp7_ENVIRONMENT_COMPARISON.json`.

Options: pin and report the zlib version as part of the configuration, or reframe
Contribution 4 around a codec set whose output is version-stable.

### F-B. Process failure — `experiments/results/` is not under version control

`git ls-files` reports the results tree as untracked. I re-ran exp7 and
**overwrote the original measurement** before establishing that. The original
per-class values were recoverable from
`results/contribution4_figures/tab_contribution4.tex` (generated from the previous
`RESULTS.json`), so nothing was lost — but only by luck, and `RESULTS.json` v1
itself was overwritten by the consolidator.

An unversioned results tree lets any re-run silently replace a published
measurement. **Track `experiments/results/`, or write each run to a timestamped
directory.** This is the same class of problem the `kind` tagging is meant to
prevent, one layer down.

### F-C. Contract naming

Spec and manuscript say `registerAnchor(id, h)`. The chain has
`registerData(bytes32,string,string)`. Reconcile.

### F-D. Algorithm 2 is not implemented

See §5. The branching exists only in `exp8_recovery_strategy.py`.

---

## 9. Files changed

| File | Change |
|------|--------|
| `orchestrator/orchestrator.py` | guard removed; Fabric failure fatal; 202 response boundary; `_anchor_row`; outbox init + relay start; `/anchor_status`, `/outbox_stats` |
| `orchestrator/outbox.py` | **new** — durable outbox + relay worker |
| `tests/test_outbox_relay.py` | **new** — 21 acceptance tests, offline |
| `experiments/exp1_latency_real.py` | rewritten — ack/completion, 3 classes, Session, JSONL, reconciliation gate |
| `experiments/exp3_gas_real.py` | rewritten — real N-leaf roots, 27 txs, flatness test, kind tags |
| `experiments/exp4_lifecycle_real.py` | storage reps 1 → 5 |
| `experiments/exp8_recovery_strategy.py` | **new** — checkpoint vs inversion, Eq (36) |
| `experiments/consolidate_results.py` | rewritten — RESULTS.json v2, mandatory `kind` |
| `experiments/generate_ipo_pipeline.py` | 3 unsupported input boxes removed |
| `experiments/DATA_SOURCES.md` | **new** — full provenance inventory |
| `experiments/results/exp7/exp7_ENVIRONMENT_COMPARISON.json` | **new** — F-A preservation |

---

## 10. To close Phase 2

On the WSL2 stack host, with Fabric + Ganache + policy engine up:

1. `python experiments/exp1_latency_real.py` — must exit 0; a gate failure exits 2
   and writes a discrepancy report instead of numbers.
2. `python experiments/exp3_gas_real.py` — 27 real transactions; recompute the
   N=200 reduction from the measured 200-leaf root.
3. `python experiments/exp5_exactly_once_real.py` — unchanged, but now exercises
   the async path; confirm duplicates still collapse to one anchor **and** that
   the relay's `preexisting:already_registered` path is hit under a real kill test.
4. `python experiments/exp7_hadc_real.py` — record Python and zlib versions in
   provenance (F-A).
5. `python experiments/consolidate_results.py` — must exit 0 with an empty
   `not_measured`.
6. Rebuild figures; they will fail loudly on any metric still withheld.

Two Change-1 acceptance criteria still need the real chain: kill the process
between the Fabric commit and the anchor (restart drains, exactly one anchor), and
submit a duplicate payload (one Fabric write, one outbox row, one anchor). Both
pass against the stub; neither has been exercised against Ganache.
