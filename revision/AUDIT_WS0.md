# WS0 — Freeze and audit

Repository: WSL `/root/Hybrid_BC_System`, branch `revision/v2`, forked from tag
`v1-submitted`. Date: 2026-09-28. Every number below comes from a script under
`revision/ws0/` run against the frozen copy in `results/v1/`. Nothing here
changes a v1 value.

---

## 0. Where the canonical repository is

The revision brief puts the repository at `e:\Hybrid_BC_System`. That copy is
stale. Three copies exist:

| Copy | State |
|---|---|
| WSL `/root/Hybrid_BC_System` | **Canonical.** Holds commit `d8ce50b9` (the measurement run), config hash `bb85df0d7803`, and per-request rows. The runtime (`/root/fabric-clean`, `/root/orbit-venv`, `/root/orbit-state`) sits next to it. |
| `C:\Users\sandr\Downloads\Hybrid_BC_System` | `origin` of the WSL repo. Same HEAD, `64859685`. |
| `e:\Hybrid_BC_System` | Forked at `f3a79290` (2026-08-11). Its one extra commit, `23636e92` (MIGRATION_PLAN.md), was superseded by `067aa0bf`. Its RESULTS.json (hash `3fa584dfbfc2`) marks exp1, exp3 and exp5 as `not_measured`. |

GitHub (`xaviwho/Hybrid_BC_System`) stops at `f3a79290`. **v1 exists only on this machine.**

## 1. Freeze

| Item | Value |
|---|---|
| Tag | `v1-submitted` → `648596854fd3` (figures rebuilt from the run) |
| Measurement run | `d8ce50b95f80`, 2026-08-19 19:27 +0900 |
| Config hash | `bb85df0d7803` |
| Frozen copy | `results/v1/`: `RESULTS.json` plus `raw/`, which holds exactly the seven files in `consolidate_results.py:SOURCES` and `exp1_requests.jsonl`. All files are mode 0444. |
| Integrity | `results/v1/SHA256SUMS`. `RESULTS.json` is `f0da4e5a…62ade4d3`. For every experiment, `RESULTS.json["raw"][expN]` equals its source file (checked on load). |

**Working-tree noise, not touched.** 814 tracked files under
`blockchain/setup/ethereum/node_modules/` show as modified: 532 `M`, 188 `D`,
94 `T`. They are the effect of a Linux `npm install` over a node_modules tree
committed from Windows (`.cmd`/`.ps1` shims removed, shims replaced by
symlinks). None of it is on the measurement path. It is left unstaged, and
WS0 stages explicit paths only.

---

## 2. Rule-2 audit

**Patterns:** `random`, `mock`, `stub`, `simulat`, `fake`, `fallback`,
`sleep(`, `HYBRID_ALLOW_SIM`, `randint`, `uniform(`, `estimate`, `approx`,
`placeholder`, `dummy`, `TODO`, `FIXME`, broad `except Exception`, and literal
result numbers in figure and consolidation code.

**Scope:** 76 tracked `.py/.go/.sol/.sh/.js/.ts` files, excluding vendored code,
`node_modules`, `fabric-samples` and `frontend`.

### 2.1 The v1 measurement path

The path was established by tracing project-local imports from each
experiment entry point and from both services:

- **Services:** `orchestrator/{orchestrator, outbox, fabric_client, contract_registry, twin_manager}.py`, `ml/privacy_filter/{policy_service, policy_engine}.py`
- **Ledger code:** `blockchain/chaincode/iot-data/go/iot-data.go`, `blockchain/setup/ethereum/contracts/IoTDataRegistry.sol`
- **Experiments:** `experiments/{exp1_latency_real, exp2_privacy_policy, exp3_gas_real, exp4_lifecycle_real, exp5_exactly_once_real, exp7_hadc_real, exp8_recovery_strategy, consolidate_results, build_all_figures}.py`

**No randomness, stub, simulation branch or estimate feeds any v1 number.**
Every hit on the path falls into one of these classes:

