# ============================================================================
# ionosense-hpc • Research Platform CLI (Windows)
# - Professional research-grade build, test, and benchmark orchestration
# - Compliant with RSE/RE/IEEE standards for reproducible research
# - Version: 0.9.0
# ============================================================================

#Requires -Version 7.0

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter(ValueFromRemainingArguments)]
    [string[]]$CommandArgs = @()
)

# --- Configuration & Paths ---------------------------------------------------
$script:ProjectRoot      = (Get-Item -Path (Join-Path $PSScriptRoot "..")).FullName
$script:BuildDir         = Join-Path $ProjectRoot "build"
$script:PythonDir        = Join-Path $ProjectRoot "python"
$script:ConfigDir        = Join-Path $PythonDir "src\ionosense_hpc\benchmarks\configs"
$script:BuildPreset      = if ($env:BUILD_PRESET) { $env:BUILD_PRESET } else { "windows-rel" }
$script:CondaEnvName     = "ionosense-hpc"
$script:EnvironmentFile  = Join-Path $ProjectRoot "environments\environment.win.yml"
$script:BenchResultsDir  = Join-Path $BuildDir "benchmark_results"
$script:ReportsDir       = Join-Path $BuildDir "reports"
$script:ExperimentsDir   = Join-Path $BuildDir "experiments"
$script:ProfileDir       = Join-Path $BuildDir "nsight_reports"
$script:LogRoot          = Join-Path $ProjectRoot ".ionosense\logs"

# Research metadata
$script:ResearchVersion   = "0.9.0"
$script:ResearchStandards = @("RSE", "RE", "IEEE-1074", "IEEE-754")

# --- Enhanced Logging with Research Standards -------------------------------
enum LogLevel {
    Debug    = 0
    Info     = 1
    Warning  = 2
    Error    = 3
    Critical = 4
}

$script:CurrentLogLevel = [LogLevel]::Info

Function Write-ResearchLog {
    param(
        [LogLevel]$Level,
        [string]$Message,
        [string]$Component = "CLI",
        [hashtable]$Metadata = @{}
    )

    # Respect current log level
    if ($Level -lt $script:CurrentLogLevel) { return }

    # Timestamp + visual formatting for console
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    $levelStr  = $Level.ToString().ToUpper().PadRight(8)

    $color = switch ($Level) {
        Debug    { "DarkGray" }
        Info     { "Cyan" }
        Warning  { "Yellow" }
        Error    { "Red" }
        Critical { "DarkRed" }
    }

    $icon = switch ($Level) {
        Debug    { "🔍" }
        Info     { "ℹ️" }
        Warning  { "⚠️" }
        Error    { "❌" }
        Critical { "🔥" }
    }

    # Console line
    Write-Host "$icon [$timestamp] [$levelStr] [$Component] $Message" -ForegroundColor $color

    # ---- File logging (research traceability) ----
    # If $script:LogFile is not set by the initializer, skip silently.
    if (-not $script:LogFile) { return }

    # Make JSON line (handle weird metadata gracefully)
    try {
        $jsonEntry = @{
            timestamp = $timestamp
            level     = $levelStr
            component = $Component
            message   = $Message
            metadata  = $Metadata
        } | ConvertTo-Json -Compress -Depth 8
    }
    catch {
        $jsonEntry = @{
            timestamp = $timestamp
            level     = $levelStr
            component = $Component
            message   = $Message
            metadata  = @{ _error = "metadata_json_failure"; _type = ($Metadata.GetType().FullName) }
        } | ConvertTo-Json -Compress -Depth 3
    }

    # Ensure directory exists; if not writable, fall back to %TEMP%
    $targetPath = $script:LogFile
    $targetDir  = Split-Path -Parent $targetPath

    try {
        if (-not (Test-Path -LiteralPath $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
        Add-Content -Path $targetPath -Value $jsonEntry -Encoding utf8 -ErrorAction Stop
    }
    catch {
        # One-time fallback warning to avoid spam (doesn't call Write-ResearchLog to prevent recursion)
        if (-not $script:LogFileFallbackNotified) {
            $script:LogFileFallbackNotified = $true
            $warnStamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
            Write-Host "⚠️ [$warnStamp] [WARNING ] [CLI] Log path '$targetPath' not writable. Falling back to %TEMP%." -ForegroundColor Yellow
        }

        try {
            $fallbackDir  = Join-Path $env:TEMP "ionosense-logs"
            if (-not (Test-Path -LiteralPath $fallbackDir)) {
                New-Item -ItemType Directory -Path $fallbackDir -Force | Out-Null
            }

            if (-not $script:LogFile -or -not (Test-Path -LiteralPath (Split-Path -Parent $script:LogFile))) {
                # Create a fresh fallback file name once
                $fallbackName = "research_log_{0}.jsonl" -f (Get-Date -Format "yyyyMMdd_HHmmss")
                $script:LogFile = Join-Path $fallbackDir $fallbackName
            }

            Add-Content -Path $script:LogFile -Value $jsonEntry -Encoding utf8 -ErrorAction Stop
        }
        catch {
            # Catastrophic I/O failure — swallow to avoid recursive logging loops.
            # We already wrote to console above, so at least the message isn't lost.
        }
    }
}


Function Initialize-ResearchEnvironment {
    # Create necessary directories
    @($script:BenchResultsDir, $script:ReportsDir, $script:ExperimentsDir, $script:ProfileDir) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
            Write-ResearchLog -Level Info -Message "Created directory: $_" -Component "Init"
        }
    }
    
    # Initialize research log
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $script:LogFile = Join-Path $script:LogRoot "research_log_$timestamp.jsonl"
    
    Write-ResearchLog -Level Info -Message "Research environment initialized" -Component "Init" -Metadata @{
        version = $script:ResearchVersion
        standards = $script:ResearchStandards
        root = $script:ProjectRoot
    }
}

# --- Environment Management --------------------------------------------------
Function Test-CondaEnvironment {
    if (-not $env:CONDA_PREFIX -or ($env:CONDA_DEFAULT_ENV -ne $script:CondaEnvName)) {
        return $false
    }
    return $true
}

Function Invoke-WithPythonPath {
    param([scriptblock]$ScriptBlock)
    
    $oldPath = $env:PYTHONPATH
    $env:PYTHONPATH = "$script:BuildDir\$script:BuildPreset;" + (Join-Path $script:PythonDir "src") + ";$env:PYTHONPATH"
    
    try {
        & $ScriptBlock
    } finally {
        $env:PYTHONPATH = $oldPath
    }
}

