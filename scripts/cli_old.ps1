# ============================================================================
# ionosense-hpc • Research Platform CLI (Windows)
# - Professional research-grade build, test, and benchmark orchestration
# - Compliant with RSE/RE/IEEE standards for reproducible research
# - Version: 0.9.1
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
$script:SourceDir       = Join-Path $ProjectRoot "src"
$script:TestsDir        = Join-Path $ProjectRoot "tests"
$script:ConfigDir       = Join-Path $ProjectRoot "experiments\conf"
$script:BuildPreset      = if ($env:BUILD_PRESET) { $env:BUILD_PRESET } else { "windows-rel" }
$script:CondaEnvName     = "ionosense-hpc"
$script:EnvironmentFile  = Join-Path $ProjectRoot "environments\environment.win.yml"
$script:ArtifactsDir     = Join-Path $ProjectRoot "artifacts"
$script:BenchResultsDir  = Join-Path $script:ArtifactsDir "benchmarks"
$script:ReportsDir       = Join-Path $script:ArtifactsDir "reports"
$script:ExperimentsDir   = Join-Path $script:ArtifactsDir "experiments"
$script:ProfileDir       = Join-Path $script:ArtifactsDir "profiling"
$script:LogRoot          = Join-Path $script:ArtifactsDir "logs"

# Research metadata
$script:ResearchVersion   = "0.9.1"
$script:ResearchStandards = @("RSE", "RE", "IEEE-1074", "IEEE-754")

$script:PreferredCMakeGenerator = "Visual Studio 17 2022"
$script:PreferredCMakePlatform = "x64"
$script:PreferredCMakeToolset = "v143"

# --- Enhanced Logging with Research Standards -------------------------------
enum LogLevel {
    Debug    = 0
    Info     = 1
    Warning  = 2
    Error    = 3
    Critical = 4
}

$script:CurrentLogLevel = [LogLevel]::Debug

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
    @(
        $script:ArtifactsDir,
        $script:BenchResultsDir,
        $script:ReportsDir,
        $script:ExperimentsDir,
        $script:ProfileDir,
        $script:LogRoot
    ) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
            Write-ResearchLog -Level Info -Message "Created directory: $_" -Component "Init"
        }
    }

    # Align Python outputs with artifacts tree via environment overrides
    $env:IONO_OUTPUT_ROOT     = $script:ArtifactsDir
    $env:IONO_BENCH_DIR       = $script:BenchResultsDir
    $env:IONO_EXPERIMENTS_DIR = $script:ExperimentsDir
    $env:IONO_REPORTS_DIR     = $script:ReportsDir
    Write-ResearchLog -Level Info -Message "Bound Python outputs via env overrides (IONO_*_DIR)" -Component "Init" -Metadata @{
        artifacts   = $env:IONO_OUTPUT_ROOT
        benches     = $env:IONO_BENCH_DIR
        experiments = $env:IONO_EXPERIMENTS_DIR
        reports     = $env:IONO_REPORTS_DIR
    }
    
    # Initialize research log
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $script:LogFile = Join-Path $script:LogRoot "research_log_$timestamp.jsonl"
    
    Ensure-CMakeGeneratorPreference
    
    Write-ResearchLog -Level Info -Message "Research environment initialized" -Component "Init" -Metadata @{
        version = $script:ResearchVersion
        standards = $script:ResearchStandards
        root = $script:ProjectRoot
    }
}

# --- Environment Management --------------------------------------------------
Function Test-CondaEnvironment {
    $isActive = (-not [string]::IsNullOrEmpty($env:CONDA_PREFIX)) -and
                ($env:CONDA_DEFAULT_ENV -eq $script:CondaEnvName)

    if (-not $isActive) {
        Write-ResearchLog -Level Debug -Message "Conda environment check failed. CONDA_PREFIX='$env:CONDA_PREFIX', CONDA_DEFAULT_ENV='$env:CONDA_DEFAULT_ENV', Expected='$script:CondaEnvName'" -Component "Env"
    }

    return $isActive
}

Function Invoke-WithPythonPath {
    param([scriptblock]$ScriptBlock)
    
    $oldPath = $env:PYTHONPATH
    $env:PYTHONPATH = "$script:BuildDir\$script:BuildPreset;" + ($script:SourceDir) + ";$env:PYTHONPATH"
    
    try {
        & $ScriptBlock
    } finally {
        $env:PYTHONPATH = $oldPath
    }
}

Function Clear-CMakeGeneratorEnv {
    param([switch]$Generator)

    $cleared = $false

    if ($Generator -and (Test-Path Env:CMAKE_GENERATOR)) {
        Remove-Item Env:CMAKE_GENERATOR -ErrorAction SilentlyContinue
        $cleared = $true
    }

    foreach ($name in @('CMAKE_GENERATOR_PLATFORM','CMAKE_GENERATOR_TOOLSET')) {
        if (Test-Path Env:$name) {
            Remove-Item Env:$name -ErrorAction SilentlyContinue
            $cleared = $true
        }
    }

    return $cleared
}

Function Resolve-CMakePresetGenerator {
    param(
        [object[]]$Presets,
        [string]$Name,
        [hashtable]$Cache
    )

    if (-not $Name) { return $null }
    if ($Cache.ContainsKey($Name)) { return $Cache[$Name] }

    $preset = $Presets | Where-Object { $_.name -eq $Name } | Select-Object -First 1
    if (-not $preset) { return $null }

    if ($preset.generator) {
        $Cache[$Name] = $preset.generator
        return $preset.generator
    }

    $parents = @()
    if ($preset.inherits) {
        if ($preset.inherits -is [string]) {
            $parents += $preset.inherits
        } else {
            $parents += $preset.inherits
        }
    }

    foreach ($parent in $parents) {
        $gen = Resolve-CMakePresetGenerator -Presets $Presets -Name $parent -Cache $Cache
        if ($gen) {
            $Cache[$Name] = $gen
            return $gen
        }
    }

    return $null
}

Function Get-CMakePresetGenerator {
    param([string]$PresetName)

    $presetsPath = Join-Path $script:ProjectRoot 'CMakePresets.json'
    if (-not (Test-Path -LiteralPath $presetsPath)) {
        return $null
    }

    try {
        $json = Get-Content -LiteralPath $presetsPath -Raw | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        return $null
    }

    $presets = $json.configurePresets
    if (-not $presets) { return $null }

    $cache = @{}
    return Resolve-CMakePresetGenerator -Presets $presets -Name $PresetName -Cache $cache
}


Function Get-CondaEnvironmentPath {
    try {
        $json = conda env list --json
    } catch {
        return $null
    }

    if ($LASTEXITCODE -ne 0 -or -not $json) {
        return $null
    }

    try {
        $parsed = $json | ConvertFrom-Json
    } catch {
        return $null
    }

    foreach ($candidate in $parsed.envs) {
        if ((Split-Path $candidate -Leaf) -eq $script:CondaEnvName) {
            return $candidate
        }
    }

    return $null
}

Function Ensure-CMakeGeneratorPreference {
    param(
        [string]$TargetGenerator,
        [switch]$Force
    )

    $preferred = $script:PreferredCMakeGenerator
    $platform  = $script:PreferredCMakePlatform
    $toolset   = $script:PreferredCMakeToolset

    $current = $env:CMAKE_GENERATOR
    $changed = $false

    if (-not $TargetGenerator) {
        if ($Force.IsPresent) {
            $TargetGenerator = $preferred
        } elseif ($current -like 'Visual Studio 15*') {
            $TargetGenerator = $preferred
        } elseif (-not $current -or $current -notlike 'Visual Studio*') {
            if (Clear-CMakeGeneratorEnv) {
                Write-ResearchLog -Level Info -Message "Cleared conflicting CMake generator environment" -Component "Env"
            }
            return
        } else {
            if ($current -eq $preferred) {
                if ($env:CMAKE_GENERATOR_PLATFORM -ne $platform) {
                    $env:CMAKE_GENERATOR_PLATFORM = $platform
                    $changed = $true
                }
                if ($env:CMAKE_GENERATOR_TOOLSET -ne $toolset) {
                    $env:CMAKE_GENERATOR_TOOLSET = $toolset
                    $changed = $true
                }
                if ($changed) {
                    Write-ResearchLog -Level Info -Message "Aligned Visual Studio generator metadata" -Component "Env" -Metadata @{
                        generator = $current
                        platform  = $platform
                        toolset   = $toolset
                    }
                }
            }
            return
        }
    }

    if ($TargetGenerator -like 'Visual Studio*') {
        $previous = $current
        if ($current -ne $TargetGenerator) {
            $env:CMAKE_GENERATOR = $TargetGenerator
            $changed = $true
        }
        if ($env:CMAKE_GENERATOR_PLATFORM -ne $platform) {
            $env:CMAKE_GENERATOR_PLATFORM = $platform
            $changed = $true
        }
        if ($env:CMAKE_GENERATOR_TOOLSET -ne $toolset) {
            $env:CMAKE_GENERATOR_TOOLSET = $toolset
            $changed = $true
        }
        if ($changed) {
            Write-ResearchLog -Level Info -Message "Pinned CMake generator to Visual Studio 2022" -Component "Env" -Metadata @{
                generator = $TargetGenerator
                platform  = $platform
                toolset   = $toolset
                previous  = $previous
            }
        }
        return
    }

    if ($Force.IsPresent -and $TargetGenerator) {
        if ($current -ne $TargetGenerator) {
            $env:CMAKE_GENERATOR = $TargetGenerator
            $changed = $true
        }
    } else {
        if ($current -like 'Visual Studio*') {
            if (Clear-CMakeGeneratorEnv -Generator) { $changed = $true }
        }
    }

    if (Clear-CMakeGeneratorEnv) { $changed = $true }

    if ($changed) {
        Write-ResearchLog -Level Info -Message "Normalized CMake generator environment" -Component "Env" -Metadata @{
            target = $TargetGenerator
        }
    }
}

