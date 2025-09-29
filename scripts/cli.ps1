#!/usr/bin/env pwsh
# ============================================================================
# ionosense-hpc • Simplified Development CLI
# Essential development tasks only - research tools use native CLIs directly
# ============================================================================

#Requires -Version 7.0

param(
    [Parameter(Position=0)]
    [string]$Command = "help",

    [Parameter(ValueFromRemainingArguments)]
    [string[]]$CommandArgs = @()
)

# --- Configuration & Paths ---------------------------------------------------
$script:ProjectRoot = (Get-Item -Path (Join-Path $PSScriptRoot "..")).FullName
$script:BuildDir = Join-Path $ProjectRoot "build"
$script:BuildPreset = if ($env:BUILD_PRESET) { $env:BUILD_PRESET } else { "windows-rel" }
$script:CondaEnvName = "ionosense-hpc"

# --- Utility Functions -------------------------------------------------------
function Write-Status {
    param([string]$Message, [string]$Color = "Cyan")
    Write-Host "🔧 $Message" -ForegroundColor $Color
}

function Write-Error {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

# --- Core Functions -----------------------------------------------------------
function Invoke-Setup {
    param([bool]$Clean = $false)

    Write-Status "Setting up development environment..."

    if ($Clean) {
        Write-Status "Cleaning existing environment..."
        & conda env remove -n $script:CondaEnvName --yes 2>$null
    }

    $envFile = Join-Path $script:ProjectRoot "environments/environment.win.yml"
    if (-not (Test-Path $envFile)) {
        Write-Error "Environment file not found: $envFile"
        exit 1
    }

    Write-Status "Creating/updating conda environment..."
    # Use update to handle existing environments gracefully
    & conda env update -f $envFile --prune

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create conda environment"
        exit 1
    }

    Write-Status "Installing package in development mode..."
    & pip install -e .[dev]

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Setup completed successfully"
    } else {
        Write-Error "Package installation failed"
        exit 1
    }
}

function Invoke-Build {
    param(
        [string]$Preset = $script:BuildPreset,
        [bool]$Clean = $false,
        [bool]$Verbose = $false
    )

    Write-Status "Building project with preset: $Preset"

    if ($Clean) {
        Write-Status "Cleaning build directory..."
        if (Test-Path $script:BuildDir) {
            Remove-Item $script:BuildDir -Recurse -Force
        }
    }

    $args = @("--preset", $Preset)
    if ($Verbose) { $args += "--verbose" }

    Write-Status "Configuring with CMake..."
    & cmake @args .

    if ($LASTEXITCODE -ne 0) {
        Write-Error "CMake configuration failed"
        exit 1
    }

    # Build directory includes the preset name when using --preset
    $actualBuildDir = if ($args -contains "--preset") {
        Join-Path $script:BuildDir $Preset
    } else {
        $script:BuildDir
    }

    Write-Status "Building..."
    & cmake --build $actualBuildDir --config Release

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Build completed successfully"
    } else {
        Write-Error "Build failed"
        exit 1
    }
}

function Invoke-Test {
    param(
        [string]$Suite = "all",
        [string]$Pattern = "",
        [bool]$Coverage = $false,
        [bool]$Verbose = $false
    )

    Write-Status "Running tests..."

    $args = @()
    if ($Coverage) { $args += "--cov=ionosense_hpc" }
    if ($Verbose) { $args += "-v" }
    if ($Pattern) { $args += "-k", $Pattern }

    switch ($Suite.ToLower()) {
        { $_ -in @("python", "py", "p") } {
            Write-Status "Running Python tests..."
            & python -m pytest tests/ @args
        }
        { $_ -in @("cpp", "c++", "cxx") } {
            Write-Status "Running C++ tests..."
            # Check preset-specific build directory first, then fallback to generic
            $presetBuildDir = Join-Path $script:BuildDir $script:BuildPreset
            $testExe = if (Test-Path $presetBuildDir) {
                Join-Path $presetBuildDir "test_engine.exe"
            } else {
                Join-Path $script:BuildDir "Release/tests/test_runner.exe"
            }

            if (Test-Path $testExe) {
                & $testExe
            } else {
                Write-Error "C++ test executable not found. Run build first."
                exit 1
            }
        }
        "all" {
            Write-Status "Running all tests..."
            & python -m pytest tests/ @args

            # Check preset-specific build directory first, then fallback to generic
            $presetBuildDir = Join-Path $script:BuildDir $script:BuildPreset
            $testExe = if (Test-Path $presetBuildDir) {
                Join-Path $presetBuildDir "test_engine.exe"
            } else {
                Join-Path $script:BuildDir "Release/tests/test_runner.exe"
            }

            if (Test-Path $testExe) {
                & $testExe
            } else {
                Write-Status "C++ tests skipped (executable not found)"
            }
        }
        default {
            Write-Error "Unknown test suite: $Suite. Use: all, python, cpp"
            exit 1
        }
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Tests completed successfully"
    } else {
        Write-Error "Tests failed"
        exit 1
    }
}