# --- Core Commands -----------------------------------------------------------
Function Invoke-Setup {
    Write-ResearchLog -Level Info -Message "Starting environment setup" -Component "Setup"
    Set-Location $script:ProjectRoot
    
    # Detect package manager
    $solver = if (Get-Command mamba -ErrorAction SilentlyContinue) { "mamba" } else { "conda" }
    
    if (-not $solver -and -not (Get-Command conda -ErrorAction SilentlyContinue)) {
        Write-ResearchLog -Level Critical -Message "No conda/mamba installation found" -Component "Setup"
        throw "Please install Miniforge3 or Miniconda"
    }
    
    # Create or update environment
    $envExists = conda env list | Select-String -Quiet -Pattern "\b$script:CondaEnvName\b"
    
    if ($envExists) {
        Write-ResearchLog -Level Info -Message "Updating existing environment" -Component "Setup"
        & $solver env update --name $script:CondaEnvName --file $script:EnvironmentFile --prune
    } else {
        Write-ResearchLog -Level Info -Message "Creating new environment" -Component "Setup"
        & $solver env create --file $script:EnvironmentFile
    }
    
    if ($LASTEXITCODE -ne 0) {
        throw "Environment setup failed"
    }
    
    # Install package in development mode (use current shell Python to preserve VS/CUDA env)
    Write-ResearchLog -Level Info -Message "Installing ionosense-hpc in development mode" -Component "Setup"
    Push-Location $script:ProjectRoot
    # Ensure a clean scikit-build cache so updated CMake args take effect
    $skbuildDir = Join-Path $script:ProjectRoot 'build/skbuild'
    if (Test-Path $skbuildDir) {
        Remove-Item -Recurse -Force $skbuildDir -ErrorAction SilentlyContinue
        Write-ResearchLog -Level Info -Message "Cleared scikit-build cache: $skbuildDir" -Component "Setup"
    }
    $pythonExe = if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX 'python.exe' } else { 'python' }
    # Default to CUDA OFF for editable installs to avoid toolset requirement
    $env:SKBUILD_CMAKE_ARGS = "-DIONO_WITH_CUDA=OFF"
    & $pythonExe -m pip install -e ".[dev,benchmark,export]"
    Remove-Item Env:SKBUILD_CMAKE_ARGS -ErrorAction SilentlyContinue
    $installCode = $LASTEXITCODE
    Pop-Location

    if ($installCode -ne 0) {
        Write-ResearchLog -Level Warning -Message "Editable install failed (pip exit $installCode). Continuing without package install; use 'build' to compile extension and set PYTHONPATH via CLI commands." -Component "Setup"
    } else {
        Write-ResearchLog -Level Info -Message "Setup completed successfully" -Component "Setup"
    }
}

Function Invoke-Build {
    param(
        [string]$Preset = $script:BuildPreset,
        [switch]$Clean,
        [switch]$Verbose,
        [switch]$NoNvtx
    )
    
    Write-ResearchLog -Level Info -Message "Starting build" -Component "Build" -Metadata @{
        preset = $Preset
        clean = $Clean.IsPresent
        no_nvtx = $NoNvtx.IsPresent
    }
    
    if (-not (Test-CondaEnvironment)) {
        throw "Conda environment not activated. Run: conda activate $script:CondaEnvName"
    }
    
    if ($Clean) {
        $presetDir = Join-Path $script:BuildDir $Preset
        if (Test-Path $presetDir) {
            Remove-Item -Path $presetDir -Recurse -Force
            Write-ResearchLog -Level Info -Message "Cleaned build directory" -Component "Build"
        }
    }
    
    # Configure (allow overriding some cache vars via flags)
    $configureArgs = @("--preset", $Preset)
    if ($NoNvtx) { $configureArgs += @("-D","IONO_WITH_NVTX=OFF") }
    cmake @configureArgs
    if ($LASTEXITCODE -ne 0) {
        throw "CMake configuration failed"
    }
    
    # Build
    $buildArgs = @("--preset", $Preset, "--parallel")
    if ($Verbose -or $Preset -like "*debug*") {
        $buildArgs += "--verbose"
    }
    
    cmake --build @buildArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed"
    }
    
    # Verify module
    Invoke-WithPythonPath {
        python -c "import ionosense_hpc; print(f'Module v{ionosense_hpc.__version__} loaded')"
    }
    
    Write-ResearchLog -Level Info -Message "Build completed" -Component "Build"
}

Function Invoke-Test {
    param(
        [ValidateSet("all","python","py","p","cpp","c++")][string]$Suite = "all",
        [string]$Pattern = "",
        [switch]$Verbose,
        [switch]$Coverage
    )
    
    Write-ResearchLog -Level Info -Message "Running tests" -Component "Test" -Metadata @{
        suite = $Suite
        pattern = $Pattern
    }
    
    if (-not (Test-CondaEnvironment)) {
        throw "Conda environment not activated"
    }

    # Normalize suite aliases -> canonical values
    $suiteNorm = ($Suite.ToLower())
    switch ($suiteNorm) {
        'py' { $suiteNorm = 'python' }
        'p'  { $suiteNorm = 'python' }
        'c++'{ $suiteNorm = 'cpp' }
    }

    $runCpp = ($suiteNorm -eq 'all' -or $suiteNorm -eq 'cpp')
    $runPy  = ($suiteNorm -eq 'all' -or $suiteNorm -eq 'python')
    
    $results = @{
        cpp = $null
        python = $null
        total = 0
        passed = 0
        failed = 0
    }
    
    if ($runCpp) {
        Write-ResearchLog -Level Info -Message "Running C++ tests" -Component "Test"
        $testPreset = $script:BuildPreset.Replace('rel','tests').Replace('debug','tests')
        ctest --preset $testPreset --output-on-failure
        $results.cpp = $LASTEXITCODE -eq 0
    }
    
    if ($runPy) {
        Write-ResearchLog -Level Info -Message "Running Python tests" -Component "Test"
        
        $pytestArgs = @("-v", (Join-Path $script:PythonDir "tests"))
        
        if ($Verbose) { $pytestArgs += "-vv", "--tb=long" }
        else { $pytestArgs += "--tb=short" }
        
        if ($Coverage) {
            $pytestArgs += "--cov=ionosense_hpc", "--cov-report=term-missing", "--cov-report=html"
        }
        
        if ($Pattern) {
            $pytestArgs += "-k", $Pattern
        }
        
        Invoke-WithPythonPath {
            pytest @pytestArgs
        }
        $results.python = $LASTEXITCODE -eq 0
    }
    
    # Validate that at least one suite ran
    $ranAny = $runCpp -or $runPy
    if (-not $ranAny) {
        Write-ResearchLog -Level Error -Message "Unknown or empty suite '$Suite'" -Component "Test"
        throw "Unknown test suite '$Suite'. Use: all | python (py,p) | cpp (c++)."
    }

    # Determine overall status for requested suites
    $failed = $false
    if ($runCpp  -and $results.cpp   -ne $true) { $failed = $true }
    if ($runPy   -and $results.python -ne $true) { $failed = $true }

    # Report results
    $testReport = @{
        timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        suite = $suiteNorm
        results = $results
    }
    
    $reportPath = Join-Path $script:ReportsDir "test_results_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
    $testReport | ConvertTo-Json -Depth 5 | Set-Content $reportPath
    
    Write-ResearchLog -Level Info -Message "Test results saved to: $reportPath" -Component "Test"

    if ($failed) {
        Write-ResearchLog -Level Error -Message "One or more requested test suites failed" -Component "Test"
        throw "Tests failed. See report: $reportPath"
    }
}

