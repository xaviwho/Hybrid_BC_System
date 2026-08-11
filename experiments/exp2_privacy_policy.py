#!/usr/bin/env python3
"""
Experiment 2 (rebuilt): Privacy Routing Correctness under a Deterministic Policy
================================================================================
Replaces the old `exp2_privacy_routing.py`, which fabricated a probabilistic
classifier (hardcoded 92% accuracy, np.random confidences, a meaningless
threshold sweep) over synthetic data. See PHASE0_FINDINGS.md.

Privacy routing is now a DETERMINISTIC policy (ml/privacy_filter/policy_engine.py).
With a deterministic gate there is no probability to sweep and no "leakage rate"
to estimate: the privacy guarantee is a CORRECTNESS PROPERTY, proven by
construction and verified here by exhaustive test.

This script reports, with NO randomness anywhere:
  1. Policy coverage  - fraction of observed fields matched by an explicit rule
                        vs. the fail-closed default.
  2. Correctness      - an adversarial battery of known-sensitive records; we
                        confirm ZERO sensitive fields reach the public-ledger
                        projection (`shareable_data`). This is 0 by construction;
                        the test exists to keep it 0 as the policy evolves.
  3. Routing accuracy - public vs. sensitive routing decision against curated
                        ground truth (exact, not sampled).

Outputs: experiments/results/exp2/exp2_policy_results.json
         experiments/results/exp2/exp2_policy_table.tex
         experiments/results/exp2/exp2_policy_coverage.{png,pdf}
"""

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

# Make the policy engine importable.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "ml"))
from privacy_filter import policy_engine  # noqa: E402
from privacy_filter.policy_engine import Sensitivity, classify_record, PUBLIC_LEDGER_THRESHOLD  # noqa: E402

OUTPUT_DIR = os.path.join(_REPO, "experiments", "results", "exp2")


@dataclass
class Case:
    """A curated, ground-truth-labeled record."""
    name: str
    record: Dict[str, Any]
    expect_sensitive: bool          # True if it must NOT be public-routable as-is
    must_redact: Set[str]           # leaf field names that must never be published


def curated_dataset() -> List[Case]:
    """Concrete, enumerated cases spanning HIPAA, GDPR Art. 9, PCI, secrets,
    quasi-identifiers, and benign telemetry. No sampling, no randomness."""
    return [
        # ---- Fully public records -------------------------------------------
        Case("env_sensor", {
            "id": "e1", "deviceId": "sensor_1", "timestamp": "2026-01-01T00:00:00Z",
            "data": {"temperature": 21.3, "humidity": 55, "pressure": 1012, "location": "zone_2"},
        }, expect_sensitive=False, must_redact=set()),
        Case("industrial_telemetry", {
            "id": "e2", "deviceType": "pump", "rpm": 1450, "voltage": 230,
            "vibration": 0.02, "status": "nominal", "facility": "plant_A",
        }, expect_sensitive=False, must_redact=set()),

        # ---- HIPAA identifiers ----------------------------------------------
        Case("healthcare_patient", {
            "id": "h1", "deviceId": "monitor_7", "timestamp": "2026-01-01T00:00:00Z",
            "patientId": "P12345", "diagnosis": "hypertension", "heartRate": 78,
            "temperature": 36.7,
        }, expect_sensitive=True, must_redact={"patientId", "diagnosis", "heartRate"}),
        Case("ssn_record", {
            "id": "h2", "ssn": "123-45-6789", "temperature": 22.0,
        }, expect_sensitive=True, must_redact={"ssn"}),
        Case("contact_pii", {
            "id": "h3", "email": "a@b.com", "phone": "555-1234", "humidity": 40,
        }, expect_sensitive=True, must_redact={"email", "phone"}),

        # ---- PCI / financial -------------------------------------------------
        Case("payment", {
            "id": "f1", "creditCard": "4111 1111 1111 1111", "cvv": "123",
            "deviceId": "kiosk_3",
        }, expect_sensitive=True, must_redact={"creditCard", "cvv"}),
        Case("bank", {
            "id": "f2", "bankAccount": "000123456", "salary": 90000, "zone": "z1",
        }, expect_sensitive=True, must_redact={"bankAccount", "salary"}),

        # ---- Secrets ---------------------------------------------------------
        Case("secrets", {
            "id": "s1", "password": "hunter2", "apiKey": "sk-xyz", "status": "ok",
        }, expect_sensitive=True, must_redact={"password", "apiKey"}),

        # ---- GDPR Art. 9 special categories ---------------------------------
        Case("gdpr_special", {
            "id": "g1", "genetic": "BRCA1+", "religion": "n/a", "temperature": 20,
        }, expect_sensitive=True, must_redact={"genetic", "religion"}),

        # ---- Precise geolocation vs coarse location -------------------------
        Case("precise_geo", {
            "id": "geo1", "exactLocation": "37.422,-122.084", "zone": "campus",
        }, expect_sensitive=True, must_redact={"exactLocation"}),

        # ---- Quasi-identifiers ----------------------------------------------
        Case("quasi_ids", {
            "id": "q1", "dateOfBirth": "1990-01-01", "zipCode": "94103",
            "temperature": 19.5,
        }, expect_sensitive=True, must_redact={"dateOfBirth", "zipCode"}),

        # ---- Value-based escalation (benign name, sensitive value) ----------
        Case("hidden_ssn_in_note", {
            "id": "v1", "note": "patient SSN 123-45-6789 on file", "humidity": 33,
        }, expect_sensitive=True, must_redact={"note"}),

        # ---- Unknown field -> fail closed -----------------------------------
        Case("unknown_field", {
            "id": "u1", "mysteryReading": 42, "temperature": 25,
        }, expect_sensitive=True, must_redact={"mysteryReading"}),
    ]


