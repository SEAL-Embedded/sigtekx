#!/usr/bin/env pwsh
# ============================================================================
# sigtekx • C++ Benchmarking & Profiling CLI
# Dedicated tool for C++ kernel development and profiling iteration
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
$script:ProfilingDir = Join-Path $ProjectRoot "artifacts\profiling"
$script:BenchmarkExe = Join-Path $BuildDir "$script:BuildPreset\benchmark_engine.exe"

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

# --- Core Functions ----------------------------------------------------------

function Invoke-Bench {
    param([string[]]$BenchArgs = @())

    if (-not (Test-Path $script:BenchmarkExe)) {
        Write-Error "C++ benchmark not found at: $script:BenchmarkExe"
        Write-Host "Run 'sigx build' to build the benchmark executable." -ForegroundColor Yellow
        exit 1
    }

    # Check for --lock-clocks flag
    $lockClocks = $false
    $gpuIndex = 0
    $useRecommended = $true
    $filteredArgs = @()

    for ($i = 0; $i -lt $BenchArgs.Length; $i++) {
        $arg = $BenchArgs[$i]

        switch ($arg) {
            "--lock-clocks" {
                $lockClocks = $true
            }
            "--gpu-index" {
                if ($i + 1 -lt $BenchArgs.Length) {
                    $gpuIndex = [int]$BenchArgs[$i + 1]
                    $i++
                }
            }
            "--max-clocks" {
                $useRecommended = $false
            }
            default {
                # Pass through to benchmark exe
                $filteredArgs += $arg
            }
        }
    }

    if ($lockClocks) {
        # GPU clock locking path
        $gpuManagerPath = Join-Path $PSScriptRoot "gpu-manager.ps1"

        if (-not (Test-Path $gpuManagerPath)) {
            Write-Error "GPU manager not found: $gpuManagerPath"
            exit 1
        }

        # Check admin privileges - elevate if needed
        $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
        $isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

        if (-not $isAdmin) {
            Write-Host ""
            Write-Host "⚠️  GPU clock locking requires administrator privileges" -ForegroundColor Yellow
            Write-Host "    UAC prompt will appear - please approve to continue" -ForegroundColor Yellow
            Write-Host ""
            Start-Sleep -Seconds 2

            # Re-launch elevated with same arguments
            $elevatedArgs = @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", $MyInvocation.PSCommandPath,
                "bench"
            )
            $elevatedArgs += $BenchArgs

            $process = Start-Process -FilePath "pwsh" -ArgumentList $elevatedArgs -Verb RunAs -Wait -PassThru
            exit $process.ExitCode
        }

        # We're admin - proceed with clock locking
        Write-Host ""
        Write-Status "Benchmarking with locked GPU clocks"
        Write-Host ""

        try {
            # Lock clocks
            & $gpuManagerPath -Action Lock -GpuIndex $gpuIndex -UseRecommended:$useRecommended
            Write-Host ""

            # Run benchmark
            Write-Status "Running C++ benchmark..."
            if ($filteredArgs.Length -gt 0) {
                & $script:BenchmarkExe @filteredArgs
            } else {
                & $script:BenchmarkExe
            }

            $benchmarkExitCode = $LASTEXITCODE

        } finally {
            # ALWAYS unlock clocks (even on error/Ctrl+C)
            Write-Host ""
            & $gpuManagerPath -Action Unlock -GpuIndex $gpuIndex
        }

        Write-Host ""
        if ($benchmarkExitCode -eq 0) {
            Write-Success "Benchmark completed successfully"
        } else {
            Write-Error "Benchmark failed with exit code $benchmarkExitCode"
            exit $benchmarkExitCode
        }

    } else {
        # Normal benchmark path (no clock locking)
        Write-Status "Running C++ benchmark..."

        if ($filteredArgs.Length -gt 0) {
            & $script:BenchmarkExe @filteredArgs
        } else {
            & $script:BenchmarkExe
        }

        if ($LASTEXITCODE -eq 0) {
            Write-Success "Benchmark completed successfully"
        } else {
            Write-Error "Benchmark failed with exit code $LASTEXITCODE"
            exit $LASTEXITCODE
        }
    }
}