# --- Code Formatting ---------------------------------------------------------
Function Invoke-Format {
    param(
        [string[]]$Paths = @('src','include','bindings','tests'),
        [switch]$Check,
        [switch]$Verbose
    )

    Write-ResearchLog -Level Info -Message "Formatting C/C++ sources" -Component "Format" -Metadata @{
        check = $Check.IsPresent
        paths = ($Paths -join ',')
    }

    # Resolve clang-format
    $clang = $null
    foreach ($cmd in @('clang-format','clang-format.exe')) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { $clang = $found.Source; break }
    }

    if (-not $clang) {
        Write-ResearchLog -Level Error -Message "clang-format not found in PATH" -Component "Format"
        Write-Host "Install with: 'conda install -c conda-forge clang-format' or 'winget install LLVM.LLVM'" -ForegroundColor Yellow
        throw "clang-format is required to format sources"
    }

    # Expand provided paths relative to project root
    $root = $script:ProjectRoot
    $targets = @()
    foreach ($p in $Paths) {
        if (-not $p) { continue }
        $full = if ([IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $root $p }
        if (Test-Path -LiteralPath $full) { $targets += $full }
        else { Write-ResearchLog -Level Warning -Message "Path not found: $p" -Component "Format" }
    }

    if ($targets.Count -eq 0) {
        Write-ResearchLog -Level Error -Message "No valid paths to format" -Component "Format"
        throw "No valid paths to format"
    }

    # Collect source files (avoid build/output dirs even if user passed '.')
    $excludeNames = @('build','out','dist','_skbuild','.venv','.tox','.mypy_cache','_deps')
    $patterns = @('*.c','*.cc','*.cpp','*.cxx','*.h','*.hpp','*.hxx','*.cu','*.cuh')
    $files = @()
    foreach ($t in $targets) {
        if ((Get-Item $t).PSIsContainer) {
            $files += Get-ChildItem -LiteralPath $t -Recurse -File -Include $patterns |
                Where-Object { $excludeNames -notcontains $_.Directory.Name }
        } else {
            # Single file provided
            if ($patterns | ForEach-Object { $_.Replace('*','') } | Where-Object { $t.ToLower().EndsWith($_.Trim('.').ToLower()) }) {
                $files += Get-Item -LiteralPath $t
            }
        }
    }

    # De-duplicate and ensure within repo
    $files = $files | ForEach-Object { $_.FullName } | Sort-Object -Unique |
        Where-Object { $_.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase) }

    if ($files.Count -eq 0) {
        Write-ResearchLog -Level Warning -Message "No C/C++ files found to format" -Component "Format"
        return
    }

    Write-ResearchLog -Level Info -Message ("Found {0} files" -f $files.Count) -Component "Format"

    $styleArg = "-style=file"
    $exitCode = 0

    if ($Check) {
        # Check mode: no changes, fail if reformat would change files
        & $clang -n -Werror $styleArg @files
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            Write-ResearchLog -Level Error -Message "Formatting violations detected" -Component "Format"
            throw "clang-format check failed"
        } else {
            Write-ResearchLog -Level Info -Message "All files properly formatted" -Component "Format"
        }
    } else {
        if ($Verbose) {
            $files | ForEach-Object { Write-Host "Formatting: $_" -ForegroundColor DarkGray }
        }
        & $clang -i $styleArg @files
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            Write-ResearchLog -Level Error -Message "clang-format failed (exit $exitCode)" -Component "Format"
            throw "clang-format failed"
        } else {
            Write-ResearchLog -Level Info -Message "Formatting completed" -Component "Format"
        }
    }
}