function Invoke-Format {
    param(
        [string[]]$Paths = @(),
        [bool]$Check = $false,
        [bool]$Verbose = $false
    )

    Write-Status "Formatting C++ code..."

    if ($Paths.Count -eq 0) {
        $Paths = @("src", "tests", "benchmarks")
    }

    $args = @()
    if ($Check) { $args += "--dry-run", "--Werror" }
    if ($Verbose) { $args += "--verbose" }

    foreach ($path in $Paths) {
        if (Test-Path $path) {
            & clang-format -i @args --style=file (Get-ChildItem $path -Recurse -Include "*.cpp", "*.hpp", "*.h")
        }
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Formatting completed"
    } else {
        Write-Error "Formatting failed"
        exit 1
    }
}

function Invoke-Lint {
    param(
        [string]$Target = "all",
        [bool]$Fix = $false,
        [bool]$Verbose = $false
    )

    Write-Status "Running linting..."

    $args = @()
    if ($Fix) { $args += "--fix" }
    if ($Verbose) { $args += "--verbose" }

    switch ($Target.ToLower()) {
        { $_ -in @("python", "py") } {
            & python -m ruff check . @args
        }
        { $_ -in @("cpp", "c++") } {
            Write-Status "C++ linting not implemented"
        }
        "all" {
            & python -m ruff check . @args
        }
        default {
            Write-Error "Unknown lint target: $Target. Use: all, python, cpp"
            exit 1
        }
    }

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Linting completed"
    } else {
        Write-Error "Linting failed"
        exit 1
    }
}

function Invoke-Clean {
    param([bool]$All = $false)

    Write-Status "Cleaning build artifacts..."

    if (Test-Path $script:BuildDir) {
        Remove-Item $script:BuildDir -Recurse -Force
        Write-Status "Removed build directory"
    }

    if ($All) {
        Write-Status "Cleaning all artifacts..."
        $artifactsDir = Join-Path $script:ProjectRoot "artifacts"
        if (Test-Path $artifactsDir) {
            Remove-Item $artifactsDir -Recurse -Force
            Write-Status "Removed artifacts directory"
        }
    }

    Write-Success "Cleanup completed"
}

function Invoke-Doctor {
    Write-Status "Checking development environment..."

    # Check conda
    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if ($conda) {
        Write-Host "  ✅ Conda: Available" -ForegroundColor Green

        $envExists = & conda env list | Select-String $script:CondaEnvName
        if ($envExists) {
            Write-Host "  ✅ Environment '$script:CondaEnvName': Exists" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Environment '$script:CondaEnvName': Not found" -ForegroundColor Red
        }
    } else {
        Write-Host "  ❌ Conda: Not found" -ForegroundColor Red
    }

    # Check CMake
    $cmake = Get-Command cmake -ErrorAction SilentlyContinue
    if ($cmake) {
        Write-Host "  ✅ CMake: Available" -ForegroundColor Green
    } else {
        Write-Host "  ❌ CMake: Not found" -ForegroundColor Red
    }

    # Check Python tools
    $tools = @("python", "ruff", "pytest")
    foreach ($tool in $tools) {
        $cmd = Get-Command $tool -ErrorAction SilentlyContinue
        if ($cmd) {
            Write-Host "  ✅ ${tool}: Available" -ForegroundColor Green
        } else {
            Write-Host "  ❌ ${tool}: Not found" -ForegroundColor Red
        }
    }

    # Check build
    if (Test-Path $script:BuildDir) {
        Write-Host "  ✅ Build directory: Exists" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Build directory: Not found (run build)" -ForegroundColor Yellow
    }
}

