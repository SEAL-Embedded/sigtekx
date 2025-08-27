# ============================================================================
# ionosense-hpc-lib • Project CLI (Windows)
# ============================================================================

# --- Paths & Defaults --------------------------------------------------------
$ProjectRoot = (Get-Item -Path (Join-Path $PSScriptRoot "..")).FullName
$BuildDir = Join-Path $ProjectRoot "build"
$VenvDir = Join-Path $ProjectRoot ".venv"
$PythonDir = Join-Path $ProjectRoot "python"
$PythonExe = Join-Path (Join-Path $VenvDir "Scripts") "python.exe"
$BuildPreset = if ($env:BUILD_PRESET) { $env:BUILD_PRESET } else { "windows-rel" }

# --- Pretty logging ----------------------------------------------------------
Function log     { param($Message) Write-Host "✅ [INFO] $Message" -ForegroundColor Cyan }
Function warn    { param($Message) Write-Host "⚠️ [WARN] $Message" -ForegroundColor Yellow }
Function err     { param($Message) Write-Host "❌ [ERR ] $Message" -ForegroundColor Red }
Function ok      { param($Message) Write-Host "👍 [OK  ] $Message" -ForegroundColor Green }
Function section { param($Message) Write-Host "`n💪 == $Message ==`n" -ForegroundColor Magenta }

$ErrorActionPreference = 'Stop'

# --- Core actions ------------------------------------------------------------
Function cmd_setup {
    section "Environment Setup (Python venv)"
    if (-not (Test-Path $VenvDir)) {
        log "Creating Python virtual environment..."
        python -m venv $VenvDir
    }
    log "Installing dependencies from requirements.txt..."
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
    
    log "Installing project in editable mode..."
    & $PythonExe -m pip install -e (Join-Path $ProjectRoot "python")
    ok "Python environment is ready."
}

Function cmd_build {
    param([string]$Preset = $BuildPreset)
    section "Configuring & Building (preset: ${Preset})"
    cmake --preset $Preset -DPython3_EXECUTABLE="$PythonExe" # Use the venv Python - Important!
    cmake --build --preset $Preset --parallel --verbose
    ok "Build finished -> $($BuildDir)\$($Preset)"
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
    section "Running All Tests"

    # Store the original PATH so we can restore it later
    $oldPath = $env:PATH

    try {
        # 1. Find the CUDA Toolkit path
        $CudaPath = $env:CUDA_PATH
        if (-not $CudaPath) {
            # Fallback for when the environment variable isn't set
            $CudaPath = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0"
        }
        if (-not (Test-Path $CudaPath)) {
            err "CUDA_PATH not found. Please set the environment variable or install to the default location."
            return
        }

        # 2. Add the CUDA bin directory to the PATH for any C++ test deps (safe to keep)
        $CudaBin = Join-Path $CudaPath "bin"
        $env:PATH = "$CudaBin;$oldPath"
        log "Temporarily added $CudaBin to PATH"

        # 3. Run the C++ tests first
        log "Running C++ tests..."
        ctest --preset "windows-tests" --output-on-failure
        ok "C++ tests completed."

        # 4. Run the Python tests (no PYTHONPATH hacks needed)
        log "Running Python tests..."
        & $PythonExe -m pytest -v (Join-Path $ProjectRoot "python\tests") --tb=short
        ok "Python tests completed."
    }
    catch {
        err "A test failed: $_"
        exit 1
    }
    finally {
        $env:PATH = $oldPath
        log "Restored original environment."
    }
}

Function cmd_list {
    param([string[]]$Args)
    if ($Args.Count -eq 0 -or $Args[0] -ne "benchmarks") {
        err "Usage: list benchmarks"
        return
    }
    section "Available Benchmarks"
    $benchmarkDir = Join-Path $PythonDir "benchmarks"
    Get-ChildItem -Path $benchmarkDir -Recurse -Filter "*.py" | 
        Where-Object { $_.Name -ne "__init__.py" } |
        ForEach-Object { $_.FullName.Substring($benchmarkDir.Length + 1).Replace(".py", "") } |
        Sort-Object
}

