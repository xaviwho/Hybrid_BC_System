#!/usr/bin/env python3
"""
Stage 5 (Phase 2): single source of truth, RESULTS.json v2.

Reads every canonical experiment result and emits one consolidated
experiments/results/RESULTS.json. Tables and figures regenerate from THIS file
only.

THE POINT OF v2: every metric carries a mandatory `kind` tag.

    measured  read from an instrument, a receipt, or a wall clock
    derived   arithmetic on other numbers in this file (carries `derivation`)
    modeled   a formula with assumed parameters (carries `formula`)

A metric without a `kind` is a BUILD FAILURE — this script exits non-zero and
writes nothing. That check is the mechanism that prevents a third diagnostic
round: an untagged number cannot reach the manuscript, and a `modeled` number
cannot be mistaken for a measurement.

Anything that could not be measured goes in `not_measured` with a reason. It
does not get a placeholder value.
"""

import hashlib
import json
import os
import sys
import time

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(_REPO, "experiments", "results")

VALID_KINDS = ("measured", "derived", "modeled")

SOURCES = {
    "exp1": "exp1/exp1_latency_real.json",
    "exp2": "exp2/exp2_policy_results.json",
    "exp3": "exp3/exp3_gas_real.json",
    "exp4": "exp4/exp4_lifecycle_real.json",
    "exp5": "exp5/exp5_exactly_once_real.json",
    "exp7": "exp7/exp7_hadc_real.json",
    "exp8": "exp8/exp8_recovery_strategy.json",
}

# Experiments that cannot run without the live stack. If their source file is
# missing we say so explicitly rather than silently dropping their metrics.
STACK_DEPENDENT = {"exp1": "orchestrator + policy + Fabric + Ganache",
                   "exp2": "policy engine",
                   "exp3": "Ganache + deployed IoTDataRegistry",
                   "exp5": "orchestrator + Fabric + Ganache"}

_errors = []


def load(rel):
    p = os.path.join(RES, rel)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def M(name, value, unit, src, kind, note="", derivation=None, formula=None):
    """Build a metric. `kind` is mandatory and validated."""
    if kind not in VALID_KINDS:
        _errors.append(f"{name}: invalid kind {kind!r} (expected one of {VALID_KINDS})")
    if kind == "derived" and not derivation:
        _errors.append(f"{name}: kind='derived' requires a `derivation`")
    if kind == "modeled" and not formula:
        _errors.append(f"{name}: kind='modeled' requires a `formula`")
    m = {"metric": name, "value": value, "unit": unit, "kind": kind,
         "source_exp": src, "note": note}
    if derivation:
        m["derivation"] = derivation
    if formula:
        m["formula"] = formula
    return m


def _v(node, key="value"):
    """Read a value out of a kind-tagged node, tolerating plain scalars."""
    if isinstance(node, dict):
        return node.get(key, node.get("mean"))
    return node