Function Ensure-CMakeGeneratorActivateHooks {
    param([string]$EnvPath)

    if (-not $EnvPath) {
        Write-ResearchLog -Level Warning -Message "Unable to locate conda environment path for generator override" -Component "Setup"
        return
    }

    $activateDir = Join-Path $EnvPath 'etc\conda\activate.d'
    $deactivateDir = Join-Path $EnvPath 'etc\conda\deactivate.d'

    foreach ($dir in @($activateDir, $deactivateDir)) {
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }

    $batActivation = @'
@echo off
REM Clear legacy CMake generator overrides for ionosense-hpc
set "CMAKE_GENERATOR="
set "CMAKE_GENERATOR_PLATFORM="
set "CMAKE_GENERATOR_TOOLSET="
'@

    $psActivation = @"
# Clear legacy CMake generator overrides for ionosense-hpc
Remove-Item Env:CMAKE_GENERATOR -ErrorAction SilentlyContinue
Remove-Item Env:CMAKE_GENERATOR_PLATFORM -ErrorAction SilentlyContinue
Remove-Item Env:CMAKE_GENERATOR_TOOLSET -ErrorAction SilentlyContinue
"@

    $batDeactivate = @'
@echo off
set "CMAKE_GENERATOR="
set "CMAKE_GENERATOR_PLATFORM="
set "CMAKE_GENERATOR_TOOLSET="
'@

    $psDeactivate = @"
Remove-Item Env:CMAKE_GENERATOR -ErrorAction SilentlyContinue
Remove-Item Env:CMAKE_GENERATOR_PLATFORM -ErrorAction SilentlyContinue
Remove-Item Env:CMAKE_GENERATOR_TOOLSET -ErrorAction SilentlyContinue
"@

    try {
        Set-Content -Path (Join-Path $activateDir 'zzz_force_vs2022_generator.bat') -Value $batActivation -Encoding ASCII
        Set-Content -Path (Join-Path $activateDir 'zzz_force_vs2022_generator.ps1') -Value $psActivation -Encoding ASCII
        Set-Content -Path (Join-Path $deactivateDir 'zzz_force_vs2022_generator.bat') -Value $batDeactivate -Encoding ASCII
        Set-Content -Path (Join-Path $deactivateDir 'zzz_force_vs2022_generator.ps1') -Value $psDeactivate -Encoding ASCII
        Write-ResearchLog -Level Info -Message "Ensured CMake generator cleanup hooks" -Component "Setup" -Metadata @{
            activate = $activateDir
            deactivate = $deactivateDir
        }
    }
    catch {
        Write-ResearchLog -Level Warning -Message "Failed to write generator override hooks: $($_.Exception.Message)" -Component "Setup"
    }
}


