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

Function Install-ProfileHelper {
    $helperPath = Join-Path $PythonDir "src\ionosense_hpc\tools\profile_helper.py"
    $helperDir = Split-Path $helperPath -Parent
    
    if (-not (Test-Path $helperDir)) {
        New-Item -ItemType Directory -Path $helperDir -Force | Out-Null
    }
    
    # The Python script content would be written here
    # For now, assume it's already saved
    
    if (Test-Path $helperPath) {
        return $helperPath
    } else {
        return $null
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
    warn "Clang-tidy runs as part of the build. Check the output below for warnings."
    # We call the build but check the exit code here to determine success
    cmd_build -Preset "windows-debug"
    if ($LASTEXITCODE -eq 0) {
        return $true
    } else {
        return $false
    }
}

# =========================
# Clickable links + openers
# =========================

function Write-Hyperlink {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Text,
        [Parameter(Mandatory)][string]$Uri
    )
    $esc = [char]27
    $st_bel = [char]7
    $oscStart = "$esc]8;;$Uri$st_bel"
    $oscEnd   = "$esc]8;;$st_bel"

    # Terminals that usually support OSC 8
    $supportsOsc8 = $false
    if ($env:WT_SESSION) { $supportsOsc8 = $true }               # Windows Terminal
    elseif ($env:TERM_PROGRAM -eq 'vscode') { $supportsOsc8 = $true }  # VS Code
    elseif ($env:TERM -match 'xterm|wezterm|alacritty|kitty|tmux') { $supportsOsc8 = $true }

    if ($supportsOsc8) {
        Write-Host "$oscStart$Text$oscEnd"
    }
    # Always print a fallback URI that’s usually clickable
    Write-Host $Uri
}

function Write-ClickablePath {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$Label = "Open"
    )
    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $uri = ([System.Uri]::new($resolved)).AbsoluteUri   # file:///C:/...
    Write-Hyperlink -Text $Label -Uri $uri
}

function Open-In-Files {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [switch]$Select
    )
    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $dir  = Split-Path -Parent $resolved

    if ($IsWindows) {
        if ($Select) {
            Start-Process explorer.exe "/select,`"$resolved`""
        } else {
            Start-Process explorer.exe "`"$dir`""
        }
    } elseif ($IsMacOS) {
        if ($Select) {
            # macOS doesn’t have “select” semantic in Finder CLI; open the dir.
            Start-Process open $dir
        } else {
            Start-Process open $dir
        }
    } else {
        Start-Process xdg-open $dir
    }
}

# =========================
# Nsight GUI resolvers/launchers
# =========================

function Resolve-Executable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string[]]$CandidateNames,
        [string[]]$ExtraSearchDirs = @()
    )
    # 1) PATH
    foreach ($name in $CandidateNames) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }

    # 2) Well-known install locations
    $search = @()
    if ($IsWindows) {
        $search += @(
            Join-Path $env:ProgramFiles 'NVIDIA Corporation'
            Join-Path $env:ProgramFiles 'NVIDIA GPU Computing Toolkit'
        )
    } else {
        $search += @('/opt/nvidia', '/usr/local', '/usr')
    }
    if ($ExtraSearchDirs) { $search += $ExtraSearchDirs }

    $results = foreach ($root in $search | Where-Object { Test-Path $_ }) {
        Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $CandidateNames -contains $_.Name }
    }

    if ($results) {
        # Prefer newest modified binary
        $pick = $results | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        return $pick.FullName
    }
    return $null
}

function Open-In-NsightSystems {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ReportPath
    )
    $exe = Resolve-Executable -CandidateNames @(
        'nsys-ui.exe','nsys-ui','nsight-systems.exe','nsight-systems'
    ) -ExtraSearchDirs @(
        # Windows typical:
        (Join-Path $env:ProgramFiles 'NVIDIA Corporation'),
        # Linux typical:
        '/opt/nvidia/nsight-systems','/opt/nvidia/nsight-systems/bin'
    )

    if (-not $exe) {
        Write-Warning "Nsight Systems GUI not found. Try launching manually and opening: $ReportPath"
        return
    }
    Start-Process $exe --% "$ReportPath"
}

