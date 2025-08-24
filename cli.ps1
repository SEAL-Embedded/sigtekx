<#
.SYNOPSIS
    Master Command-Line Tool for the CUDA Workspace.
.DESCRIPTION
    This script is the single, robust entry point for all development tasks,
    including environment setup, building, benchmarking, and profiling.
#>

# ============================================================================
# SECTION 1: USER CONFIGURATION
# ============================================================================
$Config = @{
    NcuPath         = (Get-Command ncu.exe -ErrorAction SilentlyContinue).Source
    NsysPath        = (Get-Command nsys.exe -ErrorAction SilentlyContinue).Source
    CudaToolkitPath = $env:CUDA_PATH
}

if (-not ($Config.NcuPath -and (Test-Path $Config.NcuPath))) {
    Write-Warning "Nsight Compute (ncu.exe) was not found in your PATH. The 'profile ncu' command will fail."
}
if (-not ($Config.NsysPath -and (Test-Path $Config.NsysPath))) {
    Write-Warning "Nsight Systems (nsys.exe) was not found in your PATH. The 'profile nsys' command will fail."
}
if (-not ($Config.CudaToolkitPath -and (Test-Path $Config.CudaToolkitPath))) {
    Write-Warning "CUDA_PATH environment variable not set or invalid. CMake may fail to find the toolkit."
}

# ============================================================================
# SECTION 2: SCRIPT & PROJECT SETUP
# ============================================================================
$VenvDir = ".\.venv"
$BuildDir = ".\build"
$PythonExe = "$VenvDir\Scripts\python.exe"
$ErrorActionPreference = 'Stop'

# ============================================================================
# SECTION 3: CORE FUNCTIONS
# ============================================================================

function Get-ModulePath {
    param([string]$BuildConfiguration = 'Release')
    
    # Define potential output paths
    $multiConfigPath = "$BuildDir\$BuildConfiguration" # e.g., .\build\Release
    $singleConfigPath = $BuildDir                     # e.g., .\build

    # First, check the multi-config path (for Visual Studio)
    if ((Test-Path $multiConfigPath) -and ((Get-ChildItem -Path $multiConfigPath -Filter "*.pyd" -ErrorAction SilentlyContinue).Count -gt 0)) {
        return (Get-Item -Path $multiConfigPath).FullName
    }

    # If not found, check the single-config path (for Ninja)
    if ((Test-Path $singleConfigPath) -and ((Get-ChildItem -Path $singleConfigPath -Filter "*.pyd" -ErrorAction SilentlyContinue).Count -gt 0)) {
        return (Get-Item -Path $singleConfigPath).FullName
    }

    throw "ERROR: Could not find the compiled '.pyd' module in '$multiConfigPath' or '$singleConfigPath'. Please run a build."
}

function Get-PythonDllPath {
    # Find the base Python installation directory from the venv's python.exe
    $pythonInfo = & $PythonExe -c "import sys, os; print(os.path.dirname(sys.executable))"
    
    # For a venv, this gives us the venv's Scripts directory
    # We need to find the base Python installation
    $pythonBase = & $PythonExe -c "import sys; print(sys.base_prefix)"
    
    # The python DLL is typically in the base directory on Windows
    $pythonDll = Join-Path $pythonBase "python311.dll"
    
    if (-not (Test-Path $pythonDll)) {
        # Sometimes it might be in the DLLs subdirectory
        $pythonDll = Join-Path $pythonBase "DLLs\python311.dll"
    }
    
    if (-not (Test-Path $pythonDll)) {
        Write-Warning "Could not locate python311.dll - profiling may fail"
        return $pythonBase
    }
    
    return (Split-Path $pythonDll -Parent)
}

function Verify-Build {
    param([string]$BuildConfiguration = 'Release')
    Write-Host "`n→ Verifying build artifacts..." -ForegroundColor Cyan
    $modulePath = Get-ModulePath -BuildConfiguration $BuildConfiguration
    $pydFile = Get-ChildItem -Path $modulePath -Filter "*.pyd" | Select-Object -First 1
    Write-Host "✓ Found module: $($pydFile.FullName)" -ForegroundColor Green
    
    $env:PYTHONPATH = $modulePath
    $testScript = "import cuda_lib; print(f'✓ Module imported successfully! Version: {cuda_lib.__version__}')"
    & $PythonExe -c $testScript
}

