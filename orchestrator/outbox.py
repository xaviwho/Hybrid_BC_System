"""
Transactional outbox + relay worker (Phase 2, Change 1).

Implements the architectural claim of the paper: the private commit is
acknowledged to the client immediately, and the public anchor is delivered
asynchronously, at-least-once, by a background relay worker. Before this module
the anchor was executed synchronously on the request thread
(`web3.eth.wait_for_transaction_receipt` inline in the handler), so no outbox and
no relay existed at all.

Design notes that matter for the manuscript:

* Durability. SQLite on disk, WAL mode. Survives process restart, which is what
  makes the crash-recovery claim testable: a row inserted as 'pending' before a
  kill is still 'pending' after restart and is drained by the worker.

* Idempotence. The outbox primary key is the idempotency key id = H(x || t0).
  Delivery uses INSERT OR IGNORE, so a duplicate enqueue is a no-op and a
  replayed relay attempt cannot produce a second anchor. Exactly-once *effect*
  on the public ledger is obtained from at-least-once delivery plus this key.

* Atomicity boundary (honest statement). Fabric and SQLite cannot share a
  transaction. The outbox row and the dedup record D[id] are written together in
  ONE SQLite transaction, but that transaction happens AFTER the Fabric commit
  returns. If the process dies in that window the record is committed privately
  and never anchored. `find_unanchored()` exposes exactly that set for a
  reconciliation sweep. We do not claim atomicity across the two ledgers.

* Chain-agnostic. The anchor call is injected as `anchor_fn(row) -> tx_hash`.
  NOTE for the manuscript: the deployed contract exposes
  `registerData(bytes32,string,string)`; there is no `registerAnchor(id,h)`
  function on chain. The spec's name should be reconciled with the ABI.
"""

import json
import os
import sqlite3
import threading
import time

# --- Config constants (no magic numbers inline) ---
POLL_INTERVAL_S = 0.1        # relay poll cadence
MAX_ATTEMPTS = 5             # attempts before a row is marked 'failed'
BACKOFF_BASE_S = 0.5         # exponential backoff base
BACKOFF_CAP_S = 30.0         # backoff ceiling
BUSY_TIMEOUT_MS = 5000       # SQLite lock wait

STATE_PENDING = "pending"
STATE_DELIVERED = "delivered"
STATE_FAILED = "failed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
  id            TEXT PRIMARY KEY,
  twin_key      TEXT,
  version       INTEGER,
  tau           TEXT,
  commitment    TEXT,
  state         TEXT NOT NULL DEFAULT 'pending',
  attempts      INTEGER NOT NULL DEFAULT 0,
  eth_tx_hash   TEXT,
  last_error    TEXT,
  next_attempt_at REAL NOT NULL DEFAULT 0,
  payload       TEXT,
  created_at    REAL NOT NULL,
  delivery_started_at REAL,
  delivered_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_outbox_state ON outbox(state, next_attempt_at);