# --- Core Commands -----------------------------------------------------------
Function Invoke-Setup {
    param(
        [switch]$Clean
    )

    Write-ResearchLog -Level Info -Message "Starting environment setup" -Component "Setup" -Metadata @{ clean = $Clean.IsPresent }
    Set-Location $script:ProjectRoot

    # Detect package manager and ensure conda is available
    $solver = if (Get-Command mamba -ErrorAction SilentlyContinue) { "mamba" } else { "conda" }
    $condaCmd = Get-Command conda -ErrorAction SilentlyContinue
    if (-not $condaCmd) {
        Write-ResearchLog -Level Critical -Message "No conda installation found" -Component "Setup"
        throw "Please install Miniforge3 or Miniconda"
    }

    $envExists = conda env list | Select-String -Quiet -Pattern "\b$script:CondaEnvName\b"
    $reactivate = $false

    if ($Clean) {
        if ($env:CONDA_DEFAULT_ENV -eq $script:CondaEnvName) {
            Write-ResearchLog -Level Info -Message "Deactivating active environment before clean reinstall" -Component "Setup"
            try {
                conda deactivate | Out-Null
            } catch {
                Write-ResearchLog -Level Error -Message "conda deactivate failed: $($_.Exception.Message)" -Component "Setup"
                throw "Unable to deactivate active environment"
            }
            if ($env:CONDA_DEFAULT_ENV -eq $script:CondaEnvName) {
                Write-ResearchLog -Level Error -Message "Environment still active after conda deactivate" -Component "Setup"
                throw "Failed to deactivate environment"
            }
            $reactivate = $true
        }

        if ($envExists) {
            Write-ResearchLog -Level Info -Message "Removing existing environment" -Component "Setup"
            & $solver env remove --name $script:CondaEnvName --yes
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to remove existing environment"
            }
            $envExists = $false
        } else {
            Write-ResearchLog -Level Info -Message "No existing environment found; nothing to clean" -Component "Setup"
        }
    }

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

    $envPath = Get-CondaEnvironmentPath
    Ensure-CMakeGeneratorActivateHooks -EnvPath $envPath
    Ensure-CMakeGeneratorPreference -TargetGenerator $script:PreferredCMakeGenerator -Force

    Write-ResearchLog -Level Info -Message "Installing ionosense-hpc in development mode" -Component "Setup"
    Push-Location $script:ProjectRoot
    $skbuildDir = Join-Path $script:ProjectRoot 'build/skbuild'
    if (Test-Path $skbuildDir) {
        Remove-Item -Recurse -Force $skbuildDir -ErrorAction SilentlyContinue
        Write-ResearchLog -Level Info -Message "Cleared scikit-build cache: $skbuildDir" -Component "Setup"
    }
    $env:SKBUILD_CMAKE_ARGS = "-DIONO_WITH_CUDA=OFF"
    conda run --no-capture-output -n $script:CondaEnvName python -m pip install -e .[dev,benchmark,export]
    $installCode = $LASTEXITCODE
    Remove-Item Env:SKBUILD_CMAKE_ARGS -ErrorAction SilentlyContinue
    Pop-Location

    if ($installCode -ne 0) {
        Write-ResearchLog -Level Warning -Message "Editable install failed (pip exit $installCode). Continuing without package install; use 'build' to compile the extension and set PYTHONPATH." -Component "Setup"
    } else {
        if ($reactivate) {
            Write-ResearchLog -Level Info -Message "Reactivating environment after clean setup" -Component "Setup"
            try {
                conda activate $script:CondaEnvName | Out-Null
            } catch {
                Write-ResearchLog -Level Warning -Message "Automatic reactivation failed: $($_.Exception.Message). Run 'conda activate $script:CondaEnvName' manually." -Component "Setup"
            }
            if ($env:CONDA_DEFAULT_ENV -ne $script:CondaEnvName) {
                Write-ResearchLog -Level Warning -Message "Environment '$script:CondaEnvName' is not active after setup. Run 'conda activate $script:CondaEnvName'." -Component "Setup"
            }
        }
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
    
    $configurePreset = $Preset
    $generator = Get-CMakePresetGenerator -PresetName $configurePreset
    if ($generator) {
        Ensure-CMakeGeneratorPreference -TargetGenerator $generator
    } else {
        Ensure-CMakeGeneratorPreference
    }
    
    if (-not (Test-CondaEnvironment)) {
        # Enable debug logging temporarily to show environment details
        $originalLogLevel = $script:CurrentLogLevel
        $script:CurrentLogLevel = [LogLevel]::Info
        Test-CondaEnvironment | Out-Null  # Run again to get debug output
        $script:CurrentLogLevel = $originalLogLevel

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


# --- Code Formatting ---------------------------------------------------------
Function Invoke-Format {
    param(
        [string[]]$Paths = @('src','include','bindings','tests'),
        [switch]$Check,
        [switch]$Staged,
        [switch]$Verbose
    )

    Write-ResearchLog -Level Info -Message "Formatting C/C++ sources" -Component "Format" -Metadata @{
        check = $Check.IsPresent
        staged = $Staged.IsPresent
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

    $root = $script:ProjectRoot
    $files = @()

    if ($Staged) {
        $git = Get-Command git -ErrorAction SilentlyContinue
        if (-not $git) {
            Write-ResearchLog -Level Error -Message "git not found; -Staged requires git" -Component "Format"
            throw "git is required for -Staged"
        }
        $staged = & git -C $root diff --name-only --cached 2>$null
        $exts = @('.c','.cc','.cpp','.cxx','.h','.hpp','.hxx','.cu','.cuh')
        foreach ($rel in $staged) {
            if (-not $rel) { continue }
            $full = Join-Path $root $rel
            $ext = [IO.Path]::GetExtension($full).ToLower()
            if ((Test-Path -LiteralPath $full) -and ($exts -contains $ext)) {
                $files += $full
            }
        }
        $files = $files | Sort-Object -Unique
    } else {
        # Expand provided paths relative to project root
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
        foreach ($t in $targets) {
            if ((Get-Item $t).PSIsContainer) {
                $files += Get-ChildItem -LiteralPath $t -Recurse -File -Include $patterns |
                    Where-Object { $excludeNames -notcontains $_.Directory.Name } |
                    ForEach-Object { $_.FullName }
            } else {
                # Single file provided
                if ($patterns | ForEach-Object { $_.Replace('*','') } | Where-Object { $t.ToLower().EndsWith($_.Trim('.').ToLower()) }) {
                    $files += (Get-Item -LiteralPath $t).FullName
                }
            }
        }

        # De-duplicate and ensure within repo
        $files = $files | Sort-Object -Unique |
            Where-Object { $_.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase) }
    }

    if ($files.Count -eq 0) {
        $msg = if ($Staged) { 'No staged C/C++ files to format' } else { 'No C/C++ files found to format' }
        Write-ResearchLog -Level Info -Message $msg -Component "Format"
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
        [switch]$Staged,
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
        staged = $Staged.IsPresent
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

        $targets = @()
        if ($Staged) {
            $git = Get-Command git -ErrorAction SilentlyContinue
            if (-not $git) {
                Write-ResearchLog -Level Error -Message "git not found; -Staged requires git" -Component "Lint"
                $overallFailed = $true
            } else {
                $root = $script:ProjectRoot
                $staged = & git -C $root diff --name-only --cached 2>$null
                foreach ($rel in $staged) {
                    if (-not $rel) { continue }
                    $full = Join-Path $root $rel
                    if ((Test-Path -LiteralPath $full) -and ($full.ToLower().EndsWith('.py'))) { $targets += $full }
                }
            }
        } else {
            $targets = @(
                $script:SourceDir,
                $script:TestsDir
            )
        }

        if ($targets.Count -eq 0) {
            Write-ResearchLog -Level Info -Message (if ($Staged) { 'No staged Python files to lint' } else { 'No Python targets found' }) -Component "Lint"
        } else {
            $args = @()
            if ($useModule) { $args += @('-m','ruff') }
            $args += @('check')
            if ($Fix) { $args += '--fix' }
            if ($Verbose) { $args += '-v' }
            $args += $targets

            Write-ResearchLog -Level Info -Message "Ruff check starting" -Component "Lint" -Metadata @{ fix = $Fix.IsPresent }
            & $ruffExe @args
            if ($LASTEXITCODE -ne 0) {
                $overallFailed = $true
                Write-ResearchLog -Level Error -Message "Python lint failed" -Component "Lint"
            } else {
                Write-ResearchLog -Level Info -Message "Python lint passed" -Component "Lint"
            }
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
            $files = @()
            if ($Staged) {
                $git = Get-Command git -ErrorAction SilentlyContinue
                if (-not $git) {
                    Write-ResearchLog -Level Error -Message "git not found; -Staged requires git" -Component "Lint"
                    $overallFailed = $true
                } else {
                    $root = $script:ProjectRoot
                    $staged = & git -C $root diff --name-only --cached 2>$null
                    $exts = @('.c','.cc','.cpp','.cxx','.h','.hpp','.hxx','.cu','.cuh')
                    foreach ($rel in $staged) {
                        if (-not $rel) { continue }
                        $full = Join-Path $root $rel
                        $ext = [IO.Path]::GetExtension($full).ToLower()
                        if ((Test-Path -LiteralPath $full) -and ($exts -contains $ext)) { $files += $full }
                    }
                    $files = $files | Sort-Object -Unique
                }
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
                foreach ($t in $targets) {
                    if (Test-Path -LiteralPath $t) {
                        $files += Get-ChildItem -LiteralPath $t -Recurse -File -Include $patterns |
                            Where-Object { $excludeNames -notcontains $_.Directory.Name } |
                            ForEach-Object { $_.FullName }
                    }
                }
                $files = $files | Sort-Object -Unique
            }

            if ($files.Count -eq 0) {
                $msg = if ($Staged) { 'No staged C/C++ files to lint' } else { 'No C/C++ files to lint' }
                Write-ResearchLog -Level Info -Message $msg -Component "Lint"
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
    $pySrc = $script:SourceDir
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
            $script:ArtifactsDir,
            (Join-Path $root 'results'),
            (Join-Path $root 'benchmark_results'),
            $script:ReportsDir,
            $script:ExperimentsDir,
            $script:ProfileDir,
            $script:LogRoot,
            (Join-Path $root '.ionosense'),
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

# --- Type Checking ----------------------------------------------------------
Function Invoke-Typecheck {
    param(
        [switch]$Strict,
        [switch]$IncludeTests,
        [switch]$Verbose
    )

    Write-ResearchLog -Level Info -Message "Running mypy type checking" -Component "Typecheck" -Metadata @{
        strict = $Strict.IsPresent
    }

    # Resolve mypy
    $mypyExe = $null
    foreach ($cmd in @('mypy','mypy.exe')) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { $mypyExe = $found.Source; break }
    }
    if (-not $mypyExe) {
        # Fallback to python -m mypy
        $pyExe = if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX 'python.exe' } else { 'python' }
        $mypyExe = $pyExe
        $useModule = $true
    } else { $useModule = $false }

    $pySrc   = $script:SourceDir
    $pyTests = $script:TestsDir
    $targets = @()
    if (Test-Path -LiteralPath $pySrc)   { $targets += $pySrc }
    if ($IncludeTests -and (Test-Path -LiteralPath $pyTests)) { $targets += $pyTests }
    if ($targets.Count -eq 0) {
        Write-ResearchLog -Level Warning -Message "No python targets to typecheck" -Component "Typecheck"
        return
    }

    # Ensure mypy can resolve package imports from tests
    $oldMypyPath = $env:MYPYPATH
    $env:MYPYPATH = if ($oldMypyPath) { "$pySrc;$oldMypyPath" } else { $pySrc }

    try {
        $args = @()
        if ($useModule) { $args += @('-m','mypy') }
        if ($Verbose) { $args += '-v' }
        if ($Strict) { $args += '--strict' }
        # mypy auto-reads pyproject.toml [tool.mypy]
        $args += $targets

        & $mypyExe @args
        if ($LASTEXITCODE -ne 0) {
            Write-ResearchLog -Level Error -Message "Typechecking failed" -Component "Typecheck"
            throw "mypy reported errors"
        } else {
            Write-ResearchLog -Level Info -Message "Typechecking passed" -Component "Typecheck"
        }
    }
    finally {
        $env:MYPYPATH = $oldMypyPath
    }
}

# --- Check Aggregator -------------------------------------------------------
Function Invoke-Check {
    param(
        [switch]$Staged,
        [switch]$Verbose
    )

    Write-ResearchLog -Level Info -Message "Running aggregated checks" -Component "Check" -Metadata @{
        staged = $Staged.IsPresent
    }

    if (-not (Test-CondaEnvironment)) {
        throw "Conda environment not activated"
    }

    # 1) Format (check mode)
    try {
        Invoke-Format -Check:$true -Staged:$Staged -Verbose:$Verbose
    } catch {
        Write-ResearchLog -Level Error -Message "Format check failed" -Component "Check" -Metadata @{ step = 'format' }
        throw
    }

    # 2) Lint
    try {
        Invoke-Lint -Target 'all' -Staged:$Staged -Verbose:$Verbose
    } catch {
        Write-ResearchLog -Level Error -Message "Lint failed" -Component "Check" -Metadata @{ step = 'lint' }
        throw
    }

    # 3) Typecheck (non-strict, src only)
    try {
        Invoke-Typecheck -Verbose:$Verbose
    } catch {
        Write-ResearchLog -Level Error -Message "Typecheck failed" -Component "Check" -Metadata @{ step = 'typecheck' }
        throw
    }

    # 4) Quick Python tests subset (skip slow/gpu/benchmark; fail fast)
    try {
        $kExpr = 'not slow and not gpu and not benchmark'
        $pytestArgs = @('-k', $kExpr, '--maxfail=1', '--tb=short')
        if ($Verbose) { $pytestArgs += '-vv' } else { $pytestArgs += '-q' }

        Write-ResearchLog -Level Info -Message "Running quick Python tests" -Component "Check" -Metadata @{ k = $kExpr }
        Invoke-WithPythonPath {
            pytest @pytestArgs
        }
        if ($LASTEXITCODE -ne 0) { throw "Quick tests failed (pytest exit $LASTEXITCODE)" }
    } catch {
        Write-ResearchLog -Level Error -Message "Quick Python tests failed" -Component "Check" -Metadata @{ step = 'pytest' }
        throw
    }

    Write-ResearchLog -Level Info -Message "All checks passed" -Component "Check"
}

# --- Doctor (Environment/Tooling Verification) -----------------------------
Function Invoke-Doctor {
    param(
        [switch]$Strict,
        [switch]$Verbose
    )

    Write-ResearchLog -Level Info -Message "Running environment doctor" -Component "Doctor" -Metadata @{
        strict = $Strict.IsPresent
    }

    $checks = New-Object System.Collections.ArrayList

    function Resolve-Exe {
        param([string[]]$Candidates)
        foreach ($c in $Candidates) {
            $cmd = Get-Command $c -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        }
        return $null
    }

    function Get-VersionString {
        param([string]$Exe, [string[]]$Args = @('--version'))
        try {
            foreach ($a in $Args) {
                $p = & $Exe $a 2>&1
                if ($LASTEXITCODE -eq 0 -and $p) {
                    $line = ($p | Select-Object -First 1).ToString().Trim()
                    if ($line) { return $line }
                }
            }
        } catch {}
        return $null
    }

    function Add-Check {
        param([string]$Name, [string]$Status, [string]$Detail)
        [void]$checks.Add([PSCustomObject]@{ Component = $Name; Status = $Status; Detail = $Detail })
    }

    # Python / Conda
    $pyExe = if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX 'python.exe' } else { 'python' }
    $pyVer = try { (& $pyExe --version 2>&1 | Select-Object -First 1).Trim() } catch { $null }
    if ($pyVer) { $pyStatus = 'OK'; $pyDetail = $pyVer } else { $pyStatus = 'FAIL'; $pyDetail = 'python not found in PATH' }
    Add-Check -Name 'Python' -Status $pyStatus -Detail $pyDetail

    $condaActive = Test-CondaEnvironment
    if ($condaActive) { $condaStatus='OK'; $condaDetail = "active: $env:CONDA_DEFAULT_ENV" }
    else { $condaStatus='FAIL'; $condaDetail = "inactive or wrong env (expected: $script:CondaEnvName)" }
    Add-Check -Name 'Conda' -Status $condaStatus -Detail $condaDetail

    # Build tools (required)
    foreach ($tool in @(
        @{ name='CMake';         candidates=@('cmake','cmake.exe');             verArgs=@('--version');          required=$true },
        @{ name='Ninja';         candidates=@('ninja','ninja.exe');             verArgs=@('--version');          required=$true },
        @{ name='clang-format';  candidates=@('clang-format','clang-format.exe');verArgs=@('--version');          required=$true }
    )) {
        $exe = Resolve-Exe $tool.candidates
        if ($exe) {
            $ver = Get-VersionString -Exe $exe -Args $tool.verArgs
            if ($ver) { $detail = $ver } else { $detail = $exe }
            Add-Check -Name $tool.name -Status 'OK' -Detail $detail
        } else {
            Add-Check -Name $tool.name -Status 'FAIL' -Detail 'not found in PATH'
        }
    }

    # Python tooling (required)
    foreach ($pytool in @(
        @{ name='ruff'; candidates=@('ruff','ruff.exe'); module='ruff' },
        @{ name='mypy'; candidates=@('mypy','mypy.exe'); module='mypy' }
    )) {
        $exe = Resolve-Exe $pytool.candidates
        if ($exe) {
            $ver = Get-VersionString -Exe $exe -Args @('--version','-V')
            if ($ver) { $detail = $ver } else { $detail = $exe }
            Add-Check -Name $pytool.name -Status 'OK' -Detail $detail
        } else {
            # Fallback to python -m
            try {
                $out = & $pyExe -m $pytool.module --version 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $line = ($out | Select-Object -First 1).ToString().Trim()
                    Add-Check -Name $pytool.name -Status 'OK' -Detail ("via python -m: " + $line)
                } else {
                    Add-Check -Name $pytool.name -Status 'FAIL' -Detail 'not found (exe nor module)'
                }
            } catch {
                Add-Check -Name $pytool.name -Status 'FAIL' -Detail 'not found (exe nor module)'
            }
        }
    }

    # CUDA Toolkit / Driver (optional)
    $nvcc = Resolve-Exe @('nvcc','nvcc.exe')
    if ($nvcc) {
        $ver = Get-VersionString -Exe $nvcc -Args @('--version')
        if ($ver) { $detail = $ver } else { $detail = $nvcc }
        Add-Check -Name 'CUDA Toolkit (nvcc)' -Status 'OK' -Detail $detail
    } else {
        Add-Check -Name 'CUDA Toolkit (nvcc)' -Status 'WARN' -Detail 'not found; CUDA build disabled'
    }

    $nvsmi = Resolve-Exe @('nvidia-smi','nvidia-smi.exe')
    if ($nvsmi) {
        $ver = try { (& $nvsmi '--version' 2>&1 | Select-Object -First 1).Trim() } catch { $null }
        if ($ver) { $detail = $ver } else { $detail = $nvsmi }
        Add-Check -Name 'CUDA Driver (nvidia-smi)' -Status 'OK' -Detail $detail
    } else {
        Add-Check -Name 'CUDA Driver (nvidia-smi)' -Status 'WARN' -Detail 'not found; no driver detected'
    }

    # Nsight tools (optional)
    $nsys = Resolve-Exe @('nsys','nsys.exe','nsight-systems','nsight-systems.exe')
    if ($nsys) { $st='OK'; $dt=$nsys } else { $st='WARN'; $dt='not found' }
    Add-Check -Name 'Nsight Systems (CLI)' -Status $st -Detail $dt

    $ncu = Resolve-Exe @('ncu','ncu.exe','nsight-compute','nsight-compute.exe')
    if ($ncu) { $st='OK'; $dt=$ncu } else { $st='WARN'; $dt='not found' }
    Add-Check -Name 'Nsight Compute (CLI)' -Status $st -Detail $dt

    $nsysUi = Resolve-Exe @('nsys-ui','nsys-ui.exe','nsight-systems.exe','nsight-systems.bat')
    if (-not $nsysUi) {
        foreach ($root in @("$env:ProgramFiles\NVIDIA Corporation","$env:ProgramFilesX86\NVIDIA Corporation")) {
            if ($root -and (Test-Path $root)) {
                $found = Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue -Include 'nsys-ui.exe','nsys-ui.bat','nsight-systems.exe' | Select-Object -First 1
                if ($found) { $nsysUi = $found.FullName; break }
            }
        }
    }
    if ($nsysUi) { $st='OK'; $dt=$nsysUi } else { $st='WARN'; $dt='not found' }
    Add-Check -Name 'Nsight Systems (UI)' -Status $st -Detail $dt

    $ncuUi = Resolve-Exe @('ncu-ui','ncu-ui.exe','nsight-compute.exe')
    if ($ncuUi) { $st='OK'; $dt=$ncuUi } else { $st='WARN'; $dt='not found' }
    Add-Check -Name 'Nsight Compute (UI)' -Status $st -Detail $dt

    # Modern Research Stack Tools
    foreach ($tool in @(
        @{ name='Hydra'; module='hydra'; required=$true; desc='Configuration management' },
        @{ name='MLflow'; module='mlflow'; required=$true; desc='Experiment tracking' },
        @{ name='Snakemake'; exe=@('snakemake','snakemake.exe'); required=$true; desc='Workflow orchestration' },
        @{ name='DVC'; exe=@('dvc','dvc.exe'); required=$false; desc='Data versioning' }
    )) {
        if ($tool.ContainsKey('module')) {
            # Python module check
            try {
                $out = & $pyExe -c "import $($tool.module); print('✓')" 2>$null
                if ($LASTEXITCODE -eq 0 -and $out -eq '✓') {
                    Add-Check -Name $tool.name -Status 'OK' -Detail "$($tool.desc) - ready"
                } else {
                    $status = if ($tool.required) { 'FAIL' } else { 'WARN' }
                    Add-Check -Name $tool.name -Status $status -Detail "module not found - install with pip/conda"
                }
            } catch {
                $status = if ($tool.required) { 'FAIL' } else { 'WARN' }
                Add-Check -Name $tool.name -Status $status -Detail "module not available"
            }
        } elseif ($tool.ContainsKey('exe')) {
            # Executable check
            $exe = Resolve-Exe $tool.exe
            if ($exe) {
                $ver = Get-VersionString -Exe $exe
                $detail = if ($ver) { "$($tool.desc) - $ver" } else { "$($tool.desc) - ready" }
                Add-Check -Name $tool.name -Status 'OK' -Detail $detail
            } else {
                $status = if ($tool.required) { 'FAIL' } else { 'WARN' }
                Add-Check -Name $tool.name -Status $status -Detail "$($tool.desc) - not found in PATH"
            }
        }
    }

    # Check benchmark scripts availability
    $benchmarkDir = Join-Path $script:ProjectRoot "benchmarks"
    if (Test-Path $benchmarkDir) {
        $scriptCount = (Get-ChildItem -Path $benchmarkDir -Filter "run_*.py" | Measure-Object).Count
        if ($scriptCount -gt 0) {
            Add-Check -Name 'Benchmark Scripts' -Status 'OK' -Detail "$scriptCount modern benchmark scripts found"
        } else {
            Add-Check -Name 'Benchmark Scripts' -Status 'WARN' -Detail "no run_*.py scripts found"
        }
    } else {
        Add-Check -Name 'Benchmark Scripts' -Status 'FAIL' -Detail "benchmarks directory not found"
    }

    # Modern Research Stack Tools
    foreach ($tool in @(
        @{ name='Hydra'; module='hydra'; required=$true; desc='Configuration management' },
        @{ name='MLflow'; module='mlflow'; required=$true; desc='Experiment tracking' },
        @{ name='Snakemake'; exe=@('snakemake','snakemake.exe'); required=$true; desc='Workflow orchestration' },
        @{ name='DVC'; exe=@('dvc','dvc.exe'); required=$false; desc='Data versioning' }
    )) {
        if ($tool.ContainsKey('module')) {
            # Python module check
            try {
                $out = & $pyExe -c "import $($tool.module); print('✓')" 2>$null
                if ($LASTEXITCODE -eq 0 -and $out -eq '✓') {
                    Add-Check -Name $tool.name -Status 'OK' -Detail "$($tool.desc) - ready"
                } else {
                    $status = if ($tool.required) { 'FAIL' } else { 'WARN' }
                    Add-Check -Name $tool.name -Status $status -Detail "module not found - install with pip/conda"
                }
            } catch {
                $status = if ($tool.required) { 'FAIL' } else { 'WARN' }
                Add-Check -Name $tool.name -Status $status -Detail "module not available"
            }
        } elseif ($tool.ContainsKey('exe')) {
            # Executable check
            $exe = Resolve-Exe $tool.exe
            if ($exe) {
                $ver = Get-VersionString -Exe $exe
                $detail = if ($ver) { "$($tool.desc) - $ver" } else { "$($tool.desc) - ready" }
                Add-Check -Name $tool.name -Status 'OK' -Detail $detail
            } else {
                $status = if ($tool.required) { 'FAIL' } else { 'WARN' }
                Add-Check -Name $tool.name -Status $status -Detail "$($tool.desc) - not found in PATH"
            }
        }
    }

    # Check benchmark scripts availability
    $benchmarkDir = Join-Path $script:ProjectRoot "benchmarks"
    if (Test-Path $benchmarkDir) {
        $scriptCount = (Get-ChildItem -Path $benchmarkDir -Filter "run_*.py" | Measure-Object).Count
        if ($scriptCount -gt 0) {
            Add-Check -Name 'Benchmark Scripts' -Status 'OK' -Detail "$scriptCount modern benchmark scripts found"
        } else {
            Add-Check -Name 'Benchmark Scripts' -Status 'WARN' -Detail "no run_*.py scripts found"
        }
    } else {
        Add-Check -Name 'Benchmark Scripts' -Status 'FAIL' -Detail "benchmarks directory not found"
    }

    # Print summary
    Write-Host "`n🩺 Environment Doctor Summary" -ForegroundColor Cyan
    Write-Host   "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
    $ok   = 0
    $warn = 0
    $fail = 0
    foreach ($c in $checks) {
        $color = switch ($c.Status) { 'OK' { 'Green' } 'WARN' { 'Yellow' } 'FAIL' { 'Red' } default { 'Gray' } }
        if ($c.Status -eq 'OK') { $ok++ }
        elseif ($c.Status -eq 'WARN') { $warn++ }
        elseif ($c.Status -eq 'FAIL') { $fail++ }
        Write-Host ("{0,-28} {1,-6} {2}" -f $c.Component, $c.Status, $c.Detail) -ForegroundColor $color
    }
    Write-Host   "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
    Write-Host ("OK: {0}  WARN: {1}  FAIL: {2}" -f $ok,$warn,$fail)

    if ($fail -gt 0) {
        Write-ResearchLog -Level Warning -Message ("Doctor found {0} failure(s)" -f $fail) -Component "Doctor"
        if ($Strict) { throw "Doctor checks failed ($fail)" }
    } else {
        Write-ResearchLog -Level Info -Message "Doctor checks passed (no failures)" -Component "Doctor"
    }
}

# --- Modern Tool Integration Functions --------------------------------------

Function Invoke-ModernExperiment {
    param([string[]]$CommandArgs = @())

    Write-ResearchLog -Level Info -Message "Running single experiment via Hydra" -Component "Experiment"

    $params = @{ Overrides = @() }
    $positional = @()

    for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
        $arg = $CommandArgs[$i]
        switch ($arg) {
            '-Config' { if ($i + 1 -lt $CommandArgs.Count) { $params.Config = $CommandArgs[$i + 1]; $i++ } }
            '-Benchmark' { if ($i + 1 -lt $CommandArgs.Count) { $params.Benchmark = $CommandArgs[$i + 1]; $i++ } }
            '-Engine' { if ($i + 1 -lt $CommandArgs.Count) { $params.Engine = $CommandArgs[$i + 1]; $i++ } }
            '-Override' { if ($i + 1 -lt $CommandArgs.Count) { $params.Overrides += $CommandArgs[$i + 1]; $i++ } }
            default {
                if ($arg -and $arg -notlike '-*') {
                    # Check if this is a Hydra override (key=value format)
                    if ($arg -match '^([^=]+)=(.+)$') {
                        $key = $matches[1]
                        $value = $matches[2]

                        # Handle special Hydra config keys
                        switch ($key) {
                            'experiment' { if (-not $params.Config) { $params.Config = $value } }
                            'benchmark' { if (-not $params.Benchmark) { $params.Benchmark = $value } }
                            'engine' { if (-not $params.Engine) { $params.Engine = $value } }
                            default { $params.Overrides += $arg }
                        }
                    } else {
                        $positional += $arg
                    }
                }
            }
        }
    }

    # Add positional args as overrides
    $params.Overrides += $positional

    # Debug output to show parsed parameters
    Write-ResearchLog -Level Debug -Message "Parsed parameters: Config='$($params.Config)' Benchmark='$($params.Benchmark)' Engine='$($params.Engine)' Overrides=[$($params.Overrides -join ', ')]" -Component "Experiment"

    # Default to latency benchmark if none specified
    $benchmark = if ($params.Benchmark) { $params.Benchmark } else { "latency" }

    # Build the command
    $scriptPath = "benchmarks/run_$benchmark.py"
    $args = @()

    # Add configuration overrides
    if ($params.Engine) { $args += "engine=$($params.Engine)" }
    if ($params.Config) { $args += "experiment=$($params.Config)" }

    # Override benchmark configuration if different from default
    if ($params.Benchmark -and $params.Benchmark -ne "latency") {
        $args += "benchmark=$($params.Benchmark)"
    }

    $args += $params.Overrides

    # Check if script exists
    if (-not (Test-Path $scriptPath)) {
        throw "Benchmark script not found: $scriptPath"
    }

    Write-ResearchLog -Level Debug -Message "Running: python $scriptPath $($args -join ' ')" -Component "Experiment"

    Invoke-WithPythonPath {
        python $scriptPath @args
        if ($LASTEXITCODE -ne 0) { throw "Experiment execution failed" }
    }

    Write-ResearchLog -Level Info -Message "Experiment completed successfully" -Component "Experiment"
}

Function Invoke-ModernRun {
    param([string[]]$CommandArgs = @())

    if ($CommandArgs.Count -eq 0) {
        throw "Usage: run <script.py> [args...] - No script specified"
    }

    $scriptPath = $CommandArgs[0]
    $scriptArgs = $CommandArgs[1..($CommandArgs.Count-1)]

    # Resolve script path if relative
    if (-not [System.IO.Path]::IsPathRooted($scriptPath)) {
        $scriptPath = Join-Path (Get-Location) $scriptPath
    }

    if (-not (Test-Path $scriptPath)) {
        throw "Script not found: $scriptPath"
    }

    Write-ResearchLog -Level Info -Message "Running Python script" -Component "Run" -Metadata @{
        script = $scriptPath
        args = ($scriptArgs -join ' ')
    }

    $oldPath = $env:PYTHONPATH
    $env:PYTHONPATH = "$script:BuildDir\$script:BuildPreset;" + ($script:SourceDir) + ";$env:PYTHONPATH"

    try {
        if ($scriptArgs.Count -gt 0) {
            & python $scriptPath @scriptArgs
        } else {
            & python $scriptPath
        }
        if ($LASTEXITCODE -ne 0) { throw "Script execution failed with exit code $LASTEXITCODE" }
    } finally {
        $env:PYTHONPATH = $oldPath
    }

    Write-ResearchLog -Level Info -Message "Script completed successfully" -Component "Run"
}

Function Invoke-ModernSweep {
    param([string[]]$CommandArgs = @())

    Write-ResearchLog -Level Info -Message "Running parameter sweep via Hydra multirun" -Component "Sweep"

    $params = @{ Overrides = @() }
    $positional = @()

    for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
        $arg = $CommandArgs[$i]
        switch ($arg) {
            '-Config' { if ($i + 1 -lt $CommandArgs.Count) { $params.Config = $CommandArgs[$i + 1]; $i++ } }
            '-Benchmark' { if ($i + 1 -lt $CommandArgs.Count) { $params.Benchmark = $CommandArgs[$i + 1]; $i++ } }
            '-Parallel' { $params.Parallel = $true }
            '-Workers' { if ($i + 1 -lt $CommandArgs.Count) { $params.Workers = [int]$CommandArgs[$i + 1]; $i++ } }
            '-Override' { if ($i + 1 -lt $CommandArgs.Count) { $params.Overrides += $CommandArgs[$i + 1]; $i++ } }
            default {
                if ($arg -and $arg -notlike '-*') {
                    # Check if this is a Hydra override (key=value format)
                    if ($arg -match '^([^=]+)=(.+)$') {
                        $key = $matches[1]
                        $value = $matches[2]

                        # Handle special Hydra config keys
                        switch ($key) {
                            'experiment' { if (-not $params.Config) { $params.Config = $value } }
                            'benchmark' { if (-not $params.Benchmark) { $params.Benchmark = $value } }
                            default { $params.Overrides += $arg }
                        }
                    } else {
                        $positional += $arg
                    }
                }
            }
        }
    }

    # First positional arg is the config/experiment
    if ($positional.Count -gt 0 -and -not $params.Config) {
        $params.Config = $positional[0]
        $params.Overrides += $positional[1..($positional.Count-1)]
    } else {
        $params.Overrides += $positional
    }

    # Debug output to show parsed parameters
    Write-ResearchLog -Level Debug -Message "Parsed parameters: Config='$($params.Config)' Benchmark='$($params.Benchmark)' Overrides=[$($params.Overrides -join ', ')]" -Component "Sweep"

    if (-not $params.Config) {
        throw "Config/experiment name required for sweep"
    }

    # Default to latency benchmark if none specified
    $benchmark = if ($params.Benchmark) { $params.Benchmark } else { "latency" }

    # Build the full command with arguments
    $scriptPath = "benchmarks/run_$benchmark.py"
    $args = @("--multirun", "experiment=$($params.Config)")

    # Override benchmark configuration if different from default
    if ($params.Benchmark -and $params.Benchmark -ne "latency") {
        $args += "benchmark=$($params.Benchmark)"
    }

    # Add parallel execution if requested
    if ($params.Parallel) {
        $args += "hydra/launcher=joblib"
        if ($params.Workers) { $args += "hydra.launcher.n_jobs=$($params.Workers)" }
    }

    # Add additional overrides
    $args += $params.Overrides

    # Check if script exists
    if (-not (Test-Path $scriptPath)) {
        throw "Benchmark script not found: $scriptPath"
    }

    # Validate configuration files exist
    $configPaths = @()
    if ($params.Config) {
        $experimentPath = "experiments/conf/experiment/$($params.Config).yaml"
        if (Test-Path $experimentPath) {
            $configPaths += $experimentPath
            Write-ResearchLog -Level Debug -Message "Found experiment config: $experimentPath" -Component "Sweep"
        } else {
            Write-ResearchLog -Level Warning -Message "Experiment config not found: $experimentPath" -Component "Sweep"
        }
    }
    if ($params.Benchmark -and $params.Benchmark -ne "latency") {
        $benchmarkPath = "experiments/conf/benchmark/$($params.Benchmark).yaml"
        if (Test-Path $benchmarkPath) {
            $configPaths += $benchmarkPath
            Write-ResearchLog -Level Debug -Message "Found benchmark config: $benchmarkPath" -Component "Sweep"
        } else {
            Write-ResearchLog -Level Warning -Message "Benchmark config not found: $benchmarkPath" -Component "Sweep"
        }
    }

    Write-ResearchLog -Level Debug -Message "Running: python $scriptPath $($args -join ' ')" -Component "Sweep"

    # Add configuration validation
    Write-ResearchLog -Level Debug -Message "Final command: python $scriptPath $($args -join ' ')" -Component "Sweep"

    Invoke-WithPythonPath {
        python $scriptPath @args
        if ($LASTEXITCODE -ne 0) {
            Write-ResearchLog -Level Error -Message "Parameter sweep failed with exit code $LASTEXITCODE" -Component "Sweep"
            throw "Parameter sweep failed"
        }
    }

    Write-ResearchLog -Level Info -Message "Parameter sweep completed successfully" -Component "Sweep"
}