function Open-In-NsightCompute {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ReportPath
    )
    $exe = Resolve-Executable -CandidateNames @(
        'nsight-compute.exe','nsight-compute','nv-nsight-cu.exe','nv-nsight-cu','ncu-ui.exe','ncu-ui'
    ) -ExtraSearchDirs @(
        # Windows typical:
        (Join-Path $env:ProgramFiles 'NVIDIA Corporation'),
        # Linux typical:
        '/opt/nvidia/nsight-compute','/opt/nvidia/nsight-compute/bin'
    )

    if (-not $exe) {
        Write-Warning "Nsight Compute GUI not found. Try launching manually and opening: $ReportPath"
        return
    }
    Start-Process $exe --% "$ReportPath"
}

# =========================
# Report discovery + pretty output
# =========================

function Find-LatestProfileReport {
    [CmdletBinding(DefaultParameterSetName='ByDir')]
    param(
        [Parameter(ParameterSetName='ByDir',Mandatory=$true)][string]$Directory,
        [Parameter(ParameterSetName='ByBase',Mandatory=$true)][string]$BaseWithoutExt,
        [Parameter(Mandatory=$true)][ValidateSet('nsys','ncu')]$Kind
    )
    $candidates = @()
    if ($PSCmdlet.ParameterSetName -eq 'ByBase') {
        if ($Kind -eq 'nsys') {
            $candidates += @("$BaseWithoutExt.qdrep", "$BaseWithoutExt.nsys-rep", "$BaseWithoutExt.sqlite")
        } else {
            $candidates += @("$BaseWithoutExt.ncu-rep")
        }
    } else {
        if ($Kind -eq 'nsys') {
            $candidates += Get-ChildItem -Path $Directory -Filter '*.qdrep' -File -ErrorAction SilentlyContinue
            $candidates += Get-ChildItem -Path $Directory -Filter '*.nsys-rep' -File -ErrorAction SilentlyContinue
            $candidates += Get-ChildItem -Path $Directory -Filter '*.sqlite' -File -ErrorAction SilentlyContinue
        } else {
            $candidates += Get-ChildItem -Path $Directory -Filter '*.ncu-rep' -File -ErrorAction SilentlyContinue
        }
        $candidates = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -ExpandProperty FullName -First 1
        return $candidates
    }

    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
    }
    return $null
}

function Show-ProfileArtifacts {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][ValidateSet('nsys','ncu')]$Kind,
        [string]$ReportPath,
        [string]$OutputDir,          # used if ReportPath is not provided
        [switch]$OpenFolder,
        [switch]$SelectFile,
        [switch]$OpenGui
    )

    if (-not $ReportPath) {
        if (-not $OutputDir) { throw "Provide -ReportPath or -OutputDir." }
        $ReportPath = Find-LatestProfileReport -Directory $OutputDir -Kind $Kind
    }
    if (-not $ReportPath) {
        Write-Warning "No report found."
        return
    }

    Write-Host ""
    Write-Host "📦 Saved profile:"
    Write-ClickablePath -Path $ReportPath -Label "📄 Open report"
    Write-ClickablePath -Path (Split-Path -Parent $ReportPath) -Label "📂 Open folder"

    if ($OpenFolder) { Open-In-Files -Path $ReportPath -Select:$SelectFile }

    if ($OpenGui) {
        if ($Kind -eq 'nsys') { Open-In-NsightSystems -ReportPath $ReportPath }
        else { Open-In-NsightCompute -ReportPath $ReportPath }
    }
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
    
    $verboseFlag = if ($Preset -like "*debug*") { "--verbose" } else { $null }
    cmake --build --preset $Preset --parallel $verboseFlag
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

