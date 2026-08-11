#!/usr/bin/env python3
"""
Experiment 1 (Phase 2 rebuild): acknowledgement & completion latency, throughput.

WHAT CHANGED FROM THE PREVIOUS VERSION AND WHY
----------------------------------------------
The old "public vs sensitive path" split dissolved when Change 2 made the private
commit unconditional. Every record now pays the Fabric cost; the only difference
between classes is what (if anything) gets anchored publicly. So the measured
axes are now:

  ack latency        t0 -> 202 Accepted   (client-visible; private commit done)
  completion latency t0 -> anchor delivered by the relay (async, includes queueing)

and three record classes are reported, not two:

  all_public     every field publishable  -> Fabric commit + anchor
  all_sensitive  no field publishable     -> Fabric commit only, NO anchor
  mixed          some of each             -> Fabric commit + redacted anchor
                                             (the realistic case; never measured before)

Harness fixes (Phase 2, Change 4), each closing a specific defect:
  1. requests.Session per worker  — the old code opened a new TCP connection per
     request with no keep-alive, inflating measured RTT.
  2. Server-side timing captured  — the old throughput loop discarded timing_ms
     and fabric_invoked, which is why the public/sensitive mix-up (F4) could not
     be diagnosed from the artifacts.
  3. Per-request JSONL persisted  — enables p95 of ack latency (F5), which was
     previously underivable because only aggregates were stored.
  4. RECONCILIATION GATE          — observed_tps must agree with
     concurrency / mean_ack_latency. The previous run recorded 0.442 TPS for a
     94 ms path (implying ~10.6 TPS) and nobody noticed for months. A failing
     gate now refuses to write the number.

No randomness anywhere in the measurement path (ids from a counter + run nonce).

Output:
  experiments/results/exp1/exp1_latency_real.json     (aggregates, kind-tagged)
  experiments/results/exp1/exp1_requests.jsonl        (per-request rows)
"""

import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_REPO, "experiments", "results", "exp1")
BASE = os.getenv("ORCHESTRATOR_URL", "http://localhost:5002")
ORCH = BASE + "/ingest_data"
NONCE = str(int(time.time()))

# --- Measurement configuration ---
WARMUP = 20                              # discarded, per class and per level
LAT_REPS = 200                           # >= 200 per class (spec: RESULTS.json v2)
CLASSES = ["all_public", "all_sensitive", "mixed"]
TPUT_CONC = [1, 2, 4, 8, 16, 32]
TPUT_N = 50                              # >= 50 per level
ANCHOR_POLL_S = 0.05                     # completion-latency poll cadence
ANCHOR_TIMEOUT_S = 120                   # give up waiting for an anchor
GATE_TOLERANCE = 0.25                    # reconciliation gate: +/- 25%

_sessions = threading.local()


def session():
    """One keep-alive Session per worker thread (Change 4.1)."""
    s = getattr(_sessions, "s", None)
    if s is None:
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=64)
        s.mount("http://", adapter)
        _sessions.s = s
    return s


def payload(cls, i):
    """Deterministic payload per record class. No randomness."""
    base = {"id": f"{cls}-{NONCE}-{i}", "deviceId": f"d{i % 50}"}
    if cls == "all_public":
        # Every field publishable: telemetry only.
        base.update({"temperature": 20 + (i % 10) * 0.5, "humidity": 40 + (i % 20)})
    elif cls == "all_sensitive":
        # Nothing publishable: every field is regulated PII/PHI.
        base.update({"patientId": f"P{i:05d}", "diagnosis": f"cond_{i % 7}",
                     "ssn": f"{i%900+100}-{i%90+10}-{i%9000+1000}",
                     "homeAddress": f"{i} Main St"})
    else:  # mixed
        base.update({"temperature": 20 + (i % 10) * 0.5, "humidity": 40 + (i % 20),
                     "patientId": f"P{i:05d}", "diagnosis": f"cond_{i % 7}"})
    return base


