#!/usr/bin/env python3
"""Run all evaluations and comparisons for test datasets."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

def run_command(cmd, description):
    """Run a command and show progress."""
    print(f"\n{'='*80}")
    print(f"🔄 {description}")
    print(f"{'='*80}\n")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        return False
    # Show last 20 lines of output
    lines = result.stdout.split('\n')
    print('\n'.join(lines[-20:]))
    return True

def main():
    datasets = ['test_1', 'test_2', 'test_3', 'test_4']
    
    # Step 1: Run binary (0-1) evaluations
    print("\n" + "="*80)
    print("STEP 1: Running Binary (0-1) Evaluations")
    print("="*80)
    for dataset in datasets:
        if not run_command(
            f"cd {ROOT} && python3 -m time_calibration_agent.cli quality-eval --dataset eval/datasets/{dataset}_dataset.json --scoring-mode binary --debug --output eval/results/quality_eval_debug_0-1_{dataset}.json",
            f"Binary evaluation for {dataset}"
        ):
            print(f"Failed on {dataset}")
            return

    # Step 2: Run five-point (1-5) evaluations
    print("\n" + "="*80)
    print("STEP 2: Running Five-Point (1-5) Evaluations")
    print("="*80)
    for dataset in datasets:
        if not run_command(
            f"cd {ROOT} && python3 -m time_calibration_agent.cli quality-eval --dataset eval/datasets/{dataset}_dataset.json --scoring-mode five_point --debug --output eval/results/quality_eval_debug_1-5_{dataset}.json",
            f"Five-point evaluation for {dataset}"
        ):
            print(f"Failed on {dataset}")
            return

    # Step 3: Run comparisons
    print("\n" + "="*80)
    print("STEP 3: Running Comparisons")
    print("="*80)
    for dataset in datasets:
        if not run_command(
            f"cd {ROOT} && python3 -m time_calibration_agent.cli compare-scoring --old eval/results/quality_eval_debug_1-5_{dataset}.json --new eval/results/quality_eval_debug_0-1_{dataset}.json --output eval/results/scoring_comparison_{dataset}.json",
            f"Comparison for {dataset}"
        ):
            print(f"Failed comparison on {dataset}")
            return

    print("\n" + "="*80)
    print("✅ All evaluations and comparisons complete!")
    print("="*80)
    print("\nGenerated files:")
    for dataset in datasets:
        print(f"  - eval/results/quality_eval_debug_0-1_{dataset}.json")
        print(f"  - eval/results/quality_eval_debug_1-5_{dataset}.json")
        print(f"  - eval/results/scoring_comparison_{dataset}.json")
        print(f"  - eval/results/scoring_disagreements_analysis.json (latest)")

if __name__ == "__main__":
    main()

