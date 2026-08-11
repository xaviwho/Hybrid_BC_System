"""
Digital Twin Lifecycle Management Module
Handles CRUD operations, versioning, and genealogy for digital twins.

PHASE 3 — delta + checkpoint storage (Section III-F, Algorithm 2, Eq 29/33/34/35/36).

Storage model
-------------
Version history is stored as periodic checkpoints plus deltas, not as a full
snapshot per version. Each version entry is one of:

  checkpoint  full materialized state. Written for version 1 and every q-th
              version thereafter (q = CHECKPOINT_INTERVAL, configurable).
  snapshot    full materialized state, written opportunistically when the delta
              for that version would be LARGER than the state itself. This is the
              min(delta, snapshot) fallback: it bounds worst-case storage at
              roughly the old full-snapshot model instead of tripling it, which is
              what a delta-only format does for dense updates where every field
              changes every version.
  delta       list of reversible entries {key, op, old, new}.

Hybrid delta retention
----------------------
The last R versions behind head (REVERSIBLE_WINDOW, default R = q) keep their
`old` values, so Eq (34)'s inversion-from-head path is available in the near-head
region where it is genuinely cheaper. Older deltas are compacted to forward-only:
they always have a preceding checkpoint to roll forward from, so their reverse
payload is dead weight — it costs about 3x the delta size.

Retention is a TRAILING WINDOW, not "the open checkpoint window". The latter was
tried first and is wrong: it strips every version before the most recent
checkpoint, so whenever head sits on or just after a checkpoint the entire history
becomes forward-only and inversion is unavailable for every target — killing
Eq (34) exactly where it wins.

Version numbering and the Eq (36) index convention
--------------------------------------------------
Versions are numbered from 1 (v1, v2, ...); internally they sit at 0-based
positions p = version_number - 1. A checkpoint is written wherever p mod q == 0,
i.e. at VERSION NUMBERS 1, q+1, 2q+1, ... (for q=100: 1, 101, 201, ...).

So for a target version k with head version n, the delta-application count is

    u = min{ n - k , (k-1) mod q }

which is Eq (36) verbatim once k and n are read as 0-based indices (k' = k-1,
n' = n-1). Stated with 1-based version numbers the literal form min{n-k, k mod q}
is wrong: measured against the shipped manager it matches u at 1 of 7 sampled
targets, while the index form matches 7 of 7.

NOTE for the text pass: Algorithm 2 line 42 checkpoints at (n+1) mod q == 0,
placing checkpoints at 0-based positions q-1, 2q-1, ... — a different convention
from this implementation, and one that leaves positions 0..q-2 with no preceding
checkpoint, contradicting "version 0 is always a checkpoint".

Reconstruction (Algorithm 2, both branches)
-------------------------------------------
  checkpoint path  nearest materialized entry at or before k, then forward deltas.
                   u = k - base_index
  inversion path   inverse deltas from head down to k, when every version in
                   (k, n] is a reversible delta.  u = n - k
The cheaper path is selected. The actual u and the path taken are recorded on
every reconstruction and returned by reconstruct_with_stats() — that is what
validates Eq (36) from production code rather than from an experiment harness.

Integrity (Eq 33)
-----------------
Every version stores the digest of its FULL state. Reconstruction recomputes
SHA-256 over the canonical bytes and compares. On mismatch it raises
IntegrityViolation and returns nothing. There is no silent-repair path.

Aliasing
--------
Before Phase 3, TwinVersion stored the caller's dict by reference and patch_state
stored `current_state` itself, so committed history mutated retroactively and
stored checksums silently stopped matching their states. All stored state is now
deep-copied or freshly constructed at write time; nothing shares a reference with
a caller or with the live head.

Persistence
-----------
There is none: TwinManager is an in-memory dict and twins do not survive a restart.
No format migration is provided because no twin written before this change exists
to migrate. STORAGE_FORMAT is recorded on each twin for forward-compatibility.
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from copy import deepcopy

# --- Configuration -----------------------------------------------------------

CHECKPOINT_INTERVAL = 100   # q. Mid-range of exp8's tested {50, 100, 250}.
REVERSIBLE_WINDOW = None    # R: versions kept invertible behind head. None -> q.
                            # Set to 0 to disable the inversion path entirely and
                            # store forward-only deltas everywhere (cheapest, but
                            # Eq (34) / Algorithm 2's second branch goes away).
STORAGE_FORMAT = 2          # 1 = full snapshot per version (pre-Phase-3)

KIND_CHECKPOINT = 'checkpoint'
KIND_SNAPSHOT = 'snapshot'
KIND_DELTA = 'delta'
MATERIALIZED_KINDS = (KIND_CHECKPOINT, KIND_SNAPSHOT)

PATH_CHECKPOINT = 'checkpoint'
PATH_INVERSION = 'inversion'
PATH_DIRECT = 'direct'


class IntegrityViolation(Exception):
    """Reconstructed state does not match the digest stored for that version."""


# --- Canonical serialization (Eq 29) -----------------------------------------

def canon(obj: Any) -> bytes:
    """Byte-deterministic serialization.

    sorted keys, no whitespace, UTF-8, no ASCII escaping. Float formatting relies
    on Python's shortest-round-trip repr, stable since 3.1.

    NOTE: this is NOT byte-compatible with the pre-Phase-3 checksum, which used
    json.dumps(state, sort_keys=True) with default separators and ensure_ascii.
    Digests computed before this change are not comparable to digests after it.
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def digest(obj: Any) -> str:
    """SHA-256 over the canonical bytes (Eq 29)."""
    return hashlib.sha256(canon(obj)).hexdigest()


