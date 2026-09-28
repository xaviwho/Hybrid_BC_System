"""AUDIT_WS0 F5 evidence: two v1 relays on one queue, counting anchor calls.

Imports the v1 outbox from the tagged tree (git show v1-submitted:...), so the
code under test is exactly what produced v1. The stub anchor sleeps 50 ms like
tests/test_outbox_relay.py. Repeated TRIALS times.
"""
import collections
import importlib.util
import os
import sys
import tempfile
import threading
import time

V1_OUTBOX = sys.argv[1]
TRIALS, N = 20, 40
spec = importlib.util.spec_from_file_location("outbox_v1", V1_OUTBOX)
ob_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ob_mod)

total_dupes = total_rows = 0
per_trial = []
for t in range(TRIALS):
    calls = collections.Counter()
    lock = threading.Lock()

    def anchor(row):
        with lock:
            calls[row["id"]] += 1
        time.sleep(0.05)
        return "0xstub"

    db = os.path.join(tempfile.mkdtemp(dir="/root/ws05_test/tmp"), "o.db")
    seed = ob_mod.Outbox(db, anchor_fn=anchor)
    for i in range(N):
        seed.commit_and_enqueue(f"r-{i}", f"c-{i}", f"f-{i}", payload={"i": i})
    a = ob_mod.Outbox(db, anchor_fn=anchor, poll_interval_s=0.001)
    b = ob_mod.Outbox(db, anchor_fn=anchor, poll_interval_s=0.001)
    a.start_relay(); b.start_relay()
    end = time.time() + 30
    while time.time() < end and seed.stats()["pending"] > 0:
        time.sleep(0.02)
    a.stop_relay(); b.stop_relay()
    dupes = sum(1 for i in range(N) if calls[f"r-{i}"] > 1)
    per_trial.append(dupes)
    total_dupes += dupes; total_rows += N
print({"trials": TRIALS, "rows_per_trial": N, "rows_anchored_more_than_once": total_dupes,
       "rows_total": total_rows, "per_trial": per_trial})
