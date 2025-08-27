# ============================================================================
# ionosense-hpc-lib • Project CLI (Windows)
# ============================================================================

# --- Paths & Defaults --------------------------------------------------------
$ProjectRoot = (Get-Item -Path (Join-Path $PSScriptRoot "..")).FullName
$BuildDir    = Join-Path $ProjectRoot "build"
$VenvDir     = Join-Path $ProjectRoot ".venv"
$PythonDir   = Join-Path $ProjectRoot "python"
$PythonExe   = Join-Path (Join-Path $VenvDir "Scripts") "python.exe"
$BuildPreset = if ($env:BUILD_PRESET) { $env:BUILD_PRESET } else { "windows-rel" }
$CMakePresetsPath = Join-Path $ProjectRoot "CMakePresets.json"

# --- Pretty logging ----------------------------------------------------------
Function log     { param($Message) Write-Host "✅ [INFO] $Message" -ForegroundColor Cyan }
Function warn    { param($Message) Write-Host "⚠️ [WARN] $Message" -ForegroundColor Yellow }
Function err     { param($Message) Write-Host "❌ [ERR ] $Message" -ForegroundColor Red }
Function ok      { param($Message) Write-Host "👍 [OK  ] $Message" -ForegroundColor Green }
Function section { param($Message) Write-Host "`n💪 == $Message ==`n" -ForegroundColor Magenta }

$ErrorActionPreference = 'Stop'

# --- Helpers -----------------------------------------------------------------
Function Get-WorkflowPresetFor {
    param([string]$ConfigurePresetName)
    try {
        if (-not (Test-Path $CMakePresetsPath)) { return $null }
        $json = Get-Content -Raw $CMakePresetsPath | ConvertFrom-Json
        if (-not $json.workflowPresets) { return $null }
        foreach ($wf in $json.workflowPresets) {
            foreach ($step in $wf.steps) {
                if ($step.type -eq 'configure' -and $step.name -eq $ConfigurePresetName) {
                    return $wf.name
                }
            }
        }
        return $null
    } catch {
        warn "Failed to parse workflow presets: $_"
        return $null
    }
}

Function Find-BenchmarkScript {
    param([string]$Name)

    $benchRoot = Join-Path $PythonDir "benchmarks"

    # If caller passed a relative path like "fft/raw_throughput" or "fft\raw_throughput"
    $norm = $Name -replace '/', '\'
    if ($norm -match '\\') {
        $candidate = Join-Path $benchRoot ($norm + ".py")
        if (Test-Path $candidate -PathType Leaf) { return (Resolve-Path $candidate).Path }
    }

    # Otherwise search by filename only, recursively
    $matches = Get-ChildItem -Path $benchRoot -Recurse -Filter "$Name.py" -File -ErrorAction SilentlyContinue
    if (-not $matches) {
        err "Benchmark script not found: ${Name}.py"
        log "Use '.\scripts\cli.ps1 list benchmarks' to see available scripts."
        exit 1
    }
    if ($matches.Count -gt 1) {
        err "Ambiguous script name: '$Name'. Multiple matches found:"
        $matches | ForEach-Object { Write-Host "  $($_.FullName)" }
        exit 1
    }
    return $matches[0].FullName
}


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
    # For non-workflow builds, keep forcing the venv Python
    cmake --preset $Preset -DPython3_EXECUTABLE="$PythonExe"
    cmake --build  --preset $Preset --parallel --verbose
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
    param([string]$Preset = $BuildPreset)
    section "Running All Tests"

    $oldPath = $env:PATH
    try {
        $wfPreset = Get-WorkflowPresetFor -ConfigurePresetName $Preset
        if ($wfPreset) {
            log "Using CMake workflow preset: $wfPreset"
            # Make venv Python first on PATH so FindPython3 picks it up during configure step
            $oldPathForWorkflow = $env:PATH
            $env:PATH = (Join-Path $VenvDir "Scripts") + ";" + $env:PATH
            cmake --workflow --preset $wfPreset
            $env:PATH = $oldPathForWorkflow
            ok "C++ tests (ctest) completed via workflow."
        } else {
            log "No workflow preset found for '$Preset' — falling back to build + ctest."
            cmake --preset $Preset -DPython3_EXECUTABLE="$PythonExe"
            cmake --build  --preset $Preset --parallel --verbose
            ctest --preset "${Preset.Replace('rel','tests').Replace('debug','tests')}" --output-on-failure
            ok "C++ tests (ctest) completed."
        }

        # CUDA DLLs for Python tests (safe even if staged by CMake)
        $CudaPath = if ($env:CUDA_PATH) { $env:CUDA_PATH } else { "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0" }
        if (Test-Path $CudaPath) {
            $CudaBin = Join-Path $CudaPath "bin"
            $env:PATH = "$CudaBin;$oldPath"
            log "Temporarily added $CudaBin to PATH"
        } else {
            warn "CUDA_PATH not found at '$CudaPath' (Python tests may still pass if DLLs are staged)."
        }

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
    param([string[]]$ListArgs)
    if ($ListArgs.Count -eq 0 -or $ListArgs[0] -ne "benchmarks") {
        err "Usage: list benchmarks"
        return
    }
    section "Available Benchmarks"
    $benchmarkDir = Join-Path $PythonDir "benchmarks"
    Get-ChildItem -Path $benchmarkDir -Recurse -Filter "*.py" -File |
        Where-Object { $_.Name -ne "__init__.py" } |
        ForEach-Object {
            ($_.FullName.Substring($benchmarkDir.Length + 1) -replace '\.py$','') -replace '\\','/'
        } |
        Sort-Object
}


