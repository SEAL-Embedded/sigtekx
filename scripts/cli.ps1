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
    & conda run -n $script:CondaEnvName pip install -e .[dev]

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

    $script:BuildPreset = $Preset
    $configLabel = if ($Preset -match 'debug') { 'Debug' } else { 'Release' }

    Write-Status "Building project with preset: $Preset ($configLabel)"

    if ($Clean) {
        Write-Status "Cleaning build directory..."
        if (Test-Path $script:BuildDir) {
            Remove-Item $script:BuildDir -Recurse -Force
        }
    }

    $configureArgs = @("--preset", $Preset)
    if ($Verbose) { $configureArgs += "--log-level=VERBOSE" }

    Write-Status "Configuring with CMake..."
    & cmake @configureArgs

    if ($LASTEXITCODE -ne 0) {
        Write-Error "CMake configuration failed"
        exit 1
    }

    Write-Status "Building..."
    $buildArgs = @("--build", "--preset", $Preset)
    if ($Verbose) { $buildArgs += "--verbose" }

    & cmake @buildArgs

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
            if ($Coverage) {
                Write-Status "Running C++ tests with coverage..."
                Invoke-Coverage -Verbose:$Verbose
            } else {
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

function Invoke-Coverage {
    param(
        [bool]$Verbose = $false,
        [bool]$OpenReport = $true
    )

    Write-Status "Running C++ tests with code coverage..."

    # Step 1: Build with coverage preset
    Write-Status "Building project with coverage instrumentation..."
    $buildArgs = @("--preset", "windows-coverage")
    if ($Verbose) { $buildArgs += "--log-level=VERBOSE" }

    & cmake @buildArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "CMake configuration failed"
        exit 1
    }

    & cmake --build --preset windows-coverage
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Build failed"
        exit 1
    }

    # Step 2: Run tests
    Write-Status "Running C++ tests..."
    $testExe = Join-Path $script:BuildDir "windows-coverage/test_engine.exe"
    if (-not (Test-Path $testExe)) {
        Write-Error "Test executable not found at: $testExe"
        exit 1
    }

    # Use brief output by default, full output with -Verbose
    $testArgs = @()
    if (-not $Verbose) {
        $testArgs += "--gtest_brief=1"
    }
    & $testExe @testArgs
    $testExitCode = $LASTEXITCODE

    # Step 3: Generate coverage reports
    Write-Status "Generating coverage reports..."
    $reportsDir = Join-Path $script:ProjectRoot "artifacts/reports"
    $coverageDir = Join-Path $reportsDir "coverage-cpp"

    if (-not (Test-Path $reportsDir)) {
        New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
    }
    if (Test-Path $coverageDir) {
        Remove-Item $coverageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $coverageDir -Force | Out-Null

    # Generate HTML report
    $srcDir = Join-Path $script:ProjectRoot "cpp"
    $buildCoverageDir = Join-Path $script:BuildDir "windows-coverage"

    Write-Status "Analyzing coverage data with gcovr..."

    # Convert Windows paths to forward slashes for gcovr regex compatibility
    $rootPath = $script:ProjectRoot -replace '\\', '/'
    $srcFilter = ($srcDir -replace '\\', '/') + '/.*'

    # Terminal summary
    & gcovr `
        --root $rootPath `
        --filter $srcFilter `
        --exclude ".*test.*" `
        --exclude ".*_deps.*" `
        --print-summary

    # HTML report
    & gcovr `
        --root $rootPath `
        --filter $srcFilter `
        --exclude ".*test.*" `
        --exclude ".*_deps.*" `
        --html-details "$coverageDir/index.html"

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Coverage report generated: $coverageDir/index.html"

        if ($OpenReport) {
            Write-Status "Opening coverage report in browser..."
            Start-Process "$coverageDir/index.html"
        }
    } else {
        Write-Error "Coverage report generation failed"
    }

    # Return test exit code
    if ($testExitCode -ne 0) {
        Write-Error "Tests failed"
        exit $testExitCode
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

function Invoke-Profile {
    param(
        [string]$Tool = "",
        [string]$Target = "",
        [string]$Mode = "quick",
        [string]$Script = "",
        [string]$Kernel = "",
        [int]$Duration = 0,
        [bool]$OpenAfter = $true,
        [bool]$Interactive = $false
    )

    Write-Status "Starting GPU profiling session..."

    # Validate prof_helper.py exists
    $profHelper = Join-Path $script:ProjectRoot "scripts/prof_helper.py"
    if (-not (Test-Path $profHelper)) {
        Write-Error "prof_helper.py not found at: $profHelper"
        exit 1
    }

    # Interactive mode if no parameters provided
    if (-not $Tool -or -not $Target) {
        $Interactive = $true
    }

    if ($Interactive) {
        Write-Host "`n🎯 GPU Profiling Tool Selection" -ForegroundColor Cyan
        Write-Host "1. nsys (Nsight Systems) - Timeline analysis, CUDA API tracing"
        Write-Host "2. ncu  (Nsight Compute) - Kernel performance analysis"
        do {
            $toolChoice = Read-Host "Select profiling tool (1-2)"
        } while ($toolChoice -notin @("1", "2"))

        $Tool = if ($toolChoice -eq "1") { "nsys" } else { "ncu" }

        Write-Host "`n📊 Benchmark Target Selection" -ForegroundColor Cyan
        Write-Host "1. latency    - Latency benchmark with profiling config"
        Write-Host "2. throughput - Throughput benchmark with profiling config"
        Write-Host "3. accuracy   - Accuracy benchmark with profiling config"
        Write-Host "4. realtime   - Realtime benchmark with profiling config"
        Write-Host "5. custom     - Specify custom script path"
        do {
            $targetChoice = Read-Host "Select benchmark target (1-5)"
        } while ($targetChoice -notin @("1", "2", "3", "4", "5"))

        $Target = switch ($targetChoice) {
            "1" { "latency" }
            "2" { "throughput" }
            "3" { "accuracy" }
            "4" { "realtime" }
            "5" {
                $Script = Read-Host "Enter custom script path"
                "custom"
            }
        }

        if ($Tool -eq "ncu") {
            $modeChoice = Read-Host "Profiling mode? (quick/full) [quick]"
            if ($modeChoice) { $Mode = $modeChoice }
        }
    }

    # Validate target benchmark exists for presets
    if ($Target -in @("latency", "throughput", "accuracy", "realtime")) {
        $benchmarkScript = Join-Path $script:ProjectRoot "benchmarks/run_$Target.py"
        if (-not (Test-Path $benchmarkScript)) {
            Write-Error "Benchmark script not found: $benchmarkScript"
            exit 1
        }
    }

    # Build prof_helper command
    $args = @($Tool)

    if ($Script) {
        $args += $Script
    } else {
        $args += $Target
    }

    $args += "--mode", $Mode

    if ($Kernel) { $args += "--kernel", $Kernel }
    if ($Duration -gt 0) { $args += "--duration", $Duration }

    # Add profiling config for preset benchmarks
    if ($Target -in @("latency", "throughput", "accuracy", "realtime")) {
        # Map targets to their lightweight profiling benchmark configs
        $benchmarkConfig = switch ($Target) {
            "latency"    { "profiling" }
            "throughput" { "profiling_throughput" }
            "realtime"   { "profiling_realtime" }
            "accuracy"   { "profiling_accuracy" }
        }
        $args += "--", "experiment=profiling", "+benchmark=$benchmarkConfig"
    }

    Write-Status "Executing: python `"$profHelper`" $($args -join ' ')"
    Write-Host ""

    # Run profiling
    & python $profHelper @args

    if ($LASTEXITCODE -eq 0 -and $OpenAfter) {
        Write-Host "`n🚀 Opening profiling results..." -ForegroundColor Green

        # Open artifacts/profiling directory
        $profilingDir = Join-Path $script:ProjectRoot "artifacts/profiling"
        if (Test-Path $profilingDir) {
            Write-Status "Opening profiling directory: $profilingDir"
            Start-Process "explorer.exe" -ArgumentList $profilingDir
        }
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
  build [-Preset <name>] [-Clean] [--debug|--release] [--verbose]
                          Configure and build project with CMake
  test [all|python|cpp] [-Pattern] [-Coverage] [--verbose]
                          Run tests (use -Coverage for C++ coverage)
  coverage [-NoOpen] [--verbose]
                          Run C++ tests with code coverage report
  format [paths] [-Check] [--verbose]
                          Format C++ code with clang-format
  lint [all|python|cpp] [-Fix] [--verbose]
                          Lint code with ruff
  clean [-All]            Remove build artifacts
  doctor                  Check development environment health
  ui                      Launch MLflow UI for experiment tracking

GPU PROFILING
  profile [tool] [target] Profile GPU performance with Nsight tools
                          Tools: nsys (Systems), ncu (Compute)
                          Targets: latency, throughput, accuracy, realtime, custom
                          Interactive mode if no args provided

PROFILING EXAMPLES:
  .\scripts\cli.ps1 profile nsys latency      # Profile latency benchmark
  .\scripts\cli.ps1 profile ncu throughput   # Profile throughput with NCU
  .\scripts\cli.ps1 profile                   # Interactive mode
  .\scripts\cli.ps1 profile nsys latency -Full -Duration 30
  .\scripts\cli.ps1 profile ncu custom -Script "my_script.py"

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

    $normalizedArgs = @()
    foreach ($arg in $CommandArgs) {
        if ($null -ne $arg) {
            $normalizedArgs += $arg.ToLowerInvariant()
        }
    }

    $commonDebug = $false
    $commonVerbose = $false
    if ($null -ne $PSBoundParameters) {
        if ($PSBoundParameters.ContainsKey('Debug')) { $commonDebug = $true }
        if ($PSBoundParameters.ContainsKey('Verbose')) { $commonVerbose = $true }
    }

    switch ($Command.ToLower()) {
        "help"     { Show-Help }
        "setup"    {
            $params = @{}
            if ($CommandArgs -icontains "-Clean") { $params.Clean = $true }
            Invoke-Setup @params
        }
        "build"    {
            $params = @{}

            if ($normalizedArgs -contains "-clean" -or $normalizedArgs -contains "--clean") { $params.Clean = $true }

            if ($commonVerbose -or $normalizedArgs -contains "-verbose" -or $normalizedArgs -contains "--verbose") {
                $params.Verbose = $true
            }

            # Handle preset
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Preset" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Preset = $CommandArgs[$i+1]
                }
            }

            if ($commonDebug -or $normalizedArgs -contains "-debug" -or $normalizedArgs -contains "--debug") {
                $params.Preset = "windows-debug"
            } elseif ($normalizedArgs -contains "-release" -or $normalizedArgs -contains "--release") {
                $params.Preset = "windows-rel"
            }

            Invoke-Build @params
        }

        "test"     {
            $params = @{}
            if ($normalizedArgs -contains "-coverage" -or $normalizedArgs -contains "--coverage") { $params.Coverage = $true }
            if ($commonVerbose -or $normalizedArgs -contains "-verbose" -or $normalizedArgs -contains "--verbose") { $params.Verbose = $true }

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
            if ($normalizedArgs -contains "-check" -or $normalizedArgs -contains "--check") { $params.Check = $true }
            if ($commonVerbose -or $normalizedArgs -contains "-verbose" -or $normalizedArgs -contains "--verbose") { $params.Verbose = $true }

            $paths = $CommandArgs | Where-Object { $_ -and $_ -notlike "-*" }
            if ($paths) { $params.Paths = $paths }

            Invoke-Format @params
        }

        "lint"     {
            $params = @{}
            if ($normalizedArgs -contains "-fix" -or $normalizedArgs -contains "--fix") { $params.Fix = $true }
            if ($commonVerbose -or $normalizedArgs -contains "-verbose" -or $normalizedArgs -contains "--verbose") { $params.Verbose = $true }

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
        "coverage" {
            $params = @{}
            if ($normalizedArgs -contains "-noopen" -or $normalizedArgs -contains "--no-open") { $params.OpenReport = $false }
            if ($commonVerbose -or $normalizedArgs -contains "-verbose" -or $normalizedArgs -contains "--verbose") { $params.Verbose = $true }
            Invoke-Coverage @params
        }
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
            # Use Start-Process to launch without blocking the terminal
            Start-Process mlflow @("ui", "--backend-store-uri", $uri, "--port", "5000")
            Write-Success "MLflow UI launched at http://localhost:5000"
        }
        "profile"  {
            $params = @{}

            # Parse tool and target from args
            $nonFlagArgs = $CommandArgs | Where-Object { $_ -and $_ -notlike "-*" }
            if ($nonFlagArgs.Count -ge 1) { $params.Tool = $nonFlagArgs[0] }
            if ($nonFlagArgs.Count -ge 2) { $params.Target = $nonFlagArgs[1] }

            # Parse flags
            if ($CommandArgs -icontains "-Full") { $params.Mode = "full" }
            if ($CommandArgs -icontains "-NoOpen") { $params.OpenAfter = $false }

            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Mode" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Mode = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Script" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Script = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Kernel" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Kernel = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Duration" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Duration = [int]$CommandArgs[$i+1]
                }
            }

            Invoke-Profile @params
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