# --- Delta algebra -----------------------------------------------------------

def diff_states(old: Dict, new: Dict) -> List[Dict]:
    """Reversible delta from `old` to `new`.

    Each entry carries both directions so that forward application and inversion
    are total, including for added and removed keys.
    """
    delta = []
    for key in sorted(set(old) | set(new)):
        in_old, in_new = key in old, key in new
        ov, nv = old.get(key), new.get(key)
        if in_old and in_new:
            if ov != nv:
                delta.append({'key': key, 'op': 'set', 'old': ov, 'new': nv})
        elif in_new:
            delta.append({'key': key, 'op': 'add', 'new': nv})
        else:
            delta.append({'key': key, 'op': 'del', 'old': ov})
    return delta


def apply_forward(state: Dict, delta: List[Dict]) -> Dict:
    """s' = delta(s). Mutates and returns `state`."""
    for e in delta:
        if e['op'] == 'del':
            state.pop(e['key'], None)
        else:
            state[e['key']] = deepcopy(e['new'])
    return state


def apply_inverse(state: Dict, delta: List[Dict]) -> Dict:
    """s = inv(delta)(s'). Mutates and returns `state`. Requires a reversible delta."""
    for e in delta:
        if e['op'] == 'add':
            state.pop(e['key'], None)
        else:
            if 'old' not in e:
                raise ValueError("delta is forward-only; cannot invert")
            state[e['key']] = deepcopy(e['old'])
    return state


def is_reversible(delta: List[Dict]) -> bool:
    return all(e['op'] == 'add' or 'old' in e for e in delta)


def strip_old(delta: List[Dict]) -> List[Dict]:
    """Compact a reversible delta to forward-only. 'del' keeps `old` (it is the
    only way to know what to restore), everything else drops it."""
    out = []
    for e in delta:
        if e['op'] == 'del':
            out.append(dict(e))
        else:
            out.append({k: v for k, v in e.items() if k != 'old'})
    return out


