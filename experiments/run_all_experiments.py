#!/usr/bin/env python3
"""
Unified Experiment Runner for Hybrid Blockchain Digital Twin System
====================================================================
Runs all experiments and generates a comprehensive report for the journal paper.

Experiments:
1. End-to-End Latency and Throughput (Eq. 28, 30-32)
2. Privacy Routing Accuracy and Risk Control (Eq. 35)
3. Cost and Gas Efficiency of Ethereum Anchoring (Eq. 23-26)
4. Digital Twin Lifecycle Overhead and Recovery (Eq. 38, 42)
5. Exactly-Once Semantics and Failure Handling

Usage:
    python run_all_experiments.py [--quick] [--exp N] [--output-dir DIR]
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import experiment modules
from experiments.exp1_latency_throughput import LatencyThroughputExperiment
from experiments.exp2_privacy_routing import PrivacyRoutingExperiment
from experiments.exp3_gas_efficiency import GasEfficiencyExperiment
from experiments.exp4_lifecycle_overhead import LifecycleOverheadExperiment
from experiments.exp5_exactly_once import ExactlyOnceExperiment


class ExperimentRunner:
    """Unified experiment runner and report generator"""
    
    def __init__(self, output_dir: str = "experiments/results", quick_mode: bool = False):
        self.output_dir = output_dir
        self.quick_mode = quick_mode
        self.results = {}
        self.start_time = None
        self.end_time = None
        
        # Create output directories
        os.makedirs(output_dir, exist_ok=True)
        for i in range(1, 6):
            os.makedirs(f"{output_dir}/exp{i}", exist_ok=True)
    
    def get_experiment_params(self, exp_num: int) -> Dict:
        """Get experiment parameters based on mode"""
        if self.quick_mode:
            params = {
                1: {"latency_samples": 20, "throughput_duration": 10.0},
                2: {"n_samples": 100, "privacy_budget": 0.05},
                3: {"n_single_records": 10, "samples_per_batch": 2},
                4: {"max_versions": 30, "max_rollback_depth": 20, "samples_per_depth": 2},
                5: {"idempotency_requests": 5, "failure_requests": 8, "duplicate_requests": 4}
            }
        else:
            params = {
                1: {"latency_samples": 100, "throughput_duration": 30.0},
                2: {"n_samples": 500, "privacy_budget": 0.05},
                3: {"n_single_records": 30, "samples_per_batch": 5},
                4: {"max_versions": 100, "max_rollback_depth": 50, "samples_per_depth": 5},
                5: {"idempotency_requests": 15, "failure_requests": 20, "duplicate_requests": 10}
            }
        return params.get(exp_num, {})
    
    def run_experiment_1(self) -> Dict:
        """Run Experiment 1: Latency and Throughput"""
        print("\n" + "="*80)
        print("  RUNNING EXPERIMENT 1: End-to-End Latency and Throughput")
        print("="*80)
        
        params = self.get_experiment_params(1)
        experiment = LatencyThroughputExperiment()
        
        try:
            results = experiment.run_full_experiment(**params)
            experiment.generate_plots(f"{self.output_dir}/exp1")
            experiment.export_results(f"{self.output_dir}/exp1/exp1_results.json")
            
            return {
                "status": "success",
                "summary": experiment._generate_summary_dict(),
                "latex": experiment.generate_latex_table()
            }
        except Exception as e:
            print(f"  ERROR in Experiment 1: {e}")
            return {"status": "error", "error": str(e)}
    
    def run_experiment_2(self) -> Dict:
        """Run Experiment 2: Privacy Routing"""
        print("\n" + "="*80)
        print("  RUNNING EXPERIMENT 2: Privacy Routing Accuracy and Risk Control")
        print("="*80)
        
        params = self.get_experiment_params(2)
        experiment = PrivacyRoutingExperiment()
        
        try:
            results = experiment.run_full_experiment(**params)
            experiment.generate_plots(f"{self.output_dir}/exp2")
            experiment.export_results(f"{self.output_dir}/exp2/exp2_results.json")
            
            return {
                "status": "success",
                "summary": experiment._generate_summary_dict(),
                "latex": experiment.generate_latex_table()
            }
        except Exception as e:
            print(f"  ERROR in Experiment 2: {e}")
            return {"status": "error", "error": str(e)}
    
    def run_experiment_3(self) -> Dict:
        """Run Experiment 3: Gas Efficiency"""
        print("\n" + "="*80)
        print("  RUNNING EXPERIMENT 3: Cost and Gas Efficiency")
        print("="*80)
        
        params = self.get_experiment_params(3)
        experiment = GasEfficiencyExperiment()
        
        try:
            results = experiment.run_full_experiment(**params)
            experiment.generate_plots(f"{self.output_dir}/exp3")
            experiment.export_results(f"{self.output_dir}/exp3/exp3_results.json")
            
            return {
                "status": "success",
                "summary": experiment._generate_summary_dict(),
                "latex": experiment.generate_latex_table()
            }
        except Exception as e:
            print(f"  ERROR in Experiment 3: {e}")
            return {"status": "error", "error": str(e)}
    
    def run_experiment_4(self) -> Dict:
        """Run Experiment 4: Lifecycle Overhead"""
        print("\n" + "="*80)
        print("  RUNNING EXPERIMENT 4: Digital Twin Lifecycle Overhead")
        print("="*80)
        
        params = self.get_experiment_params(4)
        experiment = LifecycleOverheadExperiment()
        
        try:
            results = experiment.run_full_experiment(**params)
            experiment.generate_plots(f"{self.output_dir}/exp4")
            experiment.export_results(f"{self.output_dir}/exp4/exp4_results.json")
            
            return {
                "status": "success",
                "summary": experiment._generate_summary_dict(),
                "latex": experiment.generate_latex_table()
            }
        except Exception as e:
            print(f"  ERROR in Experiment 4: {e}")
            return {"status": "error", "error": str(e)}
    
    def run_experiment_5(self) -> Dict:
        """Run Experiment 5: Exactly-Once Semantics"""
        print("\n" + "="*80)
        print("  RUNNING EXPERIMENT 5: Exactly-Once Semantics")
        print("="*80)
        
        params = self.get_experiment_params(5)
        experiment = ExactlyOnceExperiment()
        
        try:
            results = experiment.run_full_experiment(**params)
            experiment.generate_plots(f"{self.output_dir}/exp5")
            experiment.export_results(f"{self.output_dir}/exp5/exp5_results.json")
            
            return {
                "status": "success",
                "summary": experiment._generate_summary_dict(),
                "latex": experiment.generate_latex_table()
            }
        except Exception as e:
            print(f"  ERROR in Experiment 5: {e}")
            return {"status": "error", "error": str(e)}
    
    def run_all(self, experiments: List[int] = None) -> Dict:
        """Run all or selected experiments"""
        if experiments is None:
            experiments = [1, 2, 3, 4, 5]
        
        self.start_time = datetime.now()
        
        print("\n" + "="*80)
        print("  HYBRID BLOCKCHAIN DIGITAL TWIN SYSTEM")
        print("  COMPREHENSIVE EXPERIMENTAL EVALUATION")
        print("="*80)
        print(f"  Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Mode: {'Quick' if self.quick_mode else 'Full'}")
        print(f"  Experiments: {experiments}")
        print(f"  Output Directory: {self.output_dir}")
        print("="*80)
        
        experiment_runners = {
            1: self.run_experiment_1,
            2: self.run_experiment_2,
            3: self.run_experiment_3,
            4: self.run_experiment_4,
            5: self.run_experiment_5
        }
        
        for exp_num in experiments:
            if exp_num in experiment_runners:
                self.results[f"experiment_{exp_num}"] = experiment_runners[exp_num]()
                time.sleep(1)  # Brief pause between experiments
        
        self.end_time = datetime.now()
        
        # Generate combined report
        self.generate_combined_report()
        
        return self.results
    
    def generate_combined_report(self):
        """Generate a combined report with all results"""
        report = {
            "title": "Hybrid Blockchain Digital Twin System - Experimental Evaluation",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
            "mode": "quick" if self.quick_mode else "full",
            "experiments": self.results
        }
        
        # Save JSON report
        report_path = f"{self.output_dir}/combined_report.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Generate LaTeX document
        self.generate_latex_document()
        
        # Generate HTML report
        self.generate_html_report()
        
        # Print summary
        self._print_final_summary()
    
    def generate_latex_document(self):
        """Generate a complete LaTeX document with all tables"""
        latex = r"""
