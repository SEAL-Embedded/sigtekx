# scripts/

Development, build, and deployment scripts for SigTekX.

```
scripts/
├── cli.ps1 / cli.sh            # Main CLI (build, test, format, lint, profile, baseline)
├── cli-cpp.ps1 / cli-cpp.sh    # C++ benchmark CLI (sigxc)
├── init_pwsh.ps1 / init_bash.sh  # Shell initialization (aliases, env vars)
├── create-dev-shortcut.ps1     # Windows dev environment shortcut
│
├── gpu/                        # GPU clock management
│   ├── gpu-manager.ps1 / .sh   # Lock/unlock GPU clocks for stable benchmarking
│   ├── gpu-manager-elevated.ps1  # UAC elevation wrapper (Windows)
│   └── gpu-clocks.json         # Per-GPU clock speed database
│
├── helpers/                    # Benchmark helper scripts
│   ├── prof_helper.py          # Nsight profiling orchestration (sxp)
│   ├── baseline_helper.py      # Baseline save/compare/list operations
│   └── stage_timing_helper.py  # Per-stage timing experiments (sxst/sxstb/sxsts)
│
└── aws/                        # AWS cloud deployment
    ├── setup_iam.sh            # Create IAM role + S3 bucket
    ├── run_sagemaker_job.py    # Launch SageMaker Processing Job
    ├── sagemaker_entry.py      # Container entry point for cloud runs
    ├── download_results.sh     # Sync S3 results to local artifacts/
    └── anomaly_detection.py    # RCF anomaly detection demo
```