class TwinVersion:
    """One version record. Holds a checkpoint, a snapshot, or a delta — never the
    caller's object."""

    def __init__(self, twin: 'DigitalTwin', version_number: int, kind: str,
                 payload: Any, state_digest: str, metadata: Dict = None,
                 link: Optional[List[Dict]] = None):
        self._twin = twin
        self.version_number = version_number
        self.kind = kind
        self.payload = payload
        # Inverse link: the reversible delta from the predecessor, kept on
        # materialized entries so a checkpoint does not break the inverse chain of
        # Eq (34). Held as a separate attribute rather than wrapped into payload,
        # so a state dict is stored as itself with no envelope overhead.
        self.link = link
        self.digest = state_digest
        self.timestamp = datetime.now().isoformat()
        self.metadata = metadata or {}

    @property
    def state(self) -> Dict:
        """Materialized full state. Kept as a property so every existing caller
        (get_version_diff, the versions API, to_dict) keeps working unchanged."""
        return self._twin.reconstruct(self.version_number)

    @property
    def checksum(self) -> str:
        """Back-compatible alias for the stored digest."""
        return self.digest

    def stored_bytes(self) -> int:
        n = len(canon(self.payload))
        if self.link is not None:
            n += len(canon(self.link))
        return n

    def to_dict(self, state: Dict = None) -> Dict:
        """`state` may be passed in by a bulk walk to avoid re-reconstructing."""
        return {
            'version_number': self.version_number,
            'state': deepcopy(state) if state is not None else self.state,
            'timestamp': self.timestamp,
            'metadata': self.metadata,
            'checksum': self.digest,
            'storage_kind': self.kind,
        }


