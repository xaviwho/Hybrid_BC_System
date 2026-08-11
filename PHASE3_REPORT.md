# OrBIT Phase 3 — Execution Report

**Scope.** `PHASE3` spec: Change 7 (delta + checkpoint storage in `twin_manager`),
Change 8 (experiments exercise the shipped code), prerequisite F-B.
**Outcome.** All ten acceptance criteria met. 59/59 storage tests, 21/21 outbox tests,
`RESULTS.json` v2 rebuilt with 26 kind-tagged metrics, exit 0.
**Manuscript.** Untouched. Equation corrections recorded in §7.

Decisions taken as instructed: fix aliasing, hybrid deltas, min(delta, snapshot)
fallback, skip the converter, keep `.state` materializing, add a bulk history path.

---

## 0. Prerequisite F-B — done first

Branch `phase3/track-results`, commit `e5f43a67`, 208 files.
`experiments/results/.gitattributes` marks the tree `-text` so git cannot rewrite
line endings on checkout — these are provenance artifacts and their bytes must
survive a round trip.

Repo had no git identity; used `Xavie <vkanu@kumoh.ac.kr>` via environment
variables for that one commit, no persistent config written.

---

## 1. Change 7 — implemented

### 7b. Canonical serialization

`canon()` = `json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)`
encoded UTF-8. `digest()` = SHA-256 over those bytes (Eq 29).

A partial canonical form already existed (`sort_keys=True` inside the old
checksum) but was non-compliant: default separators, `ensure_ascii=True`, no
shared function. **Digests computed before this change are not comparable to
digests after it.** Nothing breaks, because nothing was persisted and no digest
was ever verified — but the statement belongs in the paper.

### 7c. Delta representation — hybrid, as instructed

Entries are `{key, op: set|add|del, old, new}`; forward and inverse application
are both total, including added and removed keys.

Retention is hybrid: deltas in the **open** checkpoint window keep `old` so Eq
(34)'s inversion path is available; once a window closes they are compacted to
forward-only, because every target below a checkpoint can be reached forward and
the reverse payload costs ~3× for nothing.

### 7d. Checkpoint policy

