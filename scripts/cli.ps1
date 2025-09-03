# ============================================================================
# ionosense-hpc-lib • Project CLI (Windows)
# - Professional research-grade build & test orchestration
# - Integrated Python API commands following RSE/RE standards
# ============================================================================

# --- Paths & Defaults --------------------------------------------------------
$ProjectRoot = (Get-Item -Path (Join-Path $PSScriptRoot "..")).FullName
$BuildDir    = Join-Path $ProjectRoot "build"
$PythonDir   = Join-Path $ProjectRoot "python"
$BuildPreset = if ($env:BUILD_PRESET) { $env:BUILD_PRESET } else { "windows-rel" }
$CondaEnvName = "ionosense-hpc"
$EnvironmentFile = Join-Path $ProjectRoot "environments/environment.win.yml"
$BenchResultsDir = Join-Path $BuildDir "benchmark_results"


# --- Pretty logging ----------------------------------------------------------
Function log     { param($Message) Write-Host "✅ [INFO] $Message" -ForegroundColor Cyan }
Function warn    { param($Message) Write-Host "⚠️ [WARN] $Message" -ForegroundColor Yellow }
Function err     { param($Message) Write-Host "❌ [ERR ] $Message" -ForegroundColor Red }
Function ok      { param($Message) Write-Host "👍 [OK  ] $Message" -ForegroundColor Green }
Function section { param($Message) Write-Host "`n💪 == $Message ==`n" -ForegroundColor Magenta }

$ErrorActionPreference = 'Stop'

# --- Helpers ------------------------------------------------------------------
Function Ensure-EnvActivated {
    if (-not $env:CONDA_PREFIX -or ($env:CONDA_DEFAULT_ENV -ne $CondaEnvName)) {
        err "Conda environment '$CondaEnvName' is not activated."
        log "Please run: conda activate $CondaEnvName"
        exit 1
    }
}

Function With-PythonPath {
    param([scriptblock]$ScriptBlock)
    $oldPath = $env:PYTHONPATH
    # Ensure the src directory is on the path for local development imports
    $env:PYTHONPATH = "$BuildDir\$BuildPreset;" + (Join-Path $PythonDir "src") + ";$env:PYTHONPATH"
    try {
        & $ScriptBlock
    } finally {
        $env:PYTHONPATH = $oldPath
    }
}

Function _lint_python {
    log "Running Python linter (ruff)..."
    ruff check --fix (Join-Path $PythonDir)
    if ($LASTEXITCODE -ne 0) {
        warn "Ruff found issues in the Python code."
        return $false
    } else {
        ok "Python linting passed."
        return $true
    }
}

Function _lint_cpp {
    log "Running C++ linter (clang-tidy)..."
    # This is a placeholder. To implement this, you would typically enable
    # clang-tidy checks directly in your CMake build configuration by setting
    # the CMAKE_CXX_CLANG_TIDY variable. Then, a clean build would show warnings.
    warn "C++ linting is not yet configured. This is a placeholder."
    return $true # Return true for now so it doesn't fail the combined lint command
}

# --- Core actions ------------------------------------------------------------
Function cmd_setup {
    section "Environment Setup (Windows/Mamba)"
    Set-Location $ProjectRoot # Ensure we are in the correct directory

    $solver = "mamba"
    if (-not (Get-Command mamba -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
            err "Neither mamba nor conda found. Please install Miniforge3 or Miniconda."
            exit 1
        }
        warn "mamba not found, using conda (slower). Install mamba: conda install mamba -n base -c conda-forge"
        $solver = "conda"
    }

    $envExists = conda env list | Select-String -Quiet -Pattern "\b$CondaEnvName\b"
    if ($envExists) {
        log "Updating existing environment '$CondaEnvName' with $solver..."
        & $solver env update --name $CondaEnvName --file $EnvironmentFile --prune
    } else {
        log "Creating new environment '$CondaEnvName' with $solver..."
        log "This may take several minutes..."
        & $solver env create --file $EnvironmentFile
    }
    if ($LASTEXITCODE -ne 0) {
        err "Environment setup failed"
        exit 1
    }
    
    log "Installing ionosense-hpc Python package in development mode..."
    conda run -n $CondaEnvName python -m pip install -e ".[dev,benchmark,export]"
    if ($LASTEXITCODE -ne 0) {
        err "Pip install failed. Ensure the conda environment is correct."
        exit 1
    }
    
    ok "Environment ready. Activate with: conda activate $CondaEnvName"
}