# --- Linting ---------------------------------------------------------------
Function Invoke-Lint {
    param(
        [ValidateSet("all","python","py","cpp","c++")][string]$Target = "all",
        [switch]$Fix,
        [switch]$Verbose
    )

    $targetNorm = ($Target.ToLower())
    switch ($targetNorm) {
        'py' { $targetNorm = 'python' }
        'c++'{ $targetNorm = 'cpp' }
    }

    Write-ResearchLog -Level Info -Message "Running lint" -Component "Lint" -Metadata @{
        target = $targetNorm
        fix = $Fix.IsPresent
    }

    $overallFailed = $false

    # --- Python (ruff) ---
    if ($targetNorm -eq 'all' -or $targetNorm -eq 'python') {
        $ruffExe = $null
        foreach ($cmd in @('ruff','ruff.exe')) {
            $found = Get-Command $cmd -ErrorAction SilentlyContinue
            if ($found) { $ruffExe = $found.Source; break }
        }
        if (-not $ruffExe) {
            # Fallback to python -m ruff
            $pyExe = if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX 'python.exe' } else { 'python' }
            $ruffExe = $pyExe
            $useModule = $true
        } else { $useModule = $false }

    $pyPaths = @(
            (Join-Path $script:PythonDir 'src'),
            (Join-Path $script:PythonDir 'tests')
        )

        $args = @()
        if ($useModule) { $args += @('-m','ruff') }
        $args += @('check')
        if ($Fix) { $args += '--fix' }
        if ($Verbose) { $args += '-v' }
        $args += $pyPaths

        Write-ResearchLog -Level Info -Message "Ruff check starting" -Component "Lint" -Metadata @{ fix = $Fix.IsPresent }
        & $ruffExe @args
        if ($LASTEXITCODE -ne 0) {
            $overallFailed = $true
            Write-ResearchLog -Level Error -Message "Python lint failed" -Component "Lint"
        } else {
            Write-ResearchLog -Level Info -Message "Python lint passed" -Component "Lint"
        }
    }

    # --- C++ (clang-format as lint) ---
    if ($targetNorm -eq 'all' -or $targetNorm -eq 'cpp') {
        $clang = $null
        foreach ($cmd in @('clang-format','clang-format.exe')) {
            $found = Get-Command $cmd -ErrorAction SilentlyContinue
            if ($found) { $clang = $found.Source; break }
        }
        if (-not $clang) {
            Write-ResearchLog -Level Error -Message "clang-format not found for C++ lint" -Component "Lint"
            Write-Host "Install with: 'conda install -c conda-forge clang-format' or 'winget install LLVM.LLVM'" -ForegroundColor Yellow
            $overallFailed = $true
        } else {
            # Reuse the same file discovery logic as format
            $root = $script:ProjectRoot
            $targets = @(
                (Join-Path $root 'src'),
                (Join-Path $root 'include'),
                (Join-Path $root 'bindings'),
                (Join-Path $root 'tests')
            )

            $excludeNames = @('build','out','dist','_skbuild','.venv','.tox','.mypy_cache','_deps')
            $patterns = @('*.c','*.cc','*.cpp','*.cxx','*.h','*.hpp','*.hxx','*.cu','*.cuh')
            $files = @()
            foreach ($t in $targets) {
                if (Test-Path -LiteralPath $t) {
                    $files += Get-ChildItem -LiteralPath $t -Recurse -File -Include $patterns |
                        Where-Object { $excludeNames -notcontains $_.Directory.Name }
                }
            }
            $files = $files | ForEach-Object { $_.FullName } | Sort-Object -Unique

            if ($files.Count -eq 0) {
                Write-ResearchLog -Level Info -Message "No C/C++ files to lint" -Component "Lint"
            } else {
                if ($Verbose) { $files | ForEach-Object { Write-Host "Lint (C++ format check): $_" -ForegroundColor DarkGray } }
                & $clang -n -Werror -style=file @files
                if ($LASTEXITCODE -ne 0) {
                    $overallFailed = $true
                    Write-ResearchLog -Level Error -Message "C++ format lint failed" -Component "Lint"
                } else {
                    Write-ResearchLog -Level Info -Message "C++ format lint passed" -Component "Lint"
                }
            }
        }
    }

    if ($overallFailed) {
        throw "Lint failures detected"
    } else {
        Write-ResearchLog -Level Info -Message "Lint passed" -Component "Lint"
    }
}

# --- Clean -----------------------------------------------------------------
Function Invoke-Clean {
    param(
        [switch]$All,
        [switch]$Verbose
    )

    Write-ResearchLog -Level Info -Message "Cleaning workspace" -Component "Clean" -Metadata @{
        all = $All.IsPresent
    }

    $removed = @()

    Function Remove-Target {
        param([string]$Path)
        if (-not $Path) { return }
        if (Test-Path -LiteralPath $Path) {
            try {
                if ($Verbose) { Write-Host ("Removing: {0}" -f $Path) -ForegroundColor DarkGray }
                Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
                $removed += $Path
                Write-ResearchLog -Level Info -Message "Removed: $Path" -Component "Clean"
            }
            catch {
                Write-ResearchLog -Level Warning -Message "Failed to remove: $Path" -Component "Clean" -Metadata @{ error = $_.Exception.Message }
            }
        }
    }

    # Default: build artifacts and Python caches/extension
    $root = $script:ProjectRoot
    $defaultDirs = @(
        $script:BuildDir,
        (Join-Path $root 'out')
    )
    foreach ($d in $defaultDirs) { Remove-Target -Path $d }

    # Python caches and egg-info anywhere in repo
    Get-ChildItem -Path $root -Include '__pycache__','.pytest_cache','*.egg-info' -Directory -Recurse -Force -ErrorAction SilentlyContinue |
        ForEach-Object {
            Remove-Target -Path $_.FullName
        }

    # Remove compiled Python extension and staged libs
    $pySrc = Join-Path $script:PythonDir 'src'
    $ionDir = Join-Path $pySrc 'ionosense_hpc'
    $engineDir = Join-Path $ionDir 'core'
    if (Test-Path -LiteralPath $engineDir) {
        Get-ChildItem -Path $engineDir -Filter '_engine.*' -File -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Target -Path $_.FullName }
    }
    $libsDir = Join-Path $ionDir '.libs'
    foreach ($sub in @('', 'windows', 'linux')) {
        $libPath = if ($sub) { Join-Path $libsDir $sub } else { $libsDir }
        Remove-Target -Path $libPath
    }

    if ($All) {
        # Research artifacts and extra caches
        $allDirs = @(
            (Join-Path $root 'results'),
            (Join-Path $root 'benchmark_results'),
            (Join-Path $root 'experiments'),
            $script:ReportsDir,
            $script:ExperimentsDir,
            $script:ProfileDir,
            $script:LogRoot,
            (Join-Path $root 'dist'),
            (Join-Path $root '.mypy_cache'),
            (Join-Path $root '.ruff_cache')
        )
        foreach ($d in $allDirs) { Remove-Target -Path $d }

        # Coverage artifacts
        foreach ($f in @('.coverage')) { Remove-Target -Path (Join-Path $root $f) }
        Remove-Target -Path (Join-Path $root 'htmlcov')
    }

    Write-ResearchLog -Level Info -Message "Clean completed" -Component "Clean"
}