| Hit | Where | Verdict |
|---|---|---|
| Docstrings describing what was removed ("replaces the fabricated…", "no randomness") | fabric_client:4, orchestrator:116, exp2/4/5/7/8 headers, policy_engine:15, policy_service:13 | Justified: documentation only |
| `min(delta, snapshot) fallback` | twin_manager:16,309,313,420,457; exp4; consolidate | Justified: a storage-format rule of the algorithm, not a measurement fallback |
| `approx_bytes_per_version` | exp4:200,257; consolidate:278 | Justified but misnamed: the value is measured (`stored_bytes / versions` at the stable point). Rename in v2. |
| `time.sleep(ANCHOR_POLL_S)` | exp1:231,329; exp5:79 | Justified: a poll cadence, not injected latency. **Side effect:** exp1 `completion_ms` is quantised up by 0–50 ms plus one poll round-trip (F9). |
| `except Exception` in orchestrator request handlers | orchestrator:125,390,462 and twin routes | Justified: each returns 5xx or `None`, which becomes a 502. None of them substitutes a value. |
| `except Exception` in the relay loop and `deliver` | outbox:326,372 | Justified: retry with backoff, then `failed`. See F5 for a real defect nearby. |
| `except Exception` around matplotlib import | exp2:226 | Justified: the figure is skipped and no data changes |
| Hard-coded `set_ylim` / `set_xlim` | build_all_figures:204,223,259,271,281,330,331,357,358 | Not result values, but fixed axis limits **will silently clip v2 data** if ranges move. Derive them from data in WS8. |
| Config vector literals | consolidate:386–400 | Defect: see F7 |

### 2.2 Defects found (measurement path)

Ranked by effect on reported claims. **F1–F3 change what v1 numbers mean.**
F4–F9 are correctness or methodology gaps that the revision must close.

**F1: the WSL2 kernel clock ran about 10 % slow during the v1 run, and the
wall clock was stepped to compensate.** See §4 for the evidence. The
evidence comes from exp1 (run 2026-08-19 on the rebuilt distro). Every exp1,
exp3 and exp5 duration is taken from that clock (`perf_counter`), including ack
latency, stage latency and `wall_s`. Relative to the host clock, those
durations are short by about 10 % and TPS is high by about 10 %. exp4 and exp8
(rollback latencies, run 2026-08-11 on the deleted distro) used the same
clock source on the same host, but their rate at the time is unknown and cannot
be recovered, because those files have no paired wall-clock stamps. The
c / T_ack gate cannot detect this, because both sides use the same clock.
Separately, anything computed as a difference of two `time.time()` stamps
(outbox `created_at`, `delivery_started_at` and `delivered_at`, hence
`anchor_ms` and `queue_wait_ms`) takes +3.3 s or −1.4 s steps. That is why v1
reports `anchor_cost_all_public_p95` = 168.6 ms below the mean of 203.8 ms.

**F2: the private ledger does not store the record.** `StoreIoTData`
unmarshals the payload into `IoTData{id, timestamp, device, value}` and
re-marshals it (`iot-data.go:31–52`). Every other field (`patientId`,
`diagnosis`, `ssn`, `temperature`, …) is discarded. The deployed chaincode
(`/root/hybrid-fabric/…/iot-data.go`) is byte-identical to the source. No
experiment ever reads a record back. Consequences:

- "The full record is committed to the permissioned ledger" is false as the
  system runs.
- H(m) is computed by the orchestrator over the full record, so it cannot be
  recomputed from Fabric. The WS5 auditor would fail on every record.
- `fabric_client.store_iot_data`'s docstring claim "stored verbatim (full
  record, no field loss)" is false.

**F3: the on-chain key is the record's `id` field, not the idempotency key.**
`_anchor_row` uses `sha256(payload["data_id"])`, where `data_id` is
`raw["id"]`, defaulting to `'unknown_id'` (orchestrator:155–157,387). The outbox
key is `sha256(canonical record)`. Two different records with the same `id`
map to one on-chain slot. The second hits the `getDataOwner` pre-check, is
recorded as `"preexisting:already_registered"`, and is marked **delivered**,
while the chain holds the first record's commitment. Records with no `id` all
collide on one slot. v1 payloads carried unique ids, so the v1 counts are not
affected, but the WS3 duplicate accounting and the WS5 c′ = c check would be.

**F4: exp5 can pass with no anchors.** The sequential and concurrent tests pass
on `len({tx}) == 1` (`exp5_exactly_once_real.py:109,126`). If every
`_await_anchor` timed out, `{None}` has length 1 and both tests pass. The
distinct test (40 unique hashes) shows the relay was delivering during v1, but
per-request hashes were not persisted. The v1 duplicate results therefore
cannot be re-verified from stored data. v2 must reject `None` and
`preexisting:*`, and must count from `DataRegistered` event logs.

**F5: relay claiming is not safe for more than one worker, despite its
docstring.** `_claim_one` runs its SELECT inside Python's implicit
transaction, which starts only at the UPDATE (outbox:300–316). Two workers can
select the same row. `deliver`'s `state == pending` guard does not help,
because both read `pending` before either writes. The conditional UPDATE stops
a double *record*, but not a double *broadcast*. The claim also doubles as a
30 s lease (`backoff_cap_s`): an anchor that takes longer than 30 s is
re-claimable. WS3 needs `BEGIN IMMEDIATE` with an explicit lease.

