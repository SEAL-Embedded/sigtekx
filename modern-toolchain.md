Plan for Finalizing the Modern Research StackThis plan outlines the necessary steps to refactor the current codebase into a clean, maintainable, and reproducible research workflow. The goal is to finalize the integration of Hydra, Snakemake, DVC, and MLflow, adhering to a purpose-driven project structure.1. Final Project StructureFirst, let's establish the target directory structure. This layout provides a clear separation between the installable library, developer tooling, and the scientific workflow.ionosense-hpc-lib/
|-- .dvc/                   # DVC metadata (auto-generated)
|-- .github/
|-- cpp/
|-- docs/
|-- environments/
|-- artifacts/              # For all generated outputs (data, plots, models)
|   |-- data/               # Processed data, e.g., benchmark_results.parquet
|   |-- figures/            # Generated plots and visualizations
|   `-- reports/            # Final HTML/PDF reports
|
|-- benchmarks/             # Scripts for RUNNING benchmarks
|   |-- run_latency.py
|   `-- run_throughput.py
|
|-- experiments/            # Home for the entire reproducible research pipeline
|   |-- conf/               # All Hydra configurations
|   |-- scripts/            # Python scripts for ANALYSIS and PLOTTING
|   |   |-- analyze_results.py
|   |   `-- generate_figures.py
|   `-- Snakefile           # Snakemake workflow definition
|
|-- notebooks/              # For exploratory data analysis (EDA)
|   `-- 1.0-eda.ipynb
|
|-- scripts/                # For developer TOOLING (CLI, setup scripts)
|   |-- cli.ps1
|   |-- cli.sh
|   `-- open_dev_pwsh.ps1
|
|-- src/                    # The installable Python package
|   `-- ionosense_hpc/
|       |-- core/
|       |-- config/
|       |-- utils/
|       `-- exceptions.py
|
|-- tests/                  # Python tests
|
|-- dvc.yaml                # DVC pipeline definition
|-- pyproject.toml
`-- README.md
2. File-by-File Refactoring and Creation PlanThis section details the specific actions for each file.A. Configuration (Hydra)Action: Move all generated Hydra configuration files (hydra-*.txt) into the new experiments/conf/ directory.Rationale: Centralizes all configuration in one place, as recommended by Hydra. The subdirectories (engine/, benchmark/, etc.) are a core part of Hydra's design, known as "Config Groups." This structure allows you to easily compose complex configurations and swap out components from the command line (e.g., engine=throughput). It's designed for scalability; as you add more engine types or benchmark variations, they simply become new files in the appropriate folder, keeping your configurations organized and manageable.Files to Move:hydra-engine-configs.txt -> experiments/conf/engine/*.yamlhydra-benchmark-configs.txt -> experiments/conf/benchmark/*.yamlhydra-experiment-configs.txt -> experiments/conf/experiment/*.yamlhydra-main-config.txt -> experiments/conf/config.yamlB. Benchmark ScriptsAction: Create new, simple Python scripts in the benchmarks/ directory for each benchmark type (e.g., run_latency.py). These scripts will replace the monolithic hydra-runner.py.Rationale: Decouples the act of running a benchmark from the orchestration logic. Each script does one thing well.benchmarks/run_latency.py (New File Example):import hydra
from omegaconf import DictConfig
import mlflow
from ionosense_hpc.config import LatencyBenchmarkConfig # Your Pydantic model
from ionosense_hpc.benchmarks import LatencyBenchmark

@hydra.main(config_path="../experiments/conf", config_name="config")
def run_latency_benchmark(cfg: DictConfig) -> None:
    """Runs the latency benchmark with MLflow tracking."""
    config = LatencyBenchmarkConfig(**cfg.benchmark)
    engine_config = EngineConfig(**cfg.engine)

    with mlflow.start_run(run_name="latency"):
        mlflow.log_params(cfg.benchmark)
        mlflow.log_params(cfg.engine)

        benchmark = LatencyBenchmark(config, engine_config)
        result = benchmark.run()

        mlflow.log_metrics(result.statistics)
        # The script should save its output to a file in the `artifacts/` directory
        # e.g., result.save_to_parquet("artifacts/data/latency_results.parquet")

if __name__ == "__main__":
    run_latency_benchmark()
C. Orchestration (Snakemake)Action: Refactor the snakefile.py to be a clean Snakefile in the experiments/ directory. It should call the simple benchmark and analysis scripts.Rationale: Snakemake's job is to manage the workflow and dependencies, not to manage configuration sweeps (that's Hydra's job). This simplifies the workflow considerably.experiments/Snakefile (Refactored):# experiments/Snakefile
configfile: "conf/config.yaml"

rule all:
    input:
        "../artifacts/figures/latency_vs_nfft.png",
        "../artifacts/reports/final_report.html"

rule run_latency_sweep:
    output:
        touch("../artifacts/data/latency_sweep.done") # A flag file to mark completion
    shell:
        # Hydra handles the multi-run sweep; Snakemake just triggers it
        "python ../benchmarks/run_latency.py --multirun experiment=nfft_batch_sweep"

rule analyze_results:
    input:
        "../artifacts/data/latency_sweep.done"
    output:
        "../artifacts/data/summary_statistics.csv"
    script:
        "scripts/analyze_results.py" # Note: relative path within the experiments dir

rule generate_figures:
    input:
        "../artifacts/data/summary_statistics.csv"
    output:
        "../artifacts/figures/latency_vs_nfft.png"
    script:
        "scripts/generate_figures.py"
D. Data Versioning (DVC)Action: Simplify the dvc-pipeline.txt into a top-level dvc.yaml file. DVC's primary role will be to version the artifacts/ directory.Rationale: This makes DVC a pure data versioning tool. Snakemake is the better tool for complex workflow orchestration.dvc.yaml (Refactored):stages:
  run_and_analyze:
    cmd: snakemake --cores 1 --directory experiments
    deps:
      - benchmarks/
      - experiments/
      - src/
    outs:
      - artifacts/data/
      - artifacts/figures/
E. Analysis and PlottingAction: Place the analysis-script.py and figure-generation-script.py into the new experiments/scripts/ directory.Rationale: These are part of the scientific workflow and should be co-located with the Snakefile that runs them.Files to Move:analysis-script.py -> experiments/scripts/analyze_results.pyfigure-generation-script.py -> experiments/scripts/generate_figures.py3. Core Concepts ChecklistTo ensure the refactoring is successful, follow these core principles: One Tool, One Job:Hydra: Manages configuration and parameter sweeps.Snakemake: Orchestrates the workflow (running scripts in the right order).DVC: Versions data and tracks dependencies between code and data.MLflow: Logs experiment parameters, metrics, and artifacts. Code vs. Workflow: The src/ directory is the installable library. All other directories (benchmarks/, experiments/, notebooks/) contain the research workflow that uses the library. Data as Artifacts: Scripts should communicate through files (e.g., Parquet, CSV, PNG), not by calling each other directly. A benchmark script produces a .parquet file in artifacts/data/; an analysis script consumes it.