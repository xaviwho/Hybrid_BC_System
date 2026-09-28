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
  completion latency t0 -> anchor delivered by the relay

and completion is DECOMPOSED rather than reported as one number:

  completion = ack + queue_wait + anchor

  queue_wait  time the row sat pending behind other work. A property of relay
              SCHEDULING; grows with offered load against a single-threaded relay.
  anchor      the chain call itself. A property of ETHEREUM.

Their sum is not "anchor latency", and under backlog the queue term dominates.
Each completion sample also records the outbox queue depth at submit time, so a
latency figure can be read against the backlog it queued behind.

Separately, the relay's sustained DRAIN RATE is measured (burst, then watch the
queue empty). That is the public-anchoring throughput ceiling of a
single-threaded relay — a real system property, and strictly below
1/anchor_latency once the queue is non-empty.

and three record classes are reported, not two:

  all_public     every field publishable  -> Fabric commit + anchor
  all_sensitive  named for intent, but still anchors: it carries deviceId, which
                 policy_engine rules PUBLIC, so metadata_obj is non-empty. Kept
                 unchanged for comparability with prior runs (2026-08-19).
  fabric_only    genuinely no publishable field -> Fabric commit only, NO anchor.
                 The class that actually exercises Algorithm 1's FABRIC_ONLY
                 branch; added 2026-08-19 after anchors_enqueued showed 50/50 on
                 all three original classes.
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

Revision v2 (WS1):
  * requests per throughput level = smallest multiple of c that is >= TPUT_MIN_N
    (200). v1 used 50, and n/(c*ceil(n/c)) quantisation explained most of the gap
    to c/T_ack (AUDIT_WS0 §4.2); a multiple of c removes it.
  * steady-state TPS (first and last c completions excluded, monotonic clock)
    is reported next to the gated value.
  * every row carries monotonic submit/return stamps; wall-clock stamps are
    labels only (AUDIT_WS0 F1).
  * warm-up ids are unique per level, so warm-ups exercise Fabric instead of
    hitting the idempotency cache as they did in v1.
  * the run digest (experiments/run_digest.py) is taken at start and end; a
    change in config_hash during the run fails it.
  * the relay drain phase is off by default: it measured the offered rate, not
    mu_relay (AUDIT_WS0 F9). WS3 measures mu_relay under saturation.
  * which fixtures, levels and phases run is set from the environment
    (EXP1_CLASSES, EXP1_CONC, EXP1_PHASES, ...) so the WS1/WS2 sweeps reuse
    this script unchanged.

Output (under $ORBIT_RESULTS_DIR, default experiments/results):
  exp1/exp1_latency_real.json     (aggregates, kind-tagged)
  exp1/exp1_requests.jsonl        (per-request rows)
