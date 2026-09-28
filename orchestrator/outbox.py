"""
Transactional outbox + relay worker (Phase 2, Change 1; revised in WS0.5).

Implements the architectural claim of the paper: the private commit is
acknowledged to the client immediately, and the public anchor is delivered
asynchronously, at-least-once, by a relay worker. Before this module the anchor
was executed synchronously on the request thread
(`web3.eth.wait_for_transaction_receipt` inline in the handler), so no outbox and
no relay existed at all.

Design notes that matter for the manuscript:

* Durability. SQLite on disk, WAL mode. Survives process restart, which is what
  makes the crash-recovery claim testable: a row inserted as 'pending' before a
  kill is still 'pending' after restart and is drained by the worker.

* Idempotence. The outbox primary key is the idempotency key id. Enqueue uses
  INSERT OR IGNORE, so a duplicate enqueue is a no-op, and delivery only
  transitions a still-pending row. Exactly-once *effect* on the public ledger
  comes from at-least-once delivery plus the on-chain uniqueness revert.

* Atomicity boundary (honest statement). Fabric and SQLite cannot share a
  transaction. The outbox row and the dedup record D[id] are written together in
  ONE SQLite transaction, but that transaction happens AFTER the Fabric commit
  returns. If the process dies in that window the record is committed privately
  and has NEITHER row. Only a sweep that reads Fabric can find it (WS5).
  `find_unanchored()` checks the weaker invariant that no HYBRID dedup row lacks
  its outbox row.

* Multiple relays (WS0.5, AUDIT_WS0 F5). A row is claimed under
  `BEGIN IMMEDIATE`, so two relays cannot select the same row, and the claim is a
  lease (`claimed_by`, `lease_until`) that expires if the claimant dies. Relays
  may run in-process (v1 behaviour) or as separate processes (relay_worker.py);
  each writes a heartbeat to the `relays` table.

* Clocks (WS0.5, AUDIT_WS0 F1). Every duration is a difference of
  time.monotonic() stamps (`*_mono` columns). CLOCK_MONOTONIC is system-wide, so
  stamps from the orchestrator and from a separate relay process on the same
  host are comparable. The wall-clock columns are kept as labels only; on WSL2
  the wall clock is stepped by seconds at a time.

* Chain-agnostic. The anchor call is injected as `anchor_fn(row) -> tx_hash`.
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
LEASE_S = 30.0               # claim lease; a dead claimant's row is re-claimable after this
BUSY_TIMEOUT_MS = 5000       # SQLite lock wait
HEARTBEAT_S = 1.0            # relay heartbeat period
RELAY_ALIVE_S = 5.0          # a relay is 'running' if it beat within this window

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

-- One row per relay process (or in-process relay thread).
CREATE TABLE IF NOT EXISTS relays (
  relay_id       TEXT PRIMARY KEY,
  pid            INTEGER,
  account        TEXT,
  started_at     REAL,
  heartbeat_mono REAL,
  delivered      INTEGER NOT NULL DEFAULT 0,
  failed         INTEGER NOT NULL DEFAULT 0
);
"""

# Columns added after v1. Applied with ALTER TABLE so a v1 database still opens.
_ADDED_COLUMNS = {
    "outbox": [
        ("delivery_started_at", "REAL"),
        ("sigma", "TEXT"),            # canonical sigma; commitment = H(sigma)
        ("created_mono", "REAL"),
        ("started_mono", "REAL"),
        ("delivered_mono", "REAL"),
        ("claimed_by", "TEXT"),
        ("lease_until_mono", "REAL"),
        ("delivered_by", "TEXT"),
    ],
    "dedup": [
        ("route", "TEXT"),            # HYBRID | FABRIC_ONLY
    ],
}