-- Dedup record D[id]: durable proof that this id was privately committed.
-- Written in the SAME transaction as the outbox row.
CREATE TABLE IF NOT EXISTS dedup (
  id            TEXT PRIMARY KEY,
  fabric_tx_id  TEXT,
  commitment    TEXT,
  response      TEXT,
  created_at    REAL NOT NULL
);
"""


class Outbox:
    """Durable outbox with an at-least-once relay worker."""

    def __init__(self, db_path, anchor_fn=None,
                 poll_interval_s=POLL_INTERVAL_S,
                 max_attempts=MAX_ATTEMPTS,
                 backoff_base_s=BACKOFF_BASE_S,
                 backoff_cap_s=BACKOFF_CAP_S):
        self.db_path = db_path
        self.anchor_fn = anchor_fn
        self.poll_interval_s = poll_interval_s
        self.max_attempts = max_attempts
        self.backoff_base_s = backoff_base_s
        self.backoff_cap_s = backoff_cap_s

        self._local = threading.local()
        self._worker = None
        self._stop = threading.Event()
        self._delivered_count = 0
        self._failed_count = 0

        d = os.path.dirname(os.path.abspath(db_path))
        if d:
            os.makedirs(d, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(outbox)")}
            if "delivery_started_at" not in cols:
                c.execute("ALTER TABLE outbox ADD COLUMN delivery_started_at REAL")
        self._assert_wal()

    def _assert_wal(self):
        """Refuse to run unless the database is genuinely in WAL mode.

        SQLite does not error when it cannot honour `PRAGMA journal_mode=WAL`; it
        silently reports back the mode it actually used. On a drvfs/FAT32 mount —
        which is where OUTBOX_DB lands if the env var is unset, since the repo
        sits on the Windows drive — WAL cannot work: it needs a shared-memory
        -shm file and POSIX advisory locking, and the mount provides neither.

        The result would be an outbox with no write-ahead log while still
        claiming durability. exp5's crash-recovery and exactly-once results would
        be measured against a store that cannot deliver the property they test,
        with nothing visible to say so. Fail at startup instead.
        """
        mode = self._conn().execute("PRAGMA journal_mode").fetchone()[0]
        if str(mode).lower() != "wal":
            raise RuntimeError(
                f"outbox at {self.db_path!r} is in journal_mode={mode!r}, not 'wal'.\n"
                f"SQLite silently refuses WAL on filesystems without shared memory "
                f"and POSIX locking (drvfs / FAT32 / some network mounts).\n"
                f"Durability and crash-recovery are NOT guaranteed in this mode, so "
                f"exactly-once results measured against it would be worthless.\n"
                f"Fix: point OUTBOX_DB at a native Linux filesystem, e.g.\n"
                f"    mkdir -p /root/orbit-state && "
                f"export OUTBOX_DB=/root/orbit-state/outbox.db"
            )

    # --- connection handling: one connection per thread, WAL for concurrency ---

    def _conn(self):
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.db_path, timeout=BUSY_TIMEOUT_MS / 1000.0)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=FULL")   # durability over speed
            c.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            self._local.conn = c
        return c

    # --- write path (request thread) ---

    def commit_and_enqueue(self, record_id, commitment, fabric_tx_id,
                           twin_key=None, version=None, tau=None,
                           payload=None, response=None, anchor_required=True):
        """Persist dedup record D[id] and (if publishable) the outbox row.

        ONE SQLite transaction. Returns True if an outbox row now exists for this
        id (either just inserted or already present from a duplicate request).

        anchor_required=False is the all-sensitive case: nothing is publishable,
        so the record is committed privately and no outbox row is created.
        """
        now = time.time()
        c = self._conn()
        with c:  # BEGIN ... COMMIT / ROLLBACK
            c.execute(
                "INSERT OR IGNORE INTO dedup (id, fabric_tx_id, commitment, response, created_at)"
                " VALUES (?,?,?,?,?)",
                (record_id, fabric_tx_id, commitment,
                 json.dumps(response) if response is not None else None, now),
            )
            if not anchor_required:
                return False
            c.execute(
                "INSERT OR IGNORE INTO outbox"
                " (id, twin_key, version, tau, commitment, state, attempts,"
                "  next_attempt_at, payload, created_at)"
                " VALUES (?,?,?,?,?,?,0,?,?,?)",
                (record_id, twin_key, version, tau, commitment, STATE_PENDING,
                 now, json.dumps(payload) if payload is not None else None, now),
            )
        return True

    def get_dedup(self, record_id):
        r = self._conn().execute("SELECT * FROM dedup WHERE id=?", (record_id,)).fetchone()
        return dict(r) if r else None

    def get(self, record_id):
        r = self._conn().execute("SELECT * FROM outbox WHERE id=?", (record_id,)).fetchone()
        return dict(r) if r else None

    def find_unanchored(self):
        """Reconciliation set: privately committed (dedup row) but no outbox row.

        This is the documented failure window of section 1b — a crash between the
        Fabric commit and the SQLite transaction. A sweep over Fabric keys can be
        cross-checked against this.
        """
        rows = self._conn().execute(
            "SELECT d.id, d.fabric_tx_id, d.created_at FROM dedup d"
            " LEFT JOIN outbox o ON o.id = d.id WHERE o.id IS NULL"
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self):
        c = self._conn()
        out = {s: 0 for s in (STATE_PENDING, STATE_DELIVERED, STATE_FAILED)}
        for r in c.execute("SELECT state, COUNT(*) n FROM outbox GROUP BY state"):
            out[r["state"]] = r["n"]
        out["dedup_records"] = c.execute("SELECT COUNT(*) n FROM dedup").fetchone()["n"]
        out["unanchored"] = len(self.find_unanchored())
        out["relay_running"] = bool(self._worker and self._worker.is_alive())
        # queue depth is what exp1 samples alongside each completion-latency sample
        out["queue_depth"] = out[STATE_PENDING]
        out["relay"] = self.relay_throughput()
        return out

    def drain_stats(self):
        """Delivery latency stats over delivered rows: delivered_at - created_at."""
        rows = self._conn().execute(
            "SELECT (delivered_at - created_at) * 1000.0 AS ms FROM outbox"
            " WHERE state=? AND delivered_at IS NOT NULL", (STATE_DELIVERED,)
        ).fetchall()
        return [r["ms"] for r in rows]

    def timing_of(self, record_id):
        """Decompose one row's delivery into queue wait and anchor cost.

        total = delivered_at - created_at
              = queue_wait  (created_at -> delivery_started_at)
              + anchor      (delivery_started_at -> delivered_at)

        The split matters: queue wait is a property of relay SCHEDULING and grows
        with offered load against a single-threaded relay; anchor cost is a
        property of the CHAIN. Reporting their sum as "anchor latency" would
        attribute a queueing artifact to Ethereum.
        """
        r = self.get(record_id)
        if not r or not r.get("delivered_at"):
            return None
        created, started, done = r["created_at"], r.get("delivery_started_at"), r["delivered_at"]
        out = {"total_ms": round((done - created) * 1000.0, 3),
               "queue_wait_ms": None, "anchor_ms": None, "attempts": r["attempts"]}
        if started is not None:
            out["queue_wait_ms"] = round((started - created) * 1000.0, 3)
            out["anchor_ms"] = round((done - started) * 1000.0, 3)
        return out

    def relay_throughput(self):
        """Observed drain rate of the relay — deliveries per second.

        This is a real system property: the public-anchoring throughput ceiling
        of a single-threaded relay. It is NOT the inverse of anchor latency once
        the relay is saturated, and it must not be conflated with it.

        Measured over the span of delivered rows, so it reflects sustained rate
        rather than a single sample.
        """
        r = self._conn().execute(
            "SELECT COUNT(*) n, MIN(delivered_at) lo, MAX(delivered_at) hi,"
            "       AVG((delivered_at - delivery_started_at) * 1000.0) anchor_ms,"
            "       AVG((delivery_started_at - created_at) * 1000.0) queue_ms"
            "  FROM outbox WHERE state=? AND delivered_at IS NOT NULL"
            "   AND delivery_started_at IS NOT NULL", (STATE_DELIVERED,)
        ).fetchone()
        n = r["n"] or 0
        span = (r["hi"] - r["lo"]) if (n > 1 and r["hi"] and r["lo"]) else 0.0
        return {
            "delivered": n,
            "span_s": round(span, 4),
            # n-1 intervals across n deliveries
            "drain_rate_per_s": round((n - 1) / span, 4) if span > 0 else None,
            "mean_anchor_ms": round(r["anchor_ms"], 3) if r["anchor_ms"] else None,
            "mean_queue_wait_ms": round(r["queue_ms"], 3) if r["queue_ms"] else None,
            "note": ("drain_rate_per_s is the relay's sustained delivery rate — the "
                     "single-threaded public-anchoring ceiling. Distinct from "
                     "1/mean_anchor_ms, which ignores queueing."),
        }

    # --- relay worker (background thread; never touches the request thread) ---

    def start_relay(self):
        if self._worker and self._worker.is_alive():
            return self._worker
        self._stop.clear()
        self._worker = threading.Thread(target=self._relay_loop, name="outbox-relay",
                                        daemon=True)
        self._worker.start()
        return self._worker

    def stop_relay(self, timeout=5.0):
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=timeout)

    def _claim_one(self):
        """Atomically claim one due pending row (single-worker safe, and safe for
        multiple workers via the state transition being inside a transaction)."""
        now = time.time()
        c = self._conn()
        with c:
            r = c.execute(
                "SELECT * FROM outbox WHERE state=? AND next_attempt_at<=?"
                " ORDER BY created_at LIMIT 1", (STATE_PENDING, now)
            ).fetchone()
            if not r:
                return None
            # Reserve it by pushing next_attempt_at forward; if delivery crashes,
            # the row returns to the queue after the backoff rather than spinning.
            c.execute("UPDATE outbox SET next_attempt_at=? WHERE id=?",
                      (now + self.backoff_cap_s, r["id"]))
            return dict(r)

    def _relay_loop(self):
        while not self._stop.is_set():
            try:
                row = self._claim_one()
                if row is None:
                    self._stop.wait(self.poll_interval_s)
                    continue
                self.deliver(row)
            except Exception as e:  # never let the worker die
                print(f"[outbox] relay loop error: {e}")
                self._stop.wait(self.poll_interval_s)

    def deliver(self, row):
        """Attempt one delivery. Used by the worker and by tests directly.

        Guarded: a row that is no longer 'pending' is never anchored again. Without
        this, a replayed delivery (second worker, manual retry, or a re-read of a
        claimed row) produces a SECOND anchor for one record — which would break
        the exactly-once claim of Section III-E at the application layer.
        """
        if self.anchor_fn is None:
            raise RuntimeError("Outbox.anchor_fn is not configured")
        rid = row["id"]

        current = self.get(rid)
        if current is None:
            raise RuntimeError(f"outbox row {rid} disappeared")
        if current["state"] != STATE_PENDING:
            # Already delivered (or permanently failed). Idempotent no-op.
            return current["eth_tx_hash"]

        # Stamp when the chain call actually begins. delivered_at - created_at
        # conflates two very different things: how long the row sat in the queue
        # behind other work, and how long the anchor itself took. Only the second
        # is a property of the chain; the first is a property of relay
        # scheduling and scales with offered load.
        started = time.time()
        with self._conn() as c:
            c.execute("UPDATE outbox SET delivery_started_at=? WHERE id=?",
                      (started, rid))
        try:
            tx_hash = self.anchor_fn(row)
            now = time.time()
            c = self._conn()
            with c:
                # Conditional update: only a still-pending row transitions, so two
                # racing workers cannot both record a delivery.
                c.execute(
                    "UPDATE outbox SET state=?, eth_tx_hash=?, delivered_at=?,"
                    " attempts=attempts+1, last_error=NULL WHERE id=? AND state=?",
                    (STATE_DELIVERED, tx_hash, now, rid, STATE_PENDING),
                )
            self._delivered_count += 1
            return tx_hash
        except Exception as e:
            attempts = row["attempts"] + 1
            backoff = min(self.backoff_base_s * (2 ** (attempts - 1)), self.backoff_cap_s)
            state = STATE_FAILED if attempts >= self.max_attempts else STATE_PENDING
            if state == STATE_FAILED:
                self._failed_count += 1
                print(f"[outbox] row {rid} FAILED after {attempts} attempts: {e}")
            c = self._conn()
            with c:
                c.execute(
                    "UPDATE outbox SET state=?, attempts=?, last_error=?,"
                    " next_attempt_at=? WHERE id=?",
                    (state, attempts, str(e)[:500], time.time() + backoff, rid),
                )
            return None
