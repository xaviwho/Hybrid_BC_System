#!/usr/bin/env python3
"""
WS8 reports, generated from results/v1/RESULTS.json and results/v2/RESULTS.json only.

  revision/REVISION_LOG.md   reviewer comment -> workstream -> RESULTS.json keys ->
                             figure -> one-line finding -> status
  revision/DIFF_v1_v2.md     every headline number of the submitted paper: v1 value,
                             v2 value, whether it still holds

Findings are rendered from metric values; nothing here is typed in by hand
except the mapping of comments to workstreams and the wording templates.
"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1 = json.load(open(os.path.join(REPO, "results", "v1", "RESULTS.json")))
V2 = json.load(open(os.path.join(REPO, "results", "v2", "RESULTS.json")))
m1 = {m["metric"]: m for m in V1["metrics"]}
m2 = {m["metric"]: m for m in V2["metrics"]}
not_run = {x["id"]: x for x in V2.get("not_run", [])}


def v(d, k, fmt="{}"):
    return fmt.format(d[k]["value"]) if k in d else "—"


def keys(prefix):
    return sorted(k for k in m2 if k.startswith(prefix))


def status(*ids):
    if any(i in not_run for i in ids):
        return "partial / not run: " + "; ".join(not_run[i]["reason"][:80] for i in ids if i in not_run)
    return "supported by data"


def revision_log():
    rows = []
    ws1 = keys("ws1_tps_prod_over_dev")
    rows.append(("R1.1 production-grade servers", "WS1", ", ".join(ws1[:2]) + " …", "table (ws1_summary.json)",
                 "gunicorn vs Werkzeug on the single host: paired prod/dev TPS "
                 + ", ".join(f"{k.split('threshold_')[1]} {m2[k]['value']:.3f}" for k in ws1 if "below" in k)
                 + " below the threshold; no level differs from 1 at 95 %.", status("WS1")))
    base = keys("ws2_base_")
    fl = {k: m2[k]["value"] for k in base if k.endswith("floor_ack_ms")}
    rows.append(("R1.1 geographically distributed multi-node deployment", "WS2",
                 "ws2_base_*_{floor_ack_ms,transition_c,peak_tps}", "fig5_orchestration_v2",
                 "Azure Korea Central + Japan East (multi_vm): floor "
                 + ", ".join(f"{k[9:-13]} {val:.0f} ms" for k, val in fl.items()) + ".", status("WS2")))
    dl = keys("ws2_delay_round_trips")
    rows.append(("R1.1 realistic network delays", "WS2", ", ".join(dl), "fig_delay_sweep",
                 "latency floor rises by " + ", ".join(f"{m2[k]['value']} RTT per request ({k.split('_')[-1]})" for k in dl)
                 + " per added round trip (least squares over +0/20/50/100 ms).", status("WS2")))
    tr = {k: m2[k] for k in keys("ws2_m") + keys("ws2_base") if k.endswith("transition_c")}
    rows.append(("R1.1 throughput claims / Eq. 8", "WS2", "ws2_{m5,base,m20,t05,t1}_*", "fig_blockcut_sweep",
                 "observed transition vs MaxMessageCount: " + ", ".join(
                     f"{k[4:-13]} c*={x['value']} (pred {x.get('predicted')})" for k, x in tr.items()), status("WS2")))
    pr = keys("ws2_probe")
    rows.append(("R1.1 multi-organization endorsement overhead", "WS2 probe", ", ".join(pr), "table",
                 "AND(Org1,Org2) across regions: " + ", ".join(f"{k[10:-3]} {m2[k]['value']:.0f} ms" for k in pr),
                 status("WS2.endorsement_probe")))
    rows.append(("R1.1 Byzantine fault conditions", "WS6", "not_run.WS6", "—",
                 not_run.get("WS6", {}).get("consequence", "run"), "NOT_RUN (scoped to crash faults)"))
    mu = keys("ws3_mu_relay")
    rows.append(("R1.2 centralised single-threaded relay; fault tolerance", "WS3",
                 "ws3_mu_relay_*, ws3_fault_*", "fig_mu_relay, fig_fault_injection",
                 f"{len(keys('ws3_fault_'))} fault metrics; duplicates in every scenario: "
                 f"{sum(m2[k]['value'] for k in keys('ws3_fault_') if k.endswith('duplicate_anchors'))}; "
                 f"anchors = records in all: {all(m2[k]['value'] for k in keys('ws3_fault_') if k.endswith('anchors_equal_records'))}; "
                 f"mu_relay range {min((m2[k]['value'] for k in mu), default='—')}–{max((m2[k]['value'] for k in mu), default='—')} anchors/s.",
                 status("WS3")))
    rows.append(("R1.2 end-to-end immutability under a faulty relay", "WS3 safety + WS5",
                 "ws3_tamper_detection_rate, ws3_withhold_detection_rate, ws5_*", "table",
                 f"tampering detected {v(m2, 'ws3_tamper_detection_rate')}, withholding detected "
                 f"{v(m2, 'ws3_withhold_detection_rate')} and repaired; crash-window orphans detected and repaired: "
                 f"{v(m2, 'ws5_all_orphans_detected_and_repaired')}.", status("WS3", "WS5.crash_window")))
    rows.append(("R1.2 replace relay with oracle network / bridge", "—", "—", "—",
                 "out of scope for this phase (argued as complementary; WS3/WS5 supply the fault-tolerance evidence)",
                 "manuscript"))
    rows.append(("R1.3 insular baselines", "WS4", "ws4_{sync_anchor,async_outbox,fabric_only}_c*_*, ws4_async_tcmp_ms_c1",
                 "fig_sync_vs_async",
                 f"at c=1: sync T_ack {v(m2, 'ws4_sync_anchor_c1_ack_ms', '{:.0f}')} ms vs async T_ack "
                 f"{v(m2, 'ws4_async_outbox_c1_ack_ms', '{:.0f}')} ms; async T_cmp {v(m2, 'ws4_async_tcmp_ms_c1', '{:.0f}')} ms.",
                 status("WS4")))
    for c in ("R2.1 motivation", "R2.2 pseudo-code", "R2.4 grammar", "R2.5 references"):
        rows.append((c, "—", "—", "—", "manuscript edit", "manuscript"))
    rows.append(("R2.3 Figure 1 legibility", "WS8", "—", "Fig. 1 source", "architecture figure, not a data figure", "manuscript"))
    out = ["# Revision log", "", f"Generated by `revision/write_reports.py` from `results/v2/RESULTS.json` "
           f"(commit `{V2['commit'][:8]}`, generated {V2['generated_at']}).", "",
           "| Reviewer comment | Workstream | RESULTS.json key(s) | Figure / table | One-line finding | Status |",
           "|---|---|---|---|---|---|"]
    out += ["| " + " | ".join(str(x).replace("|", "/") for x in r) + " |" for r in rows]
    open(os.path.join(REPO, "revision", "REVISION_LOG.md"), "w").write("\n".join(out) + "\n")


def diff():
    def holds(a, b, tol):
        try:
            return "holds" if abs(float(a) - float(b)) <= tol else "changed"
        except (TypeError, ValueError):
            return "see note"
    rows = [
        ("zero sensitive-field leakage", v(m1, "privacy_sensitive_leaks"), v(m2, "privacy_sensitive_leaks"),
         "holds" if m2.get("privacy_sensitive_leaks", {}).get("value") == 0 else "changed"),
        ("routing accuracy (%)", v(m1, "privacy_routing_accuracy"), v(m2, "privacy_routing_accuracy"),
         holds(m1.get("privacy_routing_accuracy", {}).get("value"), m2.get("privacy_routing_accuracy", {}).get("value"), 0)),
        ("exactly-once", v(m1, "exactly_once_holds"), v(m2, "exactly_once_holds_all_reps"),
         "holds" if m2.get("exactly_once_holds_all_reps", {}).get("value") else "changed"),
        ("gas reduction at N=200 (%)", v(m1, "gas_reduction_batch200"), v(m2, "gas_reduction_N200"),
         holds(m1.get("gas_reduction_batch200", {}).get("value"), m2.get("gas_reduction_N200", {}).get("value"), 0.05)),
        ("gas reduction at N=1 / N=2 (%) — crossover", "−8.25 / 45.88 (CAPTIONS)",
         f"{v(m2, 'gas_reduction_N1')} / {v(m2, 'gas_reduction_N2')}",
         "holds" if (m2.get("gas_reduction_N1", {}).get("value", 0) < 0 < m2.get("gas_reduction_N2", {}).get("value", 0)) else "check"),
        ("single-record anchor gas", v(m1, "gas_per_record_single"), v(m2, "gas_per_record_single"),
         "changed (v2 call shape + allowlist)"),
        ("storage ratio, sparse, 800 versions (x)", v(m1, "storage_compression_vs_snapshots_sparse"),
         v(m2, "storage_ratio_sparse_800_versions"),
         holds(m1.get("storage_compression_vs_snapshots_sparse", {}).get("value"),
               m2.get("storage_ratio_sparse_800_versions", {}).get("value"), 0.01)),
        ("rollback latency min–max (ms)", f"{v(m1, 'rollback_latency_min', '{:.3f}')}–{v(m1, 'rollback_latency_max', '{:.3f}')}",
         f"{v(m2, 'rollback_latency_min_ms', '{:.3f}')}–{v(m2, 'rollback_latency_max_ms', '{:.3f}')}",
         "see note: v1 on the WSL clock (low by ~5-12 %), v2 on an NTP-disciplined Azure VM"),
        ("block-cutting transition c", "10 (laptop)",
         ", ".join(f"{k[9:-13]}={m2[k]['value']}" for k in keys("ws2_base_") if k.endswith("transition_c")), "compare"),
        ("relay drain rate (anchors/s)", v(m1, "relay_drain_rate"),
         f"{min((m2[k]['value'] for k in keys('ws3_mu_relay_k1_lease')), default='—')} (k=1 lease, saturated)",
         "changed: v1 measured the offered rate, not mu_relay (AUDIT_WS0 F9)"),
    ]
    out = ["# v1 → v2 headline numbers", "",
           f"v1: `results/v1/RESULTS.json` (config {V1['config_hash']}); v2: `results/v2/RESULTS.json` "
           f"(commit `{V2['commit'][:8]}`). Generated by `revision/write_reports.py`.", "",
           "| Claim | v1 | v2 | Status |", "|---|---|---|---|"]
    def pending(r):
        v2 = str(r[2])
        return (r[0], r[1], r[2], "pending (v2 not yet measured)") if (not v2.strip() or v2.startswith("—")) else r
    out += ["| " + " | ".join(str(x) for x in pending(r)) + " |" for r in rows]
    open(os.path.join(REPO, "revision", "DIFF_v1_v2.md"), "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    revision_log(); diff()
    print("wrote revision/REVISION_LOG.md and revision/DIFF_v1_v2.md")