function Do-Clean {
    Write-Host "`n========================= Cleaning Workspace ========================="
    if (Test-Path $BuildDir) {
        Write-Host "→ Removing directory: $BuildDir" -ForegroundColor Yellow
        Remove-Item -Path $BuildDir -Recurse -Force
    }
    
    # Check if the conda environment exists before trying to remove it
    if ((conda env list | Select-String -Quiet "cuda_workspace")) {
        Write-Host "→ Removing Conda environment: cuda_workspace" -ForegroundColor Yellow
        conda env remove --name cuda_workspace -y
    }
    Write-Host "`n✓ Workspace cleaned." -ForegroundColor Green
}

function Do-Setup {
    Write-Host "`n========================= Setting Up Environment ========================="
    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) { throw "ERROR: Conda is not in your PATH. Please install Miniconda." }
    
    Write-Host "→ Creating Conda environment 'cuda_workspace' from environment.yml..."
    conda env create -f environment.yml
    Write-Host "`n✓ Setup complete! To use the environment, run 'conda activate cuda_workspace'" -ForegroundColor Green
}

function Do-Build {
    param([ValidateSet('Release', 'Debug')][string]$BuildConfiguration = 'Release')
    Write-Host "`n========================= Building Project ($BuildConfiguration) ========================="
    if (-not (Test-Path $PythonExe)) { throw "Virtual environment not found. Please run './cli.ps1 setup' first." }
    
    $pythonAbsPath = (Get-Item $PythonExe).FullName
    # Add quotes around the CMAKE_BUILD_TYPE value to ensure correct expansion
    cmake -S . -B $BuildDir -G "Ninja" -DPython3_EXECUTABLE="$pythonAbsPath" -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE="$BuildConfiguration"
    
    Write-Host "→ Compiling..."
    cmake --build $BuildDir --parallel
    
    Verify-Build -BuildConfiguration $BuildConfiguration
    Write-Host "`n✓ Build complete and verified!" -ForegroundColor Green
}

function Invoke-Benchmark {
    param(
        [string]$BenchmarkName, 
        [string[]]$BenchmarkArgs, 
        [string]$BuildConfiguration = 'Release',
        [string]$ProfilerExe = $null, 
        [string[]]$ProfilerArgs = $null
    )
    
    $ScriptPath = ".\python\benchmarks\$BenchmarkName.py"
    if (-not (Test-Path $ScriptPath)) { throw "ERROR: Benchmark script not found at '$ScriptPath'." }

    # --- THE COMPREHENSIVE FIX ---
    # 1. Get the path to our build directory, which contains our .pyd module AND the copied CUDA DLLs.
    $modulePath = Get-ModulePath -BuildConfiguration $BuildConfiguration
    
    # 2. Get the Python DLL directory (critical for profilers)
    $pythonDllPath = Get-PythonDllPath
    
    # 3. Build the complete PATH with both directories
    #    This ensures Windows, Python, and the Profiler can all find their required DLLs
    $env:PATH = "$modulePath;$pythonDllPath;$($env:PATH)"
    Write-Host "[INFO] Prioritizing local build directory in PATH: '$modulePath'" -ForegroundColor Gray
    Write-Host "[INFO] Added Python DLL directory to PATH: '$pythonDllPath'" -ForegroundColor Gray

    # 4. Set PYTHONPATH to ensure Python can import our module.
    $env:PYTHONPATH = $modulePath
    Write-Host "[INFO] Setting PYTHONPATH to '$($env:PYTHONPATH)'" -ForegroundColor Gray
    
    $allArgs = @()
    if ($ProfilerExe) {
        $allArgs += $ProfilerArgs; $allArgs += $PythonExe; $allArgs += $ScriptPath
        if ($BenchmarkArgs) { $allArgs += $BenchmarkArgs }
    } else {
        $allArgs += $ScriptPath
        if ($BenchmarkArgs) { $allArgs += $BenchmarkArgs }
    }
    
    $commandToRun = if ($ProfilerExe) { $ProfilerExe } else { $PythonExe }
    $displayArgs = $allArgs | ForEach-Object { if ($_ -match "\s") { "'$_'" } else { $_ } }
    Write-Host "[RUN] Executing: $commandToRun $($displayArgs -join ' ')" -ForegroundColor Cyan
    & $commandToRun $allArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark script failed."
    } 
}

