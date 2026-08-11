# Phase 3 — 7a Baseline Report

**Status: STOPPED for confirmation, per execution order step 2.**
No changes have been made to `twin_manager.py`.

Prerequisite F-B is done. Four items below need a decision before 7b–7h, including
one defect that changes what "port the delta code" means and one spec premise that
is false.

---

## 0. F-B complete — `experiments/results/` is under version control

Branch **`phase3/track-results`**, commit `e5f43a67`. 208 files tracked: experiment
JSON, `RESULTS.json`, LaTeX tables, generated figures.

Added `experiments/results/.gitattributes` with `* -text`. Without it git rewrites
LF→CRLF on checkout under `core.autocrlf`, so the JSON read back would not be the
bytes the experiment wrote — unacceptable for provenance artifacts.

Two notes:
- The commit is on a branch, not `main`, because `main` is the default branch.
  Merge when you're ready.
- **The repo had no `user.name`/`user.email`.** I used `Xavie <vkanu@kumoh.ac.kr>`
  via environment variables for this one commit — no persistent config was written.
  Set a real identity before further commits, and amend `e5f43a67` if the name is
  wrong.
- Phase 2 *code* changes remain uncommitted. Say the word and I'll commit them.

---

## 1. How `TwinVersion` stores state — and a correction to my Phase 2 report

**My Phase 2 report was wrong.** It stated "`TwinVersion.state` is a deep copy."
It is not. `TwinVersion.__init__` does:

```python
self.state = state          # line 16 — no copy of any kind
```

Every `deepcopy` in the file protects `current_state`, never the version history:

| Site | What it copies | What the version gets |
|------|----------------|-----------------------|
| `__init__:55,58` | `current_state = deepcopy(initial_state)` | `_add_version(initial_state)` — **caller's object** |
| `update_state:69-70` | `current_state = deepcopy(new_state)` | `_add_version(new_state)` — **caller's object** |
| `patch_state:75-76` | *(no copy)* `current_state.update(...)` | `_add_version(self.current_state)` — **`current_state` itself** |
| `rollback_to_version:94-95` | `current_state = deepcopy(version.state)` | `_add_version(version.state)` — **the old version's object** |
| `set_status:118` | *(no copy)* | `_add_version(self.current_state)` — **`current_state` itself** |

### Three probes against the shipped code

```
PROBE 1  caller mutates its dict after update_state
         version 2 state -> {'x': 999}                     ALIASED

PROBE 2  two consecutive patch_state calls
         version 2 state -> {'x': 3}   (should be {'x': 2})
         version 3 state -> {'x': 3}
         v2.state is v3.state -> True                      SAME OBJECT

PROBE 3  do stored checksums still match their states?
         v2: stored=24f572600e15  live=054b7d8d6d2b  match=False
         v3: stored=054b7d8d6d2b  live=054b7d8d6d2b  match=True
```

**Version history is not immutable.** `patch_state` and `set_status` store a live
reference to `current_state`, so every version created that way is the *same dict*,
and each subsequent patch retroactively rewrites all of them. `update_state` stores
the caller's object, so a caller mutating its own dict afterwards silently edits
committed history.

Probe 3 is the sharp end: the stored digest of v2 no longer matches v2's state. The
corruption is already detectable — nothing ever looks.

**This reaches production.** `PATCH /api/twins/<id>` → `patch_twin` → `patch_state`
is the aliasing path. Any twin patched twice in the running system has corrupt
history right now.

**Why no experiment caught it:** exp4, exp7 and exp8 all drive the twin via
`update_state(make_state(i))` with a freshly constructed dict that is never mutated
afterwards. Aliasing is invisible under that access pattern. The exp8 measurements
are therefore still valid — but they validate a path that the REST API does not use.

**Consequence for Phase 3:** this must be fixed as part of 7c, not after it. A delta
computed between two version states that alias each other yields an empty delta.
Porting delta storage onto the current aliasing behaviour would produce a system
that silently records no history at all.

---

## 2. How `rollback_to_version` reconstructs

