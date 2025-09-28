#!/usr/bin/env python
"""
Complete Ionosphere Study Runner
================================

This script provides a simple interface to run complete ionosphere experiments
from configuration to final charts and reports.

Usage:
    python run_complete_study.py --preset ionosphere_resolution
    python run_complete_study.py --preset ionosphere_temporal
    python run_complete_study.py --preset custom --config my_config.yaml
    python run_complete_study.py --preset quick_test

The script will:
1. Validate your configuration and environment
2. Run the specified experiment(s)
3. Analyze the results
4. Generate charts and figures
5. Create a final HTML report
6. Show you where to find everything

No need to understand the complex config system - just pick a preset!
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import yaml


def print_banner():
    """Print a nice welcome banner."""
    print("=" * 70)
    print("** Ionosphere HPC Complete Study Runner **")
    print("   From Config -> Experiments -> Analysis -> Charts -> Report")
    print("=" * 70)
    print()


def validate_environment() -> bool:
    """Check if the environment is properly set up."""
    print(">> Validating environment...")

    issues = []

    # Check Python packages
    required_packages = {
        'hydra': 'hydra-core',
        'mlflow': 'mlflow',
        'snakemake': 'snakemake',
        'pandas': 'pandas',
        'matplotlib': 'matplotlib'
    }
    for import_name, package_name in required_packages.items():
        try:
            __import__(import_name)
        except ImportError:
            issues.append(f"Missing Python package: {package_name} (install with: pip install {package_name})")

    # Check benchmark scripts
    benchmark_scripts = [
        'benchmarks/run_throughput.py',
        'benchmarks/run_latency.py',
        'benchmarks/run_accuracy.py'
    ]
    for script in benchmark_scripts:
        if not Path(script).exists():
            issues.append(f"Missing benchmark script: {script}")

    # Check config directory
    if not Path('experiments/conf').exists():
        issues.append("Missing experiments/conf directory")

    if issues:
        print("XX Environment issues found:")
        for issue in issues:
            print(f"   * {issue}")
        print("\nPlease fix these issues before running experiments.")
        return False

    print(">> Environment looks good!")
    return True


def get_preset_configs() -> Dict[str, Dict]:
    """Define preset experiment configurations."""
    return {
        'ionosphere_resolution': {
            'name': 'Ionosphere Resolution Study',
            'description': 'High-resolution frequency analysis for ionosphere monitoring',
            'experiment': 'ionosphere_resolution',
            'benchmarks': ['throughput'],
            'expected_runtime': '20-30 minutes',
            'output_focus': 'Frequency resolution vs computational cost trade-offs'
        },
        'ionosphere_temporal': {
            'name': 'Ionosphere Temporal Analysis',
            'description': 'Temporal characteristics and overlap optimization',
            'experiment': 'ionosphere_temporal',
            'benchmarks': ['throughput', 'latency'],
            'expected_runtime': '30-45 minutes',
            'output_focus': 'Temporal resolution and scintillation detection'
        },
        'ionosphere_multiscale': {
            'name': 'Comprehensive Multi-scale Study',
            'description': 'Complete analysis across different scales and engines',
            'experiment': 'ionosphere_multiscale',
            'benchmarks': ['throughput', 'latency', 'accuracy'],
            'expected_runtime': '60+ minutes',
            'output_focus': 'Comprehensive performance characterization'
        },
        'quick_test': {
            'name': 'Quick Test Run',
            'description': 'Fast test with minimal parameters for validation',
            'experiment': 'ionosphere_test',
            'benchmarks': ['throughput'],
            'expected_runtime': '5-10 minutes',
            'output_focus': 'System validation and basic functionality',
            'skip_analysis': True  # Skip complex analysis for quick testing
        },
        'baseline': {
            'name': 'Baseline Performance Study',
            'description': 'Standard parameter sweep for performance baseline',
            'experiment': 'baseline',
            'benchmarks': ['latency', 'throughput', 'accuracy'],
            'expected_runtime': '15-25 minutes',
            'output_focus': 'Baseline performance metrics across parameter ranges'
        }
    }


def show_available_presets():
    """Display all available preset configurations."""
    presets = get_preset_configs()

    print("** Available Experiment Presets:")
    print()

    for preset_name, config in presets.items():
        print(f"* {preset_name}")
        print(f"   {config['name']}")
        print(f"   {config['description']}")
        print(f"   Benchmarks: {', '.join(config['benchmarks'])}")
        print(f"   Runtime: {config['expected_runtime']}")
        print(f"   Focus: {config['output_focus']}")
        print()


def run_experiment(preset_name: str, config: Dict) -> bool:
    """Run the specified experiment configuration."""
    print(f">> Running experiment: {config['name']}")
    print(f"   Description: {config['description']}")
    print(f"   Expected runtime: {config['expected_runtime']}")
    print()

    success = True

    # Create output directories
    output_dirs = ['artifacts/data', 'artifacts/figures', 'artifacts/reports']
    for dir_path in output_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    # Run each benchmark
    for benchmark in config['benchmarks']:
        print(f">> Running {benchmark} benchmark...")

        cmd = [
            'python', f'benchmarks/run_{benchmark}.py',
            '--multirun',
            f'experiment={config["experiment"]}',
            f'+benchmark={benchmark}'
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                print(f"XX {benchmark} benchmark failed:")
                print(result.stderr)
                success = False
            else:
                print(f">> {benchmark} benchmark completed successfully")
        except subprocess.TimeoutExpired:
            print(f"!! {benchmark} benchmark timed out (>1 hour)")
            success = False
        except Exception as e:
            print(f"XX Error running {benchmark} benchmark: {e}")
            success = False

    return success


def run_analysis_pipeline() -> bool:
    """Run the analysis and visualization pipeline."""
    print(">> Running analysis and generating visualizations...")

    try:
        # Run Snakemake pipeline for analysis and figures
        cmd = ['snakemake', '--cores', '4', '--snakefile', 'experiments/Snakefile']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

        if result.returncode != 0:
            print("XX Analysis pipeline failed:")
            print(result.stderr)
            return False

        print(">> Analysis and visualization completed successfully")
        return True

    except subprocess.TimeoutExpired:
        print("!! Analysis pipeline timed out")
        return False
    except Exception as e:
        print(f"XX Error running analysis pipeline: {e}")
        return False


def show_results():
    """Show the user where to find their results."""
    print()
    print(">> Study Complete!")
    print("=" * 50)
    print()

    # Check what outputs were generated
    outputs = {
        'MLflow Experiments': 'artifacts/mlruns',
        'Raw Data': 'artifacts/data',
        'Charts & Figures': 'artifacts/figures',
        'Final Report': 'artifacts/reports/final_report.html',
        'Summary Statistics': 'artifacts/data/summary_statistics.csv'
    }

    print("** Your results are available in:")
    for name, path in outputs.items():
        if Path(path).exists():
            print(f"   >> {name}: {path}")
        else:
            print(f"   -- {name}: {path} (not generated)")

    print()
    print("** To view your results:")
    print("   * Open artifacts/reports/final_report.html in your browser")
    print("   * Run 'mlflow ui --backend-store-uri file://./artifacts/mlruns' for interactive exploration")
    print("   * Check artifacts/figures/ for individual charts")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Run complete ionosphere experiments from config to charts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--preset',
        type=str,
        help='Preset experiment configuration to run'
    )

    parser.add_argument(
        '--list-presets',
        action='store_true',
        help='Show available preset configurations'
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Custom config file (requires --preset custom)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be run without executing'
    )

    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip environment validation'
    )

    args = parser.parse_args()

    print_banner()

    if args.list_presets:
        show_available_presets()
        return

    if not args.preset:
        print("❌ No preset specified. Use --preset or --list-presets to see options.")
        parser.print_help()
        return

    # Validate environment
    if not args.skip_validation and not validate_environment():
        return

    # Get preset configuration
    presets = get_preset_configs()
    if args.preset not in presets:
        print(f"❌ Unknown preset: {args.preset}")
        print("Available presets:")
        for name in presets.keys():
            print(f"   • {name}")
        return

    config = presets[args.preset]

    if args.dry_run:
        print(">> Dry run - would execute:")
        print(f"   Experiment: {config['experiment']}")
        print(f"   Benchmarks: {', '.join(config['benchmarks'])}")
        print(f"   Expected runtime: {config['expected_runtime']}")
        return

    # Run the complete study
    start_time = time.time()

    # Step 1: Run experiments
    if not run_experiment(args.preset, config):
        print("XX Experiment execution failed")
        return

    # Step 2: Run analysis pipeline (unless skipped for quick testing)
    if not config.get('skip_analysis', False):
        if not run_analysis_pipeline():
            print("XX Analysis pipeline failed")
            return
    else:
        print(">> Skipping analysis pipeline for quick test")

    # Step 3: Show results
    elapsed = time.time() - start_time
    print(f">> Total runtime: {elapsed/60:.1f} minutes")
    show_results()


if __name__ == '__main__':
    main()