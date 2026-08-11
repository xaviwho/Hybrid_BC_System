#!/usr/bin/env python3
"""
Acceptance tests for the transactional outbox + relay worker (Phase 2, Change 1).

Runs WITHOUT the blockchain stack: the anchor call is stubbed so the outbox's own
guarantees — durability, idempotence, crash recovery, backoff — are tested in
isolation. Chain-side behaviour is verified separately by exp5 against Ganache.

Usage:  python tests/test_outbox_relay.py
"""

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "orchestrator"))
from outbox import Outbox, STATE_PENDING, STATE_DELIVERED, STATE_FAILED  # noqa: E402

ANCHOR_DELAY_S = 0.05   # stands in for the Ethereum receipt wait
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


class StubChain:
    """Counts anchor calls so a second anchor for one id is detectable."""

    def __init__(self, fail_times=0):
        self.calls = []
        self.fail_times = fail_times
        self.lock = threading.Lock()

    def __call__(self, row):
        with self.lock:
            self.calls.append(row["id"])
            n = len(self.calls)
        if n <= self.fail_times:
            raise RuntimeError("simulated chain failure")
        time.sleep(ANCHOR_DELAY_S)
        return f"0xstub{n:04d}"

    def count_for(self, rid):
        return sum(1 for c in self.calls if c == rid)


def _wait(pred, timeout=10.0, interval=0.02):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(interval)
    return False


def test_happy_path(db):
    print("\n[1] pending -> delivered, delivered_at > created_at, gap ~ anchor duration")
    chain = StubChain()
    ob = Outbox(db, anchor_fn=chain)
    ob.commit_and_enqueue("rec-1", "commit-hash-1", "fabtx-1", twin_key="twin-a",
                          payload={"data_id": "twin-a", "metadata": {"t": 1}})
    check("row starts pending", ob.get("rec-1")["state"] == STATE_PENDING)
    ob.start_relay()
    ok = _wait(lambda: ob.get("rec-1")["state"] == STATE_DELIVERED)
    ob.stop_relay()
    row = ob.get("rec-1")
    check("row reaches delivered", ok, f"state={row['state']}")
    check("eth_tx_hash written", bool(row["eth_tx_hash"]), str(row["eth_tx_hash"]))
    gap = (row["delivered_at"] or 0) - row["created_at"]
    check("delivered_at > created_at", gap > 0, f"gap={gap*1000:.1f} ms")
    check("gap ~ anchor duration", gap >= ANCHOR_DELAY_S,
          f"gap={gap*1000:.1f} ms vs anchor {ANCHOR_DELAY_S*1000:.0f} ms")
    check("exactly one anchor call", chain.count_for("rec-1") == 1,
          f"calls={chain.count_for('rec-1')}")


def test_duplicate_submission(db):
    print("\n[2] same payload twice -> one outbox row, one anchor")
    chain = StubChain()
    ob = Outbox(db, anchor_fn=chain)
    for _ in range(2):
        ob.commit_and_enqueue("rec-dup", "commit-dup", "fabtx-dup",
                              payload={"data_id": "twin-b", "metadata": {"t": 2}})
    n_rows = ob._conn().execute(
        "SELECT COUNT(*) n FROM outbox WHERE id='rec-dup'").fetchone()["n"]
    check("one outbox row for duplicate enqueue", n_rows == 1, f"rows={n_rows}")
    ob.start_relay()
    _wait(lambda: ob.get("rec-dup")["state"] == STATE_DELIVERED)
    # A replayed relay attempt after delivery must not anchor again.
    ob.deliver(ob.get("rec-dup"))
    ob.stop_relay()
    check("exactly one anchor for duplicate", chain.count_for("rec-dup") == 1,
          f"calls={chain.count_for('rec-dup')}")


def test_crash_recovery(db):
    print("\n[3] kill between Fabric commit and anchor -> restart drains, one anchor")
    chain = StubChain()
    # Process A: enqueue, never start the relay (== killed before anchoring).
    ob_a = Outbox(db, anchor_fn=chain)
    ob_a.commit_and_enqueue("rec-crash", "commit-crash", "fabtx-crash",
                            payload={"data_id": "twin-c", "metadata": {"t": 3}})
    del ob_a
    check("row survives process death as pending",
          Outbox(db, anchor_fn=chain).get("rec-crash")["state"] == STATE_PENDING)
    # Process B: fresh instance on the same DB file.
    ob_b = Outbox(db, anchor_fn=chain)
    ob_b.start_relay()
    ok = _wait(lambda: ob_b.get("rec-crash")["state"] == STATE_DELIVERED)
    ob_b.stop_relay()
    check("restarted worker drains the pending row", ok)
    check("exactly one anchor after recovery", chain.count_for("rec-crash") == 1,
          f"calls={chain.count_for('rec-crash')}")