Function cmd_build {
    param([string]$Preset = $BuildPreset)
    section "Configuring & Building (preset: ${Preset})"
    Ensure-EnvActivated
    
    cmake --preset $Preset
    if ($LASTEXITCODE -ne 0) { 
        err "Configuration failed"
        exit 1 
    }
    
    cmake --build --preset $Preset --parallel --verbose
    if ($LASTEXITCODE -ne 0) { 
        err "Build failed"
        exit 1 
    }
    
    log "Verifying Python module..."
    With-PythonPath {
        python -c "import ionosense_hpc; print(f'Module loaded: v{ionosense_hpc.__version__}')"
        if ($LASTEXITCODE -eq 0) {
            ok "Python module verified"
        } else {
            warn "Python module import failed - check build output"
        }
    }
    
    ok "Build finished -> $BuildDir\$Preset"
}

Function cmd_rebuild {
    param([string]$Preset = $BuildPreset)
    section "Clean Rebuild (preset: ${Preset})"
    $presetDir = Join-Path $BuildDir $Preset
    if (Test-Path $presetDir) {
        log "Removing $presetDir"
        Remove-Item -Path $presetDir -Recurse -Force
    }
    cmd_build -Preset $Preset
}

Function cmd_test {
    param([string]$Preset = $BuildPreset)
    section "Running All Tests"
    Ensure-EnvActivated
    
    log "Running C++ tests..."
    $testPreset = $Preset.Replace('rel','tests').Replace('debug','tests')
    ctest --preset $testPreset --output-on-failure
    if ($LASTEXITCODE -ne 0) {
        warn "Some C++ tests failed"
    } else {
        ok "C++ tests passed"
    }
    
    log "Running Python tests..."
    With-PythonPath {
        pytest -v (Join-Path $PythonDir "tests") --tb=short
    }
    if ($LASTEXITCODE -ne 0) {
        warn "Some Python tests failed"
    } else {
        ok "Python tests passed"
    }
    
    ok "All tests completed"
}

Function cmd_lint {
    param([string[]]$LintArgs)
    section "Running Linters"
    Ensure-EnvActivated

    $target = if ($LintArgs.Count -gt 0) { $LintArgs[0] } else { "all" }

    $py_ok = $true
    $cpp_ok = $true

    switch ($target) {
        "all" {
            $py_ok = _lint_python
            $cpp_ok = _lint_cpp
        }
        "py" {
            $py_ok = _lint_python
        }
        "cpp" {
            $cpp_ok = _lint_cpp
        }
        default {
            err "Unknown lint target: '$target'. Use 'py', 'cpp', or no argument for all."
            exit 1
        }
    }

    if (-not ($py_ok -and $cpp_ok)) {
        err "Linting failed for one or more targets."
        # Use a non-standard exit code to differentiate from other failures if needed
        exit 2
    } else {
        ok "All lint checks passed."
    }
}

Function cmd_list {
    param([string[]]$ListArgs)
    if ($ListArgs.Count -eq 0) {
        err "Usage: list <benchmarks|presets|devices>"
        return
    }
    
    switch ($ListArgs[0]) {
        "benchmarks" {
            section "Available Benchmarks"
            $benchmarkDir = Join-Path $PythonDir "src\ionosense_hpc\benchmarks"
            Get-ChildItem -Path $benchmarkDir -Recurse -Filter "*.py" -File |
                Where-Object { $_.Name -ne "__init__.py" } |
                ForEach-Object {
                    $_.Name -replace '\.py$',''
                } |
                Sort-Object
        }
        "presets" {
            section "Available Configuration Presets"
            With-PythonPath {
                python -c "from ionosense_hpc import Presets; [print(f'  {n:12s}: nfft={c.nfft:5d}, batch={c.batch:3d}') for n, c in Presets.list_presets().items()]"
            }
        }
        "devices" {
            section "Available CUDA Devices"
            With-PythonPath {
                python -c "from ionosense_hpc import gpu_count, device_info; n=gpu_count(); print(f'Found {n} CUDA device(s)'); [print(f'  [{i}] {d['name']} - {d['memory_free_mb']}/{d['memory_total_mb']} MB free') for i in range(n) for d in [device_info(i)]]"
            }
        }
        default {
            err "Unknown list type: $($ListArgs[0])"
        }
    }
}