`CHECKPOINT_INTERVAL = 100`, configurable per `TwinManager`. Version 1 is always a
checkpoint (this codebase numbers versions from 1; the paper's v0). Then every
q-th version. Verified at q ∈ {50, 100, 250}.

### 7e. Reconstruction — both branches

Checkpoint path (nearest materialized base, then forward, `u = k mod q`) and
inversion path (inverse deltas from head, `u = n − k`). The cheaper is selected;
`reconstruct_with_stats()` returns the path taken and the actual `u`.

### 7f. Integrity

Every version stores the digest of its full state. Reconstruction recomputes and
compares; mismatch raises `IntegrityViolation` and returns nothing. No
silent-repair path. `verify_all()` sweeps the whole history.

### 7g. Rollback

Already appended before this phase — that spec premise was already satisfied.
Now it also reconstructs through Algorithm 2, reuses χ_k, and records
`restored_digest` alongside `action: rollback`.

### 7h. Migration — skipped, as instructed

`storage_format = 2` recorded on every twin and exposed via `to_dict()`. No
converter: `TwinManager` is an in-memory dict, nothing survives a restart, so
there are no pre-change twins to migrate.

### Interface preservation

`.state` remains a materializing property, so `get_version_diff`, the versions
API and `to_dict` all work unchanged. `checksum` is kept as an alias for
`digest`. A bulk path (`iter_states()`) walks the whole history in O(n) delta
applications; `get_version_history()` uses it — **measured 6.0× faster** than
reconstructing each version independently (14.5 ms vs 87.2 ms over 1,001
versions), which is what the versions endpoint would otherwise have cost.

---

## 2. The aliasing defect — fixed

Found in 7a, confirmed by probe, now fixed and regression-tested.

Before: `TwinVersion.__init__` did `self.state = state` with no copy;
`patch_state` and `set_status` stored `current_state` **itself**. Two patches
produced versions that were literally the same object, and stored checksums
silently stopped matching their states.

After: all stored state is deep-copied or freshly constructed at write time.
Four regression tests cover caller mutation, `patch_state`, `create_twin`, and
`set_status`. All pass.

This was a prerequisite, not a nicety: a delta computed between two aliased
states is empty, so porting delta storage onto the old behaviour would have
recorded no history at all.

---

## 3. One design change I had to make mid-implementation

The first implementation put the reversible delta *inside* the checkpoint payload
and failed 5 tests. The cause was real, not a test artifact:

**A checkpoint sitting between the target and head breaks the inverse chain.**
Inversion-from-head then becomes impossible for every target below the most
recent checkpoint, Algorithm 2's second branch is unreachable in practice, and
Eq (36)'s `min{n−k, …}` term can never be attained.

Fix: materialized entries also carry their reversible delta (`link`), so the
inverse chain is continuous. Cost is one extra delta on 1/q of versions. The link
is a separate attribute rather than a payload wrapper — wrapping cost ~26 B per
version and showed up as a measurable 0.94× storage regression on the dense
model before it was removed.

Snapshot-fallback entries deliberately carry **no** link: they exist because the
delta was as expensive as the state, so attaching one would defeat the fallback.
They break the inverse chain by design; targets below them use the forward path.

---

## 4. Acceptance criteria

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Every version reconstructs and verifies | **PASS** — 301/301 both models |
| 2 | Both paths exercised and verified | **PASS** — checkpoint 296, inversion 1, direct 4 |
| 3 | `u == min{n−k, k mod q}` from production code | **PASS (sparse)** 21/21 at q ∈ {50,100,250}. **Dense 3/21 — see below** |
| 4 | Storage ratio on reversible deltas, forward-only alongside | **PASS** — table below |
| 5 | Rollback appends; history depth grows; nothing lost | **PASS** |
| 6 | Corrupted digest → `IntegrityViolation` | **PASS** — both a corrupted digest and a tampered payload |
| 7 | q configurable, verified at {50, 100, 250} | **PASS** |
| 8 | Pre-change twins readable or converted | **PASS** — none exist; `storage_format` recorded |
| 9 | exp4/exp8 rerun against shipped manager, tagged, exit 0 | **PASS** |
| 10 | Existing callers still work | **PASS** — 12 checks over the full REST-facing surface |

**Criterion 3 under dense updates: 3/21, and that is correct behaviour, not a
failure.** It is a direct consequence of the `min(delta, snapshot)` fallback you
asked for. Snapshot entries are extra materialization points, so the forward path
finds a nearer base and `u` comes out *smaller* than `min{n−k, k mod q}` predicts.
The bound `u ≤ min{n−k, q}` holds 21/21 in both models. The formula is exact
whenever the delta path is actually in use.

---

## 5. Measurements (re-run against the shipped manager)

### Storage — the III-K / IV-D comparison, now real

| condition | stored | snapshot-equivalent | ratio | entry mix |
|-----------|-------:|--------------------:|------:|-----------|
| sparse (~2/20 fields per version) | 92,965 B | 386,571 B | **4.16×** | 11 checkpoints, 990 deltas |
| dense (all 20 fields per version) | 388,102 B | 386,931 B | **1.00×** | 11 checkpoints, 990 snapshots |

exp4 at 800 versions agrees: sparse **4.01×**, dense **0.996×**.

Two things worth carrying into the text:

- The measured ratio **beat the 7a estimate** (3.13×) because hybrid retention
  compacts closed windows to forward-only. Reversible-everywhere would have been
  3.2×; forward-only-everywhere ~9.9× but with no inversion branch. The hybrid
  lands at 4.16× and keeps Eq (34).
- **The dense regression predicted in 7a did not materialise** — the
  `min(delta, snapshot)` fallback holds it at parity (0.996×) instead of the 0.32×
  a delta-only format would have produced. That was the right call.

### Rollback — the cost model changed, and it nearly produced a false headline

exp4's first Phase 3 run reported **`O(1)? True`** for the sparse condition. That
would have flipped Contribution 3's headline. It is an artifact, and I fixed the
experiment rather than the number.

Under checkpoints, `u = min{n−k, k mod q}` is **sawtooth in k**, not monotonic. The
old probe compared only target=1 against target=N — under the old linear-scan
implementation that was a valid test, and under this one it is not: both endpoints
happen to land on small `u`.

Measured `u` by target (sparse, q=100, n=1000):

```
target     1    50   100   250   500   750  1000
u          0    49    99    49    99    49     0
```

Characterization is now against `u`, not `k`:

| condition | rollback min / max | u range | bounded by q | varies with u |
|-----------|-------------------:|---------|--------------|---------------|
| sparse | 0.972 / 1.147 ms | 0 … 99 | **yes** (u_max=99 ≤ 100) | yes, 1.14× |
| dense | 0.173 / 0.194 ms | 0 (all snapshots) | yes | n/a, single u |

**The honest claim is now stronger than before: rollback is not constant time, but
it is bounded by the checkpoint interval.** That is a defensible bounded-recovery
property, and it is what Algorithm 2 is for. `RESULTS.json` carries both
`rollback_is_constant_time: False` and
`rollback_bounded_by_checkpoint_interval: True`.

Note the inversion: sparse rollback (~1 ms) is now *slower* than dense (~0.17 ms),
because dense stores snapshots and materializes directly while sparse applies up
to 99 deltas. Update latency also rose — 0.031 ms → 0.072 ms (sparse) / 0.114 ms
(dense) — since every write now computes a diff, two canonical serializations and
a digest. That is the price of integrity plus delta storage, and it should be
stated rather than hidden.

---

## 6. Change 8 — experiments now measure production code

**exp8** no longer contains any delta or checkpoint implementation. Deleted:
`derive_deltas`, `apply_delta`, `restore_from_checkpoint`, `invert_from_head`. It
now calls `twin_manager.reconstruct_with_stats()` for `u` and the path,
`twin.storage_report()` for bytes, and `twin.verify_all()` for integrity. A
diagnostic `force_path` argument was added to the manager so the two branches can
be timed head to head without reimplementing either.

`provenance.measures_production_code: true` is recorded in both exp4 and exp8, and
surfaces in `RESULTS.json` as `eq36_measured_on_production_code_*`.

**exp4** gained the sparse condition alongside dense; both are reported and
labelled. Storage is now accounted as `stored_bytes` vs `snapshot_equivalent_bytes`
rather than the size of the materialized history.

**exp7** needed no change — it derives its own deltas from materialized states —
and reproduces its Phase 2 numbers exactly (11.536× / 12.304× / 6.25%), which also
confirms the storage rewrite did not perturb materialized state.

### RESULTS.json v2

26 metrics, 8 measured / 18 derived / 0 modeled, `config_hash=3fa584dfbfc2`,
exit 0. exp1 and exp3 remain in `not_measured` pending the live stack.

The `kind` gate caught a real defect during this phase: a `None` value for
`rollback_bounded_by_checkpoint_interval` failed the build and wrote nothing,
rather than emitting a null into the paper's data. That is the mechanism working
as designed.

---

## 7. Equation corrections for the later text pass

Recorded, not applied.

**Eq (36).** Confirmed from production code: `u = min{n−k, q}` holds as an
equality at 3/21 points and as a bound at 21/21. The exact form
`u = min{n−k, k mod q}` holds at 21/21 wherever the delta path is in use. Replace
the equality, retain `q` as the worst-case bound in prose. Add the condition that
snapshot-fallback entries can make `u` strictly smaller.

**Section III-F / IV-D storage.** Replace "delta-based and full-snapshot storage
coincide" with **4.16×** (sparse, q=100, shipped format), stating the condition it
holds under (sparse field updates) and where it degenerates (dense updates make a
delta the size of a snapshot; the fallback holds it at parity, 1.00×).

**Section III-E exactly-once.** From Phase 2: the effect comes from at-least-once
relay delivery *plus* the on-chain uniqueness check in `registerData`, not from the
outbox primary key alone.

**Contribution 3 headline.** "Rollback is not O(1)" is still true but is now the
weaker half of the story. The measured property is **bounded by the checkpoint
interval**: `u ≤ q`, sawtooth in k rather than growing with it.

**F-C.** Figure 3 Step 9 says `registerAnchor(id, h)`; the chain has
`registerData(bytes32,string,string)`. Already queued for regeneration.

**Algorithm 2.** Now genuinely implemented in `twin_manager` — both branches, with
path selection. The Phase 2 caveat ("implemented in the experiment, not the
manager") no longer applies and should be removed from any draft that carries it.

---

## 8. Files changed

| File | Change |
|------|--------|
| `orchestrator/twin_manager.py` | rewritten storage core: canon/digest, reversible hybrid deltas, checkpoints, min(delta,snapshot) fallback, both reconstruction paths, integrity verification, bulk history walk, aliasing fix, `storage_report()`, `verify_all()` |
| `tests/test_twin_storage.py` | **new** — 59 tests over the 10 criteria + aliasing regressions |
| `experiments/exp8_recovery_strategy.py` | rewired to the shipped manager; local implementation deleted |
| `experiments/exp4_lifecycle_real.py` | sparse condition added; storage accounting via `storage_report()`; rollback characterized against `u` |
| `experiments/consolidate_results.py` | exp4/exp8 v2 shapes, bounded-recovery metric, per-model storage ratios |
| `experiments/results/.gitattributes` | **new** — byte preservation |
| `PHASE3_7A_BASELINE.md`, `PHASE3_REPORT.md` | **new** |

Uncommitted: everything except the F-B commit. Phase 2 code changes are also still
uncommitted.

---

## 9. Remaining work

Unchanged from Phase 2 — both need the WSL2 stack:

1. `exp1_latency_real.py` — ack/completion latency, three record classes,
   reconciliation gate.
2. `exp3_gas_real.py` — 27 real transactions, recompute the N=200 reduction.
3. `exp5_exactly_once_real.py` — now exercises the async outbox path; confirm the
   `preexisting:already_registered` branch under a real kill test.
4. `exp7_hadc_real.py` — record Python and zlib versions (F-A: Contribution 4 does
   not reproduce across zlib builds).
5. `consolidate_results.py` — must exit 0 with an empty `not_measured`.

The orchestrator's HTTP layer could not be exercised here (`web3` and `flask` are
not installed in this interpreter). `twin_manager`'s full REST-facing surface is
covered by criterion 10 at the module level, but the endpoints themselves have not
been hit since the storage rewrite.