function Invoke-Analysis {
    param(
        [int]$Cores = 4,
        [string]$Target = "all",
        [bool]$DryRun = $false
    )

    Write-Status "Running analysis pipeline..."

    $snakefileePath = Join-Path $script:ProjectRoot "experiments/Snakefile"
    if (-not (Test-Path $snakefileePath)) {
        Write-Error "Snakefile not found at: $snakefileePath"
        exit 1
    }

    $args = @("--cores", $Cores, "--snakefile", $snakefileePath)
    if ($DryRun) { $args += "--dry-run" }
    if ($Target -ne "all") { $args += $Target }

    & snakemake @args

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Analysis pipeline completed successfully"
    } else {
        Write-Error "Analysis pipeline failed"
        exit 1
    }
}

function Invoke-TypeCheck {
    param(
        [string[]]$Paths = @(),
        [bool]$Verbose = $false
    )

    Write-Status "Running type checking..."

    $mypy = Get-Command mypy -ErrorAction SilentlyContinue
    if (-not $mypy) {
        Write-Error "mypy not found. Install with: pip install mypy"
        exit 1
    }

    if ($Paths.Count -eq 0) {
        $Paths = @("src", "tests", "benchmarks", "experiments/scripts")
    }

    $args = @()
    if ($Verbose) { $args += "--verbose" }

    foreach ($path in $Paths) {
        if (Test-Path $path) {
            $args += $path
        }
    }

    & mypy @args

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Type checking completed successfully"
    } else {
        Write-Error "Type checking failed"
        exit 1
    }
}

function Show-Info {
    Write-Host @"
╔════════════════════════════════════════════════════════════════════════╗
║  IONOSENSE-HPC PROJECT INFORMATION                                     ║
╚════════════════════════════════════════════════════════════════════════╝
"@

    # Project info
    $pyprojectPath = Join-Path $script:ProjectRoot "pyproject.toml"
    if (Test-Path $pyprojectPath) {
        $content = Get-Content $pyprojectPath -Raw
        if ($content -match 'version\s*=\s*"([^"]+)"') {
            Write-Host ">> Project: ionosense-hpc v$($Matches[1])" -ForegroundColor Green
        }
    }

    # Environment info
    if ($env:CONDA_DEFAULT_ENV) {
        Write-Host ">> Environment: $($env:CONDA_DEFAULT_ENV)" -ForegroundColor Green
    } else {
        Write-Host ">> Environment: None (consider running setup)" -ForegroundColor Yellow
    }

    # Git info
    try {
        $branch = & git branch --show-current 2>$null
        if ($branch) {
            Write-Host ">> Branch: $branch" -ForegroundColor Green
        }
    } catch {}

    # MLflow info
    $mlrunsPath = Join-Path $script:ProjectRoot "artifacts/mlruns"
    if (Test-Path $mlrunsPath) {
        Write-Host ">> MLflow: Tracking data available" -ForegroundColor Green
        Write-Host "   Start UI: iono ui" -ForegroundColor Gray
    } else {
        Write-Host ">> MLflow: No tracking data yet" -ForegroundColor Yellow
    }

    # Available experiments
    $expDir = Join-Path $script:ProjectRoot "experiments/conf/experiment"
    if (Test-Path $expDir) {
        $experiments = Get-ChildItem $expDir -Name "*.yaml" | ForEach-Object { $_.Replace(".yaml", "") }
        Write-Host ">> Available experiments: $($experiments -join ', ')" -ForegroundColor Cyan
    }

    Write-Host ""
    Write-Host ">> Quick commands:" -ForegroundColor Cyan
    Write-Host "   iono status    # Show comprehensive status" -ForegroundColor Gray
    Write-Host "   iono analysis  # Run analysis pipeline" -ForegroundColor Gray
    Write-Host "   iono learn     # Research workflow examples" -ForegroundColor Gray
}