def _leaf_levels(record: Dict[str, Any]) -> List[Sensitivity]:
    """All leaf sensitivity levels of a (possibly nested) record."""
    return [fd.level for fd in classify_record(record).field_decisions]


def run() -> Dict[str, Any]:
    cases = curated_dataset()

    # ---- 2. Correctness / adversarial leakage ------------------------------
    leaks: List[Dict[str, Any]] = []
    routing_rows: List[Dict[str, Any]] = []
    correct_routes = 0

    for c in cases:
        resp = policy_engine.filter_for_publication(c.record)
        shareable = resp["shareable_data"]
        predicted_sensitive = resp["data_sensitivity"] == "sensitive"

        # (a) No field above PUBLIC may appear anywhere in shareable_data.
        published_levels = _leaf_levels(shareable)
        above = [lvl for lvl in published_levels if lvl > PUBLIC_LEDGER_THRESHOLD]
        if above:
            leaks.append({"case": c.name, "reason": "non-public leaf in shareable_data",
                          "levels": [l.name for l in above], "shareable": shareable})

        # (b) Every field we declared must-redact must be absent from shareable.
        flat_shareable_keys = set(_flatten_keys(shareable))
        for must in c.must_redact:
            if must in flat_shareable_keys:
                leaks.append({"case": c.name, "reason": f"must-redact field published: {must}",
                              "shareable": shareable})

        # (c) Routing decision vs ground truth.
        route_ok = (predicted_sensitive == c.expect_sensitive)
        correct_routes += int(route_ok)
        routing_rows.append({
            "case": c.name,
            "expected": "sensitive" if c.expect_sensitive else "public",
            "predicted": resp["data_sensitivity"],
            "max_sensitivity": resp["max_sensitivity"],
            "route_ok": route_ok,
            "redacted_fields": resp["redacted_fields"],
        })

    # ---- 1. Coverage --------------------------------------------------------
    coverage = policy_engine.policy_coverage([c.record for c in cases])

    results = {
        "experiment": "exp2_privacy_policy",
        "engine": "deterministic-policy",
        "policy_version": policy_engine.POLICY_VERSION,
        "n_cases": len(cases),
        "routing_accuracy": correct_routes / len(cases),
        "routing_correct": correct_routes,
        "leak_count": len(leaks),
        "leaks": leaks,
        "guarantee_holds": len(leaks) == 0,
        "coverage": coverage,
        "routing_detail": routing_rows,
    }
    return results