def one_request(cls, i, follow_anchor=False):
    """Send one ingest. Returns a per-request row (Change 4.3)."""
    t_submit = time.time()
    t0 = time.perf_counter()
    row = {"class": cls, "i": i, "t_submit": t_submit, "ok": False}
    try:
        r = session().post(ORCH, json=payload(cls, i), timeout=60)
        rtt = (time.perf_counter() - t0) * 1000.0
        row["t_return"] = time.time()
        row["rtt_ms"] = round(rtt, 3)
        row["status_code"] = r.status_code
        if r.status_code not in (200, 202):
            row["error"] = r.text[:200]
            return row
        j = r.json()
        t = j.get("timing_ms") or {}
        row.update({
            "ok": True,
            "policy_ms": t.get("policy_ms"),
            "fabric_ms": t.get("fabric_ms"),
            "outbox_ms": t.get("outbox_ms"),
            "ack_ms": t.get("ack_ms"),
            "fabric_invoked": t.get("fabric_invoked"),
            "anchor_enqueued": t.get("anchor_enqueued"),
            "anchor_state": j.get("anchor_state"),
            "outbox_id": j.get("outbox_id"),
            "idempotency_replay": j.get("idempotency_replay"),
        })
        if follow_anchor and j.get("anchor_state") == "pending":
            row["completion_ms"] = wait_for_anchor(j["outbox_id"], t0)
        elif row["anchor_enqueued"] is False:
            # No anchor required: completion == acknowledgement, by definition.
            row["completion_ms"] = row["ack_ms"]
            row["anchor_state"] = "not_required"
        return row
    except requests.RequestException as e:
        row["t_return"] = time.time()
        row["rtt_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
        row["error"] = str(e)[:200]
        return row


def wait_for_anchor(outbox_id, t0):
    """Poll /anchor_status until delivered; return completion latency in ms."""
    deadline = time.perf_counter() + ANCHOR_TIMEOUT_S
    url = f"{BASE}/anchor_status/{outbox_id}"
    while time.perf_counter() < deadline:
        try:
            r = session().get(url, timeout=10)
            if r.status_code == 200:
                j = r.json()
                if j.get("anchor_state") == "delivered":
                    return round((time.perf_counter() - t0) * 1000.0, 3)
                if j.get("anchor_state") == "failed":
                    return None
        except requests.RequestException:
            pass
        time.sleep(ANCHOR_POLL_S)
    return None


def _stats(xs, kind="measured"):
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"kind": kind, "n": 0}
    xs2 = sorted(xs)
    n = len(xs2)
    mean = statistics.fmean(xs2)
    sd = statistics.pstdev(xs2) if n > 1 else 0.0
    return {
        "kind": kind, "n": n,
        "mean": round(mean, 3),
        "p50": round(xs2[int(0.50 * (n - 1))], 3),
        "p95": round(xs2[int(0.95 * (n - 1))], 3),
        "p99": round(xs2[min(n - 1, int(0.99 * (n - 1)))], 3),
        "ci95": round(1.96 * sd / (n ** 0.5), 3) if n > 1 else 0.0,
    }


def write_rows(rows, tag):
    path = os.path.join(OUTPUT_DIR, "exp1_requests.jsonl")
    with open(path, "a") as f:
        for r in rows:
            r["phase"] = tag
            f.write(json.dumps(r) + "\n")


def measure_latency(cls):
    """Sequential latency: ack AND completion, per record class."""
    for i in range(WARMUP):
        one_request(cls, 900000 + i, follow_anchor=False)
    rows = []
    for i in range(LAT_REPS):
        rows.append(one_request(cls, i, follow_anchor=True))
    write_rows(rows, f"latency:{cls}")
    ok = [r for r in rows if r["ok"]]

    fabric_all = all(r.get("fabric_invoked") for r in ok) if ok else False
    anchored = sum(1 for r in ok if r.get("anchor_enqueued"))
    return {
        "class": cls,
        "n_sent": len(rows),
        "n_ok": len(ok),
        "ack_latency_ms": _stats([r.get("ack_ms") for r in ok]),
        "completion_latency_ms": _stats([r.get("completion_ms") for r in ok]),
        "client_rtt_ms": _stats([r.get("rtt_ms") for r in ok]),
        "stage_policy_ms": _stats([r.get("policy_ms") for r in ok]),
        "stage_fabric_ms": _stats([r.get("fabric_ms") for r in ok]),
        "stage_outbox_ms": _stats([r.get("outbox_ms") for r in ok]),
        "fabric_invoked_all": {"kind": "measured", "value": fabric_all},
        "anchors_enqueued": {"kind": "measured", "value": anchored},
    }


def reconciliation_gate(concurrency, observed_tps, mean_ack_ms):
    """observed_tps ~= concurrency / mean_ack_latency_s, within GATE_TOLERANCE.

    Closed-loop Little's law sanity check. A failure means the recorded rate and
    the recorded latency describe different systems — exactly the F4 failure mode.
    """
    if not mean_ack_ms or mean_ack_ms <= 0:
        return {"kind": "derived", "passed": False, "reason": "no ack latency"}
    expected = concurrency / (mean_ack_ms / 1000.0)
    rel = abs(observed_tps - expected) / expected if expected > 0 else float("inf")
    return {
        "kind": "derived",
        "expected_tps": round(expected, 3),
        "observed_tps": round(observed_tps, 3),
        "relative_error": round(rel, 3),
        "tolerance": GATE_TOLERANCE,
        "passed": rel <= GATE_TOLERANCE,
        "derivation": "concurrency / mean_ack_latency_s",
    }