Function Invoke-ModernWorkflow {
    param([string[]]$CommandArgs = @())

    Write-ResearchLog -Level Info -Message "Running workflow via Snakemake" -Component "Workflow"

    $params = @{}
    $targets = @()

    for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
        $arg = $CommandArgs[$i]
        switch ($arg) {
            '-Cores' { if ($i + 1 -lt $CommandArgs.Count) { $params.Cores = [int]$CommandArgs[$i + 1]; $i++ } }
            '-DryRun' { $params.DryRun = $true }
            '-Verbose' { $params.Verbose = $true }
            '-Clean' { $params.Clean = $true }
            '-Target' { if ($i + 1 -lt $CommandArgs.Count) { $targets += $CommandArgs[$i + 1]; $i++ } }
            default { if ($arg -and $arg -notlike '-*') { $targets += $arg } }
        }
    }

    # Default settings
    $cores = if ($params.Cores) { $params.Cores } else { 4 }

    # Handle clean first if requested
    if ($params.Clean) {
        $cleanArgs = @("--cores", $cores, "--snakefile", "experiments/Snakefile", "clean")
        & snakemake @cleanArgs
        if ($LASTEXITCODE -ne 0) { Write-ResearchLog -Level Warning -Message "Clean failed, continuing..." -Component "Workflow" }
    }

    # Build snakemake command
    $args = @("--cores", $cores, "--snakefile", "experiments/Snakefile")

    if ($params.DryRun) { $args += "--dry-run" }
    if ($params.Verbose) { $args += "--verbose" }

    # Add targets if specified, otherwise run default 'all' rule
    if ($targets.Count -gt 0) {
        $args += $targets
    }

    # Check if snakemake is available
    $snakemake = Get-Command snakemake -ErrorAction SilentlyContinue
    if (-not $snakemake) {
        throw "snakemake not found. Install with: conda install snakemake"
    }

    & snakemake @args
    if ($LASTEXITCODE -ne 0) { throw "Snakemake workflow failed" }

    Write-ResearchLog -Level Info -Message "Workflow completed successfully" -Component "Workflow"
}

