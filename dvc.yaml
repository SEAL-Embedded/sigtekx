# DVC Pipeline - Simple configuration that uses Snakemake
# Following one-tool-one-job principle: DVC tracks data, Snakemake orchestrates

stages:
  run_workflow:
    cmd: snakemake --cores 4
    deps:
      - benchmarks/
      - scripts/
      - src/ionosense_hpc/
      - conf/
      - Snakefile
    outs:
      - artifacts/data/:
          persist: true
      - artifacts/figures/:
          persist: true
      - artifacts/reports/:
          persist: true
    metrics:
      - artifacts/data/summary_statistics.csv:
          cache: false

  # Alternative: Run specific benchmarks
  benchmark_latency:
    cmd: python benchmarks/run_latency.py
    deps:
      - benchmarks/run_latency.py
      - src/ionosense_hpc/benchmarks/
      - conf/engine/
      - conf/benchmark/latency.yaml
    params:
      - conf/config.yaml:
          - seed
    outs:
      - artifacts/data/latency_summary_*.csv:
          persist: true

  benchmark_throughput:
    cmd: python benchmarks/run_throughput.py
    deps:
      - benchmarks/run_throughput.py
      - src/ionosense_hpc/benchmarks/
      - conf/engine/
      - conf/benchmark/throughput.yaml
    params:
      - conf/config.yaml:
          - seed
    outs:
      - artifacts/data/throughput_summary_*.csv:
          persist: true

  analyze:
    cmd: python scripts/analyze.py
    deps:
      - scripts/analyze.py
      - artifacts/data/
    outs:
      - artifacts/data/summary_statistics.csv:
          cache: false
      - artifacts/data/detailed_analysis.json:
          cache: false

  visualize:
    cmd: python scripts/generate_figures.py
    deps:
      - scripts/generate_figures.py
      - artifacts/data/summary_statistics.csv
    outs:
      - artifacts/figures/:
          persist: true