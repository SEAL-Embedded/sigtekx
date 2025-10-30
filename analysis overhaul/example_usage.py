#!/usr/bin/env python
"""
Example: Using the Enhanced GPU Analysis Pipeline
=================================================

This script demonstrates the key features of the new analysis system.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from analysis import (
    AnalysisEngine,
    StatisticalMetrics,
    BenchmarkType,
    EngineConfiguration
)
from analysis.visualization import ReportGenerator, PerformancePlotter


def generate_sample_data():
    """Generate synthetic benchmark data for demonstration."""
    
    np.random.seed(42)
    
    data_records = []
    
    # Generate data for different configurations
    for nfft in [512, 1024, 2048, 4096]:
        for channels in [1, 2, 4, 8, 16]:
            # Base performance characteristics
            base_latency = 50 + (nfft / 256) * 10 + (channels - 1) * 5
            base_throughput = 10000 / (1 + np.log2(nfft) * channels * 0.1)
            
            # Generate multiple measurements with noise
            for _ in range(30):  # 30 samples per config
                latency = base_latency * (1 + np.random.normal(0, 0.05))
                throughput = base_throughput * (1 + np.random.normal(0, 0.08))
                
                # Latency measurement
                data_records.append({
                    'benchmark_type': 'latency',
                    'engine_nfft': nfft,
                    'engine_channels': channels,
                    'mean_latency_us': latency,
                    'p95_latency_us': latency * 1.2,
                    'p99_latency_us': latency * 1.35,
                })
                
                # Throughput measurement
                data_records.append({
                    'benchmark_type': 'throughput',
                    'engine_nfft': nfft,
                    'engine_channels': channels,
                    'frames_per_second': throughput,
                    'gb_per_second': throughput * nfft * channels * 8 / 1e9,
                    'gpu_utilization': min(95, 10 + np.log2(nfft) * channels * 2),
                })
                
                # Accuracy measurement
                pass_rate = 0.99 - (nfft / 100000) - (channels / 1000)
                data_records.append({
                    'benchmark_type': 'accuracy',
                    'engine_nfft': nfft,
                    'engine_channels': channels,
                    'pass_rate': pass_rate + np.random.normal(0, 0.001),
                    'mean_snr_db': 60 + np.random.normal(0, 2),
                })
    
    return pd.DataFrame(data_records)


def demonstrate_basic_analysis():
    """Demonstrate basic analysis functionality."""
    
    print("=" * 70)
    print("BASIC ANALYSIS DEMONSTRATION")
    print("=" * 70)
    
    # Generate sample data
    data = generate_sample_data()
    print(f"\nGenerated {len(data)} measurements")
    print(f"Configurations: {data[['engine_nfft', 'engine_channels']].drop_duplicates().shape[0]}")
    
    # Create analysis engine
    engine = AnalysisEngine()
    
    # Generate summary
    summary = engine.generate_summary(data, "Demo GPU Benchmark")
    
    print(f"\nExperiment: {summary.experiment_name}")
    print(f"Total measurements: {summary.total_measurements}")
    print(f"Benchmark types: {[bt.value for bt in summary.benchmark_types]}")
    
    # Display optimal configurations
    print("\nOptimal Configurations:")
    for bench_type, config in summary.optimal_configs.items():
        print(f"  {bench_type}: NFFT={config.nfft}, Channels={config.channels}")
    
    # Display insights
    print("\nKey Insights:")
    for insight in summary.key_insights[:5]:
        print(f"  • {insight}")
    
    return data, summary


def demonstrate_statistical_comparison():
    """Demonstrate statistical comparison between configurations."""
    
    print("\n" + "=" * 70)
    print("STATISTICAL COMPARISON DEMONSTRATION")
    print("=" * 70)
    
    # Generate data
    data = generate_sample_data()
    engine = AnalysisEngine()
    
    # Compare two configurations
    config1 = {'engine_nfft': 1024, 'engine_channels': 4}
    config2 = {'engine_nfft': 2048, 'engine_channels': 8}
    
    print(f"\nComparing configurations:")
    print(f"  Config 1: NFFT={config1['engine_nfft']}, Channels={config1['engine_channels']}")
    print(f"  Config 2: NFFT={config2['engine_nfft']}, Channels={config2['engine_channels']}")
    
    # Run comparison for latency
    latency_data = data[data['benchmark_type'] == 'latency']
    comparison = engine.compare_configurations(
        latency_data,
        config1,
        config2,
        'mean_latency_us'
    )
    
    if comparison:
        print(f"\nStatistical Test: {comparison.test_name}")
        print(f"P-value: {comparison.p_value:.6f}")
        print(f"Significant difference: {'Yes' if comparison.is_significant else 'No'}")
        print(f"Effect size (Cohen's d): {comparison.effect_size:.3f}")
        
        print(f"\nConfig 1 mean: {comparison.baseline.mean:.2f} ± {comparison.baseline.std:.2f} μs")
        print(f"Config 2 mean: {comparison.target.mean:.2f} ± {comparison.target.std:.2f} μs")
        print(f"Difference: {comparison.mean_diff:.2f} μs ({comparison.mean_diff_pct:+.1f}%)")


def demonstrate_scaling_analysis():
    """Demonstrate scaling pattern detection."""
    
    print("\n" + "=" * 70)
    print("SCALING ANALYSIS DEMONSTRATION")
    print("=" * 70)
    
    # Generate data
    data = generate_sample_data()
    engine = AnalysisEngine()
    
    # Analyze scaling patterns
    print("\nAnalyzing scaling patterns...")
    scaling_analyses = engine.analyze_scaling(
        data,
        parameters=['engine_nfft', 'engine_channels'],
        metrics=['mean_latency_us', 'frames_per_second']
    )
    
    for analysis in scaling_analyses[:2]:  # Show first 2 analyses
        print(f"\n{analysis.parameter} scaling for metric:")
        print(f"  Type: {analysis.scaling_type}")
        print(f"  Exponent: {analysis.scaling_exponent:.3f}")
        print(f"  Model: y = {analysis.model_params['coefficient']:.2f} * x^{analysis.model_params['exponent']:.2f}")
        print(f"  R²: {analysis.model_r2:.3f}")
        print(f"  Correlation: {analysis.correlation:.3f}")
        
        if analysis.saturation_point:
            print(f"  Saturation at: {analysis.saturation_point:.0f}")


def demonstrate_custom_analyzer():
    """Demonstrate how to add a custom analyzer."""
    
    print("\n" + "=" * 70)
    print("CUSTOM ANALYZER DEMONSTRATION")
    print("=" * 70)
    
    from analysis.engine import AnalyzerBase
    
    class PowerEfficiencyAnalyzer(AnalyzerBase):
        """Custom analyzer for power efficiency metrics."""
        
        def get_metrics(self):
            return ['power_efficiency', 'perf_per_watt']
        
        def analyze(self, data):
            results = {}
            
            for (nfft, channels), group in data.groupby(['engine_nfft', 'engine_channels']):
                config_key = f"{nfft}_{channels}"
                
                # Simulate power consumption
                power_w = 150 + nfft * 0.01 + channels * 3
                
                # Calculate efficiency
                if 'frames_per_second' in group.columns:
                    fps = group['frames_per_second'].mean()
                    perf_per_watt = fps / power_w
                else:
                    perf_per_watt = 0
                
                results[config_key] = {
                    'power_w': power_w,
                    'perf_per_watt': perf_per_watt,
                    'efficiency_score': min(1.0, perf_per_watt / 10)  # Normalized score
                }
            
            return results
    
    # Use custom analyzer
    data = generate_sample_data()
    analyzer = PowerEfficiencyAnalyzer()
    
    print("\nRunning custom power efficiency analysis...")
    power_results = analyzer.analyze(data)
    
    # Display results
    print("\nPower Efficiency Results (sample):")
    for config_key, metrics in list(power_results.items())[:3]:
        nfft, channels = config_key.split('_')
        print(f"  NFFT={nfft}, Channels={channels}:")
        print(f"    Power: {metrics['power_w']:.1f} W")
        print(f"    Perf/Watt: {metrics['perf_per_watt']:.2f}")
        print(f"    Efficiency Score: {metrics['efficiency_score']:.3f}")


def demonstrate_report_generation():
    """Demonstrate HTML report generation."""
    
    print("\n" + "=" * 70)
    print("REPORT GENERATION DEMONSTRATION")
    print("=" * 70)
    
    # Generate data and analysis
    data = generate_sample_data()
    engine = AnalysisEngine()
    summary = engine.generate_summary(data, "Demo Report")
    
    # Generate report
    report_gen = ReportGenerator()
    output_path = Path("demo_report.html")
    
    print(f"\nGenerating HTML report...")
    report_gen.generate_full_report(summary, output_path)
    
    print(f"Report saved to: {output_path}")
    print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
    
    # Display report structure
    with open(output_path, 'r') as f:
        content = f.read()
        print(f"\nReport sections:")
        if "Key Insights" in content:
            print("  ✓ Key Insights")
        if "Optimal Configurations" in content:
            print("  ✓ Optimal Configurations")
        if "Performance Visualizations" in content:
            print("  ✓ Performance Visualizations")
        if "Statistical Comparisons" in content:
            print("  ✓ Statistical Comparisons")
        if "Scaling Analysis" in content:
            print("  ✓ Scaling Analysis")


def main():
    """Run all demonstrations."""
    
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " ENHANCED GPU PIPELINE ANALYSIS - FEATURE DEMONSTRATION".center(68) + "║")
    print("╚" + "=" * 68 + "╝")
    print("\nThis script demonstrates the key capabilities of the new analysis system.\n")
    
    # Run demonstrations
    demonstrate_basic_analysis()
    demonstrate_statistical_comparison()
    demonstrate_scaling_analysis()
    demonstrate_custom_analyzer()
    demonstrate_report_generation()
    
    print("\n" + "=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print("\nThe new analysis system provides:")
    print("  ✓ Statistical rigor with hypothesis testing")
    print("  ✓ Automatic scaling pattern detection")
    print("  ✓ Modular, extensible analyzer framework")
    print("  ✓ Interactive visualizations")
    print("  ✓ Comprehensive HTML reports")
    print("  ✓ Caching and incremental computation")
    print("\nSee README.md for full documentation and usage examples.")


if __name__ == "__main__":
    main()