Function cmd_bench {
    param([string[]]$BenchArgs)
    if ($BenchArgs.Count -lt 1) {
        err "Usage: bench <script_name|subpath> [args...]"
        return
    }
    $scriptName = $BenchArgs[0]
    $scriptArgs = if ($BenchArgs.Count -gt 1) { $BenchArgs[1..($BenchArgs.Length - 1)] } else { @() }

    $scriptPath = Find-BenchmarkScript -Name $scriptName

    section "Running Benchmark: $scriptName"
    & $PythonExe $scriptPath $scriptArgs
}


Function cmd_profile {
    param([string[]]$ProfileArgs)
    if ($ProfileArgs.Count -lt 2) {
        err "Usage: profile <nsys|ncu> <script_name|subpath> [args...]"
        return
    }
    $tool       = $ProfileArgs[0]
    $scriptName = $ProfileArgs[1]
    $scriptArgs = if ($ProfileArgs.Count -gt 2) { $ProfileArgs[2..($ProfileArgs.Length - 1)] } else { @() }

    $scriptPath = Find-BenchmarkScript -Name $scriptName

    $outDir  = Join-Path $BuildDir "profiles" $tool
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $outFile = Join-Path $outDir "$($scriptName -replace '[\\/]', '_')_$(Get-Date -Format 'yyyyMMdd_HHmmss')"

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
    if (Test-Path $BuildDir) {
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
  test [preset]            Use workflow (configure+build+ctest) if available, then pytest

BENCHMARKING & PROFILING
  list benchmarks          Discover and list all available benchmark scripts
  bench <name> [args...]   Run a benchmark by its name (without .py)
  profile <tool> <name>    Profile a benchmark with 'nsys' or 'ncu'

UTILITIES
  clean                    Remove all build and cache files

EXAMPLES
  .\scripts\cli.ps1 test
  .\scripts\cli.ps1 build windows-rel
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
    "build"     { if ($CommandArgs.Count -gt 0) { cmd_build   -Preset $CommandArgs[0] } else { cmd_build } }
    "rebuild"   { if ($CommandArgs.Count -gt 0) { cmd_rebuild -Preset $CommandArgs[0] } else { cmd_rebuild } }
    "test"      { if ($CommandArgs.Count -gt 0) { cmd_test    -Preset $CommandArgs[0] } else { cmd_test } }
    "clean"     { cmd_clean }
    "list"      { cmd_list    -ListArgs    $CommandArgs }
    "bench"     { cmd_bench   -BenchArgs   $CommandArgs }
    "profile"   { cmd_profile -ProfileArgs $CommandArgs }
    default     { err "Unknown command: $Command"; Show-Usage; exit 1 }
}