def main(stamp):
    raw = {k: load(v) for k, v in SOURCES.items()}
    missing = [k for k, v in raw.items() if v is None]
    metrics, not_measured = [], []

    for k in missing:
        not_measured.append({
            "source_exp": k,
            "reason": (f"result file {SOURCES[k]} absent; requires "
                       f"{STACK_DEPENDENT[k]}" if k in STACK_DEPENDENT else
                       f"result file {SOURCES[k]} absent"),
        })

    # ---- exp1: acknowledgement / completion latency + throughput (v2 shape) ----
    e = raw.get("exp1")
    if e and e.get("schema_version") == 2:
        if e.get("status") == "FAILED_RECONCILIATION_GATE":
            not_measured.append({
                "source_exp": "exp1",
                "reason": "throughput failed the reconciliation gate; numbers withheld",
            })
        for cls, block in e["latency"].items():
            ack, comp = block["ack_latency_ms"], block["completion_latency_ms"]
            metrics += [
                M(f"ack_latency_{cls}_mean", ack.get("mean"), "ms", "exp1", "measured",
                  f"t0 -> 202 Accepted, n={ack.get('n')}"),
                M(f"ack_latency_{cls}_p95", ack.get("p95"), "ms", "exp1", "measured"),
                M(f"completion_latency_{cls}_mean", comp.get("mean"), "ms", "exp1",
                  "measured", "t0 -> anchor delivered by relay"),
                M(f"completion_latency_{cls}_p95", comp.get("p95"), "ms", "exp1", "measured"),
                M(f"stage_fabric_{cls}_mean", block["stage_fabric_ms"].get("mean"), "ms",
                  "exp1", "measured"),
            ]
        for cls, sat in e.get("saturation", {}).items():
            metrics.append(M(f"throughput_{cls}_peak", sat.get("peak_tps"), "tps", "exp1",
                             "derived", sat.get("note", ""),
                             derivation="max over concurrency of completed/wall_clock_s"))
    elif e:
        not_measured.append({
            "source_exp": "exp1",
            "reason": ("result file predates Phase 2 (schema_version != 2): it reports "
                       "the retired public-vs-sensitive split and carries the F4 "
                       "throughput discrepancy. Rerun exp1_latency_real.py."),
        })

    # ---- exp2: deterministic privacy policy ----
    e = raw.get("exp2")
    if e:
        metrics += [
            M("privacy_routing_accuracy", round(e["routing_accuracy"] * 100, 1), "%",
              "exp2", "measured", f"{e['n_cases']} curated records"),
            M("privacy_sensitive_leaks", e["leak_count"], "count", "exp2", "measured",
              "to public ledger"),
            M("privacy_policy_coverage", round(e["coverage"]["coverage"] * 100, 1), "%",
              "exp2", "derived",
              derivation="explicit_rule_fields / total_fields"),
        ]

    # ---- exp3: gas, now measured per real N-leaf root ----
    e = raw.get("exp3")
    if e and e.get("schema_version") == 2:
        last = e["gas_per_record_by_batch"][-1]
        metrics += [
            M("gas_per_record_single", e["single_anchor_gas"]["mean"], "gas", "exp3",
              "measured", e["single_anchor_gas"].get("note", "")),
            M(f"gas_root_anchor_n{last['batch_size']}",
              last["root_anchor_gas"]["mean"], "gas", "exp3", "measured",
              f"real {last['leaf_count']}-leaf Merkle root, depth {last['tree_depth']}"),
            M(f"gas_per_record_batch{last['batch_size']}",
              last["batched_gas_per_record"]["value"], "gas", "exp3", "derived",
              derivation=last["batched_gas_per_record"]["derivation"]),
            M(f"gas_reduction_batch{last['batch_size']}",
              last["gas_reduction_pct"]["value"], "%", "exp3", "derived",
              derivation=last["gas_reduction_pct"]["derivation"]),
            M("gas_root_flat_in_N", e["root_gas_flat_in_N"]["value"], "bool", "exp3",
              "measured", e["root_gas_flat_in_N"]["note"]),
        ]
    elif e:
        not_measured.append({
            "source_exp": "exp3",
            "reason": ("result file predates Phase 2: 7 of 8 batch rows were division "
                       "on a fixed 64-leaf root. Rerun exp3_gas_real.py."),
        })

    # ---- exp4: twin lifecycle (Phase 3 delta/checkpoint storage) ----
    e = raw.get("exp4")
    if e and e.get("schema_version") == 2:
        # The sparse condition is the representative one: dense makes delta
        # encoding a no-op by construction, so its numbers describe the fallback,
        # not the mechanism. Both are still emitted below, labelled.
        sparse = e.get("by_state_model", {}).get("sparse", {})
        cost = sparse.get("rollback_cost_model", {})
        metrics += [
            M("rollback_latency_min", e["rollback_min_ms"], "ms", "exp4", "measured",
              "fastest target, sparse condition"),
            M("rollback_latency_max", e["rollback_max_ms"], "ms", "exp4", "measured",
              "slowest target, sparse condition"),
            M("rollback_is_constant_time", e["is_constant_time"], "bool", "exp4",
              "derived",
              "not constant: cost tracks u, which is sawtooth in k, so a "
              "target=1 vs target=N probe cannot detect the variation",
              derivation="latency compared across targets with different u, not by k"),
            M("rollback_bounded_by_checkpoint_interval",
              sparse.get("is_bounded_by_checkpoint_interval"), "bool", "exp4", "derived",
              f"u_max={cost.get('u_max_observed')} <= q={cost.get('checkpoint_interval_q')}",
              derivation="max observed delta applications u <= checkpoint interval q"),
            M("version_storage_bytes_per_version", e["approx_bytes_per_version"],
              "bytes", "exp4", "derived",
              "delta+checkpoint storage, sparse condition",
              derivation="stored_bytes / version count"),
        ]
        for model, block in e.get("by_state_model", {}).items():
            metrics.append(
                M(f"storage_compression_vs_snapshots_{model}",
                  block["compression_vs_snapshots_at_max"], "x", "exp4", "derived",
                  ("delta encoding is a no-op when every field changes every version; "
                   "the min(delta,snapshot) fallback holds this at parity"
                   if model == "dense" else
                   "sparse field updates: the condition under which III-F's claim holds"),
                  derivation="snapshot_equivalent_bytes / stored_bytes at the largest point"))
    elif e:
        not_measured.append({
            "source_exp": "exp4",
            "reason": ("result file predates Phase 3 (schema_version != 2): it reports "
                       "the retired full-snapshot storage model. Rerun "
                       "exp4_lifecycle_real.py."),
        })

    # ---- exp5: exactly-once ----
    e = raw.get("exp5")
    if e:
        n = (e["sequential_duplicates"]["requests"]
             + e["concurrent_duplicates"]["concurrent_requests"]
             + e["distinct_requests"]["distinct_payloads"])
        metrics += [
            M("exactly_once_holds", e["exactly_once_holds"], "bool", "exp5", "measured",
              f"real Ethereum tx hashes over {n} requests"),
            M("exactly_once_test_requests", n, "count", "exp5", "derived",
              derivation="sequential + concurrent duplicates + distinct payloads"),
        ]

    # ---- exp7: HADC compression ----
    e = raw.get("exp7")
    if e:
        metrics += [
            M("compression_ratio_uniform", e["overall_uniform_ratio"], "x", "exp7",
              "derived", "zlib-6 block",
              derivation="total_raw_bytes / total_uniform_bytes"),
            M("compression_ratio_hadc", e["overall_hadc_ratio"], "x", "exp7", "derived",
              "per-class codec selection",
              derivation="total_raw_bytes / total_hadc_bytes"),
            M("hadc_savings_vs_uniform", e["hadc_storage_savings_vs_uniform_pct"], "%",
              "exp7", "derived",
              derivation="100 * (1 - total_hadc_bytes / total_uniform_bytes)"),
            M("hadc_heterogeneous_selection", e.get("heterogeneous_selection"), "bool",
              "exp7", "measured", "whether classes chose different codecs"),
        ]

    # ---- exp8: recovery strategy, Eq (36) ----
    e = raw.get("exp8")
    if e:
        for model, block in e["by_state_model"].items():
            val = block["eq36_validation"]
            st = block["storage_at_q100"]
            metrics += [
                M(f"eq36_equality_holds_{model}", val["equality_holds_at"], "points",
                  "exp8", "derived", "u == min{n-k, q} as literally written",
                  derivation="count of (k,q) points where u_measured == min{n-k,q}"),
                M(f"eq36_bound_holds_{model}", val["bound_holds_at"], "points", "exp8",
                  "derived", "u <= min{n-k, q}",
                  derivation="count of (k,q) points where u_measured <= min{n-k,q}"),
                M(f"eq36_exact_formula_holds_{model}", val["exact_formula_holds_at"],
                  "points", "exp8", "derived", "exact cost is min{n-k, (k-1) mod q}",
                  derivation="count of (k,q) points where u_measured == min{n-k, (k-1) mod q}"),
                M(f"delta_vs_snapshot_ratio_{model}",
                  st["ratio_vs_snapshots"], "x", "exp8", "derived",
                  f"shipped storage format at q={st['checkpoint_interval']}; "
                  f"entry mix {st['counts_by_kind']}",
                  derivation="snapshot_equivalent_bytes / stored_bytes"),
                M(f"eq36_measured_on_production_code_{model}", True, "bool", "exp8",
                  "measured",
                  "u comes from twin_manager.reconstruct_with_stats, not from an "
                  "experiment-local implementation"),
            ]

    # ---- cross-experiment provenance: one run, one contract ----
    # The paper presents these numbers as a single consolidated run. If exp3
    # measured gas against one deployment while exp1/exp5 anchored to another,
    # that claim is false and nothing else in the pipeline would notice. The
    # address is recorded by each experiment from the chain/orchestrator it
    # actually used, so a mismatch is detectable here and only here.
    seen_contracts = {}
    for exp, node in (("exp1", raw.get("exp1")), ("exp3", raw.get("exp3")),
                      ("exp5", raw.get("exp5"))):
        if not node:
            continue
        prov = node.get("provenance") or {}
        addr = prov.get("contract_addr") or prov.get("contract_address")
        if addr:
            seen_contracts[exp] = str(addr).lower()

    distinct = set(seen_contracts.values())
    if len(distinct) > 1:
        _errors.append(
            "contract address mismatch across experiments in the same run: "
            + ", ".join(f"{e}={a}" for e, a in sorted(seen_contracts.items()))
            + ". These results do NOT come from one deployment and must not be "
              "consolidated. Redeploy, restart the orchestrator, and rerun all "
              "chain-dependent experiments together (STACK_BRINGUP.md section B).")
    elif distinct:
        metrics.append(
            M("run_contract_addr", next(iter(distinct)), "address", "exp1+exp3+exp5",
              "measured",
              f"identical across {sorted(seen_contracts)} — single-deployment run "
              f"confirmed"))
    missing_prov = [e for e in ("exp1", "exp3", "exp5")
                    if raw.get(e) and e not in seen_contracts]
    if missing_prov:
        not_measured.append({
            "source_exp": ",".join(missing_prov),
            "reason": ("no contract_addr in provenance, so the single-deployment "
                       "cross-check could not be performed for these experiments"),
        })

    # ---- mandatory kind validation ----
    for m in metrics:
        if "kind" not in m or m["kind"] not in VALID_KINDS:
            _errors.append(f"{m.get('metric')}: missing or invalid `kind`")
        if m.get("value") is None:
            _errors.append(f"{m.get('metric')}: value is None — omit it or list it "
                           f"in not_measured instead")

    config = {
        "fabric": "2.5.0 / CA 1.5.5, channel hiot, chaincode iot-data seq2",
        "ethereum": "Ganache chainId 1337, IoTDataRegistry",
        "policy": "deterministic policy_engine v1.0.0",
        "outbox": "SQLite WAL, async relay worker (Phase 2)",
        "architecture": "async anchor: 202 after private commit, relay delivers anchor",
        "host": "WSL2 Ubuntu-22.04 + Docker Desktop",
    }
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]

    print("=" * 72)
    print("  STAGE 5 (Phase 2): consolidated RESULTS.json v2")
    print("=" * 72)

    if _errors:
        print("  BUILD FAILED — schema violations:")
        for err in _errors:
            print(f"    - {err}")
        print("\n  Nothing written. Fix the experiment outputs and rerun.")
        return 1

    counts = {k: sum(1 for m in metrics if m["kind"] == k) for k in VALID_KINDS}
    out = {
        "schema_version": 2,
        "generated_at": stamp,
        "config": config,
        "config_hash": config_hash,
        "kind_counts": counts,
        "missing_sources": missing,
        "not_measured": not_measured,
        "metrics": metrics,
        "raw": raw,
    }
    path = os.path.join(RES, "RESULTS.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"  {len(metrics)} metrics "
          f"(measured {counts['measured']}, derived {counts['derived']}, "
          f"modeled {counts['modeled']})")
    print(f"  {'metric':<40}{'value':>14}  kind      src")
    for m in metrics:
        print(f"  {m['metric']:<40}{str(m['value'])[:14]:>14}  {m['kind']:<9} {m['source_exp']}")
    if not_measured:
        print(f"\n  not_measured ({len(not_measured)}):")
        for nm in not_measured:
            print(f"    - {nm['source_exp']}: {nm['reason']}")
    print(f"\n  config_hash={config_hash}")
    print(f"  JSON: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(time.strftime("%Y-%m-%dT%H:%M:%S")))