def test_all_sensitive_no_outbox_row(db):
    print("\n[4] record with no publishable fields -> dedup row, no outbox row")
    ob = Outbox(db, anchor_fn=StubChain())
    created = ob.commit_and_enqueue("rec-sens", "commit-sens", "fabtx-sens",
                                    anchor_required=False)
    check("enqueue reports no outbox row", created is False)
    check("no outbox row exists", ob.get("rec-sens") is None)
    check("dedup record persisted (committed privately)",
          ob.get_dedup("rec-sens") is not None)
    check("counted in reconciliation set (privately committed, unanchored)",
          any(r["id"] == "rec-sens" for r in ob.find_unanchored()))


def test_retry_and_failure(db):
    print("\n[5] transient failure -> retry with backoff; permanent -> failed")
    chain = StubChain(fail_times=2)          # first two attempts raise
    ob = Outbox(db, anchor_fn=chain, backoff_base_s=0.05, backoff_cap_s=0.2)
    ob.commit_and_enqueue("rec-retry", "commit-retry", "fabtx-retry",
                          payload={"data_id": "twin-d", "metadata": {"t": 5}})
    ob.start_relay()
    ok = _wait(lambda: ob.get("rec-retry")["state"] == STATE_DELIVERED, timeout=15)
    ob.stop_relay()
    row = ob.get("rec-retry")
    check("delivers after transient failures", ok, f"state={row['state']}")
    check("attempts recorded", row["attempts"] >= 3, f"attempts={row['attempts']}")

    chain2 = StubChain(fail_times=10 ** 6)   # always fails
    ob2 = Outbox(db, anchor_fn=chain2, max_attempts=3,
                 backoff_base_s=0.02, backoff_cap_s=0.05)
    ob2.commit_and_enqueue("rec-dead", "commit-dead", "fabtx-dead",
                           payload={"data_id": "twin-e", "metadata": {"t": 6}})
    ob2.start_relay()
    ok2 = _wait(lambda: ob2.get("rec-dead")["state"] == STATE_FAILED, timeout=15)
    ob2.stop_relay()
    row2 = ob2.get("rec-dead")
    check("gives up as failed after max_attempts", ok2, f"state={row2['state']}")
    check("stops at max_attempts", row2["attempts"] == 3, f"attempts={row2['attempts']}")
    check("last_error recorded", bool(row2["last_error"]))


def test_request_thread_isolation(db):
    print("\n[6] enqueue does not block on the anchor (response boundary)")
    chain = StubChain()
    ob = Outbox(db, anchor_fn=chain)
    ob.start_relay()
    t0 = time.perf_counter()
    ob.commit_and_enqueue("rec-fast", "commit-fast", "fabtx-fast",
                          payload={"data_id": "twin-f", "metadata": {"t": 7}})
    enqueue_ms = (time.perf_counter() - t0) * 1000
    _wait(lambda: ob.get("rec-fast")["state"] == STATE_DELIVERED)
    ob.stop_relay()
    check("enqueue far cheaper than the anchor it replaces",
          enqueue_ms < ANCHOR_DELAY_S * 1000,
          f"enqueue={enqueue_ms:.2f} ms vs anchor={ANCHOR_DELAY_S*1000:.0f} ms")


def main():
    print("=" * 72)
    print("  OUTBOX + RELAY ACCEPTANCE TESTS (Phase 2, Change 1)")
    print("=" * 72)
    tmp = tempfile.mkdtemp(prefix="outbox_test_")
    try:
        test_happy_path(os.path.join(tmp, "t1.db"))
        test_duplicate_submission(os.path.join(tmp, "t2.db"))
        test_crash_recovery(os.path.join(tmp, "t3.db"))
        test_all_sensitive_no_outbox_row(os.path.join(tmp, "t4.db"))
        test_retry_and_failure(os.path.join(tmp, "t5.db"))
        test_request_thread_isolation(os.path.join(tmp, "t6.db"))
    finally:
        print("\n" + "=" * 72)
        print(f"  {len(PASS)} passed, {len(FAIL)} failed")
        if FAIL:
            for f in FAIL:
                print(f"    FAILED: {f}")
        print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