\documentclass[11pt]{article}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{float}
\usepackage[margin=1in]{geometry}

\title{Hybrid Blockchain Digital Twin System\\Experimental Evaluation Results}
\author{Generated by Automated Experiment Suite}
\date{""" + datetime.now().strftime('%B %d, %Y') + r"""}

\begin{document}
\maketitle

\section{Introduction}
This document presents the experimental evaluation results for the Hybrid Blockchain Digital Twin System.
The experiments validate the analytical models presented in the paper.

"""
        # Add each experiment's LaTeX
        exp_titles = {
            1: "End-to-End Latency and Throughput (Eq. 28, 30-32)",
            2: "Privacy Routing Accuracy and Risk Control (Eq. 35)",
            3: "Cost and Gas Efficiency of Ethereum Anchoring (Eq. 23-26)",
            4: "Digital Twin Lifecycle Overhead and Recovery (Eq. 38, 42)",
            5: "Exactly-Once Semantics and Failure Handling"
        }
        
        for i in range(1, 6):
            exp_key = f"experiment_{i}"
            if exp_key in self.results and self.results[exp_key].get("status") == "success":
                latex += f"\n\\section{{Experiment {i}: {exp_titles[i]}}}\n"
                
                # Add figure references
                latex += f"""
\\begin{{figure}}[H]
\\centering
\\includegraphics[width=0.8\\textwidth]{{exp{i}/exp{i}_*.png}}
\\caption{{Experiment {i} Results}}
\\end{{figure}}

