# Snakefile
# Simple workflow orchestration following one-tool-one-job principle

configfile: "conf/config.yaml"

# Define the final outputs we want
rule all:
    input:
        "artifacts/figures/latency_vs_nfft.png",
        "artifacts/figures/throughput_scaling.png",
        "artifacts/figures/accuracy_heatmap.png",
        "artifacts/figures/combined_analysis.png",
        "artifacts/reports/final_report.html"

# Run latency benchmark sweep
rule run_latency_sweep:
    output:
        touch("artifacts/data/latency_sweep.done")
    shell:
        """
        python benchmarks/run_latency.py --multirun \
            experiment=nfft_batch_sweep \
            benchmark=latency
        """

# Run throughput benchmark sweep
rule run_throughput_sweep:
    output:
        touch("artifacts/data/throughput_sweep.done")
    shell:
        """
        python benchmarks/run_throughput.py --multirun \
            experiment=nfft_batch_sweep \
            benchmark=throughput
        """

# Run accuracy benchmark sweep
rule run_accuracy_sweep:
    output:
        touch("artifacts/data/accuracy_sweep.done")
    shell:
        """
        python benchmarks/run_accuracy.py --multirun \
            experiment=nfft_batch_sweep \
            benchmark=accuracy
        """

# Analyze all results and create summary statistics
rule analyze_results:
    input:
        "artifacts/data/latency_sweep.done",
        "artifacts/data/throughput_sweep.done",
        "artifacts/data/accuracy_sweep.done"
    output:
        "artifacts/data/summary_statistics.csv"
    shell:
        "python scripts/analyze.py"

# Generate figures from summary statistics
rule generate_figures:
    input:
        "artifacts/data/summary_statistics.csv"
    output:
        "artifacts/figures/latency_vs_nfft.png",
        "artifacts/figures/throughput_scaling.png",
        "artifacts/figures/accuracy_heatmap.png",
        "artifacts/figures/combined_analysis.png"
    shell:
        "python scripts/generate_figures.py"

# Generate final HTML report
rule generate_report:
    input:
        "artifacts/data/summary_statistics.csv",
        "artifacts/figures/combined_analysis.png"
    output:
        "artifacts/reports/final_report.html"
    shell:
        """
        python scripts/generate_report.py \
            --input artifacts/data/summary_statistics.csv \
            --figures-dir artifacts/figures \
            --output artifacts/reports/final_report.html
        """

# Clean all artifacts
rule clean:
    shell:
        """
        rm -rf artifacts/data/*
        rm -rf artifacts/figures/*
        rm -rf artifacts/reports/*
        rm -rf outputs/
        rm -rf multirun/
        echo "Cleaned all artifacts"
        """

# Quick test run with minimal parameters
rule test:
    shell:
        """
        python benchmarks/run_latency.py engine.nfft=512 engine.batch=1 benchmark.iterations=10
        python scripts/analyze.py
        python scripts/generate_figures.py
        """