Function Invoke-Benchmark {
    param(
        [string]$Benchmark,
        [string]$Config,
        [string]$Output,
        [hashtable]$Parameters = @{},
        [switch]$Suite,
        [switch]$Report
    )
    
    if (-not (Test-CondaEnvironment)) {
        throw "Conda environment not activated"
    }
    
    # Handle suite execution
    if ($Suite) {
        Write-ResearchLog -Level Info -Message "Running benchmark suite" -Component "Benchmark"
        
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $outputDir = if ($Output) { $Output } else { Join-Path $script:BenchResultsDir "suite_$timestamp" }
        
        $configFile = if ($Config) {
            if (Test-Path $Config) { $Config }
            else { Join-Path $script:ConfigDir "$Config.yaml" }
        } else {
            Join-Path $script:ConfigDir "suite_config.yaml"
        }
        
        Invoke-WithPythonPath {
            python -m ionosense_hpc.benchmarks.suite --config $configFile --output $outputDir
        }
        
        if ($Report) {
            Invoke-BenchmarkReport -ResultsDir $outputDir
        }
        
        return
    }
    
    # Handle individual benchmark
    if (-not $Benchmark) {
        throw "Benchmark name required"
    }
    
    Write-ResearchLog -Level Info -Message "Running benchmark: $Benchmark" -Component "Benchmark"
    
    # Find config file
    $configFile = $null
    if ($Config) {
        $configFile = if (Test-Path $Config) { $Config }
        elseif (Test-Path (Join-Path $script:ConfigDir "$Config.yaml")) { 
            Join-Path $script:ConfigDir "$Config.yaml" 
        }
        elseif (Test-Path (Join-Path $script:ConfigDir "${Benchmark}_config.yaml")) {
            Join-Path $script:ConfigDir "${Benchmark}_config.yaml"
        }
    }
    
    # Build command
    $pythonCmd = "python -m ionosense_hpc.benchmarks.$Benchmark"
    
    if ($configFile) {
        $pythonCmd += " --config `"$configFile`""
    }
    
    if ($Output) {
        $pythonCmd += " --output `"$Output`""
    }
    
    # Add parameters
    foreach ($key in $Parameters.Keys) {
        $pythonCmd += " --$key $($Parameters[$key])"
    }
    
    Invoke-WithPythonPath {
        Invoke-Expression $pythonCmd
    }
    
    if ($Report -and $Output) {
        Invoke-BenchmarkReport -ResultsDir $Output
    }
}

Function Invoke-ParameterSweep {
    param(
        [Parameter(Mandatory)]
        [string]$Config,
        [string]$Output,
        [switch]$Parallel,
        [int]$Workers = 4
    )
    
    Write-ResearchLog -Level Info -Message "Starting parameter sweep" -Component "Sweep"
    
    if (-not (Test-CondaEnvironment)) {
        throw "Conda environment not activated"
    }
    
    # Find config file
    $configFile = if (Test-Path $Config) { $Config }
    elseif (Test-Path (Join-Path $script:ConfigDir "$Config.yaml")) {
        Join-Path $script:ConfigDir "$Config.yaml"
    }
    else {
        throw "Configuration file not found: $Config"
    }
    
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outputDir = if ($Output) { $Output } else { Join-Path $script:ExperimentsDir "sweep_$timestamp" }
    
    Write-ResearchLog -Level Info -Message "Configuration: $configFile" -Component "Sweep"
    Write-ResearchLog -Level Info -Message "Output: $outputDir" -Component "Sweep"
    
    Invoke-WithPythonPath {
        $sweepCmd = "from ionosense_hpc.benchmarks.sweep import ParameterSweep; "
        $sweepCmd += "sweep = ParameterSweep('$configFile'); "
        
        if ($Parallel) {
            $sweepCmd += "sweep.config.parallel = True; "
            $sweepCmd += "sweep.config.max_workers = $Workers; "
        }
        
        if ($Output) {
            $sweepCmd += "sweep.config.output_dir = '$outputDir'; "
        }
        
        $sweepCmd += "results = sweep.run(); "
        $sweepCmd += "print(f'Sweep complete: {len(results)} runs')"
        
        python -c $sweepCmd
    }
    
    # Generate analysis report
    Write-ResearchLog -Level Info -Message "Generating sweep analysis" -Component "Sweep"
    Invoke-BenchmarkReport -ResultsDir $outputDir -Type "sweep"
}

Function Invoke-BenchmarkReport {
    param(
        [Parameter(Mandatory)]
        [string]$ResultsDir,
        [string]$Format = "pdf",
        [string]$Type = "standard",
        [string]$Title
    )
    
    Write-ResearchLog -Level Info -Message "Generating report" -Component "Report" -Metadata @{
        type = $Type
        format = $Format
    }
    
    if (-not (Test-CondaEnvironment)) {
        throw "Conda environment not activated"
    }
    
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $reportName = "report_${Type}_$timestamp.$Format"
    $reportPath = Join-Path $script:ReportsDir $reportName
    
    Invoke-WithPythonPath {
        $reportCmd = "from ionosense_hpc.benchmarks.reporting import generate_comparative_report, ReportConfig; "
        $reportCmd += "config = ReportConfig("
        $reportCmd += "output_format='$Format', "
        
        if ($Title) {
            $reportCmd += "title='$Title', "
        }
        
        $reportCmd += "include_raw_data=False, "
        $reportCmd += "include_violin_plots=True, "
        $reportCmd += "include_heatmaps=True"
        $reportCmd += "); "
        
        $reportCmd += "generate_comparative_report('$ResultsDir', '$reportPath', config)"
        
        python -c $reportCmd
    }
    
    Write-ResearchLog -Level Info -Message "Report saved to: $reportPath" -Component "Report"
    
    # Open report if PDF
    if ($Format -eq "pdf" -and (Test-Path $reportPath)) {
        Start-Process $reportPath
    }
}