class DigitalTwin:
    """Represents a digital twin with full lifecycle management"""

    def __init__(self, twin_id: str, twin_type: str, initial_state: Dict,
                 metadata: Dict = None, parent_id: Optional[str] = None,
                 checkpoint_interval: int = CHECKPOINT_INTERVAL,
                 reversible_window: Optional[int] = REVERSIBLE_WINDOW):
        self.twin_id = twin_id
        self.twin_type = twin_type
        self.parent_id = parent_id
        self.children = []
        self.metadata = metadata or {}
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.status = 'active'

        self.storage_format = STORAGE_FORMAT
        self.checkpoint_interval = max(1, int(checkpoint_interval))
        self.reversible_window = (self.checkpoint_interval
                                  if reversible_window is None
                                  else max(0, int(reversible_window)))

        # Version control
        self.current_version = 1
        self.versions: List[TwinVersion] = []
        self._prev_state: Dict = {}          # materialized state of the last version
        self._last_recon: Dict = {}          # path/u of the most recent reconstruction

        self._add_version(initial_state, {'action': 'created'})
        self.current_state = deepcopy(initial_state)

    # --- write path ----------------------------------------------------------

    def _add_version(self, state: Dict, metadata: Dict = None):
        """Append a version, choosing checkpoint / snapshot / delta storage.

        `state` is never retained by reference: checkpoints and snapshots store a
        deep copy, deltas store freshly built entries.
        """
        version_number = self.current_version
        position = len(self.versions)
        state_digest = digest(state)

        if position % self.checkpoint_interval == 0:
            # 7d: version 1 is always a checkpoint, then every q-th version.
            # A checkpoint ALSO carries its reversible delta so that the inverse
            # chain of Eq (34) is not broken by the checkpoint sitting in it.
            # Without this, inversion-from-head is impossible for any target below
            # the most recent checkpoint, Algorithm 2's second branch is
            # unreachable, and Eq (36)'s min{n-k, ...} term can never be attained.
            # Cost is one extra delta on 1/q of versions.
            link = diff_states(self._prev_state, state) if position else None
            kind, payload = KIND_CHECKPOINT, deepcopy(state)
        else:
            delta = diff_states(self._prev_state, state)
            link = None
            # min(delta, snapshot) fallback — bounds dense-update storage.
            if len(canon(delta)) < len(canon(state)):
                kind, payload = KIND_DELTA, delta
            else:
                # Snapshot fallback: chosen precisely because the delta is as
                # expensive as the state, so no delta is attached. This breaks the
                # inverse chain by design; targets below it use the forward path.
                kind, payload = KIND_SNAPSHOT, deepcopy(state)

        self.versions.append(
            TwinVersion(self, version_number, kind, payload, state_digest, metadata,
                        link=link))
        self.current_version += 1
        self._prev_state = deepcopy(state)
        self.updated_at = datetime.now().isoformat()

        self._age_out_reversibility()

    def _age_out_reversibility(self):
        """Strip `old` from the version that just fell out of the trailing
        reversible window.

        Retention is a TRAILING WINDOW of the last R versions, not "the open
        checkpoint window". The earlier checkpoint-window policy stripped every
        version before the most recent checkpoint — and since a checkpoint is
        itself a version, whenever the head sat on or just after one, the whole
        history became forward-only and inversion-from-head was unavailable for
        every target. That killed Eq (34) exactly in the near-head region where it
        wins (measured: at k=990, q=100, inversion needs u=11 against the
        checkpoint path's u=89, but the chain had been compacted away).

        A trailing window keeps the inverse chain intact for the last R versions,
        which is the near-head undo case, and costs the reverse payload only on
        those R versions instead of on a whole checkpoint window.
        """
        idx = len(self.versions) - 1 - self.reversible_window
        if idx < 0:
            return
        v = self.versions[idx]
        if v.kind == KIND_DELTA and is_reversible(v.payload):
            v.payload = strip_old(v.payload)
        elif v.kind in MATERIALIZED_KINDS and v.link is not None:
            v.link = None

    @staticmethod
    def _state_of(v: 'TwinVersion') -> Dict:
        """Materialized state carried by a checkpoint/snapshot entry."""
        return v.payload

    @staticmethod
    def _delta_of(v: 'TwinVersion') -> Optional[List[Dict]]:
        """Delta component of any entry, or None if it carries no inverse link."""
        if v.kind == KIND_DELTA:
            return v.payload
        return v.link

    def update_state(self, new_state: Dict, metadata: Dict = None):
        """Update twin state and create new version"""
        self._add_version(new_state, metadata or {'action': 'updated'})
        self.current_state = deepcopy(new_state)
        self.updated_at = datetime.now().isoformat()

    def patch_state(self, partial_state: Dict, metadata: Dict = None):
        """Partially update twin state (merge with existing).

        Builds a FRESH merged dict. The pre-Phase-3 version mutated current_state
        in place and stored that same object into history, so every patched
        version aliased the live head.
        """
        merged = deepcopy(self.current_state)
        merged.update(deepcopy(partial_state))
        self._add_version(merged, metadata or {'action': 'patched'})
        self.current_state = merged
        self.updated_at = datetime.now().isoformat()

    def set_status(self, status: str, metadata: Dict = None):
        """Change twin status"""
        self.status = status
        self.updated_at = datetime.now().isoformat()
        self._add_version(self.current_state, {
            'action': 'status_change',
            'new_status': status,
            **(metadata or {})
        })

    # --- read path -----------------------------------------------------------

    def get_version(self, version_number: int) -> Optional[TwinVersion]:
        """Get a specific version. Direct index (versions are appended in order),
        with a scan as a safety net."""
        idx = version_number - 1
        if 0 <= idx < len(self.versions) and \
                self.versions[idx].version_number == version_number:
            return self.versions[idx]
        for version in self.versions:
            if version.version_number == version_number:
                return version
        return None

    def _base_for(self, idx: int) -> int:
        """Index of the nearest materialized entry at or before `idx`."""
        for i in range(idx, -1, -1):
            if self.versions[i].kind in MATERIALIZED_KINDS:
                return i
        raise IntegrityViolation(
            f"twin {self.twin_id}: no materialized base at or before version {idx + 1}")

    def _can_invert(self, idx: int) -> bool:
        """True if the inverse chain from head down to `idx` is unbroken.

        Every version above `idx` must carry a reversible delta. Checkpoints do
        (see _add_version); snapshot-fallback entries do not, and break the chain.
        """
        for v in self.versions[idx + 1:]:
            d = self._delta_of(v)
            if d is None or not is_reversible(d):
                return False
        return True

    def reconstruct_with_stats(self, version_number: int, verify: bool = True,
                               force_path: str = None) -> Tuple[Dict, Dict]:
        """Reconstruct version `k`, returning (state, stats).

        stats: {path, u, base_version, head_version} where u is the number of delta
        applications actually performed — the quantity Eq (36) predicts.

        force_path is a diagnostic hook: PATH_CHECKPOINT or PATH_INVERSION forces
        one branch of Algorithm 2 so the two can be compared head to head. Normal
        callers leave it None and get the cheaper path. Raises ValueError if the
        forced path is unavailable for this target.
        """
        v = self.get_version(version_number)
        if v is None:
            raise KeyError(f"twin {self.twin_id}: no version {version_number}")
        idx = self.versions.index(v)
        head = len(self.versions) - 1

        if v.kind in MATERIALIZED_KINDS and force_path is None:
            state = deepcopy(self._state_of(v))
            stats = {'path': PATH_DIRECT, 'u': 0, 'base_version': version_number,
                     'head_version': head + 1}
        else:
            base = self._base_for(idx)
            u_fwd = idx - base
            u_inv = head - idx
            if force_path == PATH_INVERSION and not self._can_invert(idx):
                raise ValueError(
                    f"inversion path unavailable for version {version_number}: the "
                    f"inverse chain is broken by a snapshot-fallback entry")
            if force_path == PATH_INVERSION:
                use_inversion = True
            elif force_path == PATH_CHECKPOINT:
                use_inversion = False
            else:
                use_inversion = u_inv < u_fwd and self._can_invert(idx)
            if use_inversion:
                # Eq (34): reconstruct backward from head
                state = deepcopy(self._prev_state)
                for i in range(head, idx, -1):
                    apply_inverse(state, self._delta_of(self.versions[i]))
                stats = {'path': PATH_INVERSION, 'u': u_inv,
                         'base_version': head + 1, 'head_version': head + 1}
            else:
                # Algorithm 2 checkpoint branch: nearest base, then forward
                state = deepcopy(self._state_of(self.versions[base]))
                for i in range(base + 1, idx + 1):
                    apply_forward(state, self._delta_of(self.versions[i]))
                stats = {'path': PATH_CHECKPOINT, 'u': u_fwd,
                         'base_version': base + 1, 'head_version': head + 1}

        if verify and digest(state) != v.digest:
            raise IntegrityViolation(
                f"twin {self.twin_id} version {version_number}: reconstructed digest "
                f"{digest(state)[:16]} != stored {v.digest[:16]}")

        self._last_recon = dict(stats, version=version_number)
        return state, stats

    def reconstruct(self, version_number: int, verify: bool = True) -> Dict:
        return self.reconstruct_with_stats(version_number, verify=verify)[0]

    def iter_states(self, verify: bool = False):
        """Bulk history path: yield (TwinVersion, state) for every version in O(n)
        total delta applications, instead of reconstructing each independently
        (which is O(n^2) and is what the versions API would otherwise do)."""
        running: Dict = {}
        for v in self.versions:
            if v.kind in MATERIALIZED_KINDS:
                running = deepcopy(self._state_of(v))
            else:
                apply_forward(running, v.payload)
            if verify and digest(running) != v.digest:
                raise IntegrityViolation(
                    f"twin {self.twin_id} version {v.version_number}: digest mismatch "
                    f"during bulk walk")
            yield v, running

    def get_version_history(self, verify: bool = False) -> List[Dict]:
        """Get all version history. Uses the bulk path."""
        return [v.to_dict(state=s) for v, s in self.iter_states(verify=verify)]

    def rollback_to_version(self, version_number: int) -> bool:
        """Rollback to a specific version (Eq 35).

        Appends a NEW head carrying s_k; history is never truncated. The digest of
        the new head equals chi_k by construction, since the state is identical.
        """
        target = self.get_version(version_number)
        if not target:
            return False
        state = self.reconstruct(version_number)
        self._add_version(state, {
            'action': 'rollback',
            'rollback_to': version_number,
            'restored_digest': target.digest,
        })
        self.current_state = deepcopy(state)
        return True

    # --- storage accounting --------------------------------------------------

    def storage_report(self) -> Dict:
        """Measured bytes of the shipped representation vs the full-snapshot model."""
        by_kind = {KIND_CHECKPOINT: 0, KIND_SNAPSHOT: 0, KIND_DELTA: 0}
        stored = 0
        for v in self.versions:
            b = v.stored_bytes()
            stored += b
            by_kind[v.kind] += b
        snapshot_equivalent = sum(len(canon(s)) for _, s in self.iter_states())
        counts = {k: sum(1 for v in self.versions if v.kind == k) for k in by_kind}
        reversible = sum(1 for v in self.versions
                         if v.kind == KIND_DELTA and is_reversible(v.payload))
        inverse_link_bytes = sum(
            len(canon(v.link)) for v in self.versions if v.link is not None)
        return {
            'versions': len(self.versions),
            'checkpoint_interval': self.checkpoint_interval,
            'reversible_window': self.reversible_window,
            'stored_bytes': stored,
            'snapshot_equivalent_bytes': snapshot_equivalent,
            'ratio_vs_snapshots': round(snapshot_equivalent / stored, 4) if stored else 0,
            'bytes_by_kind': by_kind,
            'counts_by_kind': counts,
            'reversible_deltas': reversible,
            'forward_only_deltas': counts[KIND_DELTA] - reversible,
            'checkpoint_inverse_link_bytes': inverse_link_bytes,
        }

    def verify_all(self) -> Dict:
        """Verify every version against its stored digest (Eq 33)."""
        checked, failures = 0, []
        for v in self.versions:
            try:
                self.reconstruct(v.version_number, verify=True)
                checked += 1
            except IntegrityViolation as e:
                failures.append({'version': v.version_number, 'error': str(e)})
        return {'checked': checked, 'failures': failures, 'ok': not failures}

    def add_child(self, child_id: str):
        """Add a child twin"""
        if child_id not in self.children:
            self.children.append(child_id)
            self.updated_at = datetime.now().isoformat()

    def remove_child(self, child_id: str):
        """Remove a child twin"""
        if child_id in self.children:
            self.children.remove(child_id)
            self.updated_at = datetime.now().isoformat()

    def to_dict(self, include_versions: bool = False) -> Dict:
        """Convert twin to dictionary"""
        result = {
            'twin_id': self.twin_id,
            'twin_type': self.twin_type,
            'parent_id': self.parent_id,
            'children': self.children,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'status': self.status,
            'current_version': self.current_version - 1,
            'current_state': self.current_state,
            'version_count': len(self.versions),
            'storage_format': self.storage_format,
        }

        if include_versions:
            result['versions'] = self.get_version_history()

        return result