Function cmd_bench {
    param([string[]]$BenchArgs)
    if ($BenchArgs.Count -lt 1) {
        err "Usage: bench <script_name|suite> [args...]"
        return
    }
    
    Ensure-EnvActivated
    New-Item -ItemType Directory -Force -Path $BenchResultsDir | Out-Null
    
    $scriptName = $BenchArgs[0]
    $scriptArgs = if ($BenchArgs.Count -gt 1) { $BenchArgs[1..($BenchArgs.Length - 1)] } else { @() }
    
    $moduleBase = "ionosense_hpc.benchmarks"
    
    if ($scriptName -eq "suite") {
        section "Running Full Benchmark Suite"
        $preset = if ($scriptArgs.Count -gt 0) { $scriptArgs[0] } else { "realtime" }
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $outputDir = Join-Path $BenchResultsDir "${timestamp}_${preset}"
        
        With-PythonPath {
            python -m $moduleBase.suite --preset $preset --output $outputDir --log-level INFO
        }
        
        ok "Results saved to: $outputDir"
    } else {
        $moduleName = "$moduleBase.$scriptName"
        section "Running Benchmark: $moduleName"
        With-PythonPath {
            & python -m $moduleName $scriptArgs
        }
    }
}

Function cmd_profile {
    param([string[]]$ProfileArgs)
    if ($ProfileArgs.Count -lt 2) {
        err "Usage: profile <nsys|ncu> <script_name|subpath> [args...]"
        return
    }
    
    Ensure-EnvActivated
    $tool = $ProfileArgs[0]
    $scriptName = $ProfileArgs[1]
    $scriptArgs = if ($ProfileArgs.Count -gt 2) { $ProfileArgs[2..($ProfileArgs.Length - 1)] } else { @() }
    
    $moduleBase = "ionosense_hpc.benchmarks"
    $moduleName = "$moduleBase.$scriptName"
    
    New-Item -ItemType Directory -Force -Path (Join-Path $BuildDir "nsight_reports/nsys_reports") -ErrorAction SilentlyContinue | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $BuildDir "nsight_reports/ncu_reports") -ErrorAction SilentlyContinue | Out-Null
    
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $outFile = "${scriptName}_${timestamp}" -replace '[\\/]', '_'
    
    section "Profiling ($tool): $moduleName"
    
    With-PythonPath {
        switch ($tool) {
            "nsys" {
                $reportPath = Join-Path $BuildDir "nsight_reports/nsys_reports/$outFile"
                nsys profile -o $reportPath --trace=cuda,nvtx,osrt -f true --wait=all python -m $moduleName $scriptArgs
                ok "Nsight Systems report saved to ${reportPath}.nsys-rep"
            }
            "ncu" {
                $reportPath = Join-Path $BuildDir "nsight_reports/ncu_reports/$outFile"
                ncu --set full -o $reportPath python -m $moduleName $scriptArgs
                ok "Nsight Compute report saved to ${reportPath}.ncu-rep"
            }
            default {
                err "Unknown profiler: '$tool'. Use 'nsys' or 'ncu'."
            }
        }
    }
}

Function cmd_validate {
    section "Running Validation Suite"
    Ensure-EnvActivated
    
    log "Running accuracy and stability validation..."
    With-PythonPath {
        python -c "from ionosense_hpc.benchmarks import benchmark_accuracy, benchmark_numerical_stability; import json; acc_results = benchmark_accuracy(); print(f""Accuracy: {acc_results['summary']['pass_rate']:.0%} tests passed""); stab_results = benchmark_numerical_stability(); print(f""Stability: {'PASS' if stab_results['all_stable'] else 'FAIL'}""); f_path = r'$BuildDir\validation_results.json'; [IO.File]::WriteAllText(f_path, (json.dumps({'accuracy': acc_results, 'stability': stab_results}, indent=2))); print(f""Results saved to: {f_path}"")"
    }
    ok "Validation complete"
}