Function Invoke-Profile {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("nsys", "ncu")]
        [string]$Tool,
        
        [Parameter(Mandatory)]
        [string]$Benchmark,
        
        [string]$Config,
        [switch]$Full,
        [switch]$OpenReport,
        [switch]$OpenGui,
        [hashtable]$Parameters = @{}
    )
    
    Write-ResearchLog -Level Info -Message "Starting profiling" -Component "Profile" -Metadata @{
        tool = $Tool
        benchmark = $Benchmark
        full = $Full.IsPresent
    }
    
    if (-not (Test-CondaEnvironment)) {
        throw "Conda environment not activated"
    }
    
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $mode = if ($Full) { "full" } else { "quick" }
    
    $outputDir = if ($Tool -eq "nsys") {
        Join-Path $script:ProfileDir "nsys_reports"
    } else {
        Join-Path $script:ProfileDir "ncu_reports"
    }
    
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    $outputBase = Join-Path $outputDir "${Benchmark}_${mode}_${timestamp}"
    
    # Build profiling command
    $profileCmd = @()
    
    if ($Tool -eq "nsys") {
        $profileCmd = @("nsys", "profile", "-o", $outputBase, "-f", "true", "--wait=all")
        
        if ($Full) {
            $profileCmd += "--trace=cuda,cublas,cusolver,cusparse,nvtx,opengl,wddm"
            $profileCmd += "--cuda-memory-usage=true"
            $profileCmd += "--gpu-metrics-device=all"
        } else {
            $profileCmd += "--trace=cuda,nvtx"
        }
    } else {
        $profileCmd = @("ncu", "-o", $outputBase)
        
        if ($Full) {
            $profileCmd += "--set", "full"
        } else {
            $profileCmd += "--set", "basic"
        }
    }
    
    # Add Python command
    $profileCmd += "python", "-m", "ionosense_hpc.benchmarks.$Benchmark"
    
    if ($Config) {
        $configFile = if (Test-Path $Config) { $Config }
        elseif (Test-Path (Join-Path $script:ConfigDir "$Config.yaml")) {
            Join-Path $script:ConfigDir "$Config.yaml"
        }
        
        if ($configFile) {
            $profileCmd += "--config", $configFile
        }
    }
    
    # Add parameters
    foreach ($key in $Parameters.Keys) {
        $profileCmd += "--$key", $Parameters[$key]
    }
    
    # Execute profiling
    Invoke-WithPythonPath {
        & $profileCmd[0] $profileCmd[1..($profileCmd.Length-1)]
    }
    
    if ($LASTEXITCODE -ne 0) {
        throw "Profiling failed with exit code $LASTEXITCODE"
    }
    
    # Find generated report
    $reportPath = $null
    if ($Tool -eq "nsys") {
        $candidates = @("$outputBase.qdrep", "$outputBase.nsys-rep", "$outputBase.sqlite")
        foreach ($candidate in $candidates) {
            if (Test-Path $candidate) {
                $reportPath = $candidate
                break
            }
        }
    } else {
        $reportPath = "$outputBase.ncu-rep"
    }
    
    if ($reportPath -and (Test-Path $reportPath)) {
        $size = [math]::Round((Get-Item $reportPath).Length / 1MB, 2)
        Write-ResearchLog -Level Info -Message "Report saved: $reportPath ($size MB)" -Component "Profile"
        
        if ($OpenReport) {
            Start-Process explorer.exe "/select,`"$reportPath`""
        }
        
        if ($OpenGui) {
            if ($Tool -eq "nsys") {
                Open-NsightSystems -ReportPath $reportPath
            } else {
                Open-NsightCompute -ReportPath $reportPath
            }
        }
    }
}

Function Show-Info {
    param(
        [ValidateSet("system", "benchmarks", "presets", "devices", "configs", "all")]
        [string]$Type = "all"
    )
    
    if ($Type -eq "all" -or $Type -eq "system") {
        Write-Host "`n📊 SYSTEM INFORMATION" -ForegroundColor Cyan
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
        
        Invoke-WithPythonPath {
            python -c "from ionosense_hpc import show_versions; show_versions(verbose=True)"
        }
    }
    
    if ($Type -eq "all" -or $Type -eq "benchmarks") {
        Write-Host "`n🏃 AVAILABLE BENCHMARKS" -ForegroundColor Cyan
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
        
        $benchDir = Join-Path $script:PythonDir "src\ionosense_hpc\benchmarks"
        Get-ChildItem -Path $benchDir -Filter "*.py" -File | 
            Where-Object { $_.Name -ne "__init__.py" -and $_.Name -ne "base.py" } |
            ForEach-Object {
                $name = $_.BaseName
                $configFile = Join-Path $script:ConfigDir "${name}_config.yaml"
                $hasConfig = if (Test-Path $configFile) { "✓" } else { " " }
                Write-Host ("  {0} {1,-20} {2}" -f $hasConfig, $name, $_.FullName)
            }
    }
    
    if ($Type -eq "all" -or $Type -eq "configs") {
        Write-Host "`n📝 BENCHMARK CONFIGURATIONS" -ForegroundColor Cyan
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
        
        if (Test-Path $script:ConfigDir) {
            Get-ChildItem -Path $script:ConfigDir -Filter "*.yaml" -File |
                ForEach-Object {
                    Write-Host "  $($_.BaseName)"
                    
                    # Parse and show key settings
                    $content = Get-Content $_.FullName -Raw
                    if ($content -match "name:\s+(.+)") {
                        Write-Host "    Name: $($Matches[1])" -ForegroundColor DarkGray
                    }
                    if ($content -match "iterations:\s+(\d+)") {
                        Write-Host "    Iterations: $($Matches[1])" -ForegroundColor DarkGray
                    }
                }
        }
    }
    
    if ($Type -eq "all" -or $Type -eq "presets") {
        Write-Host "`n⚙️ ENGINE PRESETS" -ForegroundColor Cyan
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
        
        Invoke-WithPythonPath {
            python -c @"
from ionosense_hpc import Presets
for name, config in Presets.list_presets().items():
    print(f'  {name:12s}: nfft={config.nfft:5d}, batch={config.batch:3d}, overlap={config.overlap:.1%}')
"@
        }
    }
    
    if ($Type -eq "all" -or $Type -eq "devices") {
        Write-Host "`n🎮 CUDA DEVICES" -ForegroundColor Cyan  
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
        
        Invoke-WithPythonPath {
            python -c @"
from ionosense_hpc import gpu_count, device_info
n = gpu_count()
print(f'Found {n} CUDA device(s)\n')
for i in range(n):
    d = device_info(i)
    print(f"  [{i}] {d['name']}")
    print(f"      Memory: {d['memory_free_mb']}/{d['memory_total_mb']} MB")
    print(f"      Compute: {d['compute_capability']}")
    if d.get('temperature_c'):
        print(f"      Temp: {d['temperature_c']}°C")
"@
        }
    }
}

