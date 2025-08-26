# ============================================================================
# ionosense-hpc-lib • Windows CLI (Restructured)
# ============================================================================
param(
    [string]$Command,
    [string[]]$Args
)

# Configuration
$VenvDir = ".\.venv"
$BuildDir = ".\build"
$BuildPreset = if ($env:BUILD_PRESET) { $env:BUILD_PRESET } else { "windows-rel" }
$PythonExe = "$VenvDir\Scripts\python.exe"
$ErrorActionPreference = 'Stop'

# Profiler paths
$Config = @{
    NcuPath  = (Get-Command ncu.exe -ErrorAction SilentlyContinue).Source
    NsysPath = (Get-Command nsys.exe -ErrorAction SilentlyContinue).Source
}

# Functions
function Get-ModulePath {
    param([string]$Preset = $BuildPreset)
    
    $presetPath = "$BuildDir\$Preset"
    
    # Check for .pyd file
    if ((Test-Path $presetPath) -and (Get-ChildItem -Path $presetPath -Filter "*.pyd" -ErrorAction SilentlyContinue)) {
        return (Get-Item -Path $presetPath).FullName
    }
    
    throw "ERROR: Could not find compiled module in '$presetPath'. Please run a build."
}

function Get-PythonDllPath {
    $pythonBase = & $PythonExe -c "import sys; print(sys.base_prefix)"
    $pythonDll = Join-Path $pythonBase "python311.dll"
    
    if (-not (Test-Path $pythonDll)) {
        $pythonDll = Join-Path $pythonBase "DLLs\python311.dll"
    }
    
    if (Test-Path $pythonDll) {
        return (Split-Path $pythonDll -Parent)
    }
    
    Write-Warning "Could not locate python311.dll"
    return $pythonBase
}

function Verify-Build {
    param([string]$Preset = $BuildPreset)
    
    Write-Host "`n→ Verifying build artifacts..." -ForegroundColor Cyan
    $modulePath = Get-ModulePath -Preset $Preset
    $pydFile = Get-ChildItem -Path $modulePath -Filter "*.pyd" | Select-Object -First 1
    Write-Host "✓ Found module: $($pydFile.FullName)" -ForegroundColor Green
    
    $env:PYTHONPATH = $modulePath
    $testScript = "import cuda_lib; print(f'✓ Module imported successfully!')"
    & $PythonExe -c $testScript
}

function Do-Clean {
    Write-Host "`n========================= Cleaning Workspace =========================" -ForegroundColor Yellow
    if (Test-Path $BuildDir) {
        Write-Host "→ Removing directory: $BuildDir" -ForegroundColor Yellow
        Remove-Item -Path $BuildDir -Recurse -Force
    }
    
    # Clean Python cache
    Get-ChildItem -Path . -Include __pycache__,.pytest_cache -Directory -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Include *.pyc -File -Recurse -Force | Remove-Item -Force -ErrorAction SilentlyContinue
    
    Write-Host "✓ Workspace cleaned." -ForegroundColor Green
}

function Do-Setup {
    Write-Host "`n========================= Setting Up Environment =========================" -ForegroundColor Yellow
    
    if (-not (Test-Path $VenvDir)) {
        Write-Host "→ Creating Python virtual environment..."
        python -m venv $VenvDir
    }
    
    Write-Host "→ Installing Python dependencies..."
    & $PythonExe -m pip install --upgrade pip setuptools wheel
    & $PythonExe -m pip install numpy pytest pybind11 tqdm colorama
    
    Write-Host "✓ Setup complete!" -ForegroundColor Green
}

function Do-Build {
    param([string]$Preset = $BuildPreset)
    
    Write-Host "`n========================= Building Project ($Preset) =========================" -ForegroundColor Yellow
    
    if (-not (Test-Path $PythonExe)) { 
        throw "Virtual environment not found. Please run '.\scripts\cli.ps1 setup' first." 
    }
    
    $pythonAbsPath = (Get-Item $PythonExe).FullName
    
    Write-Host "→ Configuring with preset: $Preset"
    cmake --preset $Preset -DPython3_EXECUTABLE="$pythonAbsPath"
    
    Write-Host "→ Building..."
    cmake --build --preset $Preset --parallel
    
    Verify-Build -Preset $Preset
    Write-Host "✓ Build complete and verified!" -ForegroundColor Green
}

function Do-Rebuild {
    param([string]$Preset = $BuildPreset)
    
    Write-Host "`n========================= Rebuilding ($Preset) =========================" -ForegroundColor Yellow
    
    # Remove only the specific preset directory
    $presetDir = "$BuildDir\$Preset"
    if (Test-Path $presetDir) {
        Write-Host "→ Removing $presetDir"
        Remove-Item -Path $presetDir -Recurse -Force
    }
    
    Do-Build -Preset $Preset
}

function Do-Test {
    param([string]$Preset = $BuildPreset)
    
    Write-Host "`n========================= Running Tests ($Preset) =========================" -ForegroundColor Yellow
    
    # Build if needed
    $presetDir = "$BuildDir\$Preset"
    if (-not (Test-Path $presetDir)) {
        Do-Build -Preset $Preset
    }
    
    Write-Host "→ Running CTest..."
    $testPreset = $Preset -replace "windows-", "windows-tests"
    ctest --preset $testPreset --output-on-failure
    
    Write-Host "✓ Tests complete." -ForegroundColor Green
}

