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


def test_queue_wait_vs_anchor_cost(db):
    print("\n[9] completion decomposes into queue wait + anchor cost")
    chain = StubChain()                       # each anchor costs ANCHOR_DELAY_S
    ob = Outbox(db, anchor_fn=chain)

    # Enqueue a backlog BEFORE starting the relay, so later rows must wait behind
    # earlier ones. This is the regime the decomposition exists to separate.
    n = 6
    for i in range(n):
        ob.commit_and_enqueue(f"q-{i}", f"c-{i}", f"f-{i}",
                              payload={"data_id": f"t-{i}", "metadata": {"i": i}})
    check("queue depth reflects the backlog", ob.stats()["queue_depth"] == n,
          f"depth={ob.stats()['queue_depth']}")

    ob.start_relay()
    ok = _wait(lambda: ob.stats()["queue_depth"] == 0, timeout=30)
    ob.stop_relay()
    check("relay drains the backlog", ok)

    first = ob.timing_of("q-0")
    last = ob.timing_of(f"q-{n-1}")
    for label, t in (("first", first), ("last", last)):
        check(f"{label} row decomposes",
              t and t["queue_wait_ms"] is not None and t["anchor_ms"] is not None)
        check(f"{label}: queue_wait + anchor == total (±1 ms)",
              abs((t["queue_wait_ms"] + t["anchor_ms"]) - t["total_ms"]) < 1.0,
              f"{t['queue_wait_ms']:.1f} + {t['anchor_ms']:.1f} vs {t['total_ms']:.1f}")

    # The point of the split: anchor cost is flat, queue wait is what grows.
    check("anchor cost is ~constant across backlog position",
          abs(last["anchor_ms"] - first["anchor_ms"]) < ANCHOR_DELAY_S * 1000 * 0.5,
          f"first {first['anchor_ms']:.1f} ms vs last {last['anchor_ms']:.1f} ms")
    check("queue wait grows with backlog position",
          last["queue_wait_ms"] > first["queue_wait_ms"] + ANCHOR_DELAY_S * 1000,
          f"first {first['queue_wait_ms']:.1f} ms vs last {last['queue_wait_ms']:.1f} ms")
    check("conflating them would overstate anchor cost",
          last["total_ms"] > last["anchor_ms"] * 2,
          f"total {last['total_ms']:.1f} ms vs anchor {last['anchor_ms']:.1f} ms")

    rt = ob.relay_throughput()
    check("relay reports a drain rate", rt["drain_rate_per_s"] is not None,
          f"{rt['drain_rate_per_s']} anchors/s over {rt['span_s']} s")
    # A single-threaded relay doing ANCHOR_DELAY_S per anchor cannot exceed 1/delay.
    ceiling = 1.0 / ANCHOR_DELAY_S
    check("drain rate does not exceed the single-threaded ceiling",
          rt["drain_rate_per_s"] <= ceiling * 1.15,
          f"{rt['drain_rate_per_s']:.2f} /s vs ceiling {ceiling:.2f} /s")


def test_wal_guard(db):
    print("\n[7] startup guard: refuses to run without WAL")
    ob = Outbox(db, anchor_fn=StubChain())
    mode = ob._conn().execute("PRAGMA journal_mode").fetchone()[0]
    check("WAL engaged on a supported filesystem", str(mode).lower() == "wal", str(mode))

    # Simulate the drvfs/FAT32 case, where SQLite silently reports back a mode
    # other than wal instead of erroring.
    ob._conn().execute("PRAGMA journal_mode=DELETE")
    try:
        ob._assert_wal()
        check("guard raises when journal_mode is not wal", False, "no exception")
    except RuntimeError as e:
        check("guard raises when journal_mode is not wal", True)
        check("error names the fix (OUTBOX_DB)", "OUTBOX_DB" in str(e))


def test_contract_registry():
    print("\n[8] contract address: one selection rule, stale-address guard")
    import contract_registry as cr

    nets = {
        "1700000000001": {"address": "0x1111111111111111111111111111111111111111"},
        "1700000000009": {"address": "0x9999999999999999999999999999999999999999"},
        "1700000000005": {"address": "0x5555555555555555555555555555555555555555"},
    }
    nid, addr = cr.select_network(nets)
    check("highest numeric network id wins", nid == "1700000000009", f"{nid} {addr}")
    check("not merely last-in-file order",
          nid != list(nets.keys())[-1],
          "file order would have picked 1700000000005 — this is exactly the "
          "divergence the shared rule removes")

    for bad, label in ((({}), "empty networks"),
                       ({"abc": {"address": "0x1"}}, "non-numeric ids"),
                       ({"1": {}}, "entry without an address")):
        try:
            cr.select_network(bad)
            check(f"rejects {label}", False, "no exception")
        except cr.ContractResolutionError:
            check(f"rejects {label}", True)

    class _StaleW3:
        class eth:
            chain_id = 1337
            @staticmethod
            def get_code(_):
                return b"0x"      # len 2 -> no contract
        @staticmethod
        def to_checksum_address(a):
            return a
    import json as _json
    import tempfile as _tf
    p = os.path.join(_tf.mkdtemp(), "artifact.json")
    with open(p, "w") as f:
        _json.dump({"abi": [], "networks": {
            "1337": {"address": "0x" + "ab" * 20}}}, f)
    try:
        cr.resolve(p, w3=_StaleW3(), require_code=True)
        check("stale address (no bytecode) rejected", False, "no exception")
    except cr.ContractResolutionError as e:
        check("stale address (no bytecode) rejected", True)
        check("error tells you to redeploy", "truffle migrate" in str(e))


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
        test_queue_wait_vs_anchor_cost(os.path.join(tmp, "t9.db"))
        test_wal_guard(os.path.join(tmp, "t7.db"))
        test_contract_registry()
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