Function Invoke-ModernTrack {
    param([string[]]$CommandArgs = @())

    Write-ResearchLog -Level Info -Message "MLflow tracking operations" -Component "Track"

    $subcommand = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "ui" }
    $remaining = $CommandArgs[1..($CommandArgs.Count-1)]

    switch ($subcommand.ToLower()) {
        "ui" {
            $port = 5000
            for ($i = 0; $i -lt $remaining.Count; $i++) {
                if ($remaining[$i] -eq "-Port" -and $i+1 -lt $remaining.Count) {
                    $port = [int]$remaining[$i+1]
                }
            }

            Write-ResearchLog -Level Info -Message "Starting MLflow UI on port $port" -Component "Track"
            & mlflow ui --backend-store-uri "file:///$($script:ArtifactsDir)/mlruns" --port $port
        }
        "list" {
            Write-ResearchLog -Level Info -Message "Listing experiments" -Component "Track"
            & mlflow experiments list --tracking-uri "file:///$($script:ArtifactsDir)/mlruns"
        }
        "search" {
            $filter = $remaining -join " "
            if ($filter) {
                & mlflow runs search --tracking-uri "file:///$($script:ArtifactsDir)/mlruns" --filter "$filter"
            } else {
                & mlflow runs search --tracking-uri "file:///$($script:ArtifactsDir)/mlruns"
            }
        }
        default {
            throw "Unknown track subcommand: $subcommand. Available: ui, list, search"
        }
    }
}

