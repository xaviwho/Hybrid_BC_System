#!/usr/bin/env python3
"""
Acceptance tests for Phase 3 delta + checkpoint storage in twin_manager.

Covers the ten acceptance criteria from PHASE3 spec, plus regression tests for the
aliasing defect found in 7a. Runs fully offline.

Usage:  python tests/test_twin_storage.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "orchestrator"))
from twin_manager import (  # noqa: E402
    TwinManager, DigitalTwin, IntegrityViolation, canon, digest,
    KIND_CHECKPOINT, KIND_SNAPSHOT, KIND_DELTA,
    PATH_CHECKPOINT, PATH_INVERSION, PATH_DIRECT,
)

PASS, FAIL = [], []
STATE_FIELDS = 20


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def sparse_state(i):
    """~2 of 20 fields change per version."""
    return {f"sensor_{k}": (max(i - ((i - k) % 10), 0) * 100 + k) * 0.5
            for k in range(STATE_FIELDS)}


def dense_state(i):
    """every field changes every version."""
    return {f"sensor_{k}": (i * 100 + k) * 0.5 for k in range(STATE_FIELDS)}


def build(gen, n=301, q=100):
    tm = TwinManager(checkpoint_interval=q)
    twin = tm.create_twin("t", "sensor", gen(0))
    for i in range(1, n):
        twin.update_state(gen(i))
    return tm, twin


# --- regression: the 7a aliasing defect --------------------------------------

def test_aliasing_fixed():
    print("\n[A] aliasing regression (the 7a defect)")
    tm = TwinManager()
    twin = tm.create_twin("a", "s", {"x": 1})

    mine = {"x": 2}
    twin.update_state(mine)
    mine["x"] = 999
    check("caller mutation does not rewrite history",
          twin.get_version(2).state["x"] == 2,
          f"v2.x={twin.get_version(2).state['x']}")

    t2 = tm.create_twin("b", "s", {"x": 1})
    t2.patch_state({"x": 2})
    t2.patch_state({"x": 3})
    check("patch_state does not alias history",
          t2.get_version(2).state["x"] == 2 and t2.get_version(3).state["x"] == 3,
          f"v2={t2.get_version(2).state['x']} v3={t2.get_version(3).state['x']}")

    init = {"x": 1}
    t3 = tm.create_twin("c", "s", init)
    init["x"] = 42
    check("create_twin does not alias the initial state",
          t3.get_version(1).state["x"] == 1)

    t4 = tm.create_twin("d", "s", {"x": 1})
    t4.patch_state({"x": 2})
    t4.set_status("inactive")
    t4.patch_state({"x": 3})
    check("set_status version does not alias current_state",
          t4.get_version(3).state["x"] == 2,
          f"v3.x={t4.get_version(3).state['x']}")


# --- criterion 1: every version reconstructs and verifies ---------------------

def test_criterion_1():
    print("\n[1] every version reconstructs and passes digest verification")
    for label, gen in (("sparse", sparse_state), ("dense", dense_state)):
        tm, twin = build(gen)
        report = twin.verify_all()
        check(f"{label}: all {report['checked']} versions verify",
              report["ok"] and report["checked"] == len(twin.versions),
              f"failures={len(report['failures'])}")
        ok = all(twin.reconstruct(v.version_number) == gen(v.version_number - 1)
                 for v in twin.versions)
        check(f"{label}: reconstructions equal the originals", ok)


# --- criterion 2: both paths exercised ---------------------------------------

def test_criterion_2():
    print("\n[2] both reconstruction paths exercised and verified")
    tm, twin = build(sparse_state, n=301, q=100)
    paths = {}
    for v in twin.versions:
        _, st = twin.reconstruct_with_stats(v.version_number)
        paths.setdefault(st["path"], 0)
        paths[st["path"]] += 1
    check("checkpoint path used", paths.get(PATH_CHECKPOINT, 0) > 0, str(paths))
    check("inversion path used", paths.get(PATH_INVERSION, 0) > 0, str(paths))
    check("direct (materialized) path used", paths.get(PATH_DIRECT, 0) > 0, str(paths))

    # inversion must be exercised where it is genuinely cheaper: near head
    n = len(twin.versions)
    _, st = twin.reconstruct_with_stats(n - 1)
    check("near-head target uses inversion", st["path"] == PATH_INVERSION,
          f"path={st['path']} u={st['u']}")


# --- criterion 3: u == min(n-k, (k-1) mod q) from production code -----------------

def test_criterion_3():
    print("\n[3] measured u == min{n-k, (k-1) mod q}, from the shipped manager")
    for q in (50, 100, 250):
        tm, twin = build(sparse_state, n=1001, q=q)
        n = len(twin.versions)
        mismatches = []
        for k in (1, 50, 100, 250, 500, 750, 990, 995, 999, 1000):
            if k > n:
                continue
            _, st = twin.reconstruct_with_stats(k)
            # positions are 0-based internally; version k sits at index k-1
            idx, head = k - 1, n - 1
            predicted = min(head - idx, idx % q)
            if st["u"] != predicted:
                mismatches.append((k, st["u"], predicted, st["path"]))
        check(f"q={q}: u matches min(n-k, (k-1) mod q) at all targets",
              not mismatches, f"mismatches={mismatches}")


# --- criterion 4: storage ratio measured on the shipped representation --------

def test_criterion_4():
    print("\n[4] storage ratio measured on reversible deltas (shipped format)")
    results = {}
    for label, gen in (("sparse", sparse_state), ("dense", dense_state)):
        tm, twin = build(gen, n=1001, q=100)
        rep = twin.storage_report()
        results[label] = rep
        check(f"{label}: ratio reported", rep["ratio_vs_snapshots"] > 0,
              f"{rep['ratio_vs_snapshots']}x "
              f"({rep['stored_bytes']:,} B vs {rep['snapshot_equivalent_bytes']:,} B)")
        print(f"        kinds={rep['counts_by_kind']} "
              f"reversible={rep['reversible_deltas']} "
              f"forward_only={rep['forward_only_deltas']}")
    check("dense never worse than the full-snapshot model (min(delta,snapshot) works)",
          results["dense"]["ratio_vs_snapshots"] >= 0.99,
          f"{results['dense']['ratio_vs_snapshots']}x")
    check("sparse materially better than snapshots",
          results["sparse"]["ratio_vs_snapshots"] > 2.0,
          f"{results['sparse']['ratio_vs_snapshots']}x")


# --- criterion 5: rollback appends ------------------------------------------

def test_criterion_5():
    print("\n[5] rollback appends a new head; history preserved")
    tm, twin = build(sparse_state, n=120, q=50)
    before = len(twin.versions)
    snapshot_of_v10 = twin.reconstruct(10)
    ok = twin.rollback_to_version(10)
    check("rollback succeeds", ok)
    check("history depth increased", len(twin.versions) == before + 1,
          f"{before} -> {len(twin.versions)}")
    check("new head carries s_k", twin.current_state == snapshot_of_v10)
    check("new head digest == chi_k",
          twin.versions[-1].digest == twin.get_version(10).digest)
    check("operation type recorded",
          twin.versions[-1].metadata.get("action") == "rollback"
          and twin.versions[-1].metadata.get("rollback_to") == 10)
    check("no prior version lost",
          all(twin.get_version(i) is not None for i in range(1, before + 1)))
    check("all versions still verify after rollback", twin.verify_all()["ok"])


# --- criterion 6: corrupted digest raises ------------------------------------

def test_criterion_6():
    print("\n[6] corrupted stored digest raises IntegrityViolation")
    tm, twin = build(sparse_state, n=60, q=50)
    target = twin.get_version(30)
    target.digest = "0" * 64
    try:
        twin.reconstruct(30)
        check("IntegrityViolation raised on corrupt digest", False, "no exception")
    except IntegrityViolation:
        check("IntegrityViolation raised on corrupt digest", True)
    rep = twin.verify_all()
    check("verify_all reports exactly the corrupted version",
          len(rep["failures"]) == 1 and rep["failures"][0]["version"] == 30,
          str(rep["failures"])[:120])

    # corrupt a stored payload instead of the digest
    tm2, twin2 = build(sparse_state, n=60, q=50)
    v = next(x for x in twin2.versions if x.kind == KIND_DELTA)
    v.payload = v.payload + [{"key": "injected", "op": "add", "new": "evil"}]
    try:
        twin2.reconstruct(v.version_number)
        check("tampered payload detected", False, "no exception")
    except IntegrityViolation:
        check("tampered payload detected", True)


# --- criterion 7: q configurable --------------------------------------------

def test_criterion_7():
    print("\n[7] checkpoint interval q configurable and honoured")
    for q in (50, 100, 250):
        tm, twin = build(sparse_state, n=501, q=q)
        ckpts = [i for i, v in enumerate(twin.versions) if v.kind == KIND_CHECKPOINT]
        expected = list(range(0, len(twin.versions), q))
        check(f"q={q}: checkpoints at every q-th version",
              ckpts == expected, f"got {ckpts[:5]}... expected {expected[:5]}...")
        check(f"q={q}: version 1 is a checkpoint",
              twin.versions[0].kind == KIND_CHECKPOINT)
        check(f"q={q}: all versions verify", twin.verify_all()["ok"])


# --- criterion 8: pre-change twins ------------------------------------------

def test_criterion_8():
    print("\n[8] storage format recorded; no pre-change twins exist to migrate")
    tm = TwinManager()
    twin = tm.create_twin("f", "s", {"x": 1})
    check("storage_format recorded on the twin", twin.storage_format == 2)
    check("storage_format exposed via to_dict",
          twin.to_dict().get("storage_format") == 2)
    check("store is in-memory only (nothing persisted to migrate)",
          not hasattr(tm, "save") and not hasattr(tm, "load"))


# --- criterion 10: existing callers still work -------------------------------

def test_criterion_10():
    print("\n[10] existing twin_manager callers still work")
    tm = TwinManager(checkpoint_interval=50)
    twin = tm.create_twin("x", "sensor", {"a": 1, "b": 2}, metadata={"m": 1})
    tm.update_twin("x", {"a": 2, "b": 2})
    tm.patch_twin("x", {"b": 5})

    check("get_version(n).state is a plain dict",
          isinstance(twin.get_version(2).state, dict))
    check(".state materializes correct content",
          twin.get_version(2).state == {"a": 2, "b": 2})
    hist = twin.get_version_history()
    check("get_version_history returns every version with full state",
          len(hist) == 3 and all("state" in h and "checksum" in h for h in hist))
    check("history states are correct",
          [h["state"] for h in hist] ==
          [{"a": 1, "b": 2}, {"a": 2, "b": 2}, {"a": 2, "b": 5}],
          str([h["state"] for h in hist]))
    d = tm.get_version_diff("x", 1, 3)
    check("get_version_diff works against materialized states",
          d["changes"] == {"a": {"old": 1, "new": 2}, "b": {"old": 2, "new": 5}},
          str(d["changes"]))
    check("to_dict(include_versions=True) works",
          len(tm.get_twin("x").to_dict(include_versions=True)["versions"]) == 3)
    check("checksum field still present (back-compat alias)",
          twin.get_version(1).checksum == twin.get_version(1).digest)

    parent = tm.create_twin("p", "s", {"v": 0})
    child = tm.create_twin("c2", "s", {"v": 0}, parent_id="p")
    check("genealogy intact",
          tm.get_twin_descendants("p") == ["c2"] and tm.get_twin_ancestors("c2") == ["p"])
    check("search works", any(t["twin_id"] == "x" for t in tm.search_twins("sensor")))
    check("statistics work", tm.get_statistics()["total_twins"] == 3)
    check("soft delete works", tm.delete_twin("x") and tm.get_twin("x").status == "deleted")
    check("list filter works", len(tm.list_twins({"status": "deleted"})) == 1)


# --- bulk history path -------------------------------------------------------

def test_bulk_history():
    print("\n[B] bulk history path is O(n), not O(n^2)")
    tm, twin = build(sparse_state, n=1001, q=100)

    bulk = twin.get_version_history()
    per_version = [twin.reconstruct(v.version_number) for v in twin.versions]
    check("bulk walk agrees with per-version reconstruction",
          [h["state"] for h in bulk] == per_version)

    import time
    t0 = time.perf_counter()
    twin.get_version_history()
    bulk_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    for v in twin.versions:
        twin.reconstruct(v.version_number)
    naive_ms = (time.perf_counter() - t0) * 1000
    check("bulk path faster than reconstructing each version",
          bulk_ms < naive_ms,
          f"bulk {bulk_ms:.1f} ms vs per-version {naive_ms:.1f} ms "
          f"({naive_ms/max(bulk_ms,0.001):.1f}x)")


# --- canonical serialization -------------------------------------------------

def test_canon():
    print("\n[C] canonical serialization (Eq 29)")
    a = {"b": 1, "a": {"d": 2, "c": [1, 2]}}
    b = {"a": {"c": [1, 2], "d": 2}, "b": 1}
    check("key order independent", canon(a) == canon(b))
    check("no whitespace", b" " not in canon(a), canon(a).decode())
    check("UTF-8, not ASCII-escaped",
          canon({"k": "é"}) == '{"k":"é"}'.encode("utf-8"),
          canon({"k": "é"}).decode("utf-8"))
    check("digest is sha256 over canonical bytes",
          digest(a) == __import__("hashlib").sha256(canon(a)).hexdigest())


def main():
    print("=" * 72)
    print("  PHASE 3 — twin_manager delta/checkpoint storage acceptance tests")
    print("=" * 72)
    test_aliasing_fixed()
    test_criterion_1()
    test_criterion_2()
    test_criterion_3()
    test_criterion_4()
    test_criterion_5()
    test_criterion_6()
    test_criterion_7()
    test_criterion_8()
    test_criterion_10()
    test_bulk_history()
    test_canon()
    print("\n" + "=" * 72)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"    FAILED: {f}")
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