Function cmd_format {
    section "Formatting C++ Code"
    # A preset must be configured for the build directory to exist.
    $presetDir = Join-Path $BuildDir "windows-debug"
    if (-not (Test-Path "$presetDir/build.ninja")) {
        warn "Build directory not configured. Running configure step for 'windows-debug' preset..."
        cmake --preset "windows-debug"
    }
    cmake --build $presetDir --target format
    ok "C++ formatting complete."
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
        err "Usage: profile <nsys|ncu> <script_name> [--full] [--open] [--ui] [args...]"
        return
    }

    Ensure-EnvActivated

    $tool       = $ProfileArgs[0]
    $scriptName = $ProfileArgs[1]
    $scriptArgs = if ($ProfileArgs.Count -gt 2) { $ProfileArgs[2..($ProfileArgs.Length - 1)] } else { @() }

    # extract our flags; pass the rest to python
    $fullMode = $false; $openFlag = $false; $uiFlag = $false
    if ($scriptArgs -contains "--full") { $fullMode = $true;  $scriptArgs = $scriptArgs | Where-Object { $_ -ne "--full" } }
    if ($scriptArgs -contains "--open") { $openFlag = $true;  $scriptArgs = $scriptArgs | Where-Object { $_ -ne "--open" } }
    if ($scriptArgs -contains "--ui")   { $uiFlag   = $true;  $scriptArgs = $scriptArgs | Where-Object { $_ -ne "--ui" } }

    $moduleBase = "ionosense_hpc.benchmarks"
    $moduleName = "$moduleBase.$scriptName"

    $nsysDir = Join-Path $BuildDir "nsight_reports\nsys_reports"
    $ncuDir  = Join-Path $BuildDir "nsight_reports\ncu_reports"
    New-Item -ItemType Directory -Force -Path $nsysDir | Out-Null
    New-Item -ItemType Directory -Force -Path $ncuDir  | Out-Null

    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $mode      = if ($fullMode) { "full" } else { "quick" }
    $outFile   = "${scriptName}_${mode}_${timestamp}"

    # robust Windows check
    $onWindows = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
        [System.Runtime.InteropServices.OSPlatform]::Windows
    )

    # ===== Pretty link rendering (clean, labeled) =====
    function _PrintLinks([string]$reportPath, [string]$kind) {
        # Styles (safe on PS >=7; no-ops on older)
        $hasPSStyle = $PSStyle -ne $null
        $B   = if ($hasPSStyle) { $PSStyle.Bold } else { "" }
        $Dim = if ($hasPSStyle) { $PSStyle.Foreground.BrightBlack } else { "" }
        $Hi  = if ($hasPSStyle) { $PSStyle.Foreground.BrightGreen } else { "" }
        $R   = if ($hasPSStyle) { $PSStyle.Reset } else { "" }

        # Terminal OSC8 hyperlink support
        $supportsOsc8 = $false
        if ($env:WT_SESSION) { $supportsOsc8 = $true }
        elseif ($env:TERM_PROGRAM -eq 'vscode') { $supportsOsc8 = $true }
        elseif ($env:TERM -match 'xterm|wezterm|alacritty|kitty|tmux') { $supportsOsc8 = $true }

        # Paths + labels
        $resolved     = (Resolve-Path -LiteralPath $reportPath).Path
        $dir          = Split-Path -Parent $resolved
        $fileName     = [System.IO.Path]::GetFileName($resolved)
        $folderName   = Split-Path -Leaf $dir
        $uriFile      = ([System.Uri]$resolved).AbsoluteUri
        $uriFolder    = ([System.Uri](Resolve-Path -LiteralPath $dir).Path).AbsoluteUri
        $sizeStr      = try { "{0:N1} MB" -f ((Get-Item -LiteralPath $resolved).Length / 1MB) } catch { "" }

        # Hyperlink builder
        $esc = [char]27; $bel = [char]7
        function _HL($text, $uri) {
            if ($supportsOsc8) { return "$esc]8;;$uri$bel$text$esc]8;;$bel" }
            else { return "$text -> $uri" }
        }

        Write-Host ""
        Write-Host ("{0}📦 Saved profile{1}" -f ($Hi+$B), $R)
        Write-Host ("{0}────────────────────────────────────────────{1}" -f $Dim, $R)

        # Report line
        $openReport = _HL "Open report" $uriFile
        $kindLabel  = if ($kind -eq 'nsys') { "Nsight Systems" } elseif ($kind -eq 'ncu') { "Nsight Compute" } else { "Report" }
        Write-Host ("  📄 {0}: {1}  {2}({3}{4}{2})" -f $kindLabel, $openReport, $R, $Dim, "$fileName" + ($(if ($sizeStr) { " — $sizeStr" })))

        # Folder line
        $openFolder = _HL "Open folder" $uriFolder
        Write-Host ("  📂 Folder: {0}  {1}({2}{3}{1})" -f $openFolder, $R, $Dim, $dir)

        # Show raw URIs in dim text (copy-paste friendly) when OSC8 is supported
        if ($supportsOsc8) {
            Write-Host ("{0}     {1}{2}" -f $Dim, $uriFile, $R)
            Write-Host ("{0}     {1}{2}" -f $Dim, $uriFolder, $R)
        }

        Write-Host ("{0}────────────────────────────────────────────{1}" -f $Dim, $R)
    }

    # local: open file’s folder (and select file on Windows)
    function _OpenFolder([string]$reportPath) {
        try {
            $resolved = (Resolve-Path -LiteralPath $reportPath -ErrorAction Stop).Path
            $dir = Split-Path -Parent $resolved
            if ($onWindows) {
                Start-Process -FilePath explorer.exe -ArgumentList @("/select,`"$resolved`"")
            } elseif ($IsMacOS) {
                Start-Process -FilePath open -ArgumentList @($dir)
            } else {
                Start-Process -FilePath xdg-open -ArgumentList @($dir)
            }
        } catch {
            Write-Warning "Could not open folder: $($_.Exception.Message)"
        }
    }

    # local: find a GUI exe on PATH or common dirs
    function _ResolveExe([string[]]$names, [string[]]$extraDirs) {
        foreach ($n in $names) {
            $cmd = Get-Command $n -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        }
        $roots = @()
        if ($onWindows) {
            $roots += @(
                $env:ProgramFiles, $env:ProgramFilesX86,
                "$env:ProgramFiles\NVIDIA Corporation",
                "$env:ProgramFilesX86\NVIDIA Corporation"
            )
        } else {
            $roots += @('/opt/nvidia','/usr/local','/usr')
        }
        if ($extraDirs) { $roots += $extraDirs }
        foreach ($root in $roots | Where-Object { $_ -and (Test-Path $_) }) {
            foreach ($n in $names) {
                $hit = Get-ChildItem -Path $root -Recurse -File -Filter $n -ErrorAction SilentlyContinue |
                       Sort-Object LastWriteTime -Descending | Select-Object -First 1
                if ($hit) { return $hit.FullName }
            }
        }
        return $null
    }

    # local: launch Nsight UIs
    function _OpenNsightSystems([string]$reportPath) {
        $exe = _ResolveExe @('nsys-ui.exe','nsys-ui','nsight-systems.exe','nsight-systems') @()
        if (-not $exe) { Write-Warning "Nsight Systems GUI not found. Open manually and load: $reportPath"; return }
        $wd = Split-Path -Parent $reportPath
        Start-Process -FilePath $exe -WorkingDirectory $wd -ArgumentList @("$reportPath")
    }
    function _OpenNsightCompute([string]$reportPath) {
        $exe = _ResolveExe @('nsight-compute.exe','nsight-compute','nv-nsight-cu.exe','nv-nsight-cu','ncu-ui.exe','ncu-ui') @()
        if (-not $exe) { Write-Warning "Nsight Compute GUI not found. Open manually and load: $reportPath"; return }
        $wd = Split-Path -Parent $reportPath
        Start-Process -FilePath $exe -WorkingDirectory $wd -ArgumentList @("$reportPath")
    }

    section "Profiling ($tool $mode): $moduleName"

    With-PythonPath {
        switch ($tool) {
            'nsys' {
                $outBase = Join-Path $nsysDir $outFile
                $cmd = @('nsys','profile','-o',$outBase,'-f','true','--wait=all')

                if ($fullMode) {
                    log "Full mode: All available GPU traces (Windows-safe)"
                    $cmd += '--trace=cuda,cublas,cusolver,cusparse,nvtx,opengl,wddm'
                    $cmd += '--cuda-memory-usage=true'
                    $cmd += '--gpu-metrics-device=all'
                } else {
                    log "Quick mode: CUDA + NVTX only"
                    $cmd += '--trace=cuda,nvtx'
                }

                $cmd += 'python','-m',$moduleName
                if ($scriptArgs.Count -gt 0) { $cmd += $scriptArgs }

                & $cmd[0] $cmd[1..($cmd.Length-1)]
                if ($LASTEXITCODE -ne 0) { err "nsys exited with code $LASTEXITCODE"; return }

                $candidates = @("$outBase.qdrep","$outBase.nsys-rep","$outBase.sqlite")
                $reportPath = $null
                foreach ($p in $candidates) { if (Test-Path -LiteralPath $p) { $reportPath = (Resolve-Path -LiteralPath $p).Path; break } }

                if ($reportPath) {
                    try {
                        $sizeMB = [math]::Round((Get-Item -LiteralPath $reportPath).Length / 1MB, 2)
                        ok "Report saved: $([System.IO.Path]::GetFileName($reportPath)) ($sizeMB MB)"
                    } catch { ok "Report saved: $([System.IO.Path]::GetFileName($reportPath))" }

                    _PrintLinks $reportPath 'nsys'
                    if ($openFlag) { _OpenFolder $reportPath }
                    if ($uiFlag)   { _OpenNsightSystems $reportPath }
                } else {
                    err "Report not found"
                }
            }
            'ncu' {
                $outBase = Join-Path $ncuDir $outFile
                $cmd = @('ncu','-o',$outBase)

                if ($fullMode) {
                    warn "Full mode: heavy metric set (slow)"
                    $cmd += '--set','full'
                } else {
                    log "Quick mode: basic metric set"
                    $cmd += '--set','basic'
                }

                $cmd += 'python','-m',$moduleName
                if ($scriptArgs.Count -gt 0) { $cmd += $scriptArgs }

                & $cmd[0] $cmd[1..($cmd.Length-1)]
                if ($LASTEXITCODE -ne 0) { err "ncu exited with code $LASTEXITCODE"; return }

                $reportPath = "$outBase.ncu-rep"
                if (Test-Path -LiteralPath $reportPath) {
                    try {
                        $sizeMB = [math]::Round((Get-Item -LiteralPath $reportPath).Length / 1MB, 2)
                        ok "Report saved: $([System.IO.Path]::GetFileName($reportPath)) ($sizeMB MB)"
                    } catch { ok "Report saved: $([System.IO.Path]::GetFileName($reportPath))" }

                    _PrintLinks $reportPath 'ncu'
                    if ($openFlag) { _OpenFolder $reportPath }
                    if ($uiFlag)   { _OpenNsightCompute $reportPath }
                } else {
                    err "Report not found"
                }
            }
            default {
                err "Unknown profiler: '$tool'"
            }
        }
    }
}




# Command to check profiling reports status
Function cmd_profile_status {
    section "Profiling Reports Status"
    
    $reportsDir = Join-Path $BuildDir "nsight_reports"
    if (-not (Test-Path $reportsDir)) {
        warn "No reports directory found. Run a profiling session first."
        return
    }
    
    # Function to format age
    function Format-Age($lastWriteTime) {
        $age = (Get-Date) - $lastWriteTime
        if ($age.TotalMinutes -lt 60) { 
            return "$([int]$age.TotalMinutes)m ago" 
        } elseif ($age.TotalHours -lt 24) { 
            return "$([int]$age.TotalHours)h ago" 
        } else { 
            return "$([int]$age.TotalDays)d ago" 
        }
    }
    
    Write-Host "`n📊 NSIGHT SYSTEMS REPORTS:" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor DarkGray
    
    $nsysReports = Get-ChildItem -Path "$reportsDir\nsys_reports" -Filter "*.nsys-rep" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 10
    
    if ($nsysReports) {
        foreach ($report in $nsysReports) {
            $size = [math]::Round($report.Length / 1MB, 2)
            $age = Format-Age $report.LastWriteTime
            $name = $report.Name
            
            # Parse mode from filename if present
            $modeTag = if ($name -match "_full_") { "[FULL]" } 
                       elseif ($name -match "_quick_") { "[QUICK]" }
                       else { "" }
            
            Write-Host ("  {0,-45} {1,6}MB  {2,10}  {3}" -f $name.Substring(.0, [Math]::Min($name.Length, 45)), $size, $age, $modeTag)
        }
    } else {
        Write-Host "  No reports found" -ForegroundColor DarkGray
    }
    
    Write-Host "`n🔬 NSIGHT COMPUTE REPORTS:" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────" -ForegroundColor DarkGray
    
    $ncuReports = Get-ChildItem -Path "$reportsDir\ncu_reports" -Filter "*.ncu-rep" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 10
        
    if ($ncuReports) {
        foreach ($report in $ncuReports) {
            $size = [math]::Round($report.Length / 1MB, 2)
            $age = Format-Age $report.LastWriteTime
            $name = $report.Name
            
            $modeTag = if ($name -match "_full_") { "[FULL]" }
                       elseif ($name -match "_quick_") { "[QUICK]" }
                       else { "" }
            
            Write-Host ("  {0,-45} {1,6}MB  {2,10}  {3}" -f $name.Substring(0, [Math]::Min($name.Length, 45)), $size, $age, $modeTag)
        }
    } else {
        Write-Host "  No reports found" -ForegroundColor DarkGray
    }
    
    # Summary stats
    Write-Host "`n📈 SUMMARY:" -ForegroundColor Yellow
    Write-Host "─────────────────────────────────────────" -ForegroundColor DarkGray
    
    $allReports = @()
    if ($nsysReports) { $allReports += $nsysReports }
    if ($ncuReports) { $allReports += $ncuReports }
    
    if ($allReports.Count -gt 0) {
        $totalSize = ($allReports | Measure-Object -Property Length -Sum).Sum / 1MB
        $oldestReport = ($allReports | Sort-Object LastWriteTime | Select-Object -First 1)
        $newestReport = ($allReports | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
        
        Write-Host ("  Total reports:  {0}" -f $allReports.Count)
        Write-Host ("  Total size:     {0:N2} MB" -f $totalSize)
        Write-Host ("  Newest:         {0} ({1})" -f $newestReport.Name, (Format-Age $newestReport.LastWriteTime))
        Write-Host ("  Oldest:         {0} ({1})" -f $oldestReport.Name, (Format-Age $oldestReport.LastWriteTime))
    }
    
    Write-Host ""
    Write-Host "💡 TIP: Set IONO_USE_PY_PROFILER=1 to use the advanced Python profiler with progress tracking" -ForegroundColor DarkCyan
}

# Quick alias for common profiling tasks
Function cmd_qprof {
    param([string]$script = "latency")
    cmd_profile @("nsys", $script, "--quick")
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
  format                     Auto-format C++ code (clang-format)
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
$CommandArgs = @($Args | Select-Object -Skip 1)

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
    "lint"            { cmd_lint -LintArgs $CommandArgs }
    "format"          { cmd_format }
    "clean"           { cmd_clean }
    "list"            { cmd_list -ListArgs $CommandArgs }
    "bench"           { cmd_bench -BenchArgs $CommandArgs }
    "profile"         { cmd_profile -ProfileArgs $CommandArgs }
    "profile-status"  { cmd_profile_status }
    "qprof"           { cmd_qprof -script $(if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { "latency" }) }
    "validate"        { cmd_validate }
    "monitor"         { cmd_monitor }
    "info"            { cmd_info }
    default           { err "Unknown command: $Command"; Show-Usage; exit 1 }
}