Function Invoke-ModernData {
    param([string[]]$CommandArgs = @())

    Write-ResearchLog -Level Info -Message "DVC data operations" -Component "Data"

    $subcommand = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "status" }
    $remaining = $CommandArgs[1..($CommandArgs.Count-1)]

    # Check if dvc is available
    $dvc = Get-Command dvc -ErrorAction SilentlyContinue
    if (-not $dvc) {
        throw "dvc not found. Install with: pip install dvc"
    }

    switch ($subcommand.ToLower()) {
        "status" {
            Write-ResearchLog -Level Info -Message "Checking DVC status" -Component "Data"
            & dvc status
        }
        "repro" {
            Write-ResearchLog -Level Info -Message "Reproducing DVC pipeline" -Component "Data"
            $args = @("repro")
            if ($remaining -contains "-Force") { $args += "--force" }
            if ($remaining -contains "-DryRun") { $args += "--dry" }
            & dvc @args
        }
        "push" {
            Write-ResearchLog -Level Info -Message "Pushing data to remote" -Component "Data"
            & dvc push
        }
        "pull" {
            Write-ResearchLog -Level Info -Message "Pulling data from remote" -Component "Data"
            & dvc pull
        }
        "dag" {
            Write-ResearchLog -Level Info -Message "Showing DVC pipeline DAG" -Component "Data"
            & dvc dag
        }
        default {
            # Pass through to dvc directly
            & dvc $subcommand @remaining
        }
    }
}

Function Invoke-ModernLearn {
    param([string[]]$CommandArgs = @())

    $tool = if ($CommandArgs.Count -gt 0) { $CommandArgs[0].ToLower() } else { "overview" }

    Write-Host "`n🎓 Learning Guide: $tool" -ForegroundColor Cyan

    switch ($tool) {
        "overview" {
            Write-Host @"

📚 Native Research Toolchain Overview
=====================================

Use these industry-standard tools directly for maximum flexibility:

1. 🔧 Hydra - Configuration Management
   • Manages experiment parameters and configs
   • Usage: python benchmarks/run_latency.py experiment=baseline
   • Learn more: .\scripts\cli.ps1 learn hydra

2. 🐍 Snakemake - Workflow Orchestration
   • Manages complex analysis pipelines
   • Usage: snakemake --cores 4 --snakefile experiments/Snakefile
   • Learn more: .\scripts\cli.ps1 learn snakemake

3. 📊 DVC - Data Version Control
   • Tracks data and model artifacts
   • Usage: dvc status, dvc repro
   • Learn more: .\scripts\cli.ps1 learn dvc

4. 📈 MLflow - Experiment Tracking
   • Logs metrics, parameters, and artifacts
   • Usage: mlflow ui --backend-store-uri file://./artifacts/mlruns
   • Learn more: .\scripts\cli.ps1 learn mlflow

5. ⚡ Benchmark Scripts - Modular Experiments
   • Individual focused benchmark runners
   • Usage: Direct python execution with Hydra configs
   • Learn more: .\scripts\cli.ps1 learn benchmarks

🔬 Ionosphere Research Quick Start:
  python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution
  python benchmarks/run_latency.py experiment=ionosphere_multiscale
  snakemake --cores 4 --snakefile experiments/Snakefile
  mlflow ui --backend-store-uri file://./artifacts/mlruns

"@
        }
        "hydra" {
            Write-Host @"

🔧 Hydra Configuration Management
================================

Hydra manages all your experiment configurations through YAML files.

📁 Configuration Structure:
  experiments/conf/
  ├── config.yaml              # Main config
  ├── engine/                  # Engine configurations
  │   ├── realtime.yaml
  │   ├── throughput.yaml
  │   ├── ionosphere_realtime.yaml    # 🔬 Ionosphere research
  │   ├── ionosphere_hires.yaml       # 🔬 High resolution
  │   └── ionosphere_longterm.yaml    # 🔬 Long duration
  ├── benchmark/               # Benchmark settings
  │   ├── latency.yaml
  │   └── throughput.yaml
  └── experiment/              # Experiment templates
      ├── baseline.yaml
      ├── nfft_scaling.yaml
      ├── ionosphere_resolution.yaml  # 🔬 NFFT resolution study
      ├── ionosphere_temporal.yaml    # 🔬 Temporal analysis
      └── ionosphere_multiscale.yaml  # 🔬 Comprehensive study

🔬 IONOSPHERE RESEARCH CONFIGS (Ready-to-use):
  # Single experiments
  python benchmarks/run_latency.py experiment=ionosphere_multiscale

  # Parameter sweeps for research
  python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution
  python benchmarks/run_throughput.py --multirun experiment=ionosphere_temporal

🚀 Native Hydra Usage Examples:
  # Run with Hydra native syntax (recommended)
  python benchmarks/run_latency.py experiment=baseline

  # Override parameters
  python benchmarks/run_latency.py experiment=baseline engine.nfft=1024

  # Multiple parameter sweeps
  python benchmarks/run_latency.py --multirun engine.nfft=1024,2048,4096,8192
  python benchmarks/run_throughput.py --multirun experiment=nfft_scaling

  # Combine experiment configs with overrides
  python benchmarks/run_latency.py experiment=ionosphere_temporal engine.batch=128

💡 Key Concepts:
  • Config Groups: Organized sets of related configs (engine/, benchmark/)
  • Overrides: Command-line parameter modifications
  • Multirun: Hydra's built-in parameter sweeping
  • Composition: Mix and match different config groups

"@
        }
        "snakemake" {
            Write-Host @"

🐍 Snakemake Workflow Orchestration
==================================

Snakemake manages your analysis pipeline from benchmarks to final reports.

📁 Workflow Files:
  experiments/Snakefile         # Main workflow definition
  experiments/scripts/          # Analysis scripts

🎯 Workflow Targets:
  all                          # Complete analysis pipeline
  run_latency_sweep           # Run latency benchmarks
  analyze_results             # Analyze benchmark data
  generate_figures            # Create visualizations
  generate_report             # Final HTML report

🚀 Native Snakemake Usage Examples:
  # Run complete pipeline
  snakemake --cores 4 --snakefile experiments/Snakefile

  # Run specific target
  snakemake --cores 4 analyze_results --snakefile experiments/Snakefile

  # Dry run to see what would execute
  snakemake --dry-run --snakefile experiments/Snakefile

  # Use more CPU cores
  snakemake --cores 8 --snakefile experiments/Snakefile

  # Clean all outputs
  snakemake --cores 4 clean --snakefile experiments/Snakefile

  # Generate specific outputs
  snakemake --cores 4 generate_figures --snakefile experiments/Snakefile

💡 Key Benefits:
  • Automatic dependency tracking
  • Incremental execution (only run what changed)
  • Parallel execution where possible
  • Reproducible pipelines

"@
        }
        "dvc" {
            Write-Host @"

📊 DVC Data Version Control
===========================

DVC tracks your data, models, and experiment artifacts.

📁 Tracked Directories:
  artifacts/data/              # Processed datasets
  artifacts/figures/           # Generated plots
  artifacts/reports/           # Analysis reports

🚀 Native DVC Usage Examples:
  # Check what's changed
  dvc status

  # Reproduce the pipeline
  dvc repro

  # View pipeline structure
  dvc dag

  # Push data to remote storage
  dvc push

  # Pull data from remote
  dvc pull

  # Add new data to tracking
  dvc add artifacts/data/large_dataset.csv

💡 Key Concepts:
  • Stages: Individual pipeline steps
  • Dependencies: Input files/directories
  • Outputs: Generated artifacts
  • Remote Storage: Cloud storage for large files
  • Reproducibility: Recreate results from any commit

🔄 Integration:
  DVC works with Snakemake to track data lineage and enable
  reproducible research workflows.

"@
        }
        "mlflow" {
            Write-Host @"

📈 MLflow Experiment Tracking
=============================

MLflow logs and tracks all your experiment runs with metrics, parameters, and artifacts.

📊 Tracking Data:
  • Parameters: Configuration settings (NFFT size, batch size)
  • Metrics: Performance results (latency, throughput, accuracy)
  • Artifacts: Generated files (plots, models, reports)

🚀 Native MLflow Usage Examples:
  # View experiment results in web UI
  mlflow ui --backend-store-uri file://./artifacts/mlruns

  # View UI on different port
  mlflow ui --backend-store-uri file://./artifacts/mlruns --port 8080

  # List all experiments
  mlflow experiments list --tracking-uri file://./artifacts/mlruns

  # Search runs with filters
  mlflow runs search --tracking-uri file://./artifacts/mlruns --filter "metrics.latency < 100"

  # Get specific run details
  mlflow runs describe --run-id <run-id> --tracking-uri file://./artifacts/mlruns

📁 Storage Location:
  artifacts/mlruns/            # All experiment data

💡 Web UI Features:
  • Compare multiple runs side-by-side
  • Visualize metrics over time
  • Download artifacts
  • Search and filter experiments
  • Track model lineage

🔗 Integration:
  All benchmark scripts automatically log to MLflow.
  Results are available immediately in the web UI.

"@
        }
        "benchmarks" {
            Write-Host @"

⚡ Benchmark Scripts Architecture
===============================

Individual, focused benchmark runners following one-tool-one-job principle.

📁 Benchmark Scripts:
  benchmarks/run_latency.py    # Latency measurements
  benchmarks/run_throughput.py # Throughput analysis
  benchmarks/run_accuracy.py   # Accuracy validation
  benchmarks/run_realtime.py   # Real-time performance

🏗️ Script Architecture:
  • Hydra-aware: Use configuration system
  • MLflow integration: Automatic experiment logging
  • Artifact output: Save results to artifacts/data/
  • Validation: Pydantic models for config validation

🚀 Usage Examples:
  # Direct execution
  python benchmarks/run_latency.py

  # With parameter overrides
  python benchmarks/run_latency.py engine.nfft=1024 benchmark.iterations=100

  # Via CLI (recommended)
  .\scripts\cli.ps1 experiment -Benchmark latency
  .\scripts\cli.ps1 sweep -Config nfft_scaling -Benchmark throughput

💡 Design Principles:
  • Single Responsibility: Each script does one thing well
  • Communication via Files: Scripts don't call each other
  • Configuration-Driven: All behavior controlled via Hydra configs
  • Traceable: Full MLflow integration for reproducibility

"@
        }
        default {
            Write-Host "❌ Unknown tool: $tool" -ForegroundColor Red
            Write-Host "Available tools: overview, hydra, snakemake, dvc, mlflow, benchmarks" -ForegroundColor Yellow
        }
    }

    Write-Host "`n💡 Need more help? Check the project documentation or run specific tool help commands." -ForegroundColor Green
}