def measure_throughput(cls):
    rows_out, gate_failures = [], []
    for c in TPUT_CONC:
        for i in range(WARMUP):
            one_request(cls, 800000 + i)
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=c) as ex:
            futs = [ex.submit(one_request, cls, 10000 * c + i) for i in range(TPUT_N)]
            reqs = [f.result() for f in futs]
        wall = time.perf_counter() - t0
        write_rows(reqs, f"throughput:{cls}:c{c}")

        ok = [r for r in reqs if r["ok"]]
        tps = len(ok) / wall if wall > 0 else 0.0
        ack = _stats([r.get("ack_ms") for r in ok])
        gate = reconciliation_gate(c, tps, ack.get("mean"))
        row = {
            "concurrency": c,
            "n_sent": len(reqs), "n_ok": len(ok),
            "errors": len(reqs) - len(ok),
            "wall_s": {"kind": "measured", "value": round(wall, 3)},
            "throughput_tps": {"kind": "derived", "value": round(tps, 3),
                               "derivation": "completed_requests / wall_clock_s"},
            "ack_latency_ms": ack,
            "client_rtt_ms": _stats([r.get("rtt_ms") for r in ok]),
            "fabric_invoked_all": {"kind": "measured",
                                   "value": all(r.get("fabric_invoked") for r in ok) if ok else False},
            "reconciliation_gate": gate,
        }
        rows_out.append(row)
        status = "OK " if gate["passed"] else "GATE FAILED"
        print(f"    c={c:>2}: {tps:>6.3f} TPS  ack {ack.get('mean')} ms  "
              f"expected {gate.get('expected_tps')} TPS  [{status}]")
        if not gate["passed"]:
            gate_failures.append({"class": cls, "concurrency": c, **gate})
        if row["errors"] > 0:
            print(f"        {row['errors']} errors at c={c}; stopping sweep for {cls}")
            break
    return rows_out, gate_failures


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    jsonl = os.path.join(OUTPUT_DIR, "exp1_requests.jsonl")
    if os.path.exists(jsonl):
        os.remove(jsonl)

    try:
        h = requests.get(BASE + "/health", timeout=5)
        assert h.status_code == 200
    except Exception as e:
        print(f"ERROR: orchestrator not reachable at {BASE}: {e}")
        print("This experiment requires the live stack (orchestrator + policy + "
              "Fabric + Ganache). Nothing was written — a missing number is "
              "recoverable, a fabricated one is not.")
        return 1

    print("=" * 72)
    print("  EXPERIMENT 1 (Phase 2): ack/completion latency + throughput")
    print("=" * 72)

    latency = {}
    for cls in CLASSES:
        print(f"  latency: {cls} (n={LAT_REPS}, warmup={WARMUP})")
        latency[cls] = measure_latency(cls)

    throughput, all_gate_failures = {}, []
    for cls in CLASSES:
        print(f"  throughput: {cls}")
        rows, failures = measure_throughput(cls)
        throughput[cls] = rows
        all_gate_failures.extend(failures)

    saturated = {}
    for cls, rows in throughput.items():
        tps = [r["throughput_tps"]["value"] for r in rows]
        peak = max(tps) if tps else 0.0
        saturated[cls] = {
            "kind": "measured",
            "peak_tps": peak,
            "peak_at_concurrency": TPUT_CONC[tps.index(peak)] if tps else None,
            "saturation_reached": bool(tps) and tps[-1] <= peak * 1.05 and len(tps) > 1,
            "note": ("TPS flattened or declined at the top of the sweep"
                     if bool(tps) and tps[-1] <= peak * 1.05 and len(tps) > 1
                     else f"saturation NOT reached; highest level tested = {TPUT_CONC[len(tps)-1] if tps else None}"),
        }

    results = {
        "experiment": "exp1_latency_real",
        "schema_version": 2,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": {
            "data_source": "synthetic telemetry generated in exp1_latency_real.py:payload()",
            "n_per_class": LAT_REPS,
            "warmups_discarded": WARMUP,
            "per_request_rows": "experiments/results/exp1/exp1_requests.jsonl",
            "architecture": ("async: private commit acknowledged at 202, public "
                             "anchor delivered by the outbox relay worker"),
        },
        "latency": latency,
        "throughput": throughput,
        "saturation": saturated,
        "reconciliation_gate_failures": all_gate_failures,
    }

    if all_gate_failures:
        # Spec: do not record the number — record the discrepancy and stop.
        results["status"] = "FAILED_RECONCILIATION_GATE"
        results["not_measured"] = [{
            "metric": "throughput_*",
            "reason": ("observed TPS disagrees with concurrency/mean_ack_latency by "
                       f"more than {GATE_TOLERANCE*100:.0f}% at "
                       f"{len(all_gate_failures)} level(s); throughput numbers are "
                       "NOT fit to publish until this is explained"),
        }]
        path = os.path.join(OUTPUT_DIR, "exp1_latency_real.FAILED.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2)
        print("\n" + "!" * 72)
        print("  RECONCILIATION GATE FAILED — throughput NOT written to results.")
        for g in all_gate_failures:
            print(f"    {g['class']} c={g['concurrency']}: observed {g['observed_tps']} "
                  f"TPS vs expected {g['expected_tps']} TPS "
                  f"(rel err {g['relative_error']})")
        print(f"  Discrepancy report: {path}")
        print("!" * 72)
        return 2

    results["status"] = "OK"
    path = os.path.join(OUTPUT_DIR, "exp1_latency_real.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  All reconciliation gates passed. JSON: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
