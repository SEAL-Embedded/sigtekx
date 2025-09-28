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
            $testExe = Join-Path $script:BuildDir "Release/tests/test_runner.exe"
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

            $testExe = Join-Path $script:BuildDir "Release/tests/test_runner.exe"
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
        "ui"       {
            Write-Status "Starting MLflow UI..."
            $uri = Join-Path $script:ProjectRoot "artifacts/mlruns"
            Write-Status "Backend URI: $uri"
            # Use Start-Process to launch without blocking the terminal
            Start-Process mlflow @("ui", "--backend-store-uri", $uri, "--port", "5000")
            Write-Success "MLflow UI launched at http://localhost:5000"
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
    if ($Command -notin @("clean", "doctor", "help", "ui") -and $LASTEXITCODE -ne 0) {
        Write-Error "Command failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }

} catch {
    Write-Error "Command failed: $($_.Exception.Message)"
    exit 1
}