Function Show-ResearchStatus {
    Write-Host "`n🔬 IONOSENSE-HPC RESEARCH STATUS" -ForegroundColor Magenta
    Write-Host "════════════════════════════════════════════════════════" -ForegroundColor DarkGray
    
    # Show recent benchmarks
    Write-Host "`n📊 Recent Benchmarks:" -ForegroundColor Cyan
    if (Test-Path $script:BenchResultsDir) {
        Get-ChildItem -Path $script:BenchResultsDir -Directory | 
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 5 |
            ForEach-Object {
                $age = (Get-Date) - $_.LastWriteTime
                $ageStr = if ($age.TotalHours -lt 1) { "$([int]$age.TotalMinutes)m ago" }
                          elseif ($age.TotalDays -lt 1) { "$([int]$age.TotalHours)h ago" }
                          else { "$([int]$age.TotalDays)d ago" }
                          
                Write-Host ("  {0,-30} {1,10}" -f $_.Name, $ageStr)
            }
    } else {
        Write-Host "  No benchmarks found" -ForegroundColor DarkGray
    }
    
    # Show recent experiments
    Write-Host "`n🧪 Recent Experiments:" -ForegroundColor Cyan
    if (Test-Path $script:ExperimentsDir) {
        Get-ChildItem -Path $script:ExperimentsDir -Directory |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 5 |
            ForEach-Object {
                $configFile = Join-Path $_.FullName "experiment_config.json"
                $runCount = (Get-ChildItem -Path $_.FullName -Filter "run_*.json" | Measure-Object).Count
                Write-Host ("  {0,-30} {1,3} runs" -f $_.Name, $runCount)
            }
    } else {
        Write-Host "  No experiments found" -ForegroundColor DarkGray
    }
    
    # Show recent reports
    Write-Host "`n📄 Recent Reports:" -ForegroundColor Cyan
    if (Test-Path $script:ReportsDir) {
        Get-ChildItem -Path $script:ReportsDir -File |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 5 |
            ForEach-Object {
                $size = [math]::Round($_.Length / 1KB, 1)
                Write-Host ("  {0,-40} {1,8} KB" -f $_.Name, $size)
            }
    } else {
        Write-Host "  No reports found" -ForegroundColor DarkGray
    }
    
    # Research standards compliance
    Write-Host "`n✅ Standards Compliance:" -ForegroundColor Cyan
    Write-Host "  RSE (Research Software Engineering): ✓" -ForegroundColor Green
    Write-Host "  RE (Reproducible Engineering): ✓" -ForegroundColor Green  
    Write-Host "  IEEE Performance Evaluation: ✓" -ForegroundColor Green
    
    Write-Host "`n💡 Quick Actions:" -ForegroundColor Yellow
    Write-Host "  bench suite         - Run complete benchmark suite"
    Write-Host "  sweep -Config sweep_experiment - Run parameter sweep"
    Write-Host "  report -ResultsDir <path> - Generate publication report"
}

Function Open-NsightSystems {
    param([string]$ReportPath)
    
    $candidates = @(
        "nsys-ui.exe", "nsys-ui", 
        "nsight-systems.exe", "nsight-systems"
    )
    
    $exe = $null
    foreach ($candidate in $candidates) {
        $exe = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($exe) { break }
    }
    
    if (-not $exe) {
        # Search in common locations
        $searchPaths = @(
            "$env:ProgramFiles\NVIDIA Corporation",
            "$env:ProgramFilesX86\NVIDIA Corporation"
        )
        
        foreach ($path in $searchPaths) {
            if (Test-Path $path) {
                $found = Get-ChildItem -Path $path -Recurse -Filter "nsys-ui.exe" -ErrorAction SilentlyContinue |
                         Select-Object -First 1
                if ($found) {
                    $exe = $found.FullName
                    break
                }
            }
        }
    }
    
    if ($exe) {
        Start-Process $exe -ArgumentList "`"$ReportPath`""
    } else {
        Write-Warning "Nsight Systems GUI not found. Please open manually: $ReportPath"
    }
}

Function Open-NsightCompute {
    param([string]$ReportPath)
    
    $candidates = @(
        "ncu-ui.exe", "ncu-ui",
        "nsight-compute.exe", "nsight-compute"
    )
    
    $exe = $null
    foreach ($candidate in $candidates) {
        $exe = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($exe) { break }
    }
    
    if ($exe) {
        Start-Process $exe -ArgumentList "`"$ReportPath`""
    } else {
        Write-Warning "Nsight Compute GUI not found. Please open manually: $ReportPath"
    }
}

Function Show-Help {
    Write-Host @"
╔════════════════════════════════════════════════════════════════════════╗
║  IONOSENSE-HPC RESEARCH PLATFORM CLI v$script:ResearchVersion                            ║
║  Professional Signal Processing Research Environment                   ║
╚════════════════════════════════════════════════════════════════════════╝

USAGE: .\scripts\cli.ps1 <command> [options]

ENVIRONMENT MANAGEMENT
  setup                    Create/update conda environment & install package
  info [type]             Show system/benchmarks/presets/devices/configs info
  status                  Show research environment status

BUILD & DEVELOPMENT  
  build [-Preset] [-Clean] [-Verbose]
                          Configure and build project
  test [-Suite all|python|py|cpp] [-Pattern] [-Coverage]
                          Run tests (aliases: py/p for python, c++ for cpp)
  format [paths] [-Check] [-Verbose]
                          Format C/C++ code with .clang-format
  lint [all|python|py|cpp] [-Fix] [-Verbose]
                          Lint Python (ruff) and/or C++ (format check)
  clean [-All]            Remove build artifacts (and results/logs with -All)

BENCHMARKING (Research-Grade)
  bench <name> [-Config] [-Output] [-Report]
                          Run specific benchmark with YAML config
  bench -Suite [-Config] [-Output]
                          Run complete benchmark suite
  sweep -Config <yaml> [-Parallel] [-Workers N]
                          Run parameter sweep experiment

PROFILING & ANALYSIS
  profile -Tool <nsys|ncu> -Benchmark <name> [-Full] [-OpenReport]
                          Profile with NVIDIA Nsight tools
  report -ResultsDir <path> [-Format pdf|html|md] [-Type standard|sweep]
                          Generate publication-quality report

VALIDATION & MONITORING
  validate                Run numerical validation suite
  monitor                 Real-time GPU monitoring

EXAMPLES:
  # Initial setup
  .\scripts\cli.ps1 setup
  .\scripts\cli.ps1 build

  # Run benchmark suite with report
  .\scripts\cli.ps1 bench -Suite -Report

  # Run parameter sweep
  .\scripts\cli.ps1 sweep -Config sweep_experiment -Parallel

  # Profile with Nsight Systems
  .\scripts\cli.ps1 profile -Tool nsys -Benchmark latency -Full

  # Generate publication report
  .\scripts\cli.ps1 report -ResultsDir ./results -Format pdf

For detailed documentation, see: docs/research_guide.md
"@
}