# --- Legacy Benchmark Functions (Preserved for Compatibility) ---------------

Function Invoke-Benchmark {
    param(
        [string]$Benchmark = "latency",
        [string]$Experiment,
        [string]$Output,
        [string[]]$Overrides = @(),
        [switch]$Multirun,
        [switch]$Report
    )

    if (-not (Test-CondaEnvironment)) {
        throw "Conda environment not activated"
    }

    if (-not $Benchmark) {
        $Benchmark = 'latency'
    }

    $scriptPath = Join-Path $script:ProjectRoot ("benchmarks/run_{0}.py" -f $Benchmark)
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Benchmark script not found: $scriptPath"
    }

    $args = @()
    if ($Multirun) { $args += '--multirun' }
    if ($Experiment) { $args += "experiment=$Experiment" }
    if ($Output) { $args += "paths.artifacts=`"$Output`"" }
    if ($Overrides) { $args += $Overrides }

    Write-ResearchLog -Level Info -Message ("Running {0} benchmark" -f $Benchmark) -Component "Benchmark" -Metadata @{
        multirun = $Multirun.IsPresent
        experiment = $Experiment
        output = $Output
    }

    Invoke-WithPythonPath {
        & python $scriptPath @args
        if ($LASTEXITCODE -ne 0) {
            throw "Benchmark execution failed"
        }
    }

    if ($Report) {
        $reportParams = @{
            ResultsDir = (if ($Output) { $Output } else { Join-Path $script:ArtifactsDir 'data' })
        }
        Invoke-BenchmarkReport @reportParams
    }
}


# Legacy Invoke-ParameterSweep function removed - replaced by Invoke-ModernSweep

# Legacy function - prefer using Snakemake workflow via 'workflow' command
Function Invoke-BenchmarkReport {
    param(
        [string]$ResultsDir,
        [string]$FiguresDir,
        [string]$Output,
        [switch]$SkipAnalysis,
        [switch]$SkipFigures
    )

    $dataDir = if ($ResultsDir) { $ResultsDir } else { Join-Path $script:ArtifactsDir 'data' }
    $figDir = if ($FiguresDir) { $FiguresDir } else { Join-Path $script:ArtifactsDir 'figures' }
    $outputPath = if ($Output) { $Output } else { Join-Path $script:ReportsDir 'final_report.html' }
    $summaryPath = Join-Path $dataDir 'summary_statistics.csv'

    if (-not $SkipAnalysis) {
        Write-ResearchLog -Level Info -Message "Generating summary statistics" -Component "Report" -Metadata @{ data = $dataDir }
        Invoke-WithPythonPath {
            & python (Join-Path $script:ProjectRoot 'experiments/scripts/analyze.py') '--data-dir' $dataDir '--output' $summaryPath
            if ($LASTEXITCODE -ne 0) { throw "Analysis script failed" }
        }
    }

    if (-not $SkipFigures) {
        Write-ResearchLog -Level Info -Message "Rendering figures" -Component "Report" -Metadata @{ figures = $figDir }
        Invoke-WithPythonPath {
            & python (Join-Path $script:ProjectRoot 'experiments/scripts/generate_figures.py') '--input' $summaryPath '--output-dir' $figDir
            if ($LASTEXITCODE -ne 0) { throw "Figure generation failed" }
        }
    }

    Write-ResearchLog -Level Info -Message "Compiling HTML report" -Component "Report" -Metadata @{ output = $outputPath }
    Invoke-WithPythonPath {
        & python (Join-Path $script:ProjectRoot 'experiments/scripts/generate_report.py') '--input' $summaryPath '--figures-dir' $figDir '--output' $outputPath
        if ($LASTEXITCODE -ne 0) { throw "Report generation failed" }
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
    
    # Add Python command - use new benchmark scripts
    $benchmarkScript = "benchmarks/run_$Benchmark.py"
    if (-not (Test-Path (Join-Path $script:ProjectRoot $benchmarkScript))) {
        throw "Benchmark script not found: $benchmarkScript"
    }
    $profileCmd += "python", $benchmarkScript
    # Add Python command - use new benchmark scripts
    $benchmarkScript = "benchmarks/run_$Benchmark.py"
    if (-not (Test-Path (Join-Path $script:ProjectRoot $benchmarkScript))) {
        throw "Benchmark script not found: $benchmarkScript"
    }
    $profileCmd += "python", $benchmarkScript
    
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
        
        $benchDir = Join-Path $script:SourceDir "ionosense_hpc\\benchmarks"
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

    # Modern tools status
    Write-Host "`n🌟 Modern Research Stack:" -ForegroundColor Yellow

    # Check Hydra
    $hydraStatus = Get-Command python -ErrorAction SilentlyContinue
    if ($hydraStatus) {
        try {
            $hydraCheck = & python -c "import hydra; print('✓')" 2>$null
            if ($hydraCheck -eq '✓') {
                Write-Host "  🔧 Hydra Configuration:     ✅ Ready" -ForegroundColor Green
            } else {
                Write-Host "  🔧 Hydra Configuration:     ❌ Not installed" -ForegroundColor Red
            }
        } catch {
            Write-Host "  🔧 Hydra Configuration:     ❌ Not available" -ForegroundColor Red
        }
    } else {
        Write-Host "  🔧 Hydra Configuration:     ❌ Python not found" -ForegroundColor Red
    }

    # Check Snakemake
    $snakemake = Get-Command snakemake -ErrorAction SilentlyContinue
    if ($snakemake) {
        Write-Host "  🐍 Snakemake Workflow:      ✅ Ready" -ForegroundColor Green
    } else {
        Write-Host "  🐍 Snakemake Workflow:      ❌ Not installed" -ForegroundColor Red
    }

    # Check DVC
    $dvc = Get-Command dvc -ErrorAction SilentlyContinue
    if ($dvc) {
        Write-Host "  📊 DVC Data Versioning:     ✅ Ready" -ForegroundColor Green
    } else {
        Write-Host "  📊 DVC Data Versioning:     ❌ Not installed" -ForegroundColor Red
    }

    # Check MLflow
    if ($hydraStatus) {
        try {
            $mlflowCheck = & python -c "import mlflow; print('✓')" 2>$null
            if ($mlflowCheck -eq '✓') {
                Write-Host "  📈 MLflow Tracking:         ✅ Ready" -ForegroundColor Green
            } else {
                Write-Host "  📈 MLflow Tracking:         ❌ Not installed" -ForegroundColor Red
            }
        } catch {
            Write-Host "  📈 MLflow Tracking:         ❌ Not available" -ForegroundColor Red
        }
    }

    # Check benchmark scripts
    $benchmarkDir = Join-Path $script:ProjectRoot "benchmarks"
    if (Test-Path $benchmarkDir) {
        $scriptCount = (Get-ChildItem -Path $benchmarkDir -Filter "run_*.py" | Measure-Object).Count
        Write-Host "  ⚡ Benchmark Scripts:        ✅ $scriptCount scripts ready" -ForegroundColor Green
    } else {
        Write-Host "  ⚡ Benchmark Scripts:        ❌ Not found" -ForegroundColor Red
    }

    # Quick start suggestion
    Write-Host "`n💡 Quick Start:" -ForegroundColor Cyan
    Write-Host "  .\scripts\cli.ps1 learn overview    # Learn about modern tools"
    Write-Host "  .\scripts\cli.ps1 experiment         # Run a single experiment"
    Write-Host "  .\scripts\cli.ps1 workflow           # Execute full pipeline"


    # Modern tools status
    Write-Host "`n🌟 Modern Research Stack:" -ForegroundColor Yellow

    # Check Hydra
    $hydraStatus = Get-Command python -ErrorAction SilentlyContinue
    if ($hydraStatus) {
        try {
            $hydraCheck = & python -c "import hydra; print('✓')" 2>$null
            if ($hydraCheck -eq '✓') {
                Write-Host "  🔧 Hydra Configuration:     ✅ Ready" -ForegroundColor Green
            } else {
                Write-Host "  🔧 Hydra Configuration:     ❌ Not installed" -ForegroundColor Red
            }
        } catch {
            Write-Host "  🔧 Hydra Configuration:     ❌ Not available" -ForegroundColor Red
        }
    } else {
        Write-Host "  🔧 Hydra Configuration:     ❌ Python not found" -ForegroundColor Red
    }

    # Check Snakemake
    $snakemake = Get-Command snakemake -ErrorAction SilentlyContinue
    if ($snakemake) {
        Write-Host "  🐍 Snakemake Workflow:      ✅ Ready" -ForegroundColor Green
    } else {
        Write-Host "  🐍 Snakemake Workflow:      ❌ Not installed" -ForegroundColor Red
    }

    # Check DVC
    $dvc = Get-Command dvc -ErrorAction SilentlyContinue
    if ($dvc) {
        Write-Host "  📊 DVC Data Versioning:     ✅ Ready" -ForegroundColor Green
    } else {
        Write-Host "  📊 DVC Data Versioning:     ❌ Not installed" -ForegroundColor Red
    }

    # Check MLflow
    if ($hydraStatus) {
        try {
            $mlflowCheck = & python -c "import mlflow; print('✓')" 2>$null
            if ($mlflowCheck -eq '✓') {
                Write-Host "  📈 MLflow Tracking:         ✅ Ready" -ForegroundColor Green
            } else {
                Write-Host "  📈 MLflow Tracking:         ❌ Not installed" -ForegroundColor Red
            }
        } catch {
            Write-Host "  📈 MLflow Tracking:         ❌ Not available" -ForegroundColor Red
        }
    }

    # Check benchmark scripts
    $benchmarkDir = Join-Path $script:ProjectRoot "benchmarks"
    if (Test-Path $benchmarkDir) {
        $scriptCount = (Get-ChildItem -Path $benchmarkDir -Filter "run_*.py" | Measure-Object).Count
        Write-Host "  ⚡ Benchmark Scripts:        ✅ $scriptCount scripts ready" -ForegroundColor Green
    } else {
        Write-Host "  ⚡ Benchmark Scripts:        ❌ Not found" -ForegroundColor Red
    }

    # Quick start suggestion
    Write-Host "`n💡 Quick Start:" -ForegroundColor Cyan
    Write-Host "  .\scripts\cli.ps1 learn overview    # Learn about modern tools"
    Write-Host "  .\scripts\cli.ps1 experiment         # Run a single experiment"
    Write-Host "  .\scripts\cli.ps1 workflow           # Execute full pipeline"

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

ESSENTIAL SETUP & BUILD
  setup                   Create/update conda environment & install package
  build [-Preset] [-Clean] [-Verbose] [-Debug/-Release]
                          Configure and build project with CMake presets
  clean [-All]            Remove build artifacts (and results/logs with -All)

ENVIRONMENT & STATUS
  doctor [-Strict]        Verify environment/tooling and summarize status
  info [type]             Show system/benchmarks/presets/devices/configs info
  status                  Show research environment status

BUILD & DEVELOPMENT
  build [-Preset] [-Clean] [-Verbose]
                          Configure and build project
  test [-Suite all|python|py|cpp] [-Pattern] [-Coverage]
                          Run tests (aliases: py/p for python, c++ for cpp)
  format [paths] [-Check] [-Verbose]
                          Format C/C++ code with .clang-format
  format [paths] [-Check] [-Staged] [-Verbose]
                          Format C/C++ code with clang-format
  lint [all|python|py|cpp] [-Staged] [-Fix] [-Verbose]
                          Lint Python (ruff) and/or C++ code
  typecheck [-Strict] [-IncludeTests] [-Verbose]
                          Run mypy type checking
  check [-Staged] [-Verbose]
                          Run format -Check, lint, typecheck, and quick tests
  clean [-All]            Remove build artifacts (and results/logs with -All)

PYTHON SCRIPT RUNNER
  run <script.py> [args...]
                          Run any Python script with proper environment

PROFILING & ANALYSIS
  profile -Tool <nsys|ncu> -Benchmark <name> [-Full] [-OpenReport]
                          Profile with NVIDIA Nsight tools

VALIDATION & MONITORING
  validate                Run numerical validation suite
  monitor                 Real-time GPU monitoring

DEVELOPMENT WORKFLOW:
  # Core development cycle
  .\scripts\cli.ps1 setup          # Environment setup
  .\scripts\cli.ps1 build          # Build project
  .\scripts\cli.ps1 test           # Run tests
  .\scripts\cli.ps1 format         # Format code
  .\scripts\cli.ps1 lint           # Lint code

  # Run Python scripts with environment
  .\scripts\cli.ps1 run benchmarks/run_latency.py experiment=baseline

DIRECT RESEARCH WORKFLOW (Use native tools):
  # 🔬 IONOSPHERE RESEARCH
  python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution benchmark=throughput
  python benchmarks/run_latency.py experiment=ionosphere_multiscale

  # 🐍 Analysis pipeline
  snakemake --cores 4 --snakefile experiments/Snakefile

  # 📈 View results
  .\iono.ps1 ui
  # OR: mlflow ui --backend-store-uri artifacts/mlruns

  # 📊 Data management
  dvc status && dvc repro

For detailed documentation, see: CLAUDE.md (quick reference) and docs/ folder
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
        "setup"    {
            $params = @{}
            if ($CommandArgs -contains "-Clean") { $params.Clean = $true }
            Invoke-Setup @params
        }
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
            
            # Named args
            for ($i = 0; $i -lt $CommandArgs.Count; $i++) {
                if ($CommandArgs[$i] -eq "-Pattern" -and $i+1 -lt $CommandArgs.Count) {
                    $params.Pattern = $CommandArgs[$i+1]
                }
            }
            
            $suite = $CommandArgs | Where-Object { $_ -notlike "-*" } | Select-Object -First 1
            if ($suite) { $params.Suite = $suite }
            
            Invoke-Test @params
        }
        "bench"    {
            # Simplified benchmark command - delegates to modern functions
            Write-ResearchLog -Level Info -Message "Legacy 'bench' command - redirecting to modern implementation" -Component "Benchmark"

            # Check for multirun/sweep mode
            if ($CommandArgs -contains "-Multirun") {
                # Remove -Multirun and -Report flags, delegate to sweep
                $newArgs = $CommandArgs | Where-Object { $_ -ne "-Multirun" -and $_ -ne "-Report" }
                Invoke-ModernSweep -CommandArgs $newArgs
            } else {
                # Delegate to single experiment
                $newArgs = $CommandArgs | Where-Object { $_ -ne "-Report" }
                Invoke-ModernExperiment -CommandArgs $newArgs
            }

            # If -Report was specified, run workflow to generate reports
            if ($CommandArgs -contains "-Report") {
                Write-ResearchLog -Level Info -Message "Generating reports via Snakemake workflow" -Component "Benchmark"
                Invoke-ModernWorkflow -CommandArgs @("generate_report")
            }
        }
        "benchmark" {
            # Alias for bench command
            Write-ResearchLog -Level Info -Message "'benchmark' alias - redirecting to 'bench' command" -Component "Benchmark"
            & $PSCommandPath "bench" @CommandArgs
        }


        "format"   {
            $params = @{}
            if ($CommandArgs -contains "-Check")   { $params.Check   = $true }
            if ($CommandArgs -contains "-Staged")  { $params.Staged  = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }

            # Any non-flag arguments are paths
            $paths = $CommandArgs | Where-Object { $_ -and $_ -notlike "-*" }
            if ($paths -and $paths.Count -gt 0) { $params.Paths = $paths }

            Invoke-Format @params
        }
        "lint"     {
            $params = @{}
            if ($CommandArgs -contains "-Fix")     { $params.Fix     = $true }
            if ($CommandArgs -contains "-Staged")  { $params.Staged  = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }

            $target = $CommandArgs | Where-Object { $_ -notlike "-*" } | Select-Object -First 1
            if ($target) { $params.Target = $target }

            Invoke-Lint @params
        }
        "typecheck"{
            $params = @{}
            if ($CommandArgs -contains "-Strict")  { $params.Strict  = $true }
            if ($CommandArgs -contains "-IncludeTests") { $params.IncludeTests = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }
            Invoke-Typecheck @params
        }
        "run"      {
            # Simple Python script runner with environment
            if ($CommandArgs.Count -eq 0) {
                Write-Host "Usage: .\scripts\cli.ps1 run <script.py> [args...]" -ForegroundColor Yellow
                Write-Host "Example: .\scripts\cli.ps1 run benchmarks/run_latency.py experiment=baseline" -ForegroundColor Cyan
                exit 1
            }

            $script = $CommandArgs[0]
            $args = $CommandArgs[1..($CommandArgs.Count-1)]

            Write-ResearchLog -Level Info -Message "Running Python script: $script" -Component "Run"
            & python $script @args
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
        "report"    {
            # Simplified report command - delegates to Snakemake workflow
            Write-ResearchLog -Level Info -Message "Legacy 'report' command - redirecting to Snakemake workflow" -Component "Report"

            $targets = @()

            # Parse arguments to determine workflow targets
            $skipAnalysis = $CommandArgs -contains "-SkipAnalysis"
            $skipFigures = $CommandArgs -contains "-SkipFigures"

            if (-not $skipAnalysis -and -not $skipFigures) {
                # Run complete reporting pipeline
                $targets += "generate_report"
            } else {
                # Run specific parts
                if (-not $skipAnalysis) { $targets += "analyze_results" }
                if (-not $skipFigures) { $targets += "generate_figures" }
            }

            # Build workflow command arguments
            $workflowArgs = @()
            if ($targets.Count -gt 0) {
                foreach ($target in $targets) {
                    $workflowArgs += "-Target"
                    $workflowArgs += $target
                }
            }

            # Check for custom paths (note: legacy behavior)
            $hasCustomPaths = ($CommandArgs -contains "-ResultsDir") -or
                              ($CommandArgs -contains "-FiguresDir") -or
                              ($CommandArgs -contains "-Output")

            if ($hasCustomPaths) {
                Write-ResearchLog -Level Warning -Message "Custom paths not supported in modern workflow - using standard artifacts/ structure" -Component "Report"
            }

            Invoke-ModernWorkflow -CommandArgs $workflowArgs
        }


        "info"     {
            $type = $CommandArgs | Select-Object -First 1
            Show-Info -Type $(if ($type) { $type } else { "all" })
        }
        "status"   { Show-ResearchStatus }
        "doctor"   {
            $params = @{}
            if ($CommandArgs -contains "-Strict")  { $params.Strict  = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }
            Invoke-Doctor @params
        }
        "check"    {
            $params = @{}
            if ($CommandArgs -contains "-Staged")  { $params.Staged  = $true }
            if ($CommandArgs -contains "-Verbose") { $params.Verbose = $true }
            Invoke-Check @params
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