# ============================================================================
# SECTION 4: MAIN COMMAND DISPATCHER
# ============================================================================
function Show-Usage {
    Write-Host @"

Usage: ./cli.ps1 <command> [options]

Core Commands:
  clean              Deletes the build directory and Python virtual environment.
  setup              Creates the Python venv and installs dependencies.
  build [config]     Builds the C++/CUDA code (config: release|debug, default: release).
  rebuild [config]   Cleans and rebuilds the project.

Running Code:
  test [config]      Builds and runs the C++ unit tests (default: release).
  bench <name> [args...]  Runs a Python benchmark by name.
    Example: ./cli.ps1 bench fft_raw -b 32

Profiling:
  profile <tool> <name> [args...] Runs a benchmark under an Nsight profiler.
    Example: ./cli.ps1 profile nsys fft_raw
"@
}

if ($args.Count -eq 0) { Show-Usage; return }
$Command = $args[0].ToLower()

try {
    switch ($Command) {
        "clean"   { Do-Clean }
        "setup"   { Do-Setup }
        "build"   { 
            $buildConfig = if ($args.Count -gt 1) { $args[1] } else { 'Release' }
            Do-Build -BuildConfiguration $buildConfig 
        }
        "rebuild" { 
            $buildConfig = if ($args.Count -gt 1) { $args[1] } else { 'Release' }
            Do-Clean; Do-Setup; Do-Build -BuildConfiguration $buildConfig
        }
        "test"    {
            $buildConfig = if ($args.Count -gt 1) { $args[1] } else { 'Release' }
            Write-Host "`n========================= Configuring & Building Tests ($buildConfig) ========================="
            
            $pythonAbsPath = (Get-Item $PythonExe).FullName
            cmake -S . -B $BuildDir -G "Ninja" -DPython3_EXECUTABLE="$pythonAbsPath" -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE="$buildConfig"

            Write-Host "`n→ Compiling test targets..."
            cmake --build $BuildDir --parallel --target run_tests
            
            Write-Host "`n→ Executing CTest..."
            ctest --test-dir $BuildDir --build-config $buildConfig --output-on-failure
            Write-Host "`n✓ Test run complete." -ForegroundColor Green
        }
        "bench"   { 
            if ($args.Count -lt 2) { throw "ERROR: 'bench' command requires a benchmark name." }
            $benchmarkName = $args[1]
            $benchmarkArgs = if ($args.Count -gt 2) { $args[2..($args.Count-1)] } else { @() }
            Invoke-Benchmark -BenchmarkName $benchmarkName -BenchmarkArgs $benchmarkArgs
        }
        "profile" { 
            if ($args.Count -lt 3) { throw "ERROR: 'profile' command requires a tool and a benchmark name." }
            $toolName = $args[1]
            $benchmarkName = $args[2]
            $benchmarkArgs = if ($args.Count -gt 3) { $args[3..($args.Count-1)] } else { @() }
            
            $ReportDir = "$BuildDir\reports\$toolName"; New-Item -ItemType Directory -Path $ReportDir -Force -ErrorAction SilentlyContinue | Out-Null
            $Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
            $ReportPath = "$ReportDir\${benchmarkName}_${Timestamp}"
            
            $profilerExe, $profilerArgs = switch ($toolName) {
                'ncu'  { $Config.NcuPath, @("--set", "full", "--target-processes", "all", "-o", $ReportPath) }
                'nsys' { $Config.NsysPath, @("profile", "--trace=cuda,nvtx", "-o", "$ReportPath.nsys-rep") }
            }
            if (-not (Test-Path $profilerExe)) { throw "ERROR: Profiler not found at '$profilerExe'." }
            
            Write-Host "[PROFILE] Report will be saved to '$ReportPath'" -ForegroundColor Magenta
            Invoke-Benchmark -BenchmarkName $benchmarkName -BenchmarkArgs $benchmarkArgs -ProfilerExe $profilerExe -ProfilerArgs $profilerArgs
        }
        default { Write-Host "✗ ERROR: Unknown command '$Command'" -ForegroundColor Red; Show-Usage }
    }
} catch {
    Write-Host "`n✗ FATAL ERROR: $_" -ForegroundColor Red
    exit 1
}