```python
version = self.get_version(version_number)      # linear scan from the front, O(n)
self.current_state = deepcopy(version.state)    # copy
self._add_version(version.state, {'action': 'rollback', 'rollback_to': k})
```

**7g is already satisfied, mostly.** Rollback already *appends* a new head and never
truncates, and the operation type is already recorded (`metadata.action == 'rollback'`,
plus `rollback_to`). What 7g still needs: the new head aliases the target version's
state object (item 1), and no anchor payload is emitted from this path.

Cost profile matches exp4: linear scan + full deepcopy, 0.045 → 0.146 ms across
target index. Not O(1), as already reported.

---

## 3. Canonical serialization — a partial form exists, non-compliant

`TwinVersion._calculate_checksum`, line 24, is the only canonicalization:

```python
state_str = json.dumps(self.state, sort_keys=True)
```

Against 7b's requirements:

| 7b requirement | Present? |
|----------------|----------|
| sorted keys | **yes** |
| fixed separators | **no** — defaults `', '` and `': '`, whitespace included |
| UTF-8 | **no** — `ensure_ascii=True` by default, non-ASCII escaped to `\uXXXX` |
| stable float formatting | **no** — platform `repr()` |
| shared `canon()` used everywhere | **no** — inline, single-use |

There is a second, *inconsistent* serialization at line 324 (`search_twins`) using
`json.dumps(twin.current_state)` with no `sort_keys` — search only, not digests, but
it shows there is no single canonical function.

**Decision needed.** A 7b-compliant `canon()` changes the byte string, therefore
changes every digest. Per the spec I must state it plainly: **digests computed before
this change are not comparable to digests after it.** Since nothing is persisted
(item 6) and no digest is ever verified (item 4), nothing actually breaks — but the
statement belongs in the paper.

---

## 4. Digest χ — computed, stored, exposed, never verified

```python
self.checksum = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
```

- Computed once, at `TwinVersion` construction.
- Stored as `.checksum` (not `χ`, not `digest`).
- Exposed through `to_dict()` → `GET /api/twins/<id>/versions` and `/versions/<n>`.
- **Never compared to anything.** The only four occurrences in the orchestrator
  package are the assignment, the method definition, and the `to_dict` field.

Eq (33) integrity verification does not exist in any form. 7f is genuinely new work,
not a port. Probe 3 shows the check would already be firing today.

---

## 5. Every call site outside `experiments/`

Exactly one module: `orchestrator/orchestrator.py`. One process-wide singleton at
line 134. No other Python imports it; the frontend goes through REST. Nothing in
`api/`, `ml/`, or `frontend/` touches it directly.

**Interface contract that 7c must preserve:**

| Endpoint | Manager call | Constraint on a delta representation |
|----------|--------------|--------------------------------------|
| `POST /api/twins` | `create_twin` | — |
| `GET /api/twins` | `list_twins` | — |
| `GET /api/twins/<id>` | `get_twin` → `to_dict(include_versions)` | may materialize **all** versions |
| `PUT /api/twins/<id>` | `update_twin` | — |
| `PATCH /api/twins/<id>` | `patch_twin` | **the aliasing path (item 1)** |
| `DELETE /api/twins/<id>` | `delete_twin` | — |
| `GET /versions` | `get_version_history()` | returns **every version's full state** |
| `GET /versions/<n>` | `get_version(n).to_dict()` | `.state` must be a real dict |
| `POST /rollback/<n>` | `twin.rollback_to_version(n)` | must keep appending |
| `GET /diff` | `get_version_diff` | reads `v1.state` / `v2.state` **directly** |
| `GET /hierarchy`, `/ancestors`, `/descendants`, `/children` | genealogy | — |
| `GET /search`, `/statistics` | `current_state` only | — |

Two land mines for a delta port:

1. **`get_version_diff` reads `.state` as a plain dict.** If `TwinVersion.state`
   becomes a delta, this endpoint breaks unless `.state` stays a materializing
   property.
2. **`get_version_history()` materializes everything.** Under delta storage that
   becomes O(n) reconstructions per call — and it is on the hot path for
   `GET /versions` *and* for exp4's storage measurement
   (`len(json.dumps(twin.get_version_history()))`). Expect exp4's numbers to change
   meaning, and expect a latency cliff on that endpoint unless it is reworked.