"""
                # Add tables
                if "latex" in self.results[exp_key]:
                    latex += self.results[exp_key]["latex"]
        
        latex += r"""
\section{Conclusion}
The experimental results validate the analytical models presented in the paper.
Key findings are summarized in the individual experiment sections above.

\end{document}
"""
        
        latex_path = f"{self.output_dir}/experimental_results.tex"
        with open(latex_path, 'w') as f:
            f.write(latex)
        
        print(f"\n  LaTeX document saved to: {latex_path}")
    
    def generate_html_report(self):
        """Generate an HTML report with embedded results"""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Experimental Evaluation Results</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 40px; }}
        .experiment {{ background: #ecf0f1; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .experiment h3 {{ color: #2980b9; margin-top: 0; }}
        .status {{ display: inline-block; padding: 5px 15px; border-radius: 20px; font-weight: bold; }}
        .status.success {{ background: #2ecc71; color: white; }}
        .status.error {{ background: #e74c3c; color: white; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #3498db; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .metric {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
        .metric-label {{ font-size: 14px; color: #7f8c8d; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        img {{ max-width: 100%; height: auto; margin: 10px 0; border-radius: 5px; }}
        .timestamp {{ color: #7f8c8d; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Hybrid Blockchain Digital Twin System</h1>
        <h2>Experimental Evaluation Results</h2>
        <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p class="timestamp">Mode: {'Quick' if self.quick_mode else 'Full'} | Duration: {(self.end_time - self.start_time).total_seconds():.1f}s</p>
"""
        
        exp_titles = {
            1: "End-to-End Latency and Throughput",
            2: "Privacy Routing Accuracy",
            3: "Gas Efficiency",
            4: "Lifecycle Overhead",
            5: "Exactly-Once Semantics"
        }
        
        for i in range(1, 6):
            exp_key = f"experiment_{i}"
            if exp_key in self.results:
                result = self.results[exp_key]
                status = result.get("status", "unknown")
                status_class = "success" if status == "success" else "error"
                
                html += f"""
        <div class="experiment">
            <h3>Experiment {i}: {exp_titles[i]}</h3>
            <span class="status {status_class}">{status.upper()}</span>
"""
                
                if status == "success" and "summary" in result:
                    summary = result["summary"]
                    html += '<div class="metrics-grid">'
                    for key, value in summary.items():
                        if isinstance(value, (int, float)):
                            if isinstance(value, float):
                                display_value = f"{value:.4f}" if value < 1 else f"{value:.2f}"
                            else:
                                display_value = str(value)
                            html += f"""
                <div class="metric-card">
                    <div class="metric">{display_value}</div>
                    <div class="metric-label">{key.replace('_', ' ').title()}</div>
                </div>
"""
                    html += '</div>'
                
                html += "</div>"
        
        html += """
    </div>
</body>
</html>
"""
        
        html_path = f"{self.output_dir}/report.html"
        with open(html_path, 'w') as f:
            f.write(html)
        
        print(f"  HTML report saved to: {html_path}")
    
    def _print_final_summary(self):
        """Print final summary of all experiments"""
        print("\n" + "="*80)
        print("  EXPERIMENTAL EVALUATION COMPLETE")
        print("="*80)
        
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        print(f"\n  Total Duration: {duration:.1f} seconds")
        print(f"  Output Directory: {self.output_dir}")
        
        print("\n  Experiment Status:")
        print(f"  {'-'*50}")
        
        exp_titles = {
            1: "Latency & Throughput",
            2: "Privacy Routing",
            3: "Gas Efficiency",
            4: "Lifecycle Overhead",
            5: "Exactly-Once"
        }
        
        for i in range(1, 6):
            exp_key = f"experiment_{i}"
            if exp_key in self.results:
                status = self.results[exp_key].get("status", "not run")
                icon = "OK" if status == "success" else "FAIL" if status == "error" else "SKIP"
                print(f"  {icon:6} Experiment {i}: {exp_titles[i]}")
        
        print(f"\n  Generated Files:")
        print(f"    - {self.output_dir}/combined_report.json")
        print(f"    - {self.output_dir}/experimental_results.tex")
        print(f"    - {self.output_dir}/report.html")
        print(f"    - {self.output_dir}/exp[1-5]/*.png (plots)")
        print(f"    - {self.output_dir}/exp[1-5]/*.json (detailed results)")
        
        print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description="Run experimental evaluation for Hybrid Blockchain Digital Twin System"
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Run in quick mode with reduced sample sizes"
    )
    parser.add_argument(
        "--exp", "-e",
        type=int,
        nargs="+",
        choices=[1, 2, 3, 4, 5],
        help="Run specific experiments (e.g., --exp 1 3 5)"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="experiments/results",
        help="Output directory for results"
    )
    
    args = parser.parse_args()
    
    runner = ExperimentRunner(
        output_dir=args.output_dir,
        quick_mode=args.quick
    )
    
    experiments = args.exp if args.exp else None
    results = runner.run_all(experiments)
    
    return results


if __name__ == "__main__":
    main()