Function cmd_bench {
    param([string[]]$Args)
    if ($Args.Count -lt 1) {
        err "Usage: bench <script_name> [args...]"
        return
    }
    $scriptName = $Args[0]
    $scriptArgs = if ($Args.Count -gt 1) { $Args[1..($Args.Length - 1)] } else { @() }
    
    $scriptPath = (Get-ChildItem -Path (Join-Path $PythonDir "benchmarks") -Recurse -Filter "${scriptName}.py").FullName
    if (-not $scriptPath) {
        err "Benchmark script not found: ${scriptName}.py"
        return
    }
    
    section "Running Benchmark: $scriptName"
    & $PythonExe $scriptPath $scriptArgs
}

Function cmd_profile {
    param([string[]]$Args)
    if ($Args.Count -lt 2) {
        err "Usage: profile <nsys|ncu> <script_name> [args...]"
        return
    }
    $tool = $Args[0]
    $scriptName = $Args[1]
    $scriptArgs = if ($Args.Count -gt 2) { $Args[2..($Args.Length - 1)] } else { @() }

    $scriptPath = (Get-ChildItem -Path (Join-Path $PythonDir "benchmarks") -Recurse -Filter "${scriptName}.py").FullName
    if (-not $scriptPath) {
        err "Benchmark script not found: ${scriptName}.py"
        return
    }
    
    $outDir = Join-Path $BuildDir "profiles" $tool
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $outFile = Join-Path $outDir "$($scriptName)_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    
    section "Profiling ($tool): $scriptName"
    
    switch ($tool) {
        "nsys" {
            nsys profile -o "$outFile" --trace=cuda,nvtx -f true --wait=all $PythonExe $scriptPath $scriptArgs
            ok "Nsight Systems report saved to ${outFile}.nsys-rep"
        }
        "ncu" {
            ncu --set full --target-processes all -o "$outFile" $PythonExe $scriptPath $scriptArgs
            ok "Nsight Compute report saved to ${outFile}.ncu-rep"
        }
        default {
            err "Unknown profiler: '$tool'. Use 'nsys' or 'ncu'."
        }
    }
}

Function cmd_clean {
    section "Cleaning Workspace"
    if(Test-Path $BuildDir) {
        log "Removing build directory: $BuildDir"
        Remove-Item -Path $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Get-ChildItem -Path $ProjectRoot -Include __pycache__,.pytest_cache -Directory -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $ProjectRoot -Include *.pyc -File -Recurse -Force | Remove-Item -Force -ErrorAction SilentlyContinue
    ok "Workspace cleaned."
}

Function Show-Usage {
    Write-Host @"
IONOSENSE-HPC • Scalable Project CLI (Windows)
Usage: ./scripts/cli.ps1 <command> [options]

CORE WORKFLOW
  setup                    Initialize Python venv and install dependencies
  build [preset]           Configure & build (default: $($BuildPreset))
  rebuild [preset]         Clean and rebuild
  test                     Run all C++ and Python unit tests
  
BENCHMARKING & PROFILING
  list benchmarks          Discover and list all available benchmark scripts
  bench <name> [args...]   Run a benchmark by its name (without .py)
  profile <tool> <name>    Profile a benchmark with 'nsys' or 'ncu'

UTILITIES
  clean                    Remove all build and cache files

EXAMPLES
  .\scripts\cli.ps1 test
  .\scripts\cli.ps1 list benchmarks
  .\scripts\cli.ps1 bench raw_throughput -n 4096
"@
}

# --- Main Dispatcher ---
$Command = if ($Args.Count -gt 0) { $Args[0] } else { "help" }
$CommandArgs = if ($Args.Count -gt 1) { $Args[1..($Args.Length - 1)] } else { @() }

Set-Location $ProjectRoot

switch ($Command) {
    "help"      { Show-Usage }
    "-h"        { Show-Usage }
    "--help"    { Show-Usage }
    "setup"     { cmd_setup }
    "build"     { 
        if ($CommandArgs.Count -gt 0) {
            cmd_build -Preset $CommandArgs[0]
        } else {
            cmd_build
        }
    }
    "rebuild"   {
        if ($CommandArgs.Count -gt 0) {
            cmd_rebuild -Preset $CommandArgs[0]
        } else {
            cmd_rebuild
        }
    }
    "test"      { cmd_test }
    "clean"     { cmd_clean }
    "list"      { cmd_list -Args $CommandArgs }
    "bench"     { cmd_bench -Args $CommandArgs }
    "profile"   { cmd_profile -Args $CommandArgs }
    default     {
        err "Unknown command: $Command"
        Show-Usage
        exit 1
    }
}