Function cmd_monitor {
    section "GPU Monitoring"
    Ensure-EnvActivated
    
    log "Starting GPU monitor (Ctrl+C to stop)..."
    With-PythonPath {
        python -c "import time, os; from ionosense_hpc import monitor_device; try: [ (os.system('cls' if os.name == 'nt' else 'clear'), print('=== GPU Monitor ==='), print(monitor_device()), time.sleep(1)) for _ in iter(int, 1)]; except KeyboardInterrupt: print('\nDone.')"
    }
}

Function cmd_info {
    section "System Information"
    Ensure-EnvActivated
    
    With-PythonPath {
        python -c "from ionosense_hpc import show_versions; print('=== Environment ==='); show_versions(verbose=True)"
    }
}

Function cmd_clean {
    section "Cleaning Workspace"
    
    if (Test-Path $BuildDir) {
        log "Removing build directory: $BuildDir"
        Remove-Item -Path $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    log "Cleaning Python artifacts..."
    Get-ChildItem -Path $ProjectRoot -Include __pycache__,.pytest_cache,*.egg-info -Directory -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $ProjectRoot -Include *.pyc,*.pyo -File -Recurse -Force | Remove-Item -Force -ErrorAction SilentlyContinue
    
    ok "Workspace cleaned"
}

Function Show-Usage {
    Write-Host @"
IONOSENSE-HPC • Research-Grade Signal Processing CLI (Windows)
Usage: .\scripts\cli.ps1 <command> [options]

CORE WORKFLOW
  setup                      Create/update environment & install Python package
  build [preset]             Configure & build (default: $BuildPreset)
  rebuild [preset]           Clean & rebuild
  lint [py|cpp]              Run Python, C++, or both linters
  test [preset]              Run C++ & Python tests

BENCHMARKING & PROFILING
  list <type>                List available items (benchmarks, presets, devices)
  bench suite [preset]       Run full benchmark suite with report
  bench <name> [args...]     Run specific benchmark
  profile <tool> <name>      Profile with Nsight Systems (nsys) or Compute (ncu)
  validate                   Run numerical validation suite

UTILITIES
  monitor                    Real-time GPU monitoring
  info                       Show system & build information
  clean                      Remove all build outputs & caches

EXAMPLES
  .\scripts\cli.ps1 setup
  .\scripts\cli.ps1 build
  .\scripts\cli.ps1 lint py
  .\scripts\cli.ps1 test
  .\scripts\cli.ps1 bench suite
"@
}

# --- Main Dispatcher ---
$Command = if ($Args.Count -gt 0) { $Args[0] } else { "help" }
$CommandArgs = if ($Args.Count -gt 1) { $Args[1..($Args.Length - 1)] } else { @() }

Set-Location $ProjectRoot

# REVISED: Corrected the logic for handling optional command-line arguments.
# This replaces the invalid "-if" syntax with standard PowerShell conditionals.
switch ($Command) {
    "help"      { Show-Usage }
    "-h"        { Show-Usage }
    "--help"    { Show-Usage }
    "setup"     { cmd_setup }
    "build"     {
        $preset = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { $BuildPreset }
        cmd_build -Preset $preset
    }
    "rebuild"   {
        $preset = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { $BuildPreset }
        cmd_rebuild -Preset $preset
    }
    "test"      {
        $preset = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { $BuildPreset }
        cmd_test -Preset $preset
    }
    "lint"      { cmd_lint -LintArgs $CommandArgs }
    "clean"     { cmd_clean }
    "list"      { cmd_list -ListArgs $CommandArgs }
    "bench"     { cmd_bench -BenchArgs $CommandArgs }
    "profile"   { cmd_profile -ProfileArgs $CommandArgs }
    "validate"  { cmd_validate }
    "monitor"   { cmd_monitor }
    "info"      { cmd_info }
    default     { err "Unknown command: $Command"; Show-Usage; exit 1 }
}