class Outbox:
    """Durable outbox with an at-least-once relay worker."""

    def __init__(self, db_path, anchor_fn=None,
                 poll_interval_s=POLL_INTERVAL_S,
                 max_attempts=MAX_ATTEMPTS,
                 backoff_base_s=BACKOFF_BASE_S,
                 backoff_cap_s=BACKOFF_CAP_S,
                 lease_s=LEASE_S,
                 relay_id=None, relay_account=None):
        self.db_path = db_path
        self.anchor_fn = anchor_fn
        self.poll_interval_s = poll_interval_s
        self.max_attempts = max_attempts
        self.backoff_base_s = backoff_base_s
        self.backoff_cap_s = backoff_cap_s
        self.lease_s = lease_s
        self.relay_id = relay_id or f"inproc-{os.getpid()}"
        self.relay_account = relay_account

        self._local = threading.local()
        self._worker = None
        self._stop = threading.Event()
        self._delivered_count = 0
        self._failed_count = 0
        self._last_beat = 0.0

        d = os.path.dirname(os.path.abspath(db_path))
        if d:
            os.makedirs(d, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)
            for table, cols in _ADDED_COLUMNS.items():
                have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
                for name, typ in cols:
                    if name not in have:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
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
                           payload=None, response=None, anchor_required=True,
                           sigma=None):
        """Persist dedup record D[id] and (if publishable) the outbox row.

        ONE SQLite transaction. Returns True if an outbox row now exists for this
        id (either just inserted or already present from a duplicate request).

        anchor_required=False is the FABRIC_ONLY case: nothing is publishable,
        so the record is committed privately and no outbox row is created.
        """
        now, mono = time.time(), time.monotonic()
        route = "HYBRID" if anchor_required else "FABRIC_ONLY"
        c = self._conn()
        with c:  # BEGIN ... COMMIT / ROLLBACK
            c.execute(
                "INSERT OR IGNORE INTO dedup"
                " (id, fabric_tx_id, commitment, response, created_at, route)"
                " VALUES (?,?,?,?,?,?)",
                (record_id, fabric_tx_id, commitment,
                 json.dumps(response) if response is not None else None, now, route),
            )
            if not anchor_required:
                return False
            c.execute(
                "INSERT OR IGNORE INTO outbox"
                " (id, twin_key, version, tau, commitment, state, attempts,"
                "  next_attempt_at, payload, created_at, created_mono, sigma)"
                " VALUES (?,?,?,?,?,?,0,?,?,?,?,?)",
                (record_id, twin_key, version, tau, commitment, STATE_PENDING,
                 mono, json.dumps(payload) if payload is not None else None, now,
                 mono, sigma),
            )
        return True

    def record_response(self, record_id, response):
        """Store the client response on D[id] so a replay after restart can serve it."""
        c = self._conn()
        with c:
            c.execute("UPDATE dedup SET response=? WHERE id=?",
                      (json.dumps(response), record_id))

    def get_dedup(self, record_id):
        r = self._conn().execute("SELECT * FROM dedup WHERE id=?", (record_id,)).fetchone()
        return dict(r) if r else None

    def get(self, record_id):
        r = self._conn().execute("SELECT * FROM outbox WHERE id=?", (record_id,)).fetchone()
        return dict(r) if r else None

    def find_unanchored(self):
        """HYBRID dedup rows with no outbox row. Empty by construction.

        Dedup and outbox rows are written in one transaction, so a non-empty
        result means that invariant broke. The crash window (Fabric committed,
        process died before this transaction) leaves NO row here; finding it
        requires the Fabric-side sweep of WS5.

        Before WS0.5 this returned every dedup row without an outbox row, which
        was exactly the FABRIC_ONLY records: correct, unanchored by design, and
        not a reconciliation target.
        """
        rows = self._conn().execute(
            "SELECT d.id, d.fabric_tx_id, d.created_at FROM dedup d"
            " LEFT JOIN outbox o ON o.id = d.id"
            " WHERE o.id IS NULL AND COALESCE(d.route, 'HYBRID') = 'HYBRID'"
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self):
        c = self._conn()
        out = {s: 0 for s in (STATE_PENDING, STATE_DELIVERED, STATE_FAILED)}
        for r in c.execute("SELECT state, COUNT(*) n FROM outbox GROUP BY state"):
            out[r["state"]] = r["n"]
        out["dedup_records"] = c.execute("SELECT COUNT(*) n FROM dedup").fetchone()["n"]
        out["unanchored"] = len(self.find_unanchored())
        relays = self.relays()
        out["relays"] = relays
        out["relays_alive"] = sum(1 for r in relays if r["alive"])
        out["relay_running"] = (bool(self._worker and self._worker.is_alive())
                                or out["relays_alive"] > 0)
        # queue depth is what exp1 samples alongside each completion-latency sample
        out["queue_depth"] = out[STATE_PENDING]
        out["relay"] = self.relay_throughput()
        return out

    def relays(self):
        now = time.monotonic()
        rows = self._conn().execute("SELECT * FROM relays ORDER BY relay_id").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["alive"] = (d["heartbeat_mono"] is not None
                          and now - d["heartbeat_mono"] <= RELAY_ALIVE_S)
            out.append(d)
        return out

    def drain_stats(self):
        """Delivery latency over delivered rows, monotonic: delivered - created."""
        rows = self._conn().execute(
            "SELECT (delivered_mono - created_mono) * 1000.0 AS ms FROM outbox"
            " WHERE state=? AND delivered_mono IS NOT NULL AND created_mono IS NOT NULL",
            (STATE_DELIVERED,)
        ).fetchall()
        return [r["ms"] for r in rows]

    def timing_of(self, record_id):
        """Decompose one row's delivery into queue wait and anchor cost.

        total = delivered - created
              = queue_wait  (created -> delivery started)
              + anchor      (delivery started -> delivered)

        The split matters: queue wait is a property of relay SCHEDULING and grows
        with offered load; anchor cost is a property of the CHAIN. Reporting their
        sum as "anchor latency" would attribute a queueing artifact to Ethereum.

        Monotonic stamps only. A v1 row (no *_mono columns) returns None rather
        than a wall-clock difference that may contain a clock step.
        """
        r = self.get(record_id)
        if not r or r.get("delivered_mono") is None or r.get("created_mono") is None:
            return None
        created, started, done = r["created_mono"], r.get("started_mono"), r["delivered_mono"]
        out = {"total_ms": round((done - created) * 1000.0, 3),
               "queue_wait_ms": None, "anchor_ms": None, "attempts": r["attempts"],
               "clock": "monotonic"}
        if started is not None:
            out["queue_wait_ms"] = round((started - created) * 1000.0, 3)
            out["anchor_ms"] = round((done - started) * 1000.0, 3)
        return out

    def relay_throughput(self):
        """Observed drain rate over delivered rows — deliveries per second.

        This is the delivery rate actually achieved over the span of delivered
        rows. It equals the relay's capacity mu_relay ONLY if the relay was
        saturated (queue never empty) over that span; otherwise it is the offered
        rate (AUDIT_WS0 F9). WS3 measures mu_relay under saturation.
        """
        r = self._conn().execute(
            "SELECT COUNT(*) n, MIN(delivered_mono) lo, MAX(delivered_mono) hi,"
            "       AVG((delivered_mono - started_mono) * 1000.0) anchor_ms,"
            "       AVG((started_mono - created_mono) * 1000.0) queue_ms"
            "  FROM outbox WHERE state=? AND delivered_mono IS NOT NULL"
            "   AND started_mono IS NOT NULL AND created_mono IS NOT NULL",
            (STATE_DELIVERED,)
        ).fetchone()
        n = r["n"] or 0
        span = (r["hi"] - r["lo"]) if (n > 1 and r["hi"] and r["lo"]) else 0.0
        return {
            "delivered": n,
            "span_s": round(span, 4),
            # n-1 intervals across n deliveries
            "delivery_rate_per_s": round((n - 1) / span, 4) if span > 0 else None,
            "mean_anchor_ms": round(r["anchor_ms"], 3) if r["anchor_ms"] else None,
            "mean_queue_wait_ms": round(r["queue_ms"], 3) if r["queue_ms"] else None,
            "note": ("delivery_rate_per_s is the achieved rate over the delivered "
                     "span. It is mu_relay only under saturation."),
        }

    # --- relay worker ---

    def start_relay(self):
        """Run the relay loop on a background thread of this process."""
        if self._worker and self._worker.is_alive():
            return self._worker
        self._stop.clear()
        self._worker = threading.Thread(target=self.run_relay, name="outbox-relay",
                                        daemon=True)
        self._worker.start()
        return self._worker

    def stop_relay(self, timeout=5.0):
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=timeout)

    def _heartbeat(self, force=False):
        now = time.monotonic()
        if not force and now - self._last_beat < HEARTBEAT_S:
            return
        self._last_beat = now
        c = self._conn()
        with c:
            c.execute(
                "INSERT INTO relays (relay_id, pid, account, started_at, heartbeat_mono,"
                " delivered, failed) VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(relay_id) DO UPDATE SET pid=excluded.pid,"
                " account=excluded.account, heartbeat_mono=excluded.heartbeat_mono,"
                " delivered=excluded.delivered, failed=excluded.failed",
                (self.relay_id, os.getpid(), self.relay_account, time.time(), now,
                 self._delivered_count, self._failed_count),
            )

    def _claim_one(self):
        """Atomically claim one due row under an exclusive write lock.

        BEGIN IMMEDIATE takes SQLite's RESERVED lock before the SELECT, so no
        other connection (thread or process) can claim between our read and our
        write. Before WS0.5 the SELECT ran outside any write transaction and two
        relays could select the same row (AUDIT_WS0 F5).

        Due means: pending, past its backoff, and not under another relay's live
        lease. A claimant that dies leaves its lease to expire after lease_s.
        """
        now = time.monotonic()
        c = self._conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            r = c.execute(
                "SELECT * FROM outbox WHERE state=? AND next_attempt_at<=?"
                " AND (lease_until_mono IS NULL OR lease_until_mono<=?)"
                " ORDER BY created_mono LIMIT 1", (STATE_PENDING, now, now)
            ).fetchone()
            if not r:
                c.execute("COMMIT")
                return None
            c.execute("UPDATE outbox SET claimed_by=?, lease_until_mono=? WHERE id=?",
                      (self.relay_id, now + self.lease_s, r["id"]))
            c.execute("COMMIT")
            return dict(r)
        except Exception:
            c.execute("ROLLBACK")
            raise

    def run_relay(self):
        """The relay loop. Used by start_relay() and by relay_worker.py."""
        self._heartbeat(force=True)
        while not self._stop.is_set():
            try:
                self._heartbeat()
                row = self._claim_one()
                if row is None:
                    self._stop.wait(self.poll_interval_s)
                    continue
                self.deliver(row)
            except Exception as e:  # never let the worker die
                print(f"[outbox] relay loop error: {e}")
                self._stop.wait(self.poll_interval_s)
        self._heartbeat(force=True)

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

        # Stamp when the chain call actually begins, so queue wait and anchor
        # cost can be separated (see timing_of).
        started, started_mono = time.time(), time.monotonic()
        with self._conn() as c:
            c.execute("UPDATE outbox SET delivery_started_at=?, started_mono=? WHERE id=?",
                      (started, started_mono, rid))
        try:
            tx_hash = self.anchor_fn(row)
            now, mono = time.time(), time.monotonic()
            c = self._conn()
            with c:
                # Conditional update: only a still-pending row transitions, so two
                # racing workers cannot both record a delivery.
                c.execute(
                    "UPDATE outbox SET state=?, eth_tx_hash=?, delivered_at=?,"
                    " delivered_mono=?, delivered_by=?, lease_until_mono=NULL,"
                    " attempts=attempts+1, last_error=NULL WHERE id=? AND state=?",
                    (STATE_DELIVERED, tx_hash, now, mono, self.relay_id,
                     rid, STATE_PENDING),
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
                    " next_attempt_at=?, lease_until_mono=NULL WHERE id=?",
                    (state, attempts, str(e)[:500], time.monotonic() + backoff, rid),
                )
            return None