---

## 6. Spec premise 7h is false — there is no persistence at all

`TwinManager.__init__` is `self.twins: Dict[str, DigitalTwin] = {}`. No file I/O, no
database, no pickle, no serialization to disk anywhere in the module.

**Twins do not survive a process restart.** So 7h's "Existing twins hold full
snapshots… what happens to a twin written before this change" has no subject: there
are no persisted twins to migrate. A converter would convert nothing.

What I propose instead, for confirmation: add a `storage_format` field for
forward-compatibility, skip the converter, and record in the report that migration
was not required because the store is in-memory.

**Larger issue this raises.** Section III-F describes durable delta-and-checkpoint
storage for a component that has **no durability whatsoever**. The storage ratios in
exp4/exp8 are measured on in-process JSON serialization, not on stored bytes. This
looks like a fifth instance of the pattern the phases have been closing
(`store_on_fabric`, the outbox, FlexSim, III-F). Flagging rather than acting: adding
persistence is well beyond this spec's scope, but "delta storage saves 3.2×" is a
claim about a store that does not exist.

---

## 7. Reversible-delta ratio — measured now, because it gates the design

7c asks for this to be measured rather than guessed, and says to report before
proceeding if it is poor enough to change the design. It is, so here it is up front.

Deltas alone, 1,001 real versions, both state models:

| model | snapshots | forward-only | reversible `{key,op,old,new}` | rev/fwd |
|-------|----------:|-------------:|------------------------------:|--------:|
| dense | 425,970 B | 42.5 KB → **1.00×** | 1,321,160 B → **0.32×** | 3.10× |
| sparse | 425,440 B | 42,383 B → **10.04×** | 131,479 B → **3.24×** | 3.10× |

Including checkpoints at q=100 (the shipped format is checkpoints **plus** deltas):

| model | checkpoints + reversible deltas | vs snapshots |
|-------|--------------------------------:|-------------:|
| dense | ~1,325,420 B | **0.32×** — *three times worse than today* |
| sparse | ~135,733 B | **3.13×** |

Three things follow:

1. The spec's guess was "plausibly around 5×". Measured is **3.24×** (deltas only),
   **3.13×** (with checkpoints). Lower than expected, still a real saving for sparse
   workloads.
2. **For dense workloads the shipped design is a regression** — 0.32×, i.e. storage
   triples. Any twin whose fields all move every version is worse off. That needs to
   be a stated condition in III-F, not discovered later.
3. **The `old` values may not be earning their keep.** 7d says version 0 is always a
   checkpoint, so *every* target has a preceding checkpoint, so the inversion path is
   never *required* for correctness — it is purely a fast path for when `n−k <
   k mod q`. Storing `old` triples delta size to serve that optimization. Options:
   (a) keep reversible deltas at 3.13×; (b) forward-only at ~9.9× with checkpoints,
   dropping Eq (34)'s inversion path and the `min{n−k, ...}` term with it;
   (c) reversible only within the current checkpoint window.

Option (b) is materially cheaper but contradicts Eq (34) and Algorithm 2's second
branch, so I am not choosing it unilaterally.

---

## Decisions needed before I proceed to 7b–7h

1. **Aliasing defect (item 1)** — confirm I fix `_add_version` to deep-copy (or
   freeze) state as part of 7c. It is a prerequisite, not optional: delta computation
   over aliased states yields empty deltas.
2. **Delta representation (item 7)** — reversible at 3.13×, forward-only at ~9.9×
   without the inversion path, or a hybrid. Reversible is the spec's stated intent
   and I will default to it if you don't say otherwise.
3. **Dense-workload regression (item 7)** — confirm it is acceptable to ship a format
   that is 3× worse for dense updates, documented as a condition.
4. **7h (item 6)** — confirm skipping the converter, since nothing is persisted.

Also for the record, two spec premises did not survive contact with the code: 7g
(rollback-appends) is already implemented, and 7h's migration subject does not exist.
Neither blocks the phase.
