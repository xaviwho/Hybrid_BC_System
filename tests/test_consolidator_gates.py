#!/usr/bin/env python3
"""
Tests for the consolidator's admission gates.

These decide what is allowed to become a published metric. Two failure modes
they exist to prevent, both of which have actually occurred in this project:

  1. A result file from a superseded architecture being reported as current.
     exp5's pre-Phase-2 run measured the SYNCHRONOUS orchestrator (200 with
     ethereum_tx_hash inline). Reported unchanged, `exactly_once_holds: true`
     would have stood as `measured` evidence for the async outbox design — a
     property of a system that no longer exists.

  2. A chain-dependent run with no recorded contract address. "No address
     recorded" is indistinguishable from "recorded a different address" as far
     as the single-deployment claim goes, so it must fail closed rather than
     be annotated and admitted.

Usage:  python tests/test_consolidator_gates.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "experiments"))
import consolidate_results as C  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


ADDR = "0xe78A0F7E598Cc8b0Bb87894B0F60dD2a88d6a8Ab"


def v2(**prov):
    return {"schema_version": 2, "provenance": prov}


def test_schema_gate():
    print("\n[1] superseded result files are withheld, not reported")
    for exp in C.REQUIRE_SCHEMA_V2:
        node = {"measured": True}          # the v1 shape
        check(f"{exp}: v1 file withheld", C.gate(exp, node) is not None)
        check(f"{exp}: reason names the architecture change",
              "architecture" in (C.gate(exp, node) or ""))
    check("exp5 v1 specifically withheld — the synchronous-era exactly-once run",
          C.gate("exp5", {"measured": True, "exactly_once_holds": True}) is not None)


def test_contract_gate_fails_closed():
    print("\n[2] chain-dependent runs without a contract address FAIL CLOSED")
    for exp in C.REQUIRE_CONTRACT_ADDR:
        check(f"{exp}: v2 with no provenance -> withheld",
              C.gate(exp, {"schema_version": 2}) is not None)
        check(f"{exp}: v2 with empty provenance -> withheld",
              C.gate(exp, v2()) is not None)
        check(f"{exp}: v2 with provenance but no address -> withheld",
              C.gate(exp, v2(chain_id=1337, network_id="1337")) is not None)
        check(f"{exp}: v2 with an address -> admitted",
              C.gate(exp, v2(contract_addr=ADDR)) is None)
    check("either provenance spelling is accepted",
          C.gate("exp3", v2(contract_address=ADDR)) is None)
    check("withholding reason says unprovable is treated as failed",
          "unprovable" in (C.gate("exp1", v2()) or ""))


def test_offline_experiments_ungated():
    print("\n[3] offline experiments are not gated on chain provenance")
    for exp in ("exp2", "exp7"):
        check(f"{exp}: admitted without schema_version or address",
              C.gate(exp, {"measured": True}) is None,
              "deterministic and offline; has no contract to record")
    check("exp4 and exp8 still require v2 (they were rebuilt)",
          C.gate("exp4", {"measured": True}) is not None
          and C.gate("exp8", {"measured": True}) is not None)


def test_address_mismatch_still_fails_build():
    print("\n[4] differing addresses across experiments fail the whole build")
    # The gate admits each individually; the cross-check must then reject the set.
    a, b = ADDR, "0x" + "11" * 20
    for exp, addr in (("exp1", a), ("exp3", b), ("exp5", a)):
        check(f"{exp} admitted individually", C.gate(exp, v2(contract_addr=addr)) is None)
    lowered = {str(x).lower() for x in (a, b, a)}
    check("the set is detectably inconsistent", len(lowered) > 1,
          f"{len(lowered)} distinct addresses")
    check("consolidator treats a mismatch as a build error, not a note",
          "contract address mismatch" in open(
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "experiments", "consolidate_results.py"),
              encoding="utf-8").read())


def test_gate_runs_before_metrics():
    print("\n[5] gating happens before metric construction")
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "experiments", "consolidate_results.py"),
               encoding="utf-8").read()
    body = src[src.index("def main("):]
    gate_at = body.index("admitted = {")
    # No experiment block may read `raw` directly after the gate — that would be a
    # path by which a withheld experiment could still emit a metric.
    after = body[gate_at:]
    check("no experiment block reads `raw.get(` after the gate",
          "raw.get(" not in after,
          "all blocks read `admitted`")
    check("every experiment block reads `admitted`",
          after.count("admitted.get(") >= 7,
          f"{after.count('admitted.get(')} blocks")


def main():
    print("=" * 72)
    print("  CONSOLIDATOR ADMISSION GATES")
    print("=" * 72)
    test_schema_gate()
    test_contract_gate_fails_closed()
    test_offline_experiments_ungated()
    test_address_mismatch_still_fails_build()
    test_gate_runs_before_metrics()
    print("\n" + "=" * 72)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"    FAILED: {f}")
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