function Invoke-ProfileNsys {
    param([string[]]$Args = @())

    if (-not (Test-Path $script:BenchmarkExe)) {
        Write-Error "C++ benchmark not found at: $script:BenchmarkExe"
        Write-Host "Run 'sigx build' to build the benchmark executable." -ForegroundColor Yellow
        exit 1
    }

    # Ensure profiling directory exists
    New-Item -ItemType Directory -Path $script:ProfilingDir -Force | Out-Null

    # Parse arguments
    $mode = "profile"
    $outputPath = Join-Path $script:ProfilingDir "cpp_dev"
    $nsysArgs = @()
    $stats = $false

    for ($i = 0; $i -lt $Args.Length; $i++) {
        $arg = $Args[$i]

        switch ($arg) {
            "--mode" {
                if ($i + 1 -lt $Args.Length) {
                    $mode = $Args[$i + 1]
                    $i++
                }
            }
            "--output" {
                if ($i + 1 -lt $Args.Length) {
                    $outputPath = $Args[$i + 1]
                    $i++
                }
            }
            "--stats" {
                $stats = $true
            }
            default {
                # Pass through other args to nsys
                $nsysArgs += $arg
            }
        }
    }

    Write-Status "Profiling with Nsight Systems (mode: $mode)..."

    # Build nsys command
    $nsysCommand = @("profile")
    if ($stats) {
        $nsysCommand += "--stats=true"
    }
    $nsysCommand += "--force-overwrite"
    $nsysCommand += "true"
    $nsysCommand += "-o"
    $nsysCommand += $outputPath
    $nsysCommand += $nsysArgs
    $nsysCommand += $script:BenchmarkExe
    $nsysCommand += "--$mode"
    $nsysCommand += "--safe-print"

    Write-Host "Command: nsys $($nsysCommand -join ' ')" -ForegroundColor DarkGray
    & nsys @nsysCommand

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Profiling completed: $outputPath.nsys-rep"
        Write-Host "View with: nsys-ui $outputPath.nsys-rep" -ForegroundColor Cyan
    } else {
        Write-Error "Profiling failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

function Invoke-ProfileNcu {
    param([string[]]$Args = @())

    if (-not (Test-Path $script:BenchmarkExe)) {
        Write-Error "C++ benchmark not found at: $script:BenchmarkExe"
        Write-Host "Run 'sigx build' to build the benchmark executable." -ForegroundColor Yellow
        exit 1
    }

    # Ensure profiling directory exists
    New-Item -ItemType Directory -Path $script:ProfilingDir -Force | Out-Null

    # Parse arguments
    $mode = "profile"
    $outputPath = Join-Path $script:ProfilingDir "cpp_dev_ncu"
    $metricSet = "default"
    $ncuArgs = @()

    for ($i = 0; $i -lt $Args.Length; $i++) {
        $arg = $Args[$i]

        switch ($arg) {
            "--mode" {
                if ($i + 1 -lt $Args.Length) {
                    $mode = $Args[$i + 1]
                    $i++
                }
            }
            "--output" {
                if ($i + 1 -lt $Args.Length) {
                    $outputPath = $Args[$i + 1]
                    $i++
                }
            }
            "--set" {
                if ($i + 1 -lt $Args.Length) {
                    $metricSet = $Args[$i + 1]
                    $i++
                }
            }
            default {
                # Pass through other args to ncu
                $ncuArgs += $arg
            }
        }
    }

    Write-Status "Profiling with Nsight Compute (mode: $mode, set: $metricSet)..."
    Write-Host "⚠️  This may take 5-15 minutes depending on metric set..." -ForegroundColor Yellow

    # Build ncu command
    $ncuCommand = @("--set", $metricSet, "-o", $outputPath)
    $ncuCommand += $ncuArgs
    $ncuCommand += $script:BenchmarkExe
    $ncuCommand += "--$mode"
    $ncuCommand += "--safe-print"

    Write-Host "Command: ncu $($ncuCommand -join ' ')" -ForegroundColor DarkGray
    & ncu @ncuCommand

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Profiling completed: $outputPath.ncu-rep"
        Write-Host "View with: ncu-ui $outputPath.ncu-rep" -ForegroundColor Cyan
    } else {
        Write-Error "Profiling failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

function Invoke-Compare {
    param([string[]]$Args = @())

    if ($Args.Length -lt 2) {
        Write-Error "Usage: sigxc compare <before.csv> <after.csv>"
        Write-Host "Expected CSV files with benchmark results" -ForegroundColor Yellow
        exit 1
    }

    $beforeFile = $Args[0]
    $afterFile = $Args[1]

    if (-not (Test-Path $beforeFile)) {
        Write-Error "Before file not found: $beforeFile"
        exit 1
    }

    if (-not (Test-Path $afterFile)) {
        Write-Error "After file not found: $afterFile"
        exit 1
    }

    Write-Status "Comparing benchmark results..."

    # Simple CSV comparison (assumes format from benchmark_engine.exe)
    Write-Host "📊 Benchmark Comparison" -ForegroundColor Cyan
    Write-Host "Before: $beforeFile" -ForegroundColor DarkGray
    Write-Host "After:  $afterFile" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Feature not yet implemented - manual comparison:" -ForegroundColor Yellow
    Write-Host "  diff $beforeFile $afterFile" -ForegroundColor Gray
}

function Invoke-Clean {
    Write-Status "Cleaning profiling artifacts..."

    if (Test-Path $script:ProfilingDir) {
        $files = Get-ChildItem -Path $script:ProfilingDir -Recurse
        $count = $files.Count

        if ($count -eq 0) {
            Write-Host "No profiling artifacts to clean." -ForegroundColor Gray
            return
        }

        Remove-Item -Path "$script:ProfilingDir\*" -Recurse -Force
        Write-Success "Removed $count profiling artifact(s)"
    } else {
        Write-Host "Profiling directory does not exist." -ForegroundColor Gray
    }
}

function Show-Help {
    Write-Host @"
╔════════════════════════════════════════════════════════════════════════╗
║  IONOC - C++ Benchmarking & Profiling CLI                             ║
║  Dedicated tool for C++ kernel development and profiling iteration    ║
╚════════════════════════════════════════════════════════════════════════╝

USAGE: sigxc <command> [options]

COMMANDS:
  bench [options]               Run C++ benchmark with presets
  profile nsys [options]        Profile with Nsight Systems
  profile ncu [options]         Profile with Nsight Compute
  compare <before> <after>      Compare benchmark results
  clean                         Clean profiling artifacts
  help                          Show this help

═══════════════════════════════════════════════════════════════════════════

BENCHMARK PRESETS:
  dev (default)   Quick validation (20 iter, ~10s)
  latency         Latency measurement (5000 iter, ~2min)
  throughput      Throughput measurement (10s duration)
  realtime        Real-time streaming (10s duration)
  accuracy        Accuracy validation (10 iter, 8 signals)

RUN MODES:
  --quick         Fast validation (reduced iterations/duration)
  --profile       Profile-ready (moderate iterations/duration)
  --full          Production equivalent (default)

IONOSPHERE VARIANTS:
  --iono          Standard ionosphere (48kHz, 4096/16384 NFFT, 0.75 overlap)
  --ionox         Extreme ionosphere (48kHz, 8192/32768 NFFT, 0.9/0.9375 overlap)

GPU CLOCK CONTROL:
  --lock-clocks   Lock GPU clocks for stable benchmarks (requires admin)
  --gpu-index <N> Select GPU to lock (default: 0, use with --lock-clocks)
  --max-clocks    Use max clocks instead of recommended (use with --lock-clocks)

BENCHMARK EXAMPLES:
  # Quick development validation (default)
  sigxc bench

  # Production latency benchmark
  sigxc bench --preset latency --full

  # Standard ionosphere realtime profiling
  sigxc bench --preset realtime --iono --profile

  # Extreme ionosphere throughput (missile detection)
  sigxc bench --preset throughput --ionox --full

  # Custom experimentation
  sigxc bench --preset throughput --nfft 4096 --batch 16 --quick

  # Blank canvas (override everything)
  sigxc bench --nfft 8192 --batch 32 --overlap 0.875 --iterations 100

  # GPU clock locking for stability (CV reduction)
  sigxc bench --preset latency --full --lock-clocks

  # For all options, use:
  sigxc bench --help

═══════════════════════════════════════════════════════════════════════════

NSYS PROFILING:
  sigxc profile nsys [options]

  Options:
    --mode <quick|profile|full>  Benchmark mode (default: profile)
    --output <path>              Output file path (default: artifacts\profiling\cpp_dev)
    --stats                      Generate statistics
    --trace <types>              Trace types (e.g., cuda,nvtx,osrt)
    --duration <seconds>         Time limit
    [nsys flags]                 Any other nsys flags

  Examples:
    sigxc profile nsys                              # Basic profile
    sigxc profile nsys --stats                      # With statistics
    sigxc profile nsys --trace cuda,nvtx            # Specific traces
    sigxc profile nsys --mode quick --duration 5    # Quick 5s profile

═══════════════════════════════════════════════════════════════════════════

NCU PROFILING:
  sigxc profile ncu [options]

  Options:
    --mode <quick|profile|full>  Benchmark mode (default: profile)
    --output <path>              Output file path (default: artifacts\profiling\cpp_dev_ncu)
    --set <metric-set>           Metric set (default, roofline, full)
    --kernel-name <pattern>      Filter specific kernels
    --metrics <list>             Custom metrics
    [ncu flags]                  Any other ncu flags

  Examples:
    sigxc profile ncu                                      # Basic profile
    sigxc profile ncu --set roofline                       # Roofline analysis
    sigxc profile ncu --kernel-name "fft_kernel"           # Specific kernel
    sigxc profile ncu --set full --mode profile            # Full metrics

  ⚠️  NCU profiling is slow (5-15 minutes). Use nsys first!

═══════════════════════════════════════════════════════════════════════════

TYPICAL WORKFLOW:
  1. sigxc bench                                 # Quick dev validation (~10s)
  2. sigxc bench --preset latency --profile      # Profile-ready run (~30s)
  3. sigxc profile nsys --stats                  # Profile with nsys (~1min)
  4. sigxc profile ncu --kernel-name "fft..."    # Analyze kernel (~10min)
  5. sigxc clean                                 # Clean artifacts

FOR PRODUCTION PROFILING:
  Use 'sxp nsys latency' for end-to-end Python workflow validation.
  sigxc is for C++ development iteration only.

═══════════════════════════════════════════════════════════════════════════

ARTIFACTS LOCATION:
  All profiling results are saved to: artifacts\profiling\

  - cpp_dev.nsys-rep         Nsight Systems reports
  - cpp_dev_ncu.ncu-rep      Nsight Compute reports

  Clean with: sigxc clean

═══════════════════════════════════════════════════════════════════════════
"@
}

# --- Main Execution ----------------------------------------------------------
try {
    Set-Location $script:ProjectRoot

    switch ($Command.ToLower()) {
        "bench" {
            Invoke-Bench -BenchArgs $CommandArgs
        }
        "profile" {
            if ($CommandArgs.Length -eq 0) {
                Write-Error "Usage: sigxc profile <nsys|ncu> [options]"
                Write-Host "Run 'sigxc help' for examples" -ForegroundColor Yellow
                exit 1
            }

            $tool = $CommandArgs[0].ToLower()
            $remainingArgs = if ($CommandArgs.Length -gt 1) { $CommandArgs[1..($CommandArgs.Length-1)] } else { @() }

            switch ($tool) {
                "nsys" {
                    Invoke-ProfileNsys -Args $remainingArgs
                }
                "ncu" {
                    Invoke-ProfileNcu -Args $remainingArgs
                }
                default {
                    Write-Error "Unknown profiling tool: $tool"
                    Write-Host "Use 'nsys' or 'ncu'" -ForegroundColor Yellow
                    exit 1
                }
            }
        }
        "compare" {
            Invoke-Compare -Args $CommandArgs
        }
        "clean" {
            Invoke-Clean
        }
        "help" {
            Show-Help
        }
        default {
            Write-Error "Unknown command: $Command"
            Write-Host "Run 'sigxc help' for available commands" -ForegroundColor Yellow
            exit 1
        }
    }

} catch {
    Write-Error "Command failed: $($_.Exception.Message)"
    exit 1
}
