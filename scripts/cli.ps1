# ============================================================================
# ionosense-hpc-lib • Project CLI (Windows)
# ----------------------------------------------------------------------------
# Features smart discovery for benchmarks and other scripts.
# Parallels the structure of cli.sh for a consistent cross-platform UX.
# ============================================================================

# --- Paths & Defaults --------------------------------------------------------
$ProjectRoot = (Get-Item -Path (Join-Path $PSScriptRoot "..")).FullName
$BuildDir = Join-Path $ProjectRoot "build"
$VenvDir = Join-Path $ProjectRoot ".venv"
$PythonDir = Join-Path $ProjectRoot "python"
$PythonExe = Join-Path $VenvDir "Scripts" "python.exe"
$BuildPreset = $env:BUILD_PRESET | Out-String -Default "windows-rel"

# --- Pretty logging ----------------------------------------------------------
# Text styling requires a compatible terminal (e.g., Windows Terminal)
Function log     { param($Message) Write-Host "✅ [INFO] $Message" -ForegroundColor Cyan }
Function warn    { param($Message) Write-Host "⚠️ [WARN] $Message" -ForegroundColor Yellow }
Function err     { param($Message) Write-Host "❌ [ERR ] $Message" -ForegroundColor Red }
Function ok      { param($Message) Write-Host "👍 [OK  ] $Message" -ForegroundColor Green }
Function section { param($Message) Write-Host "`n💪 == $Message ==`n" -ForegroundColor Magenta }

# Trap errors for better debugging
$ErrorActionPreference = 'Stop'

# --- Helpers -----------------------------------------------------------------
# Activates the virtual environment for the current scope
Function Activate-Venv {
    if (-not (Test-Path $PythonExe)) {
        err "Python virtual environment not found. Please run: .\scripts\cli.ps1 setup"
        throw "Venv missing."
    }
    # This is a simplified activation for script execution context
}

# Sets PYTHONPATH and executes a command
Function With-PythonPath {
    param(
        [scriptblock]$Command
    )
    $oldPath = $env:PYTHONPATH
    $modulePath = Join-Path $BuildDir $BuildPreset
    $env:PYTHONPATH = "$modulePath;$PythonDir;$oldPath"
    
    try {
        & $Command
    } finally {
        $env:PYTHONPATH = $oldPath
    }
}

# Smartly find a script by its name, searching recursively
Function Find-Script {
    param(
        [string]$Type, # e.g., "Benchmark"
        [string]$Dir,  # e.g., (Join-Path $PythonDir "benchmarks")
        [string]$Name  # e.g., "raw_throughput"
    )
    $foundFiles = Get-ChildItem -Path $Dir -Recurse -Filter "${Name}.py"
    if ($foundFiles.Count -eq 0) {
        err "$Type script not found: ${Name}.py"
        log "Use '.\scripts\cli.ps1 list benchmarks' to see available scripts."
        throw "Script not found."
    } elseif ($foundFiles.Count -gt 1) {
        err "Ambiguous script name: '$Name'. Multiple matches found:"
        $foundFiles.FullName | ForEach-Object { Write-Host $_ }
        throw "Ambiguous script."
    }
    return $foundFiles.FullName
}

# --- Core actions ------------------------------------------------------------
Function cmd_setup {
    section "Environment Setup (Python venv)"
    if (-not (Test-Path $VenvDir)) {
        log "Creating Python virtual environment..."
        python -m venv $VenvDir
    }
    log "Activating environment and installing dependencies from requirements.txt..."
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
    ok "Python environment is ready."
}

Function cmd_build {
    param([string]$Preset = $BuildPreset)
    section "Configuring & Building (preset: ${Preset})"
    cmake --preset $Preset
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
    # C++ Tests
    log "Running C++ tests..."
    ctest --preset "windows-tests" --output-on-failure
    
    # Python Tests
    if (Test-Path (Join-Path $PythonDir "tests")) {
        log "Running Python tests..."
        Activate-Venv
        With-PythonPath -Command {
            & $PythonExe -m pytest -q (Join-Path $PythonDir "tests")
        }
    }
    ok "All tests completed."
}

Function cmd_list {
    param([string[]]$Args)
    if ($Args[0] -ne "benchmarks") {
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
    $scriptArgs = $Args[1..($Args.Length - 1)]
    
    $scriptPath = Find-Script "Benchmark" (Join-Path $PythonDir "benchmarks") $scriptName
    
    section "Running Benchmark: $scriptName"
    Activate-Venv
    With-PythonPath -Command {
        & $PythonExe $scriptPath $scriptArgs
    }
}

Function cmd_profile {
    param([string[]]$Args)
    if ($Args.Count -lt 2) {
        err "Usage: profile <nsys|ncu> <script_name> [args...]"
        return
    }
    $tool = $Args[0]
    $scriptName = $Args[1]
    $scriptArgs = $Args[2..($Args.Length - 1)]

    $scriptPath = Find-Script "Benchmark" (Join-Path $PythonDir "benchmarks") $scriptName
    $outDir = Join-Path $BuildDir "profiles" $tool
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $outFile = Join-Path $outDir "$($scriptName)_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    
    section "Profiling ($tool): $scriptName"
    Activate-Venv
    
    switch ($tool) {
        "nsys" {
            With-PythonPath -Command {
                nsys profile -o "$outFile" --trace=cuda,nvtx -f true --wait=all $PythonExe "$scriptPath" $scriptArgs
            }
            ok "Nsight Systems report saved to ${outFile}.nsys-rep"
        }
        "ncu" {
             With-PythonPath -Command {
                ncu --set full --target-processes all -o "$outFile" $PythonExe "$scriptPath" $scriptArgs
            }
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
        Remove-Item -Path $BuildDir -Recurse -Force
    }
    # Clean Python cache
    Get-ChildItem -Path $ProjectRoot -Include __pycache__,.pytest_cache -Directory -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $ProjectRoot -Include *.pyc -File -Recurse -Force | Remove-Item -Force -ErrorAction SilentlyContinue
    ok "Workspace cleaned."
}


# --- Usage & Main ------------------------------------------------------------
Function Show-Usage {
    Write-Host @"
IONOSENSE-HPC • Scalable Project CLI (Windows)
Usage: ./scripts/cli.ps1 <command> [options]

CORE WORKFLOW
  setup                    Initialize Python venv and install dependencies
  build [preset]           Configure & build the project (default: $($BuildPreset))
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
  .\scripts\cli.ps1 profile nsys graphs_comparison
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
    "build"     { cmd_build -Preset ($CommandArgs[0] | Out-String -Default $BuildPreset) }
    "rebuild"   { cmd_rebuild -Preset ($CommandArgs[0] | Out-String -Default $BuildPreset) }
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