"""

import json
import math
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(os.getenv("ORBIT_RESULTS_DIR",
                                    os.path.join(_REPO, "experiments", "results")), "exp1")
BASE = os.getenv("ORCHESTRATOR_URL", "http://localhost:5002")
ORCH = BASE + "/ingest_data"
NONCE = os.getenv("EXP1_NONCE", str(int(time.time())))


def _env_list(name, default, conv=str):
    v = os.getenv(name)
    return [conv(x) for x in v.split(",")] if v else default


# --- Measurement configuration ---
WARMUP = int(os.getenv("EXP1_WARMUP", "20"))        # discarded, per class and per level
LAT_REPS = int(os.getenv("EXP1_LAT_REPS", "200"))   # >= 200 per class
CLASSES = _env_list("EXP1_CLASSES", ["all_public", "all_sensitive", "mixed", "fabric_only"])
TPUT_CONC = _env_list("EXP1_CONC", [1, 2, 4, 8, 10, 12, 14, 16, 20, 24, 32], int)
TPUT_MIN_N = int(os.getenv("EXP1_TPUT_MIN_N", "200"))  # >= 200 per level (v1: 50)
TPUT_WARMUP_ROUNDS = int(os.getenv("EXP1_TPUT_WARMUP_ROUNDS", "2"))  # discarded, per level
PHASES = set(_env_list("EXP1_PHASES", ["latency", "throughput"]))  # + "drain"
ANCHOR_POLL_S = 0.05                     # completion-latency poll cadence
ANCHOR_TIMEOUT_S = 120                   # give up waiting for an anchor
GATE_TOLERANCE = 0.25                    # reconciliation gate: +/- 25%


def n_for_level(c):
    """Smallest multiple of c that is >= TPUT_MIN_N."""
    return c * math.ceil(TPUT_MIN_N / c)

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
    if cls == "fabric_only":
        # Algorithm 1 FABRIC_ONLY branch: nothing publishable at all, so
        # metadata_obj is empty and anchor_required is False -- private commit
        # with no public anchor. Deliberately omits deviceId, which
        # policy_engine rules PUBLIC (PUB-DEVICEID) and which every other class
        # carries; that field is why the other three all anchor despite their
        # names. Returned before `base` so the existing three classes are
        # byte-identical to previous runs and stay comparable.
        return {"id": f"{cls}-{NONCE}-{i}",
                "patientId": f"P{i:05d}", "diagnosis": f"cond_{i % 7}",
                "ssn": f"{i%900+100}-{i%90+10}-{i%9000+1000}",
                "homeAddress": f"{i} Main St"}
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


def queue_depth():
    """Pending rows in the outbox right now, or None if unreadable.

    Sampled OUTSIDE the timed region — an extra HTTP round trip inside it would
    inflate the ack latency it is meant to contextualise.
    """
    try:
        r = session().get(f"{BASE}/outbox_stats", timeout=5)
        if r.status_code == 200:
            return r.json().get("queue_depth")
    except requests.RequestException:
        pass
    return None


def one_request(cls, i, follow_anchor=False, sample_depth=False):
    """Send one ingest. Returns a per-request row (Change 4.3)."""
    # Depth at submit time, so completion latency can be read against the backlog
    # it actually queued behind. Only sampled in the sequential latency phase:
    # doing it per request during the throughput sweep would double the request
    # count against the orchestrator and perturb the thing being measured.
    depth_before = queue_depth() if sample_depth else None
    t_submit = time.time()
    t0 = time.perf_counter()
    row = {"class": cls, "i": i, "t_submit": t_submit, "t_submit_mono": t0,
           "ok": False, "queue_depth_at_submit": depth_before}
    try:
        r = session().post(ORCH, json=payload(cls, i), timeout=60)
        t1 = time.perf_counter()
        rtt = (t1 - t0) * 1000.0
        row["t_return"] = time.time()
        row["t_return_mono"] = t1
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
            "fabric_ms": t.get("fabric_ms"),          # invoke (endorse+order+commit)
            "readback_ms": t.get("readback_ms"),      # Alg. 1 l.22 query (v2)
            "fabric_stage_ms": t.get("fabric_stage_ms"),
            "outbox_ms": t.get("outbox_ms"),
            "route": j.get("route"),
            "ack_ms": t.get("ack_ms"),
            "fabric_invoked": t.get("fabric_invoked"),
            "anchor_enqueued": t.get("anchor_enqueued"),
            "anchor_state": j.get("anchor_state"),
            "outbox_id": j.get("outbox_id"),
            "idempotency_replay": j.get("idempotency_replay"),
        })
        if follow_anchor and j.get("anchor_state") == "pending":
            done = wait_for_anchor(j["outbox_id"], t0)
            row.update(done)
        elif row["anchor_enqueued"] is False:
            # No anchor required: completion == acknowledgement, by definition.
            # queue_wait/anchor stay None — there was no anchor to decompose.
            row["completion_ms"] = row["ack_ms"]
            row["anchor_state"] = "not_required"
        return row
    except requests.RequestException as e:
        t1 = time.perf_counter()
        row["t_return"] = time.time()
        row["t_return_mono"] = t1
        row["rtt_ms"] = round((t1 - t0) * 1000.0, 3)
        row["error"] = str(e)[:200]
        return row


def wait_for_anchor(outbox_id, t0):
    """Poll /anchor_status until delivered.

    Returns the completion latency AND its decomposition:

        completion = ack + queue_wait + anchor

    queue_wait is time the row sat pending behind other work — a property of
    relay scheduling under load. anchor is the chain call itself. Reporting the
    sum as "anchor latency" would attribute queueing to Ethereum, so the three
    are kept separate all the way into RESULTS.json.
    """
    deadline = time.perf_counter() + ANCHOR_TIMEOUT_S
    url = f"{BASE}/anchor_status/{outbox_id}"
    out = {"completion_ms": None, "queue_wait_ms": None, "anchor_ms": None,
           "anchor_attempts": None}
    while time.perf_counter() < deadline:
        try:
            r = session().get(url, timeout=10)
            if r.status_code == 200:
                j = r.json()
                if j.get("anchor_state") == "delivered":
                    out["completion_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
                    out["queue_wait_ms"] = j.get("queue_wait_ms")
                    out["anchor_ms"] = j.get("anchor_ms")
                    out["anchor_attempts"] = j.get("attempts")
                    return out
                if j.get("anchor_state") == "failed":
                    out["anchor_state"] = "failed"
                    return out
        except requests.RequestException:
            pass
        time.sleep(ANCHOR_POLL_S)
    return out


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
        rows.append(one_request(cls, i, follow_anchor=True, sample_depth=True))
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
        # completion = ack + queue_wait + anchor. Reported separately on purpose:
        # queue_wait is relay scheduling, anchor is the chain. See below.
        "queue_wait_ms": _stats([r.get("queue_wait_ms") for r in ok]),
        "anchor_ms": _stats([r.get("anchor_ms") for r in ok]),
        "queue_depth_at_submit": _stats([r.get("queue_depth_at_submit") for r in ok]),
        "client_rtt_ms": _stats([r.get("rtt_ms") for r in ok]),
        "stage_policy_ms": _stats([r.get("policy_ms") for r in ok]),
        "stage_fabric_ms": _stats([r.get("fabric_ms") for r in ok]),
        "stage_readback_ms": _stats([r.get("readback_ms") for r in ok]),
        "stage_outbox_ms": _stats([r.get("outbox_ms") for r in ok]),
        "fabric_invoked_all": {"kind": "measured", "value": fabric_all},
        "anchors_enqueued": {"kind": "measured", "value": anchored},
    }


def measure_drain_rate(cls="all_public", burst=100):
    """Sustained drain rate of the relay — the public-anchoring throughput ceiling.

    This is a real system property and belongs in the results: a single-threaded
    relay can only deliver so many anchors per second, and that bound governs how
    fast the public ledger can be kept current, independent of how fast the API
    can acknowledge.

    It must NOT be conflated with anchor latency. Once the queue is non-empty the
    relay is the bottleneck, so completion latency grows with backlog while the
    anchor itself costs the same. 1/mean_anchor_ms is an upper bound the relay
    does not reach; this measures what it actually sustains.

    Method: enqueue `burst` anchors as fast as the API will accept them WITHOUT
    following each one, then watch the queue drain to zero. Rate is
    delivered/elapsed over the drain, cross-checked against the relay's own
    accounting from /outbox_stats.
    """
    depth0 = queue_depth()
    for i in range(WARMUP):
        one_request(cls, 700000 + i)

    t_start = time.perf_counter()
    rows = [one_request(cls, 600000 + i) for i in range(burst)]
    enqueued = sum(1 for r in rows if r["ok"] and r.get("anchor_enqueued"))
    t_enqueued = time.perf_counter()

    # Drain to empty.
    deadline = time.perf_counter() + ANCHOR_TIMEOUT_S
    depth_samples, drained = [], False
    while time.perf_counter() < deadline:
        d = queue_depth()
        depth_samples.append(d)
        if d == 0:
            drained = True
            break
        time.sleep(ANCHOR_POLL_S)
    t_drained = time.perf_counter()

    enqueue_s = t_enqueued - t_start
    drain_s = t_drained - t_start
    relay = {}
    try:
        r = session().get(f"{BASE}/outbox_stats", timeout=10)
        if r.status_code == 200:
            relay = r.json().get("relay", {})
    except requests.RequestException:
        pass

    return {
        "class": cls,
        "burst": burst,
        "anchors_enqueued": enqueued,
        "queue_depth_before": depth0,
        "peak_queue_depth_observed": max([d for d in depth_samples if d is not None],
                                         default=None),
        "fully_drained": drained,
        "enqueue_wall_s": {"kind": "measured", "value": round(enqueue_s, 4)},
        "drain_wall_s": {"kind": "measured", "value": round(drain_s, 4)},
        "ingest_rate_per_s": {
            "kind": "derived", "value": round(enqueued / enqueue_s, 4) if enqueue_s else None,
            "derivation": "anchors_enqueued / enqueue_wall_s",
            "note": "how fast the API accepts work — bounded by ack latency"},
        "drain_rate_per_s": {
            "kind": "derived",
            "value": round(enqueued / drain_s, 4) if drain_s and drained else None,
            "derivation": "anchors_enqueued / drain_wall_s (enqueue start -> queue empty)",
            "note": ("sustained public-anchoring ceiling of the single-threaded "
                     "relay; NOT 1/anchor_latency")},
        "relay_self_reported": relay,
        "backlog_forms": {
            "kind": "derived",
            "value": bool(enqueue_s and drain_s and drain_s > enqueue_s * 1.5),
            "derivation": "drain_wall_s > 1.5 * enqueue_wall_s",
            "note": ("true means ingest outruns the relay and a backlog forms — the "
                     "regime where completion latency is dominated by queue wait "
                     "rather than by anchor cost")},
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


def _error_detail(reqs):
    """Group failed requests by (status_code, message) so a sweep level reports
    WHY it failed, not just how many times."""
    buckets = {}
    for r in reqs:
        if r.get("ok"):
            continue
        key = (r.get("status_code"), (r.get("error") or r.get("exc") or "")[:160])
        buckets[key] = buckets.get(key, 0) + 1
    return [{"status_code": k[0], "detail": k[1], "count": v}
            for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])]


def steady_state_tps(ok, c):
    """Completions per second with the first and last c completions excluded.

    Those are the ramp-up (workers starting together) and drain (fewer than c
    requests left in flight) phases, where a closed loop of c workers is not at
    concurrency c. Monotonic return stamps only. None if too few completions.
    """
    ends = sorted(r["t_return_mono"] for r in ok if r.get("t_return_mono") is not None)
    if len(ends) < 2 * c + 2:
        return None
    lo, hi = ends[c - 1], ends[len(ends) - c - 1]
    return (len(ends) - 2 * c) / (hi - lo) if hi > lo else None


def measure_throughput(cls):
    rows_out, gate_failures = [], []
    for c in TPUT_CONC:
        n = n_for_level(c)
        # Warm-up: TPUT_WARMUP_ROUNDS rounds AT this level's concurrency, unique
        # ids (v1 sent 20 sequential requests re-using the same ids at every
        # level, which after the first level were idempotency-cache hits).
        with ThreadPoolExecutor(max_workers=c) as ex:
            list(ex.map(lambda i: one_request(cls, 800000 + 1000 * c + i),
                        range(TPUT_WARMUP_ROUNDS * c)))
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=c) as ex:
            futs = [ex.submit(one_request, cls, 10000 * c + i) for i in range(n)]
            reqs = [f.result() for f in futs]
        wall = time.perf_counter() - t0
        write_rows(reqs, f"throughput:{cls}:c{c}")

        ok = [r for r in reqs if r["ok"]]
        tps = len(ok) / wall if wall > 0 else 0.0
        ss = steady_state_tps(ok, c)
        ack = _stats([r.get("ack_ms") for r in ok])
        gate = reconciliation_gate(c, tps, ack.get("mean"))
        row = {
            "concurrency": c,
            "n_sent": len(reqs), "n_ok": len(ok),
            "errors": len(reqs) - len(ok),
            "wall_s": {"kind": "measured", "value": round(wall, 3)},
            "throughput_tps": {"kind": "derived", "value": round(tps, 3),
                               "derivation": "completed_requests / wall_clock_s"},
            "throughput_steady_tps": {
                "kind": "derived", "value": round(ss, 3) if ss else None,
                "derivation": ("(n - 2c) / (t_return[n-c] - t_return[c]) over sorted "
                               "monotonic return stamps")},
            "ack_latency_ms": ack,
            "client_rtt_ms": _stats([r.get("rtt_ms") for r in ok]),
            # Stage decomposition per level: isolates WHERE the transition happens.
            "stage_policy_ms": _stats([r.get("policy_ms") for r in ok]),
            "stage_fabric_ms": _stats([r.get("fabric_ms") for r in ok]),
            "stage_readback_ms": _stats([r.get("readback_ms") for r in ok]),
            "stage_outbox_ms": _stats([r.get("outbox_ms") for r in ok]),
            # outbox_ms spans commit_and_enqueue, so it absorbs any SQLite
            "anchors_enqueued": {"kind": "measured",
                                 "value": sum(1 for r in ok if r.get("anchor_enqueued"))},
            "error_detail": _error_detail(reqs),
            "fabric_invoked_all": {"kind": "measured",
                                   "value": all(r.get("fabric_invoked") for r in ok) if ok else False},
            "reconciliation_gate": gate,
        }
        rows_out.append(row)
        status = "OK " if gate["passed"] else "GATE FAILED"
        print(f"    c={c:>2} n={n}: {tps:>6.3f} TPS (steady {ss if ss is None else round(ss, 3)})"
              f"  ack {ack.get('mean')} ms  expected {gate.get('expected_tps')} TPS  [{status}]",
              flush=True)
        if not gate["passed"]:
            gate_failures.append({"class": cls, "concurrency": c, **gate})
        if row["errors"] > 0:
            for e in row["error_detail"]:
                print(f"        {e['count']}x error at c={c} status={e['status_code']}: {e['detail']}")
    return rows_out, gate_failures


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    jsonl = os.path.join(OUTPUT_DIR, "exp1_requests.jsonl")
    if os.path.exists(jsonl):
        os.remove(jsonl)

    try:
        h = requests.get(BASE + "/health", timeout=5)
        assert h.status_code == 200
        health = h.json()
    except Exception as e:
        print(f"ERROR: orchestrator not reachable at {BASE}: {e}")
        print("This experiment requires the live stack (orchestrator + policy + "
              "Fabric + Ganache). Nothing was written — a missing number is "
              "recoverable, a fabricated one is not.")
        return 1

    import run_digest
    digest_start = run_digest.collect()

    print("=" * 72)
    print("  EXPERIMENT 1 (v2): ack/completion latency + throughput")
    print(f"  server={health.get('server')} workers={health.get('server_workers')} "
          f"threads={health.get('server_threads')} readback={health.get('fabric_readback')} "
          f"config_hash={digest_start['config_hash']}")
    print("=" * 72, flush=True)

    latency = {}
    if "latency" in PHASES:
        for cls in CLASSES:
            print(f"  latency: {cls} (n={LAT_REPS}, warmup={WARMUP})", flush=True)
            latency[cls] = measure_latency(cls)

    drain = None
    if "drain" in PHASES:
        print("  relay delivery at offered load (NOT mu_relay; see AUDIT_WS0 F9)")
        drain = measure_drain_rate()
        print(f"    ingest {drain['ingest_rate_per_s']['value']} /s -> "
              f"delivered {drain['drain_rate_per_s']['value']} /s "
              f"(peak queue depth {drain['peak_queue_depth_observed']}, "
              f"backlog forms: {drain['backlog_forms']['value']})")

    throughput, all_gate_failures = {}, []
    if "throughput" in PHASES:
        for cls in CLASSES:
            print(f"  throughput: {cls}", flush=True)
            rows, failures = measure_throughput(cls)
            throughput[cls] = rows
            all_gate_failures.extend(failures)

    digest_end = run_digest.collect()

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
        "schema_version": 3,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "provenance": {
            "data_source": "synthetic telemetry generated in exp1_latency_real.py:payload()",
            "nonce": NONCE,
            "phases": sorted(PHASES),
            "classes": CLASSES,
            "concurrency_levels": TPUT_CONC,
            "n_per_class": LAT_REPS,
            "n_per_level": {str(c): n_for_level(c) for c in TPUT_CONC},
            "warmups_discarded": {"latency_phase": WARMUP,
                                  "throughput_rounds_per_level": TPUT_WARMUP_ROUNDS},
            "per_request_rows": os.path.relpath(jsonl, _REPO),
            "config_hash": digest_start["config_hash"],
            "config_hash_end": digest_end["config_hash"],
            "run_digest_start": digest_start,
            "run_digest_end": digest_end,
            "orchestrator_health": health,
            "architecture": ("async: private commit acknowledged at 202, public "
                             "anchor delivered by the outbox relay worker"),
            # Recorded so consolidate_results.py can prove every experiment in a
            # run anchored to the SAME contract. Without this, exp3 measuring gas
            # on one deployment while exp1/exp5 use another is undetectable.
            "contract_addr": health.get("contract_addr"),
            "chain_id": health.get("chain_id"),
            "network_id": health.get("network_id"),
            "outbox_db": health.get("outbox_db"),
            # Server mode is part of the config vector from 2026-08-19 on.
            "server_mode": health.get("server_mode"),
        },
        "latency": latency,
        "relay_drain": drain,
        "throughput": throughput,
        "saturation": saturated,
        "reconciliation_gate_failures": all_gate_failures,
    }

    if digest_start["config_hash"] != digest_end["config_hash"]:
        # The system changed under the run (restart, redeploy, new relay...).
        results["status"] = "FAILED_CONFIG_CHANGED"
        path = os.path.join(OUTPUT_DIR, "exp1_latency_real.FAILED.json")
        with open(path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  CONFIG CHANGED DURING RUN ({digest_start['config_hash']} -> "
              f"{digest_end['config_hash']}); results NOT admitted. {path}")
        return 3

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