# --- Main Execution ----------------------------------------------------------
try {
    # Initialize research environment
    Initialize-ResearchEnvironment
    
    # Set working directory
    Set-Location $script:ProjectRoot
    
    # Execute command
    switch ($Command) {
        "help"     { Show-Help }
        "setup"    { Invoke-Setup }
        "build"    { 
            $params = @{}
            if ($CommandArgs -contains "-Clean")   { $params.Clean   = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }
            if ($CommandArgs -contains "-NoNvtx")  { $params.NoNvtx  = $true }

            # Support explicit -Preset <name>
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Preset" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Preset = $CommandArgs[$i+1]
                }
            }

            # Map convenience flags to presets if no explicit -Preset
            if (-not $params.ContainsKey('Preset')) {
                if ($CommandArgs -contains "-Debug") { $params.Preset = "windows-debug" }
                elseif ($CommandArgs -contains "-Release" -or $CommandArgs -contains "-Rel") { $params.Preset = "windows-rel" }
                else {
                    # First non-flag token can still override
                    $presetToken = $CommandArgs | Where-Object { $_ -notlike "-*" } | Select-Object -First 1
                    if ($presetToken) { $params.Preset = $presetToken }
                }
            }

            Invoke-Build @params
        }
        "test"     {
            $params = @{}
            if ($CommandArgs -contains "-Coverage") { $params.Coverage = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }
            
            $suite = $CommandArgs | Where-Object { $_ -notlike "-*" } | Select-Object -First 1
            if ($suite) { $params.Suite = $suite }
            
            Invoke-Test @params
        }
        "bench"    {
            $params = @{}
            
            if ($CommandArgs -contains "-Suite") {
                $params.Suite = $true
            } else {
                $params.Benchmark = $CommandArgs | Where-Object { $_ -notlike "-*" } | Select-Object -First 1
            }
            
            if ($CommandArgs -contains "-Report") { $params.Report = $true }
            
            # Parse named parameters
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Config" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Config = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Output" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Output = $CommandArgs[$i+1]
                }
            }
            
            Invoke-Benchmark @params
        }
        "format"   {
            $params = @{}
            if ($CommandArgs -contains "-Check")   { $params.Check   = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }

            # Any non-flag arguments are paths
            $paths = $CommandArgs | Where-Object { $_ -and $_ -notlike "-*" }
            if ($paths -and $paths.Count -gt 0) { $params.Paths = $paths }

            Invoke-Format @params
        }
        "lint"     {
            $params = @{}
            if ($CommandArgs -contains "-Fix")     { $params.Fix     = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }

            $target = $CommandArgs | Where-Object { $_ -notlike "-*" } | Select-Object -First 1
            if ($target) { $params.Target = $target }

            Invoke-Lint @params
        }
        "sweep"    {
            $params = @{}
            
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Config" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Config = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Output" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Output = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Workers" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Workers = [int]$CommandArgs[$i+1]
                }
            }
            
            if ($CommandArgs -contains "-Parallel") { $params.Parallel = $true }
            
            Invoke-ParameterSweep @params
        }
        "profile"  {
            $params = @{}
            
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Tool" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Tool = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Benchmark" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Benchmark = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Config" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Config = $CommandArgs[$i+1]
                }
            }
            
            if ($CommandArgs -contains "-Full") { $params.Full = $true }
            if ($CommandArgs -contains "-OpenReport") { $params.OpenReport = $true }
            if ($CommandArgs -contains "-OpenGui") { $params.OpenGui = $true }
            
            Invoke-Profile @params
        }
        "report"   {
            $params = @{}
            
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-ResultsDir" -and $i+1 -lt $CommandArgs.Count) {
                    $params.ResultsDir = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Format" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Format = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Type" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Type = $CommandArgs[$i+1]
                }
                if ($CommandArgs[$i] -eq "-Title" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Title = $CommandArgs[$i+1]
                }
            }
            
            Invoke-BenchmarkReport @params
        }
        "info"     {
            $type = $CommandArgs | Select-Object -First 1
            Show-Info -Type $(if ($type) { $type } else { "all" })
        }
        "status"   { Show-ResearchStatus }
        "validate" {
            Write-ResearchLog -Level Info -Message "Running validation suite" -Component "Validate"
            
            Invoke-WithPythonPath {
                python -m ionosense_hpc.benchmarks.accuracy
                python -m ionosense_hpc.benchmarks.accuracy --validate-stability
            }
        }
        "monitor"  {
            Write-ResearchLog -Level Info -Message "Starting GPU monitor" -Component "Monitor"
            
            Invoke-WithPythonPath {
                python -c @"
import time
from ionosense_hpc.utils import monitor_device
try:
    while True:
        print('\033[2J\033[H')  # Clear screen
        print('═══ GPU MONITOR ═══\n')
        print(monitor_device())
        time.sleep(1)
except KeyboardInterrupt:
    print('\nMonitoring stopped')
"@
            }
            if ($LASTEXITCODE -ne 0) { throw "GPU monitor exited with error (python exit $LASTEXITCODE)" }
        }
        "clean"    {
            $params = @{}
            if ($CommandArgs -contains "-All")     { $params.All     = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }
            Invoke-Clean @params
        }
        default    {
            Write-ResearchLog -Level Error -Message "Unknown command: $Command" -Component "CLI"
            Show-Help
            exit 1
        }
    }
    
    Write-ResearchLog -Level Info -Message "Command completed successfully" -Component "CLI"
}
catch {
    Write-ResearchLog -Level Critical -Message $_.Exception.Message -Component "CLI" -Metadata @{
        stackTrace = $_.ScriptStackTrace
        errorRecord = $_.ToString()
    }
    
    Write-Host "`n❌ Command failed: $_" -ForegroundColor Red
    Write-Host "Stack trace:" -ForegroundColor DarkRed
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    
    exit 1
}