function Show-Status {
    Write-Host @"
╔════════════════════════════════════════════════════════════════════════╗
║  IONOSENSE-HPC PROJECT STATUS                                          ║
╚════════════════════════════════════════════════════════════════════════╝
"@

    # Git status
    Write-Host ">> Git Status:" -ForegroundColor Cyan
    try {
        $gitStatus = & git status --porcelain 2>$null
        if ($gitStatus) {
            Write-Host "   Modified files detected" -ForegroundColor Yellow
        } else {
            Write-Host "   Working tree clean" -ForegroundColor Green
        }

        $branch = & git branch --show-current 2>$null
        if ($branch) {
            Write-Host "   Branch: $branch" -ForegroundColor Green
        }
    } catch {
        Write-Host "   Git not available or not a repository" -ForegroundColor Red
    }

    # DVC status
    Write-Host ""
    Write-Host ">> DVC Status:" -ForegroundColor Cyan
    try {
        $dvcStatus = & dvc status 2>$null
        if ($LASTEXITCODE -eq 0) {
            if ($dvcStatus) {
                Write-Host "   Changes detected in pipeline" -ForegroundColor Yellow
            } else {
                Write-Host "   Pipeline up to date" -ForegroundColor Green
            }
        } else {
            Write-Host "   DVC not initialized or unavailable" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "   DVC not available" -ForegroundColor Red
    }

    # Environment status
    Write-Host ""
    Write-Host ">> Environment Status:" -ForegroundColor Cyan
    if ($env:CONDA_DEFAULT_ENV) {
        Write-Host "   Active: $($env:CONDA_DEFAULT_ENV)" -ForegroundColor Green
    } else {
        Write-Host "   No conda environment active" -ForegroundColor Yellow
    }

    # Build status
    Write-Host ""
    Write-Host ">> Build Status:" -ForegroundColor Cyan
    if (Test-Path $script:BuildDir) {
        Write-Host "   Build directory exists" -ForegroundColor Green
    } else {
        Write-Host "   No build found (run 'iono build')" -ForegroundColor Yellow
    }

    # MLflow experiments
    Write-Host ""
    Write-Host ">> MLflow Status:" -ForegroundColor Cyan
    $mlrunsPath = Join-Path $script:ProjectRoot "artifacts/mlruns"
    if (Test-Path $mlrunsPath) {
        try {
            $experiments = Get-ChildItem $mlrunsPath -Directory | Where-Object { $_.Name -ne "0" } | Measure-Object
            Write-Host "   $($experiments.Count) experiment(s) tracked" -ForegroundColor Green
        } catch {
            Write-Host "   Tracking data available" -ForegroundColor Green
        }
    } else {
        Write-Host "   No experiments tracked yet" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host ">> Next steps:" -ForegroundColor Cyan
    Write-Host "   iono analysis  # Run analysis pipeline" -ForegroundColor Gray
    Write-Host "   iono ui        # View experiment results" -ForegroundColor Gray
    Write-Host "   iono learn     # Research workflow examples" -ForegroundColor Gray
}

function Show-Learn {
    Write-Host @"
╔════════════════════════════════════════════════════════════════════════╗
║  IONOSENSE-HPC RESEARCH WORKFLOW GUIDE                                 ║
╚════════════════════════════════════════════════════════════════════════╝
"@

    Write-Host ""
    Write-Host ">> START HERE - IONO WORKFLOW COMMANDS" -ForegroundColor Green
    Write-Host ""
    Write-Host "1. Check your setup:" -ForegroundColor Cyan
    Write-Host "   iono info                  # Project info & available experiments" -ForegroundColor Gray
    Write-Host "   iono status                # Git, environment & MLflow status" -ForegroundColor Gray
    Write-Host ""
    Write-Host "2. Run experiments & analysis:" -ForegroundColor Cyan
    Write-Host "   iono analysis              # Run full analysis pipeline" -ForegroundColor Gray
    Write-Host "   iono analysis -DryRun      # Preview what will run" -ForegroundColor Gray
    Write-Host ""
    Write-Host "3. View results:" -ForegroundColor Cyan
    Write-Host "   iono ui                    # Launch MLflow UI for results" -ForegroundColor Gray
    Write-Host ""
    Write-Host "4. Code quality:" -ForegroundColor Cyan
    Write-Host "   iono typecheck             # Check Python types" -ForegroundColor Gray
    Write-Host "   iono test                  # Run tests" -ForegroundColor Gray
    Write-Host "   iono lint                  # Check code style" -ForegroundColor Gray
    Write-Host ""
    Write-Host ">> IONOSPHERE RESEARCH EXPERIMENTS" -ForegroundColor Green
    Write-Host ""
    Write-Host "Start with testing:" -ForegroundColor Cyan
    Write-Host "   python benchmarks/run_throughput.py --multirun experiment=ionosphere_test +benchmark=throughput" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Then try full studies:" -ForegroundColor Cyan
    Write-Host "   python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput" -ForegroundColor Gray
    Write-Host "   python benchmarks/run_throughput.py --multirun experiment=ionosphere_temporal +benchmark=throughput" -ForegroundColor Gray
    Write-Host "   python benchmarks/run_latency.py experiment=ionosphere_multiscale +benchmark=latency" -ForegroundColor Gray
    Write-Host ""
    Write-Host ">> ADVANCED DIRECT CONTROLS" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Snakemake pipeline:" -ForegroundColor Cyan
    Write-Host "   snakemake --cores 4 --snakefile experiments/Snakefile" -ForegroundColor Gray
    Write-Host "   snakemake --cores 4 generate_figures --snakefile experiments/Snakefile" -ForegroundColor Gray
    Write-Host ""
    Write-Host "MLflow direct:" -ForegroundColor Cyan
    Write-Host "   mlflow ui --backend-store-uri file://./artifacts/mlruns" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Data versioning:" -ForegroundColor Cyan
    Write-Host "   dvc status                 # Check pipeline status" -ForegroundColor Gray
    Write-Host "   dvc repro                  # Reproduce pipeline" -ForegroundColor Gray
    Write-Host "   dvc dag                    # View pipeline DAG" -ForegroundColor Gray
    Write-Host ""
    Write-Host "!! CRITICAL REQUIREMENTS" -ForegroundColor Red
    Write-Host ""
    Write-Host "* ALWAYS specify +benchmark=throughput for throughput tests" -ForegroundColor Red
    Write-Host "* ALWAYS specify +benchmark=latency for latency tests" -ForegroundColor Red
    Write-Host "* Use experiment=ionosphere_test for quick testing" -ForegroundColor Yellow
    Write-Host ""
    Write-Host ">> More detailed examples: See CLAUDE.md" -ForegroundColor Cyan
}

function Show-Help {
    Write-Host @"
╔════════════════════════════════════════════════════════════════════════╗
║  IONOSENSE-HPC DEVELOPMENT CLI                                         ║
║  Essential development tasks - research tools use native CLIs directly ║
╚════════════════════════════════════════════════════════════════════════╝

USAGE: .\scripts\cli.ps1 <command> [options]

ESSENTIAL DEVELOPMENT
  setup [-Clean]          Create/update conda environment & install package
  build [-Preset] [-Clean] [-Verbose] [-Debug/-Release]
                          Configure and build project with CMake
  test [all|python|cpp] [-Pattern] [-Coverage] [-Verbose]
                          Run tests
  format [paths] [-Check] [-Verbose]
                          Format C++ code with clang-format
  lint [all|python|cpp] [-Fix] [-Verbose]
                          Lint code with ruff
  clean [-All]            Remove build artifacts
  doctor                  Check development environment health
  ui                      Launch MLflow UI for experiment tracking

NEW RESEARCH & STATUS COMMANDS
  analysis [-Cores] [-Target] [-DryRun]
                          Run analysis pipeline via Snakemake
  info                    Show project information and available experiments
  status                  Show comprehensive project status (git, DVC, MLflow)
  typecheck [paths] [-Verbose]
                          Run Python type checking with mypy
  learn                   Show research workflow examples and best practices

PYTHON SCRIPT RUNNER
  run <script.py> [args...]
                          Run Python script with proper environment

DEVELOPMENT WORKFLOW:
  .\scripts\cli.ps1 setup          # Environment setup
  .\scripts\cli.ps1 build          # Build project
  .\scripts\cli.ps1 test           # Run tests
  .\scripts\cli.ps1 format         # Format code
  .\scripts\cli.ps1 lint           # Lint code

RESEARCH WORKFLOW (Use native tools directly):
  # 🔬 Ionosphere research - ALWAYS specify +benchmark=
  python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput
  python benchmarks/run_latency.py experiment=ionosphere_multiscale +benchmark=latency

  # ⚠️  CRITICAL: Must specify +benchmark=latency or +benchmark=throughput
  #     Without it, you'll get: Key 'benchmark' is not in struct

  # 🐍 Analysis pipeline
  snakemake --cores 4 --snakefile experiments/Snakefile

  # 📈 View results
  .\iono.ps1 ui
  # OR: mlflow ui --backend-store-uri artifacts/mlruns

  # 📊 Data management
  dvc status && dvc repro

For detailed research workflow, see: CLAUDE.md
"@
}

# --- Main Execution ----------------------------------------------------------
try {
    Set-Location $script:ProjectRoot

    switch ($Command.ToLower()) {
        "help"     { Show-Help }
        "setup"    {
            $params = @{}
            if ($CommandArgs -icontains "-Clean") { $params.Clean = $true }
            Invoke-Setup @params
        }
        "build"    {
            $params = @{}
            if ($CommandArgs -icontains "-Clean") { $params.Clean = $true }
            if ($CommandArgs -icontains "-Verbose") { $params.Verbose = $true }

            # Handle preset
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Preset" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Preset = $CommandArgs[$i+1]
                }
            }

            if ($CommandArgs -icontains "-Debug") { $params.Preset = "windows-debug" }
            elseif ($CommandArgs -icontains "-Release") { $params.Preset = "windows-rel" }

            Invoke-Build @params
        }
        "test"     {
            $params = @{}
            if ($CommandArgs -icontains "-Coverage") { $params.Coverage = $true }
            if ($CommandArgs -icontains "-Verbose") { $params.Verbose = $true }

            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Pattern" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Pattern = $CommandArgs[$i+1]
                }
            }

            $suite = $CommandArgs | Where-Object { $_ -notlike "-*" } | Select-Object -First 1
            if ($suite) { $params.Suite = $suite }

            Invoke-Test @params
        }
        "format"   {
            $params = @{}
            if ($CommandArgs -icontains "-Check") { $params.Check = $true }
            if ($CommandArgs -icontains "-Verbose") { $params.Verbose = $true }

            $paths = $CommandArgs | Where-Object { $_ -and $_ -notlike "-*" }
            if ($paths) { $params.Paths = $paths }

            Invoke-Format @params
        }
        "lint"     {
            $params = @{}
            if ($CommandArgs -icontains "-Fix") { $params.Fix = $true }
            if ($CommandArgs -icontains "-Verbose") { $params.Verbose = $true }

            $target = $CommandArgs | Where-Object { $_ -notlike "-*" } | Select-Object -First 1
            if ($target) { $params.Target = $target }

            Invoke-Lint @params
        }
        "clean"    {
            $params = @{}
            if ($CommandArgs -icontains "-All") { $params.All = $true }
            Invoke-Clean @params
        }
        "doctor"   { Invoke-Doctor }
        "analysis" {
            $params = @{}
            if ($CommandArgs -icontains "-DryRun") { $params.DryRun = $true }

            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Cores" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Cores = [int]$CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Target" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Target = $CommandArgs[$i+1]
                }
            }

            Invoke-Analysis @params
        }
        "typecheck" {
            $params = @{}
            if ($CommandArgs -icontains "-Verbose") { $params.Verbose = $true }

            $paths = $CommandArgs | Where-Object { $_ -and $_ -notlike "-*" }
            if ($paths) { $params.Paths = $paths }

            Invoke-TypeCheck @params
        }
        "info"     { Show-Info }
        "status"   { Show-Status }
        "learn"    { Show-Learn }
        "ui"       {
            Write-Status "Starting MLflow UI..."
            $uri = Join-Path $script:ProjectRoot "artifacts/mlruns"
            Write-Status "Backend URI: $uri"

            # Check if MLflow is available
            $mlflow = Get-Command mlflow -ErrorAction SilentlyContinue
            if (-not $mlflow) {
                Write-Error "MLflow not found. Install with: pip install mlflow"
                exit 1
            }

            # Check if backend directory exists
            if (-not (Test-Path $uri)) {
                Write-Error "MLflow tracking directory not found: $uri"
                Write-Host "Run some experiments first to generate tracking data" -ForegroundColor Yellow
                exit 1
            }

            Write-Host ""
            Write-Success "Starting MLflow UI at http://localhost:5000"
            Write-Host ">> Press Ctrl+C to stop the server when done" -ForegroundColor Yellow
            Write-Host ""

            # Run MLflow UI directly (blocking)
            & mlflow ui --backend-store-uri $uri --port 5000

            if ($LASTEXITCODE -ne 0) {
                Write-Error "MLflow UI failed to start"
                exit 1
            }
        }
        "run"      {
            if ($CommandArgs.Count -eq 0) {
                Write-Error "Usage: .\scripts\cli.ps1 run <script.py> [args...]"
                exit 1
            }

            $script = $CommandArgs[0]
            $args = $CommandArgs[1..($CommandArgs.Count-1)]

            Write-Status "Running Python script: $script"
            & python $script @args
        }
        default {
            Write-Error "Unknown command: $Command"
            Write-Host "Run '.\scripts\cli.ps1 help' for available commands"
            exit 1
        }
    }

    # Only check exit code for commands that actually set it
    # Clean command doesn't set LASTEXITCODE, so don't check it
    if ($Command -notin @("clean", "doctor", "help", "ui", "info", "status", "learn") -and $LASTEXITCODE -ne 0) {
        Write-Error "Command failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }

} catch {
    Write-Error "Command failed: $($_.Exception.Message)"
    exit 1
}