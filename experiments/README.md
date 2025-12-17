# Experimental Evaluation Suite

This directory contains the comprehensive experimental evaluation suite for the **Hybrid Blockchain Digital Twin System** journal paper.

## Overview

The suite validates the analytical models presented in the paper through five mandatory experiments:

| Experiment | Description | Equations Validated |
|------------|-------------|---------------------|
| **Exp 1** | End-to-End Latency and Throughput | Eq. 28, 30-32 |
| **Exp 2** | Privacy Routing Accuracy and Risk Control | Eq. 35 |
| **Exp 3** | Cost and Gas Efficiency of Ethereum Anchoring | Eq. 23-26 |
| **Exp 4** | Digital Twin Lifecycle Overhead and Recovery | Eq. 38, 42 |
| **Exp 5** | Exactly-Once Semantics and Failure Handling | - |

## Prerequisites

1. **System Services Running:**
   - Orchestrator service (port 5002)
   - Privacy Filter ML service (port 5001)
   - Ganache/Ethereum node (port 8545)
   - Hyperledger Fabric network (optional for full tests)

2. **Python Dependencies:**
   ```bash
   pip install -r experiments/requirements.txt
   ```

## Quick Start

### Run All Experiments (Quick Mode)
```bash
python experiments/run_all_experiments.py --quick
```

### Run All Experiments (Full Mode)
```bash
python experiments/run_all_experiments.py
```

### Run Specific Experiments
```bash
# Run only experiments 1 and 3
python experiments/run_all_experiments.py --exp 1 3

# Run experiment 2 in quick mode
python experiments/run_all_experiments.py --quick --exp 2
```

### Run Individual Experiments
```bash
python experiments/exp1_latency_throughput.py
python experiments/exp2_privacy_routing.py
python experiments/exp3_gas_efficiency.py
python experiments/exp4_lifecycle_overhead.py
python experiments/exp5_exactly_once.py
```

## Output Structure

```
experiments/results/
├── combined_report.json      # Aggregated results
├── experimental_results.tex  # LaTeX document with tables
├── report.html               # HTML visualization
├── exp1/
│   ├── exp1_results.json
│   ├── exp1_latency_breakdown.png
│   ├── exp1_throughput_curve.png
│   └── exp1_latency_distribution.png
├── exp2/
│   ├── exp2_results.json
│   ├── exp2_confusion_matrix.png
│   ├── exp2_threshold_sweep.png
│   └── exp2_precision_recall.png
├── exp3/
│   ├── exp3_results.json
│   ├── exp3_gas_vs_batch.png
│   ├── exp3_cost_latency.png
│   └── exp3_comparison_bar.png
├── exp4/
│   ├── exp4_results.json
│   ├── exp4_storage_growth.png
│   ├── exp4_rollback_latency.png
│   └── exp4_checkpoint_speedup.png
└── exp5/
    ├── exp5_results.json
    ├── exp5_failure_results.png
    └── exp5_idempotency.png
```

## Experiment Details

### Experiment 1: End-to-End Latency and Throughput

**Purpose:** Validate the queuing-theoretic latency model and throughput bounds.

**Metrics:**
- Per-stage latency breakdown (preprocessing, ML inference, Fabric commit, Ethereum anchor, notification)
- Mean, P95, P99 latencies
- Throughput vs arrival-rate curves
- Saturation point and back-pressure onset

**Scenarios:**
- Fabric-only path (public data)
- Fabric + Ethereum anchoring path (sensitive data)

**Reviewer Question:** *Does Ethereum anchoring dominate latency, and is it bounded as claimed?*

---

### Experiment 2: Privacy Routing Accuracy and Risk Control

**Purpose:** Validate the privacy leakage budget ε and threshold τ selection.

**Metrics:**
- Classification accuracy, precision, recall per class
- Confusion matrix (Public vs Confidential)
- Misrouting probability vs threshold τ
- Privacy budget compliance verification

**Key Validation:** Pr[misroute to public] ≤ ε

**Reviewer Question:** *Does the system actually respect the privacy budget?*

---

### Experiment 3: Cost and Gas Efficiency of Ethereum Anchoring

**Purpose:** Validate the gas model and batching strategy effectiveness.

**Metrics:**
- Gas per record (single vs Merkle-batched)
- Gas reduction percentage
- Cost-latency trade-off curve
- Optimal batch size (knee point)

**Comparison:**
- Single-item anchoring baseline
- Merkle-batched anchoring (N = 1, 2, 5, 10, 20, 50, 100, 200)

**Reviewer Question:** *Is batching worth it, and where is the knee point?*

---

### Experiment 4: Digital Twin Lifecycle Overhead and Recovery

**Purpose:** Validate versioning storage model and rollback time bounds.

**Metrics:**
- Storage growth vs number of versions
- Delta-based vs full snapshot comparison
- Rollback latency vs rollback depth
- Checkpoint impact on recovery time

**Key Validation:**
- Storage overhead follows Eq. 38
- Rollback time follows Eq. 42

**Reviewer Question:** *Is rollback practical at scale?*

---

### Experiment 5: Exactly-Once Semantics and Failure Handling

**Purpose:** Validate idempotency and transactional guarantees under failure.

**Tests:**
- Idempotency (duplicate requests with same key)
- Orchestrator crash recovery
- Ethereum relay failure handling
- Concurrent duplicate request handling

**Verification:**
- No duplicate anchors
- No lost commits
- Consistent Fabric/Ethereum state

**Reviewer Question:** *Does exactly-once hold under failure?*

## Configuration

Default service endpoints (modify in each experiment file if needed):

```python
ORCHESTRATOR_URL = "http://localhost:5002"
PRIVACY_FILTER_URL = "http://localhost:5001"
GANACHE_URL = "http://localhost:8545"
```

## Generating Paper-Ready Outputs

After running experiments, you'll find:

1. **LaTeX Tables:** In `experimental_results.tex` and printed to console
2. **Publication-Quality Plots:** PNG (300 DPI) and PDF formats
3. **Raw Data:** JSON files for custom analysis

### Including in Paper

```latex
% In your paper's preamble
\usepackage{graphicx}
\usepackage{booktabs}

% Include a figure
\begin{figure}[htbp]
\centering
\includegraphics[width=0.8\textwidth]{experiments/results/exp1/exp1_latency_breakdown.pdf}
\caption{End-to-end latency breakdown by processing stage}
\label{fig:latency_breakdown}
\end{figure}

% Include the generated tables directly
\input{experiments/results/experimental_results.tex}
```

## Troubleshooting

### Services Not Running
```
Error: Cannot connect to orchestrator
```
**Solution:** Start the system services first:
```bash
./start-hybrid-system.sh
```

### Missing Dependencies
```
ModuleNotFoundError: No module named 'matplotlib'
```
**Solution:** Install requirements:
```bash
pip install -r experiments/requirements.txt
```

### Timeout Errors
If experiments timeout, the services may be overloaded. Try:
1. Running in quick mode first
2. Reducing concurrent load
3. Increasing timeout values in experiment files

## Citation

If you use this experimental suite, please cite the paper:

```bibtex
@article{hybrid_blockchain_dt,
  title={Hybrid Blockchain Architecture for Privacy-Preserving Digital Twin Systems},
  author={...},
  journal={...},
  year={2024}
}
```
