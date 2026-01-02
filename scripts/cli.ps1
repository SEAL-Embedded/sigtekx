#!/usr/bin/env pwsh
# ============================================================================
# sigtekx • Simplified Development CLI
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
$script:CondaEnvName = "sigtekx"

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
    if ($Coverage) { $args += "--cov=sigtekx" }
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
                    Join-Path $presetBuildDir "sigtekx_tests.exe"
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
                Join-Path $presetBuildDir "sigtekx_tests.exe"
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

    # Step 2: Run tests with coverage
    Write-Status "Running C++ tests with coverage analysis..."
    $testExe = Join-Path $script:BuildDir "windows-coverage/sigtekx_tests.exe"
    if (-not (Test-Path $testExe)) {
        Write-Error "Test executable not found at: $testExe"
        exit 1
    }

    # Step 3: Setup coverage report directories
    $reportsDir = Join-Path $script:ProjectRoot "artifacts/reports"
    $coverageDir = Join-Path $reportsDir "coverage-cpp"

    if (-not (Test-Path $reportsDir)) {
        New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
    }
    if (Test-Path $coverageDir) {
        Remove-Item $coverageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $coverageDir -Force | Out-Null

    # Detect platform and use appropriate coverage tool
    # $IsWindows is a built-in read-only variable in PowerShell Core (v6+)
    $onWindows = if ($PSVersionTable.PSVersion.Major -ge 6) { $IsWindows } else { $true }

    if ($onWindows) {
        # Windows: Use OpenCppCoverage (MSVC native)
        Write-Status "Using OpenCppCoverage for MSVC coverage analysis..."

        if (-not (Get-Command OpenCppCoverage -ErrorAction SilentlyContinue)) {
            Write-Error "OpenCppCoverage not found. Install via: choco install opencppcoverage"
            Write-Host "See: https://github.com/OpenCppCoverage/OpenCppCoverage" -ForegroundColor Yellow
            exit 1
        }

        # Build test arguments
        $testArgs = @()
        if (-not $Verbose) {
            $testArgs += "--gtest_brief=1"
        }

        # OpenCppCoverage arguments
        $coverageArgs = @(
            "--sources", "cpp\src",
            "--sources", "cpp\include",
            "--excluded_sources", "cpp\tests",
            "--excluded_sources", "*\googletest*",
            "--excluded_sources", "*\_deps\*",
            "--export_type", "html:$coverageDir",
            "--",
            $testExe
        )
        if ($testArgs.Count -gt 0) {
            $coverageArgs += $testArgs
        }

        & OpenCppCoverage @coverageArgs
        $testExitCode = $LASTEXITCODE

    } else {
        # Linux: Use gcovr (GCC/Clang coverage)
        Write-Status "Using gcovr for GCC/Clang coverage analysis..."

        # Run tests first
        $testArgs = @()
        if (-not $Verbose) {
            $testArgs += "--gtest_brief=1"
        }
        & $testExe @testArgs
        $testExitCode = $LASTEXITCODE

        # Analyze coverage with gcovr
        $srcDir = Join-Path $script:ProjectRoot "cpp"
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
    }

    # Check coverage report generation (separate from test success)
    $coverageReportExists = Test-Path "$coverageDir/index.html"

    if ($coverageReportExists) {
        Write-Success "Coverage report generated: $coverageDir/index.html"

        if ($OpenReport) {
            Write-Status "Opening coverage report in browser..."
            Start-Process "$coverageDir/index.html"
        }
    } else {
        Write-Error "Coverage report generation failed"
        Write-Host "This indicates a problem with OpenCppCoverage itself, not the tests." -ForegroundColor Yellow
    }

    # Report test results (separate from coverage generation)
    if ($testExitCode -eq 0) {
        Write-Success "All tests passed"
    } else {
        Write-Error "Tests failed with exit code: $testExitCode"
        Write-Host "Coverage report was still generated - check it to see which code paths were tested." -ForegroundColor Yellow
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
        $Paths = @("cpp/src", "cpp/tests", "cpp/include", "cpp/bindings", "examples")
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

function Invoke-TypeCheck {
    param(
        [string[]]$Paths = @(),
        [bool]$Strict = $false,
        [bool]$Verbose = $false
    )

    Write-Status "Running mypy type checking..."

    # Default paths
    if ($Paths.Count -eq 0) {
        $Paths = @("src/sigtekx")
    }

    # Verify mypy is available
    $mypy = Get-Command mypy -ErrorAction SilentlyContinue
    if (-not $mypy) {
        Write-Error "mypy not found. Install via: pip install mypy"
        exit 1
    }

    # Build arguments
    $args = @()
    if ($Verbose) { $args += "-v" }
    if ($Strict) { $args += "--strict" }

    # mypy reads configuration from pyproject.toml [tool.mypy]
    $args += $Paths

    & mypy @args

    if ($LASTEXITCODE -eq 0) {
        Write-Success "Type checking completed"
    } else {
        Write-Error "Type checking failed"
        exit 1
    }
}

function Invoke-Clean {
    param([bool]$All = $false)

    Write-Status "Cleaning artifacts..."

    # Default: clean artifacts directory only
    $artifactsDir = Join-Path $script:ProjectRoot "artifacts"
    if (Test-Path $artifactsDir) {
        Remove-Item $artifactsDir -Recurse -Force
        Write-Status "Removed artifacts directory"
    }

    # With -All: also clean build directory
    if ($All) {
        Write-Status "Cleaning build directory..."
        if (Test-Path $script:BuildDir) {
            Remove-Item $script:BuildDir -Recurse -Force
            Write-Status "Removed build directory"
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

    # Check C++ coverage tool (Windows only)
    if ($IsWindows -or ($PSVersionTable.PSVersion.Major -lt 6)) {
        $opencppcov = Get-Command OpenCppCoverage -ErrorAction SilentlyContinue
        if ($opencppcov) {
            Write-Host "  ✅ OpenCppCoverage: Available (C++ coverage)" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️  OpenCppCoverage: Not found (C++ coverage unavailable)" -ForegroundColor Yellow
            Write-Host "     Install via: choco install opencppcoverage" -ForegroundColor DarkGray
        }
    }

    # Check build
    if (Test-Path $script:BuildDir) {
        Write-Host "  ✅ Build directory: Exists" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Build directory: Not found (run build)" -ForegroundColor Yellow
    }
}

function Invoke-Dev {
    <#
    .SYNOPSIS
    Display development workflow quick reference with dynamic experiment discovery
    #>
    param(
        [bool]$Verbose = $false
    )

    # Dynamic experiment discovery
    $experimentDir = Join-Path $script:ProjectRoot "experiments/conf/experiment"
    $experiments = @()

    if (Test-Path $experimentDir) {
        $experiments = Get-ChildItem -Path $experimentDir -Filter "*.yaml" -File |
            ForEach-Object { $_.BaseName } |
            Sort-Object
    }

    # Display header
    Write-Host @"
╔════════════════════════════════════════════════════════════════════════╗
║  SIGTEKX DEVELOPMENT WORKFLOW QUICK REFERENCE                          ║
╚════════════════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

    # Python Single Experiments
    Write-Host "═══ PYTHON SINGLE EXPERIMENTS ═══" -ForegroundColor Green
    Write-Host "  python benchmarks/run_latency.py experiment=ionosphere_test +benchmark=latency" -ForegroundColor Gray -NoNewline
    Write-Host "             # Quick test" -ForegroundColor DarkCyan
    Write-Host "  python benchmarks/run_latency.py experiment=ionosphere_streaming +benchmark=latency" -ForegroundColor Gray -NoNewline
    Write-Host "      # Ionosphere VLF/ULF" -ForegroundColor DarkCyan
    Write-Host "  python benchmarks/run_throughput.py experiment=ionosphere_streaming_throughput +benchmark=throughput" -ForegroundColor Gray
    Write-Host "  python benchmarks/run_latency.py experiment=baseline_streaming_100k_latency +benchmark=latency" -ForegroundColor Gray -NoNewline
    Write-Host " # Methods Paper" -ForegroundColor DarkCyan
    Write-Host "  python benchmarks/run_accuracy.py experiment=accuracy_validation +benchmark=accuracy" -ForegroundColor Gray
    Write-Host ""

    # Python Multi-Run Experiments
    Write-Host "═══ PYTHON MULTI-RUN EXPERIMENTS ═══" -ForegroundColor Green
    Write-Host "  python benchmarks/run_latency.py --multirun experiment=full_parameter_grid_48k +benchmark=latency" -ForegroundColor Gray
    Write-Host "  python benchmarks/run_throughput.py --multirun experiment=full_parameter_grid_100k +benchmark=throughput" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Custom parameter sweeps:" -ForegroundColor DarkCyan
    Write-Host "  python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096,8192 +benchmark=latency experiment=ionosphere_streaming" -ForegroundColor Gray
    Write-Host ""

    # Snakemake Workflows
    Write-Host "═══ SNAKEMAKE WORKFLOWS ═══" -ForegroundColor Green
    Write-Host "  snakemake --cores 4 --snakefile experiments/Snakefile" -ForegroundColor Gray
    Write-Host "  snakemake --dry-run --snakefile experiments/Snakefile" -ForegroundColor DarkGray -NoNewline
    Write-Host "  # Preview" -ForegroundColor DarkCyan
    Write-Host ""

    # UI and Analysis Tools
    Write-Host "═══ ANALYSIS & VISUALIZATION ═══" -ForegroundColor Green
    Write-Host "  sigx dashboard" -ForegroundColor Gray -NoNewline
    Write-Host "                                   # Streamlit (recommended)" -ForegroundColor DarkCyan
    Write-Host "  streamlit run experiments/streamlit/app.py" -ForegroundColor DarkGray -NoNewline
    Write-Host "      # Alternative" -ForegroundColor DarkCyan
    Write-Host "  mlflow ui --backend-store-uri file://./artifacts/mlruns" -ForegroundColor Gray -NoNewline
    Write-Host "  # Experiment tracking" -ForegroundColor DarkCyan
    Write-Host ""

    # Available Experiments (Dynamic)
    Write-Host "═══ AVAILABLE EXPERIMENTS ($($experiments.Count)) ═══" -ForegroundColor Green

    if ($experiments.Count -eq 0) {
        Write-Host "  No experiments found in experiments/conf/experiment/" -ForegroundColor Red
    } else {
        # Group experiments by category
        $ionosphere = $experiments | Where-Object { $_ -like "ionosphere_*" }
        $baseline = $experiments | Where-Object { $_ -like "baseline*" -or $_ -like "profiling*" }
        $scaling = $experiments | Where-Object { $_ -like "*scaling*" -or $_ -like "*sweep*" -or $_ -like "*grid*" }
        $other = $experiments | Where-Object {
            $_ -notin $ionosphere -and $_ -notin $baseline -and $_ -notin $scaling
        }

        if ($ionosphere.Count -gt 0) {
            Write-Host "  Ionosphere Research:" -ForegroundColor Yellow
            foreach ($exp in $ionosphere) {
                Write-Host "    - $exp" -ForegroundColor Gray
            }
        }

        if ($scaling.Count -gt 0) {
            Write-Host "  Performance Scaling:" -ForegroundColor Yellow
            foreach ($exp in $scaling) {
                Write-Host "    - $exp" -ForegroundColor Gray
            }
        }

        if ($baseline.Count -gt 0) {
            Write-Host "  Baseline & Profiling:" -ForegroundColor Yellow
            foreach ($exp in $baseline) {
                Write-Host "    - $exp" -ForegroundColor Gray
            }
        }

        if ($other.Count -gt 0) {
            Write-Host "  Other:" -ForegroundColor Yellow
            foreach ($exp in $other) {
                Write-Host "    - $exp" -ForegroundColor Gray
            }
        }
    }

    Write-Host ""

    # Verbose mode - show experiment details
    if ($Verbose -and $experiments.Count -gt 0) {
        Write-Host "═══ EXPERIMENT DETAILS (--verbose) ═══" -ForegroundColor Green
        foreach ($exp in $experiments | Select-Object -First 5) {
            $yamlPath = Join-Path $experimentDir "$exp.yaml"
            $content = Get-Content $yamlPath -Raw

            Write-Host "  $exp" -ForegroundColor Cyan -NoNewline

            # Extract description if available
            if ($content -match 'description:\s*(.+)') {
                Write-Host " - $($matches[1])" -ForegroundColor DarkGray
            } else {
                Write-Host ""
            }
        }

        if ($experiments.Count -gt 5) {
            Write-Host "  ... and $($experiments.Count - 5) more (use 'sigx dev --verbose' for all)" -ForegroundColor DarkCyan
        }
        Write-Host ""
    }

    # Footer
    Write-Host "Tip: Use 'sigx help' for full CLI reference" -ForegroundColor DarkCyan
    Write-Host "     See CLAUDE.md for detailed workflow documentation" -ForegroundColor DarkCyan
    Write-Host ""
}

# ==============================================================================
# Diagram Generation Helper Functions
# ==============================================================================

function Get-DiagramLayoutConfig {
    <#
    .SYNOPSIS
    Load diagram layout configuration from JSON file
    .DESCRIPTION
    Loads layout-config.json with graceful fallback to defaults if missing or invalid
    #>
    param([string]$ConfigPath)

    if (-not (Test-Path $ConfigPath)) {
        Write-Warning "Layout config not found: $ConfigPath"
        Write-Host "  Using default layout engine: dagre" -ForegroundColor Yellow
        return @{
            default_layout = "dagre"
            layouts = @{}
            excluded_paths = @("common/")
        }
    }

    try {
        $configJson = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        return @{
            default_layout = $configJson.default_layout
            layouts = $configJson.layouts
            excluded_paths = $configJson.excluded_paths
        }
    } catch {
        Write-Error "Failed to parse layout config: $ConfigPath"
        Write-Error "  JSON error: $($_.Exception.Message)"
        exit 1
    }
}

function Test-DiagramPathExcluded {
    <#
    .SYNOPSIS
    Check if a diagram path should be excluded from rendering
    #>
    param(
        [string]$RelativePath,
        [array]$ExcludedPaths
    )

    foreach ($excluded in $ExcludedPaths) {
        $normalizedExcluded = $excluded.Replace('/', '\')
        if ($RelativePath.StartsWith($normalizedExcluded)) {
            return $true
        }
    }
    return $false
}

function Get-DiagramLayoutEngine {
    <#
    .SYNOPSIS
    Resolve layout engine for a diagram (CLI override > config > default)
    #>
    param(
        [string]$Filename,
        [hashtable]$Config,
        [string]$Override
    )

    # CLI override takes highest precedence
    if ($Override) {
        return $Override
    }

    # Lookup in config layouts mapping
    if ($Config.layouts.PSObject.Properties.Name -contains $Filename) {
        return $Config.layouts.$Filename
    }

    # Fallback to default layout
    return $Config.default_layout
}

function Show-AvailableDiagrams {
    <#
    .SYNOPSIS
    Display list of available diagrams when target not found
    #>
    param([array]$Diagrams)

    Write-Host "`nAvailable diagrams:" -ForegroundColor Yellow
    $Diagrams | Sort-Object Name | ForEach-Object {
        $displayName = $_.Name.Replace('.d2', '')
        Write-Host "  - $displayName" -ForegroundColor DarkGray
    }
    Write-Host ""
}

# ==============================================================================
# Diagram Generation Main Function
# ==============================================================================

function Invoke-Diagrams {
    param(
        [string]$Target = "all",
        [string]$Format = "svg",
        [string]$Layout = "",
        [bool]$Force = $false,
        [bool]$Verbose = $false
    )

    Write-Status "Generating architecture diagrams..."

    # Verify d2 is available
    if (-not (Get-Command d2 -ErrorAction SilentlyContinue)) {
        Write-Error "d2 not found. Install via: scoop install d2"
        Write-Host "See: https://d2lang.com/" -ForegroundColor Yellow
        exit 1
    }

    # Validate format
    if ($Format -notin @("svg", "png", "pdf")) {
        Write-Error "Invalid format: $Format. Use: svg, png, pdf"
        exit 1
    }

    # Setup paths
    $srcDir = Join-Path $script:ProjectRoot "docs\diagrams\src"
    $outDir = Join-Path $script:ProjectRoot "docs\diagrams\generated"
    $configPath = Join-Path $srcDir "common\layout-config.json"

    if (-not (Test-Path $srcDir)) {
        Write-Error "Diagram source directory not found: $srcDir"
        exit 1
    }

    # Ensure output directory exists
    if (-not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }

    # Load layout configuration
    $layoutConfig = Get-DiagramLayoutConfig -ConfigPath $configPath

    # Discover all .d2 files (excluding common/ subdirectory)
    $allDiagrams = Get-ChildItem -Path $srcDir -Filter "*.d2" -Recurse | Where-Object {
        $relativePath = $_.FullName.Substring($srcDir.Length + 1)
        -not (Test-DiagramPathExcluded -RelativePath $relativePath -ExcludedPaths $layoutConfig.excluded_paths)
    }

    if ($allDiagrams.Count -eq 0) {
        Write-Error "No diagram files found in: $srcDir"
        exit 1
    }

    # Filter diagrams by target
    $selectedDiagrams = if ($Target.ToLower() -eq "all") {
        $allDiagrams
    } else {
        # Support flexible matching:
        #   "01" -> "01*.d2"
        #   "01_system_overview" -> "01_system_overview.d2"
        #   "01_system_overview.d2" -> exact match
        $pattern = if ($Target.EndsWith(".d2")) {
            $Target
        } else {
            "${Target}*.d2"
        }

        $matches = $allDiagrams | Where-Object { $_.Name -like $pattern }

        if ($matches.Count -eq 0) {
            Write-Error "No diagrams matched target: $Target"
            Show-AvailableDiagrams -Diagrams $allDiagrams
            exit 1
        }

        $matches
    }

    if ($Verbose) {
        Write-Host "`nProcessing $($selectedDiagrams.Count) diagram(s)..." -ForegroundColor Cyan
    }

    $successCount = 0
    $skipCount = 0
    $errorCount = 0

    foreach ($diagram in $selectedDiagrams) {
        # Resolve layout engine (override > config > default)
        $layoutEngine = Get-DiagramLayoutEngine `
            -Filename $diagram.Name `
            -Config $layoutConfig `
            -Override $Layout

        $srcFile = $diagram.FullName
        $outFilename = $diagram.Name.Replace('.d2', ".$Format")
        $outFile = Join-Path $outDir $outFilename

        # Smart regeneration: check if output is newer than source
        if (-not $Force -and (Test-Path $outFile)) {
            $srcTime = (Get-Item $srcFile).LastWriteTime
            $outTime = (Get-Item $outFile).LastWriteTime
            if ($outTime -gt $srcTime) {
                if ($Verbose) {
                    Write-Host "  ✓ Skipped: $($diagram.Name) (up to date)" -ForegroundColor DarkGray
                }
                $skipCount++
                continue
            }
        }

        Write-Host "  🔨 Rendering: $($diagram.Name) with $layoutEngine → $Format..." -ForegroundColor Cyan

        # Invoke d2 (must run from source directory for import resolution)
        $previousLocation = Get-Location
        try {
            Set-Location -Path $srcDir
            $relativeSrcFile = Resolve-Path -Relative $srcFile
            $d2Args = @("--layout", $layoutEngine, $relativeSrcFile, $outFile)
            if ($Verbose) {
                & d2 @d2Args
            } else {
                & d2 @d2Args 2>&1 | Out-Null
            }
        } finally {
            Set-Location -Path $previousLocation
        }

        if ($LASTEXITCODE -eq 0) {
            Write-Host "     ✅ $outFilename" -ForegroundColor Green
            $successCount++
        } else {
            Write-Host "     ❌ Failed: $($diagram.Name)" -ForegroundColor Red
            $errorCount++
        }
    }

    Write-Host ""
    if ($Force) {
        Write-Success "Diagram generation complete: $successCount generated, $skipCount skipped, $errorCount errors"
    } else {
        Write-Success "Diagram generation complete: $successCount generated, $skipCount skipped (use --force to regenerate all), $errorCount errors"
    }

    if ($errorCount -gt 0) {
        exit 1
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
        [bool]$Interactive = $false,
        [string[]]$HydraArgs = @()
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
    # IMPORTANT: argparse with REMAINDER requires flags BEFORE positionals!
    $args = @()

    # Add flags first (before positional arguments)
    $args += "--mode", $Mode
    if ($Kernel) { $args += "--kernel", $Kernel }
    if ($Duration -gt 0) { $args += "--duration", $Duration }

    # Then add positional arguments
    $args += $Tool
    if ($Script) {
        $args += $Script
    } else {
        $args += $Target
    }

    # Add profiling config for preset benchmarks
    if ($Target -in @("latency", "throughput", "accuracy", "realtime")) {
        # Only add defaults if user didn't provide custom Hydra overrides
        if ($HydraArgs.Count -eq 0) {
            # Map targets to their lightweight profiling benchmark configs
            $benchmarkConfig = switch ($Target) {
                "latency"    { "profiling" }
                "throughput" { "profiling_throughput" }
                "realtime"   { "profiling_realtime" }
                "accuracy"   { "profiling_accuracy" }
            }
            $args += "--", "experiment=profiling", "+benchmark=$benchmarkConfig"
        } else {
            # User provided custom Hydra args - use them instead
            $args += "--"
            $args += $HydraArgs
        }
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
║  SIGTEKX DEVELOPMENT CLI                                               ║
║  Custom tooling for C++ builds, profiling, and development workflows   ║
╚════════════════════════════════════════════════════════════════════════╝

USAGE: sigx <command> [options]
   OR: .\scripts\cli.ps1 <command> [options]  (explicit path for automation)

═══════════════════════════════════════════════════════════════════════════
CORE DEVELOPMENT COMMANDS
═══════════════════════════════════════════════════════════════════════════

  setup [-Clean]          Create/update conda environment & install package
  build [-Preset <name>] [-Clean] [--debug|--release] [--verbose]
                          Configure and build C++ project with CMake
  test [all|python|cpp] [-Pattern] [-Coverage] [--verbose]
                          Run Python and/or C++ test suites
  coverage [-NoOpen]      Run C++ tests with code coverage report (OpenCppCoverage)
  clean [-All]            Remove artifacts/ (use -All to also remove build/)
  doctor                  Check development environment health

═══════════════════════════════════════════════════════════════════════════
CODE QUALITY
═══════════════════════════════════════════════════════════════════════════

  format [paths] [-Check]     Format C++ code with clang-format
  lint [all|python|cpp] [-Fix] Lint code with ruff (Python) or clang-tidy (C++)
  typecheck [-Strict]         Run mypy type checking on Python code

═══════════════════════════════════════════════════════════════════════════
DOCUMENTATION & DIAGRAMS
═══════════════════════════════════════════════════════════════════════════

  diagrams [target] [options]   Generate architecture diagrams from D2 sources

      Targets:
        all (default)           Generate all diagrams with smart regeneration
        <prefix>                Match by number/name prefix (e.g., 01, cpp_class)
        <filename>              Specific diagram (e.g., 01_system_overview.d2)

      Options:
        --format <fmt>          Output format: svg (default), png, pdf
        --layout <engine>       Override layout engine: elk, dagre, tala
        --force                 Force regenerate all (skip timestamp check)
        --verbose               Show detailed d2 output

  Examples:
    sigx diagrams                                    # All diagrams (smart regen)
    sigx diagrams --force                            # Force regenerate all
    sigx diagrams 01                                 # Match prefix: 01_system_overview
    sigx diagrams cpp_class                          # Match prefix: cpp_class_hierarchy
    sigx diagrams 02_py_structure                    # Specific diagram (no .d2 needed)
    sigx diagrams cpp_class_hierarchy.d2 --format png # Specific diagram as PNG
    sigx diagrams 02 --layout elk                    # Override to elk layout
    sigx diagrams all --format pdf --force           # All diagrams as PDF

  Direct d2 invocation (bypasses CLI, most flexible):
    d2 --layout elk docs\diagrams\src\01_system_overview.d2 ^
       docs\diagrams\generated\01_system_overview.svg

  Layout Configuration:
    Layout engines are configured in: docs\diagrams\src\common\layout-config.json
    Use --layout flag to override layout engine for testing

  Requirements:
    Install d2 via 'scoop install d2' (Windows) or see https://d2lang.com/

  See: docs\diagrams\README.md for diagram documentation and style guide

═══════════════════════════════════════════════════════════════════════════
GPU PROFILING & PERFORMANCE
═══════════════════════════════════════════════════════════════════════════

  profile [tool] [target]     Profile GPU performance with Nsight tools
      Tools:   nsys (Nsight Systems - timeline, API calls, NVTX)
               ncu (Nsight Compute - kernel analysis, roofline)
      Targets: latency, throughput, accuracy, realtime, custom

  Quick Examples (auto-uses fast profiling configs):
    sxp nsys latency                  # Nsight Systems: ~20 iterations, ~30s
    sxp nsys throughput               # Nsight Systems: ~3s duration
    sxp ncu latency                   # Nsight Compute: ~5-10min kernel analysis

  Override Parameters (profiling config auto-loaded, then overrides applied):
    sxp nsys latency engine.nfft=8192 engine.overlap=0.75
    sxp nsys latency engine.nfft=4096 benchmark.iterations=100
    sxp ncu throughput engine.mode=streaming benchmark.lock_gpu_clocks=true

  Custom Benchmark Configs (full control):
    sxp nsys latency +benchmark=latency benchmark.lock_gpu_clocks=true
    sxp nsys latency experiment=ionosphere_hires +benchmark=profiling

  Common Override Parameters:
    engine.nfft=<size>           FFT size (1024, 2048, 4096, 8192, 16384, 32768)
    engine.overlap=<ratio>       Window overlap (0.5, 0.75, 0.875, 0.9375)
    engine.mode=<mode>           Execution mode (batch, streaming)
    engine.channels=<count>      Number of channels (1, 2, 4, 8)
    benchmark.iterations=<n>     Number of iterations
    benchmark.lock_gpu_clocks=<bool>  Lock GPU clocks (true/false)
    +benchmark=<config>          Benchmark config (profiling, latency, throughput)
    experiment=<config>          Experiment config (profiling, ionosphere_*, etc.)

  How It Works:
    • No custom args:      Uses fast profiling configs automatically
    • With overrides:      Loads profiling config + applies your overrides
    • With +benchmark=:    Uses your specified config + any overrides

  See: python prof_helper.py --help  for detailed argument documentation

GPU CLOCK LOCKING (Benchmark Stability)
  Reduce coefficient of variation from 20-40% → 5-15%

  Python benchmarks (via Hydra config):
    python benchmarks/run_latency.py +benchmark=latency \\
        benchmark.lock_gpu_clocks=true

  C++ benchmarks (via sigxc):
    sigxc bench --preset latency --full --lock-clocks

  See: docs/performance/gpu-clock-locking.md for full details

═══════════════════════════════════════════════════════════════════════════
C++ DEVELOPMENT WORKFLOW (Pre-Python Integration)
═══════════════════════════════════════════════════════════════════════════

  Use 'sigxc' CLI for C++ kernel development iteration:
    sigxc bench                         # Quick validation (~10s)
    sigxc bench --preset latency --full # Production benchmark
    sigxc profile nsys --stats          # Profile C++ directly
    sigxc help                          # Full sigxc documentation

  See: CLAUDE.md "C++ Development Workflow" section

═══════════════════════════════════════════════════════════════════════════
TYPICAL WORKFLOWS
═══════════════════════════════════════════════════════════════════════════

Development Setup:
  sigx setup                  # First-time environment setup
  sigx build                  # Build C++ components
  sigx test                   # Verify everything works

Code Quality Check:
  sigx format && sigx lint    # Format and lint all code
  sigx typecheck              # Check Python types
  sigx test -Coverage         # Run tests with coverage

Research & Benchmarking:
  # Run benchmarks (native Hydra CLI)
  python benchmarks/run_throughput.py --multirun \\
      experiment=ionosphere_resolution +benchmark=throughput

  # Analysis pipeline (native Snakemake)
  snakemake --cores 4 --snakefile experiments/Snakefile

  # View results (native tools)
  mlflow ui --backend-store-uri artifacts/mlruns
  streamlit run experiments/streamlit/app.py

  # Data versioning (native DVC)
  dvc status && dvc repro

═══════════════════════════════════════════════════════════════════════════
DEVELOPMENT WORKFLOWS
═══════════════════════════════════════════════════════════════════════════

  dev [--verbose]         Display development workflow quick reference
                          - Direct commands for Python experiments (copy-paste ready)
                          - Snakemake workflow commands
                          - MLflow and Streamlit UI commands
                          - Dynamically lists available experiments

  Examples:
    sigx dev              # Show workflow quick reference
    sigx dev --verbose    # Include experiment details
    sxd                   # Shorthand version

═══════════════════════════════════════════════════════════════════════════
ADDITIONAL RESOURCES
═══════════════════════════════════════════════════════════════════════════

  CLAUDE.md                              Complete development & research guide
  docs/performance/gpu-clock-locking.md  GPU stability optimization
  docs/guides/development.md             Detailed development workflows

For C++ benchmarking: sigxc help
For Python profiling:  sxp --help
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
        "typecheck" {
            $params = @{}
            if ($normalizedArgs -contains "-strict" -or $normalizedArgs -contains "--strict") { $params.Strict = $true }
            if ($commonVerbose -or $normalizedArgs -contains "-verbose" -or $normalizedArgs -contains "--verbose") { $params.Verbose = $true }

            $paths = $CommandArgs | Where-Object { $_ -and $_ -notlike "-*" }
            if ($paths) { $params.Paths = $paths }

            Invoke-TypeCheck @params
        }
        "diagrams" {
            $params = @{}

            # Parse target (first non-flag argument)
            $target = $CommandArgs | Where-Object { $_ -and $_ -notlike "-*" -and $_ -notlike "--*" } | Select-Object -First 1
            if ($target) { $params.Target = $target }

            # Parse --format and --layout flags
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -in @("-Format", "--format") -and $i+1 -lt $CommandArgs.Count) {
                    $params.Format = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -in @("-Layout", "--layout") -and $i+1 -lt $CommandArgs.Count) {
                    $params.Layout = $CommandArgs[$i+1]
                }
            }

            # Parse --force flag
            if ($normalizedArgs -contains "-force" -or $normalizedArgs -contains "--force") {
                $params.Force = $true
            }

            # Parse --verbose flag
            if ($commonVerbose -or $normalizedArgs -contains "-verbose" -or $normalizedArgs -contains "--verbose") {
                $params.Verbose = $true
            }

            Invoke-Diagrams @params
        }
        "profile"  {
            $params = @{}

            # Pattern-based argument classification (same as sxp)
            # Separate tool args from Hydra configs by regex patterns
            $profileArgs = @()
            $hydraArgs = @()

            foreach ($arg in $CommandArgs) {
                # Hydra config patterns: key=value, +key=value, ++key=value, ~key, ~key=value
                if ($arg -match '^[\+~]{0,2}[\w\.\-/]+=' -or $arg -match '^~[\w\.\-/]+$') {
                    $hydraArgs += $arg
                }
                # Everything else is a profile argument (tool, target, flags)
                else {
                    $profileArgs += $arg
                }
            }

            # Parse tool and target from profile args
            $nonFlagArgs = $profileArgs | Where-Object { $_ -and $_ -notlike "-*" }
            if ($nonFlagArgs.Count -ge 1) { $params.Tool = $nonFlagArgs[0] }
            if ($nonFlagArgs.Count -ge 2) { $params.Target = $nonFlagArgs[1] }

            # Parse flags from profile args
            if ($profileArgs -icontains "-Full") { $params.Mode = "full" }
            if ($profileArgs -icontains "-NoOpen") { $params.OpenAfter = $false }

            for ($i = 0; $i -lt $profileArgs.Count; $i++) {
                if ($profileArgs[$i] -eq "-Mode" -and $i+1 -lt $profileArgs.Count) {
                    $params.Mode = $profileArgs[$i+1]
                }
                if ($profileArgs[$i] -eq "-Script" -and $i+1 -lt $profileArgs.Count) {
                    $params.Script = $profileArgs[$i+1]
                }
                if ($profileArgs[$i] -eq "-Kernel" -and $i+1 -lt $profileArgs.Count) {
                    $params.Kernel = $profileArgs[$i+1]
                }
                if ($profileArgs[$i] -eq "-Duration" -and $i+1 -lt $profileArgs.Count) {
                    $params.Duration = [int]$profileArgs[$i+1]
                }
            }

            # Add Hydra passthrough args if present
            if ($hydraArgs.Count -gt 0) {
                $params.HydraArgs = @() + $hydraArgs  # Force array type
            }

            Invoke-Profile @params
        }
        "dev"      {
            $params = @{}

            # Check for verbose flag
            if ($commonVerbose -or $normalizedArgs -contains "-verbose" -or $normalizedArgs -contains "--verbose") {
                $params.Verbose = $true
            }

            Invoke-Dev @params
        }
        default {
            Write-Error "Unknown command: $Command"
            Write-Host "Run '.\scripts\cli.ps1 help' for available commands"
            exit 1
        }
    }

    # Only check exit code for commands that actually set it
    # Clean command doesn't set LASTEXITCODE, so don't check it
    if ($Command -notin @("clean", "doctor", "help") -and $LASTEXITCODE -ne 0) {
        Write-Error "Command failed with exit code $LASTEXITCODE"
        exit $LASTEXITCODE
    }

} catch {
    Write-Error "Command failed: $($_.Exception.Message)"
    exit 1
}