**F6: v1 "production" is not a production server.** `socketio.run(...,
debug=False, allow_unsafe_werkzeug=True)` is Werkzeug. The service also holds
process-local state:

- the in-memory idempotency cache and condition variables;
- a relay thread started at import;
- `TwinManager`.

Under gunicorn with more than one worker, concurrent duplicates would reach
Fabric more than once, and each worker would run its own uncoordinated relay.
WS1 must either run 1 worker with N threads, or move this state out first.

**F7: the config hash is a hash of hand-written strings.**
`consolidate_results.py:386–400` hashes literals such as
`"chaincode iot-data seq2"` and a host description. The hash covers no code
commit, contract address, orderer `BatchTimeout` or `MaxMessageCount`,
endorsement policy, server workers or threads, or dependency versions. Two runs
that differ in any of these hash identically. The code comment already records
one instance: debug and non-debug differed by 131 %. v2's config digest must
be read from the running system.

**F8: small, single-run samples.** v1 used 50 requests per level, one run per
configuration, and no CI on TPS. `all_public` is non-monotonic above the
transition (c = 12, 14, 16, 20 → 6.73, 5.14, 10.07, 4.08 TPS). CAPTIONS.md
already warns about 2–3× run-to-run variance above c = 16.

**F9: the "relay drain rate" (0.458 anchors/s) is the ingest rate.** The drain
burst was submitted sequentially at c = 1, so `enqueue_wall_s` (218.18 s)
≈ `drain_wall_s` (218.32 s), `peak_queue_depth_observed` = 1, and
`backlog_forms` = false. The relay was never saturated. Its self-reported mean
anchor time of 195 ms implies roughly 5 anchors/s single-threaded, before F1
correction. µ_relay was not measured in v1; WS3 measures it.

Minor items:

- `completion_ms` is quantised by the 50 ms poll (see §2.1).
- H(m) is `sha256(json.dumps(raw))` without `sort_keys` or fixed separators, so
  it is not canonical.
- No signature σ exists anywhere in the code, although the WS5 spec asks the
  auditor to recompute one.

### 2.3 Off-path code: disposition

| Files | Hits | Disposition |
|---|---|---|
| `experiments/{exp1_latency_throughput, exp3_gas_efficiency, exp4_lifecycle_overhead, exp5_exactly_once, run_all_experiments}.py` | `simulation_mode` auto-enabled on failed health check; `np.random` latencies, gas and failure events | **Removed from the tree** → `experiments/_quarantine/legacy/`, with a README mapping each to its replacement. `experiments/README.md`, which documented only this suite, now carries a stale banner. Nothing on the path imports them; only `run_all_experiments.py` did. |
| `api/system_orchestrator.py`, `blockchain/public/ethereum_client.py`, `blockchain/private/hyperledger_fabric.py` | "Simulate … blockchain" in-memory stand-ins | Justified off-path: pre-2025 prototype, imported by nothing on the path. Candidate for quarantine in WS0.5. |
| `quantum/*`, `ml/classification/*`, `ml/gateway_filter/*`, `ml/preprocessing/*`, `ml/privacy_filter/predict.py` | `random`, dummy training data | Justified off-path: not imported by `policy_service`/`policy_engine`, which is the only ML code the orchestrator calls (over HTTP). |
| `performance-test.py`, `test-realtime-stream.py`, `test-twin-lifecycle.py`, `interactive-test.sh`, `start-*.sh` | `random.uniform` payloads, `sleep` pacing | Justified off-path: manual demo tooling. `STACK_BRINGUP.md` launches services directly, not through these scripts. |
| `orchestrator-js/*` | a few | Justified off-path: an alternative orchestrator that was never the system of record. |
| `tests/test_outbox_relay.py` | `StubChain`, `sleep` | Justified: a unit-test double for the anchor function. It exercises outbox logic and produces no results. |
| `experiments/generate_ipo_pipeline.py` | `np.random.seed(42)` | Justified: methodology diagram. The seed is set but never drawn from. |
| `simple-iot-chaincode/iot-data.go` | `GetStub` | Not a hit (Fabric API name). The directory is an unused chaincode copy. |

---

## 3. Provenance question 1: storage ratio, 4.01× vs 4.04×

**Both are correct.** They are the same quantity, the sparse-update model at
checkpoint interval q = 100, measured at two history lengths by two
experiments:

| Source | Versions | Stored | Snapshot-equivalent | Ratio |
|---|---:|---:|---:|---:|
| exp4 `storage_growth` | 400 | 39 540 B | 151 580 B | 3.8336 |
| exp4 `storage_growth` | **800** | **76 744 B** | **307 980 B** | **4.0131** |
| exp8 `storage_at_q100` | **1 001** | **95 737 B** | **386 571 B** | **4.0378** |

307 980 / 76 744 = 4.01308; 386 571 / 95 737 = 4.03784. The ratio rises with
n because the fixed checkpoint cost is amortised over more deltas, so the
three rows form one consistent series.

**Where each is computed and printed:**

- **4.0131:** computed in `exp4_lifecycle_real.py:113`. Admitted as the
  `storage_compression_vs_snapshots_sparse` metric (`consolidate_results.py:285`,
  RESULTS.json:494). Drawn in Fig. 8(b) by `build_all_figures.py:346–352` and
  quoted as "4.01x at 800 versions" in `CAPTIONS.md:86,125,139`.
- **4.0378:** computed in `exp8_recovery_strategy.py` (`ratio_vs_snapshots`).
  Admitted as `delta_vs_snapshot_ratio_sparse` (`consolidate_results.py:339`,
  RESULTS.json:626). Quoted as **4.04×** in `PHASE3_REPORT.md:161,173,274`.
  Line 274 recommends 4.04× for §III-F/IV-D.

**Why both appeared.** PHASE3_REPORT (2026-08-11) was written from the exp8
measurement against the shipped manager and recommended its figure for the
text. The Section IV figures were rebuilt on 2026-08-19 from exp4, whose
largest point is 800 versions, and the captions quote the figure's own number.

**Recommendation.** Quote **4.01× at 800 versions** wherever Fig. 8(b) is
cited, because that is the plotted point. If 4.04× is used, it must read
"4.04× at 1 001 versions (exp8)". It must not appear unqualified next to
Fig. 8(b). F1 does not affect either value, because both are byte counts.

---

## 4. Provenance question 2: reconciliation-gate arithmetic

Code: `exp1_latency_real.py:373` (`reconciliation_gate`), tolerance at `:89`.
The check is `expected = c / (mean_ack_ms / 1000)` and
`pass ⇔ |tps − expected| / expected ≤ 0.25`, where `tps = n_ok / wall_s`
(`:420`). Recomputed on the frozen rows by
`revision/ws0/gate_recompute.py` → `gate_recompute.json`.

### 4.1 The stored arithmetic is internally correct

- Recomputing mean ack, expected TPS and relative error from
  `exp1_requests.jsonl` reproduces all 44 stored values: **0 mismatches**.
- All 44 levels pass as stored. The maximum relative error is 0.211
  (`fabric_only`, c = 32).

### 4.2 The residual is systematic, and it is batch quantisation, not a system effect

Observed TPS is below c / T_ack at 40 of the 44 levels. Below the
block-cutting threshold, where every round lasts one BatchTimeout, a closed
loop of c workers draining n = 50 requests takes ⌈n/c⌉ rounds. That predicts
observed/expected = n / (c·⌈n/c⌉):

| c | Predicted | Observed (4 fixtures) |
|---|---:|---|
| 1 | 1.0000 | 0.9993–0.9998 |
| 2 | 1.0000 | 0.9981–0.9991 |
| 4 | 0.9615 | 0.9609–0.9617 |
| 8 | 0.8929 | 0.8944–0.9059 |

The fit is to three or four decimals. The gate is therefore mostly measuring
the choice n = 50, not agreement between throughput and latency. At c = 24
and c = 32 the predicted shortfall reaches 31 % and 22 %. Only
desynchronisation above the threshold keeps those levels inside the 25 %
tolerance. **Fix for v2:** n a multiple of c (200 = 8 × 25 works for most
levels), or TPS measured over a steady-state window that excludes the first
and last c completions.

### 4.3 The gate is recomputable only from `wall_s`, not from the per-request stamps

If TPS is recomputed from the rows (n / (last `t_return` − first `t_submit`)),
6 of 44 levels fail:

| Level | Relative error |
|---|---:|
| `fabric_only` c = 20 | 0.661 |
| `all_sensitive` c = 14 | 0.626 |
| `all_sensitive` c = 32 | 0.439 |
| `all_public` c = 10 | 0.400 |
| `all_public` c = 20 | 0.342 |
| `all_public` c = 32 | 0.309 |

The cause is F1, not the system:

- **Wall-clock steps.** In 290 of the 3 000 rows, `t_return − t_submit`
  disagrees with the `perf_counter` RTT measured around the same call. The
  median positive step is **+3 314 ms**; steps range from −6 283 to +9 709 ms.
  Steps recur at roughly 33 s intervals throughout the run
  (`clock_skew_v1.json`).
- **Clock rate.** On back-to-back c = 1 and c = 2 levels, `wall_s` /
  realtime span = **0.892–0.908** across all eight levels. This is only
  possible if the monotonic clock ran about 10 % slower than the stepped wall
  clock.
- **Live check, 2026-09-28** (`clock_calibrate_2026-09-28.json`, 301.5 s):
  against the Windows host, WSL `CLOCK_MONOTONIC` runs at **0.99597** and
  `CLOCK_REALTIME` at **0.99979** (±0.00074). The wall clock is stepped by
  +0.07 to +0.14 s every ~30 s. A 150 s run earlier the same day gave 0.9897
  (not saved; it came from the prototype of this script). The drift therefore
  persists today at 0.4–1 % rather than about 10 %, and **it varies between
  runs**. It has to be measured per run and cannot be applied as a constant
  correction.
  **Caveat:** the Windows Time service is stopped (`w32tm_status_2026-09-28.txt`),
  so the host clock is not NTP-disciplined. This shows a WSL-vs-host rate
  mismatch. It is not yet an absolute error against UTC.

**If the manuscript reports a gate discrepancy,** its source is one of:

- (a) the n = 50 quantisation in §4.2, which explains the systematic
  under-shoot;
- (b) mixing `perf_counter` durations with `time.time()` stamps, as in §4.3.

The manuscript's own statement is needed to say which. The stored gate values
themselves are arithmetically exact.

---

## 5. Consequences for the revision plan

| Item | Action | When |
|---|---|---|
| F1 clock | Establish a trusted reference: start w32time and check against NTP, or time from outside WSL. Record `clock_calibrate.py` output before and after every run, as a provenance field. Keep all durations on `perf_counter`; never subtract two `time.time()` stamps; move outbox timings to `time.monotonic()`. Decide with co-authors whether v1 durations are re-stated with a rate correction or simply superseded by v2. | Before WS1 |
| F2 chaincode, F3 key, canonical H(m) | Store the payload verbatim plus H(m); key on-chain by the idempotency key; canonical JSON; read-back check in every experiment | WS0.5 |
| F4 exp5 | Reject `None` and `preexisting:*`; count from `DataRegistered` logs; persist per-request hashes | WS0.5 / WS7 |
| F5 relay claim | `BEGIN IMMEDIATE` plus explicit lease columns | WS3 (design in WS0.5) |
| F6 server | Relay as its own process; idempotency moved into SQLite; gunicorn with 1 worker × N threads | WS0.5 → WS1 |
| F7 config hash | Digest read from the running system (commit, contract, channel config, endorsement policy, server, versions) | WS0.5 |
| F8 samples, gate n | n = 200, 5 repetitions, n a multiple of c or steady-state TPS | WS1 onward |
| F9 µ_relay | Measure under saturation | WS3 |
| Storage | Quote 4.01× at 800 versions for Fig. 8(b); qualify 4.04× if used | Manuscript |
| Contract changes | Relay allowlist plus the F3 key change in **one** redeploy, so all of v2 shares one address | WS0.5 |

---

## Addendum (WS0.5, 2026-09-28)

Resolved or confirmed in `revision/WS0_5.md`:

- **F5 confirmed on the v1 code:** 20 of 800 rows were anchored twice with two
  relays (`ws05/f5_v1_race_result_2026-09-28.json`).
- **F7, two more instances found by querying the system:**
  - the config string "chaincode iot-data seq2" was wrong; the committed
    definition was sequence 1 with the channel-default endorsement policy;
  - the images are tagged `:latest`, and resolve to 2.5.0 only by coincidence.
- **New:** the Raft orderer has **one consenter**, so it tolerates no orderer
  failure.
- **New:** the manuscript defines h = Keccak-256 of the *redacted* metadata m,
  and anchors c = H(σ) with σ = ⟨id, k, ν, τ, h⟩ (Eqs. 12, 20a, 22). It also
  specifies a Fabric read-back before the acknowledgement (Alg. 1 l.22). v1
  anchored SHA-256 over the full record, including sensitive fields, and did
  no read-back. v2 implements the manuscript's model.
- **Correction to §0:** GitHub could not be updated. The push was denied for
  user `CHYMEE`.