function Invoke-Benchmark {
    param(
        [string]$BenchmarkName,
        [string[]]$BenchmarkArgs,
        [string]$Preset = $BuildPreset,
        [string]$ProfilerExe = $null,
        [string[]]$ProfilerArgs = $null
    )
    
    $ScriptPath = ".\python\benchmarks\$BenchmarkName.py"
    if (-not (Test-Path $ScriptPath)) { 
        throw "ERROR: Benchmark script not found at '$ScriptPath'." 
    }
    
    # Set up environment
    $modulePath = Get-ModulePath -Preset $Preset
    $pythonDllPath = Get-PythonDllPath
    
    $env:PATH = "$modulePath;$pythonDllPath;$($env:PATH)"
    $env:PYTHONPATH = $modulePath
    
    Write-Host "[INFO] Module path: $modulePath" -ForegroundColor Gray
    Write-Host "[INFO] Python DLL path: $pythonDllPath" -ForegroundColor Gray
    
    $allArgs = @()
    if ($ProfilerExe) {
        $allArgs += $ProfilerArgs
        $allArgs += $PythonExe
        $allArgs += $ScriptPath
        if ($BenchmarkArgs) { $allArgs += $BenchmarkArgs }
    } else {
        $allArgs += $ScriptPath
        if ($BenchmarkArgs) { $allArgs += $BenchmarkArgs }
    }
    
    $commandToRun = if ($ProfilerExe) { $ProfilerExe } else { $PythonExe }
    Write-Host "[RUN] Executing: $commandToRun $($allArgs -join ' ')" -ForegroundColor Cyan
    
    & $commandToRun $allArgs
    
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark script failed."
    }
}

function Show-Usage {
    Write-Host @"

ionosense-hpc-lib CLI (Windows, Restructured)
Usage: .\scripts\cli.ps1 <command> [options]

Core Commands:
  clean              Remove build artifacts
  setup              Create Python venv and install dependencies  
  build [preset]     Build the project (default: $BuildPreset)
                    Presets: windows-rel, windows-debug, windows-vs
  rebuild [preset]   Clean and rebuild
  test [preset]      Run tests

Benchmarks:
  bench <name> [args...]  Run a Python benchmark
    Example: .\scripts\cli.ps1 bench fft_raw -b 32

Profiling:
  profile <tool> <name> [args...]  Profile a benchmark
    Tools: nsys, ncu
    Example: .\scripts\cli.ps1 profile nsys fft_raw

"@
}

# Main dispatcher
try {
    switch ($Command) {
        "clean"   { Do-Clean }
        "setup"   { Do-Setup }
        "build"   { Do-Build -Preset $(if ($Args[0]) { $Args[0] } else { $BuildPreset }) }
        "rebuild" { Do-Rebuild -Preset $(if ($Args[0]) { $Args[0] } else { $BuildPreset }) }
        "test"    { Do-Test -Preset $(if ($Args[0]) { $Args[0] } else { $BuildPreset }) }
        
        "bench" {
            if ($Args.Count -lt 1) { throw "ERROR: 'bench' requires a benchmark name." }
            $benchName = $Args[0]
            $benchArgs = if ($Args.Count -gt 1) { $Args[1..($Args.Count-1)] } else { @() }
            Invoke-Benchmark -BenchmarkName $benchName -BenchmarkArgs $benchArgs
        }
        
        "profile" {
            if ($Args.Count -lt 2) { throw "ERROR: 'profile' requires a tool and benchmark name." }
            $tool = $Args[0]
            $benchName = $Args[1]
            $benchArgs = if ($Args.Count -gt 2) { $Args[2..($Args.Count-1)] } else { @() }
            
            $ReportDir = "$BuildDir\nsight_reports\${tool}_reports"
            New-Item -ItemType Directory -Path $ReportDir -Force -ErrorAction SilentlyContinue | Out-Null
            
            $Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
            $ReportPath = "$ReportDir\${benchName}_${Timestamp}"
            
            $profilerExe, $profilerArgs = switch ($tool) {
                'ncu'  { 
                    $Config.NcuPath, @("--set", "full", "--target-processes", "all", "-o", $ReportPath) 
                }
                'nsys' { 
                    $Config.NsysPath, @("profile", "--trace=cuda,nvtx", "-o", "$ReportPath") 
                }
                default { throw "Unknown profiler: $tool (use nsys or ncu)" }
            }
            
            if (-not (Test-Path $profilerExe)) { 
                throw "ERROR: Profiler not found at '$profilerExe'." 
            }
            
            Write-Host "[PROFILE] Report will be saved to '$ReportPath'" -ForegroundColor Magenta
            Invoke-Benchmark -BenchmarkName $benchName -BenchmarkArgs $benchArgs `
                            -ProfilerExe $profilerExe -ProfilerArgs $profilerArgs
        }
        
        default { Show-Usage }
    }
} catch {
    Write-Host "`n✗ ERROR: $_" -ForegroundColor Red
    exit 1
}