class TwinManager:
    """Manages all digital twins with CRUD operations"""

    def __init__(self, checkpoint_interval: int = CHECKPOINT_INTERVAL,
                 reversible_window: Optional[int] = REVERSIBLE_WINDOW):
        self.twins: Dict[str, DigitalTwin] = {}
        self.checkpoint_interval = checkpoint_interval
        self.reversible_window = reversible_window

    def create_twin(self, twin_id: str, twin_type: str, initial_state: Dict,
                    metadata: Dict = None, parent_id: Optional[str] = None) -> DigitalTwin:
        """Create a new digital twin"""
        if twin_id in self.twins:
            raise ValueError(f"Twin with ID '{twin_id}' already exists")

        if parent_id and parent_id not in self.twins:
            raise ValueError(f"Parent twin '{parent_id}' does not exist")

        twin = DigitalTwin(twin_id, twin_type, initial_state, metadata, parent_id,
                           checkpoint_interval=self.checkpoint_interval,
                           reversible_window=self.reversible_window)
        self.twins[twin_id] = twin

        if parent_id:
            self.twins[parent_id].add_child(twin_id)

        return twin

    def get_twin(self, twin_id: str) -> Optional[DigitalTwin]:
        """Get a twin by ID"""
        return self.twins.get(twin_id)

    def update_twin(self, twin_id: str, new_state: Dict, metadata: Dict = None) -> bool:
        """Update a twin's state (full replacement)"""
        twin = self.get_twin(twin_id)
        if twin:
            twin.update_state(new_state, metadata)
            return True
        return False

    def patch_twin(self, twin_id: str, partial_state: Dict, metadata: Dict = None) -> bool:
        """Partially update a twin's state"""
        twin = self.get_twin(twin_id)
        if twin:
            twin.patch_state(partial_state, metadata)
            return True
        return False

    def delete_twin(self, twin_id: str, soft_delete: bool = True) -> bool:
        """Delete a twin (soft or hard delete)"""
        twin = self.get_twin(twin_id)
        if not twin:
            return False

        if soft_delete:
            twin.set_status('deleted', {'action': 'soft_delete'})
        else:
            if twin.parent_id:
                parent = self.get_twin(twin.parent_id)
                if parent:
                    parent.remove_child(twin_id)

            for child_id in twin.children[:]:
                child = self.get_twin(child_id)
                if child:
                    child.parent_id = None

            del self.twins[twin_id]

        return True

    def list_twins(self, filters: Dict = None) -> List[Dict]:
        """List all twins with optional filters"""
        result = []
        for twin in self.twins.values():
            if filters:
                if 'status' in filters and twin.status != filters['status']:
                    continue
                if 'twin_type' in filters and twin.twin_type != filters['twin_type']:
                    continue
                if 'parent_id' in filters and twin.parent_id != filters['parent_id']:
                    continue

            result.append(twin.to_dict())

        return result

    def get_twin_hierarchy(self, twin_id: str) -> Dict:
        """Get full hierarchy tree for a twin"""
        twin = self.get_twin(twin_id)
        if not twin:
            return None

        def build_tree(tid: str) -> Dict:
            t = self.get_twin(tid)
            if not t:
                return None

            tree = t.to_dict()
            tree['children_details'] = [build_tree(cid) for cid in t.children]
            return tree

        return build_tree(twin_id)

    def get_twin_ancestors(self, twin_id: str) -> List[str]:
        """Get all ancestors of a twin (parent, grandparent, etc.)"""
        ancestors = []
        twin = self.get_twin(twin_id)

        while twin and twin.parent_id:
            ancestors.append(twin.parent_id)
            twin = self.get_twin(twin.parent_id)

        return ancestors

    def get_twin_descendants(self, twin_id: str) -> List[str]:
        """Get all descendants of a twin (children, grandchildren, etc.)"""
        descendants = []
        twin = self.get_twin(twin_id)

        if not twin:
            return descendants

        def collect_descendants(tid: str):
            t = self.get_twin(tid)
            if t:
                for child_id in t.children:
                    descendants.append(child_id)
                    collect_descendants(child_id)

        collect_descendants(twin_id)
        return descendants

    def get_version_diff(self, twin_id: str, version1: int, version2: int) -> Dict:
        """Compare two versions of a twin"""
        twin = self.get_twin(twin_id)
        if not twin:
            return None

        v1 = twin.get_version(version1)
        v2 = twin.get_version(version2)

        if not v1 or not v2:
            return None

        # Materialize once each; .state would reconstruct on every access.
        s1 = twin.reconstruct(version1)
        s2 = twin.reconstruct(version2)

        diff = {
            'version1': version1,
            'version2': version2,
            'timestamp1': v1.timestamp,
            'timestamp2': v2.timestamp,
            'changes': {}
        }

        all_keys = set(s1.keys()) | set(s2.keys())
        for key in all_keys:
            val1 = s1.get(key)
            val2 = s2.get(key)
            if val1 != val2:
                diff['changes'][key] = {
                    'old': val1,
                    'new': val2
                }

        return diff

    def search_twins(self, query: str) -> List[Dict]:
        """Search twins by ID, type, or state content"""
        results = []
        query_lower = query.lower()

        for twin in self.twins.values():
            if (query_lower in twin.twin_id.lower() or
                query_lower in twin.twin_type.lower() or
                    query_lower in canon(twin.current_state).decode('utf-8').lower()):
                results.append(twin.to_dict())

        return results

    def get_statistics(self) -> Dict:
        """Get statistics about all twins"""
        stats = {
            'total_twins': len(self.twins),
            'by_status': {},
            'by_type': {},
            'total_versions': 0,
            'orphaned_twins': 0,
            'root_twins': 0
        }

        for twin in self.twins.values():
            stats['by_status'][twin.status] = stats['by_status'].get(twin.status, 0) + 1
            stats['by_type'][twin.twin_type] = stats['by_type'].get(twin.twin_type, 0) + 1
            stats['total_versions'] += len(twin.versions)
            if not twin.parent_id:
                stats['root_twins'] += 1
            # NOTE: 'orphaned_twins' is never incremented here — that is pre-existing
            # behaviour, preserved deliberately. Out of scope for Phase 3.

        return stats