def _flatten_keys(obj: Any) -> List[str]:
    """Recursively collect leaf key names from a nested dict/list."""
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                out.extend(_flatten_keys(v))
            else:
                out.append(k)
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_flatten_keys(v))
    return out


def write_latex(results: Dict[str, Any], path: str) -> None:
    cov = results["coverage"]
    lines = [
        r"\begin{table}[htbp]", r"\centering",
        r"\caption{Deterministic privacy-routing policy: correctness and coverage (Experiment 2)}",
        r"\label{tab:privacy_policy}",
        r"\begin{tabular}{lc}", r"\toprule",
        r"\textbf{Metric} & \textbf{Value} \\", r"\midrule",
        f"Curated test records & {results['n_cases']} \\\\",
        f"Routing accuracy & {results['routing_accuracy']*100:.1f}\\% \\\\",
        f"Sensitive-field leaks to public ledger & {results['leak_count']} \\\\",
        f"Public-ledger guarantee holds & {'Yes' if results['guarantee_holds'] else 'No'} \\\\",
        f"Policy field coverage & {cov['coverage']*100:.1f}\\% \\\\",
        f"Fields via explicit rule & {cov['explicit_rule_fields']}/{cov['total_fields']} \\\\",
        f"Fields via fail-closed default & {cov['default_fields']}/{cov['total_fields']} \\\\",
        r"\bottomrule", r"\end{tabular}", r"\end{table}",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def write_figure(results: Dict[str, Any], path_png: str) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    cov = results["coverage"]
    fig, ax = plt.subplots(figsize=(6, 4))
    explicit = cov["explicit_rule_fields"]
    default = cov["default_fields"]
    ax.bar(["Explicit rule", "Fail-closed default"], [explicit, default],
           color=["#2ecc71", "#e67e22"])
    ax.set_ylabel("Field count")
    ax.set_title(f"Policy coverage ({cov['coverage']*100:.0f}% explicit) — {results['leak_count']} leaks")
    for i, v in enumerate([explicit, default]):
        ax.text(i, v, str(v), ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(path_png, dpi=300, bbox_inches="tight")
    fig.savefig(path_png.replace(".png", ".pdf"), bbox_inches="tight")
    plt.close(fig)
    return True


def main() -> int:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = run()

    json_path = os.path.join(OUTPUT_DIR, "exp2_policy_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    write_latex(results, os.path.join(OUTPUT_DIR, "exp2_policy_table.tex"))
    fig_ok = write_figure(results, os.path.join(OUTPUT_DIR, "exp2_policy_coverage.png"))

    print("=" * 68)
    print("  EXPERIMENT 2 (rebuilt): Deterministic Privacy-Routing Correctness")
    print("=" * 68)
    print(f"  Curated records            : {results['n_cases']}")
    print(f"  Routing accuracy           : {results['routing_accuracy']*100:.1f}% "
          f"({results['routing_correct']}/{results['n_cases']})")
    print(f"  Sensitive-field leaks      : {results['leak_count']}")
    print(f"  Public-ledger guarantee    : {'HOLDS' if results['guarantee_holds'] else 'VIOLATED'}")
    print(f"  Policy field coverage      : {results['coverage']['coverage']*100:.1f}%  "
          f"({results['coverage']['explicit_rule_fields']}/{results['coverage']['total_fields']} explicit)")
    if results["coverage"]["unmatched_field_names"]:
        print(f"  Unmatched (fail-closed)    : {results['coverage']['unmatched_field_names']}")
    if results["leaks"]:
        print("\n  !!! LEAKS DETECTED:")
        for lk in results["leaks"]:
            print(f"    - {lk}")
    print(f"\n  JSON  : {json_path}")
    print(f"  LaTeX : {os.path.join(OUTPUT_DIR, 'exp2_policy_table.tex')}")
    print(f"  Figure: {'written' if fig_ok else 'skipped (matplotlib unavailable)'}")
    print("=" * 68)

    # Non-zero exit if the privacy guarantee is violated (CI-friendly).
    return 0 if results["guarantee_holds"] and results["routing_accuracy"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
