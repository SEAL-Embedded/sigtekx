<#
 open_dev_pwsh.ps1 — pwsh7 → MSVC (x64) + optional conda/mamba activation
 - No hardcoded user paths
 - No conda/mamba hook dot-sourcing (prevents prompt duplication)
 - Uses VS DevShell first; vcvars fallback (safe Set-Item Env:)
 - Enforces 64-bit session (CUDA/MSVC need x64)
 - Interactive mode prompts to setup conda environment if missing/corrupted
#>

param(
    [string]$EnvName = 'ionosense-hpc',
    [ValidateSet('x64')][string]$VSArch = 'x64',   # lock to x64 for CUDA
    [string]$Repo = (Resolve-Path "$PSScriptRoot\.."),  # default: repo root (parent of /scripts)
    [switch]$NoConda,
    [switch]$Quiet,
    [switch]$Interactive
)

# ---- hard fail if not 64-bit pwsh ----
if (-not [Environment]::Is64BitProcess) {
    throw "This script must run in 64-bit PowerShell 7 (pwsh.exe), not powershell(x86). CUDA and MSVC require x64."
}

$ErrorActionPreference = 'Stop'
function Info($m){ if(-not $Quiet){ Write-Host $m -ForegroundColor Cyan } }
function Ok($m)  { if(-not $Quiet){ Write-Host $m -ForegroundColor Green } }
function Warn($m){ if(-not $Quiet){ Write-Warning $m } }

# ----- VS Dev Env -----
function Get-VswherePath {
    $pf   = [Environment]::GetEnvironmentVariable('ProgramFiles')
    $pf86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    $cands = @()
    if ($pf)   { $cands += [IO.Path]::Combine($pf,   'Microsoft Visual Studio','Installer','vswhere.exe') }
    if ($pf86) { $cands += [IO.Path]::Combine($pf86, 'Microsoft Visual Studio','Installer','vswhere.exe') }
    foreach ($p in $cands) { if (Test-Path $p) { return $p } }
    return $null
}

function Enter-VSDev {
    if (Get-Command cl -ErrorAction SilentlyContinue) { Info "MSVC already on PATH."; return }

    $vswhere = Get-VswherePath
    if (-not $vswhere) { Warn "vswhere.exe not found; skipping VS DevShell (install VS Build Tools to enable)."; return }

    $vsPath = & $vswhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath

    if ([string]::IsNullOrWhiteSpace($vsPath)) { Warn "No VS install with C++ tools detected."; return }

    $devShell = [IO.Path]::Combine($vsPath, 'Common7','Tools','Microsoft.VisualStudio.DevShell.dll')
    if (Test-Path $devShell) {
        try {
            Import-Module $devShell -ErrorAction Stop
            Enter-VsDevShell -VsInstallPath $vsPath -DevCmdArguments "-arch=$VSArch -host_arch=$VSArch" | Out-Null
            Ok "Entered VS DevShell ($VSArch)."
            return
        } catch {
            Warn "DevShell import failed: $($_.Exception.Message)"
        }
    }

    # Fallback: vcvars* → capture env safely
    $vcvarsRel = [IO.Path]::Combine('VC','Auxiliary','Build','vcvars64.bat')  # x64 only for CUDA/MSVC
    $vcvars = [IO.Path]::Combine($vsPath, $vcvarsRel)
    if (-not (Test-Path $vcvars)) { Warn "vcvars batch not found; cannot set MSVC env."; return }

    Info "Falling back to $(Split-Path -Leaf $vcvars)..."
    $envDump = cmd.exe /c "`"$vcvars`" & set"
    foreach ($line in $envDump) {
        $kv = $line -split '=',2
        if ($kv.Count -eq 2 -and $kv[0]) {
            Set-Item -Path ("Env:{0}" -f $kv[0]) -Value $kv[1]
        }
    }
    if (Get-Command cl -ErrorAction SilentlyContinue) { Ok "MSVC env loaded via vcvars." }
}

# ----- Conda/Mamba activation (no hook sourcing) -----
function Activate-CondaEnv {
    param([string]$Name)

    if ($NoConda) { return }
    if ($env:CONDA_DEFAULT_ENV -eq $Name) { Info "Conda env '$Name' already active."; return }

    # Check if the 'conda' command is available before trying to use it.
    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
        Warn "conda executable not found; cannot activate '$Name'."
        return
    }

    try {
        # Ask conda to generate the activation script for PowerShell and execute it.
        # This is the official, path-independent way to activate an environment.
        & conda shell.powershell activate $Name | Invoke-Expression

        # Verify that the activation was successful.
        if ($env:CONDA_DEFAULT_ENV -eq $Name) {
            Ok "Activated '$Name' via conda shell integration."
        } else {
            # This might happen if the conda command is a broken alias or function.
            Warn "Conda activation script ran, but the environment was not set as expected."
        }
    } catch {
        Warn "An error occurred during conda activation for '$Name'."
        Write-Warning $_.Exception.Message
        return
    }
}
# ----- Ensure conda is available on PATH (robust for non-profile sessions) -----
function Ensure-CondaOnPath {
    if (Get-Command conda -ErrorAction SilentlyContinue) { return }

    $candidates = @()

    if ($env:CONDA_EXE) {
        $candidates += (Split-Path -Parent $env:CONDA_EXE)
        $candidates += (Split-Path -Parent (Split-Path -Parent $env:CONDA_EXE))
    }
    if ($env:CONDA_PREFIX) { $candidates += $env:CONDA_PREFIX }

    $user = [Environment]::GetFolderPath('UserProfile')
    $programData = [Environment]::GetFolderPath('CommonApplicationData')

    $candidates += @(
        (Join-Path $user 'miniconda3'),
        (Join-Path $user 'mambaforge'),
        (Join-Path $user 'anaconda3'),
        (Join-Path $programData 'miniconda3'),
        (Join-Path $programData 'Anaconda3')
    )

    foreach ($root in $candidates | Where-Object { $_ -and (Test-Path $_) }) {
        $condabin = Join-Path $root 'condabin'
        $scripts  = Join-Path $root 'Scripts'
        $tryPaths = @(
            (Join-Path $condabin 'conda.bat'),
            (Join-Path $condabin 'conda.exe'),
            (Join-Path $scripts  'conda.exe')
        )
        foreach ($p in $tryPaths) {
            if (Test-Path $p) {
                $binDir = Split-Path -Parent $p
                if ($env:PATH -notlike "*${binDir}*") {
                    $env:PATH = "$binDir;" + $env:PATH
                }
                Info "Added conda to PATH: $binDir"
                return
            }
        }
    }
    Warn "conda not found on PATH and no standard install detected."
}

# ----- Optional: detect duplicate prompt decorators (inform only) -----
function Check-PromptDupes {
    try {
        $sb = (Get-Item function:\prompt -ErrorAction Stop).ScriptBlock.ToString()
        $n  = ([regex]::Matches($sb, 'CONDA_PROMPT_MODIFIER')).Count
        if ($n -gt 1) { Warn "Multiple conda/mamba prompt decorators detected (matches: $n). This script didn’t add any; check your PowerShell profiles." }
    } catch { }
}

# ----- Set a session-specific, conda-aware prompt -----
function Set-SessionPrompt {
    # Define a prompt function in the global scope for this session only.
    # This avoids permanently changing the user's profile.
    function global:prompt {
        if ($env:CONDA_DEFAULT_ENV) {
            # If a conda environment is active, display its name.
            Write-Host "($($env:CONDA_DEFAULT_ENV)) " -NoNewline -ForegroundColor Green
        }
        # Display the standard "PS C:\Path>" prompt.
        "PS $($executionContext.SessionState.Path.CurrentLocation)$('>' * ($nestedPromptLevel + 1)) "
    }
}

# ----- Interactive conda environment setup -----
function Test-CondaEnvironmentExists {
    param([string]$Name)

    if (-not (Get-Command conda -ErrorAction SilentlyContinue)) { return $false }

    $envList = conda env list 2>$null
    if ($LASTEXITCODE -ne 0) { return $false }

    return ($envList | Select-String -Quiet -Pattern "\b$Name\b")
}

function Test-GhostEnvironment {
    param([string]$Name)

    # Check if we're in an environment that doesn't exist in conda's registry
    return ($env:CONDA_DEFAULT_ENV -eq $Name) -and (-not (Test-CondaEnvironmentExists -Name $Name))
}

function Invoke-InteractiveEnvironmentSetup {
    param([string]$Name)

    if ($NoConda -or $Quiet) { return }

    $envExists = Test-CondaEnvironmentExists -Name $Name
    $isGhost = Test-GhostEnvironment -Name $Name

    if ($isGhost) {
        Warn "Detected ghost environment '$Name' - current session thinks it's active but conda doesn't recognize it."
        Write-Host "This usually happens after removing an environment while it was active." -ForegroundColor Yellow
        Write-Host ""
    }

    if (-not $envExists -or $isGhost) {
        Write-Host "Conda environment '$Name' " -NoNewline
        if ($isGhost) {
            Write-Host "needs to be recreated." -ForegroundColor Yellow
        } else {
            Write-Host "does not exist." -ForegroundColor Yellow
        }

        $response = Read-Host "Initialize conda environment '$Name'? (Y/n)"
        if ([string]::IsNullOrWhiteSpace($response) -or $response -match '^[Yy]') {
            Write-Host ""
            Info "Running environment setup..."

            try {
                # Force to base environment first if in ghost state
                if ($isGhost) {
                    $env:CONDA_DEFAULT_ENV = $null
                    $env:CONDA_PREFIX = $null
                    conda activate base 2>$null
                }

                # Run the setup command
                & (Join-Path $Repo 'scripts\cli.ps1') setup
                if ($LASTEXITCODE -eq 0) {
                    Ok "Environment setup completed successfully!"
                } else {
                    Warn "Environment setup failed. Continuing without conda activation."
                    return $false
                }
            } catch {
                Warn "Environment setup failed: $($_.Exception.Message)"
                return $false
            }
        } else {
            Info "Skipping environment setup. Use 'iono setup' manually when ready."
            return $false
        }
    }

    return $true
}

# ----- Run -----

# Set a default for colored logging in the Python backend.
# This allows the user to override it for the session if needed.
if (-not $env:IONO_LOG_COLOR) {
    $env:IONO_LOG_COLOR = "1"
    Info "Defaulted IONO_LOG_COLOR=1 for rich Python logging."
}

Enter-VSDev
Ensure-CondaOnPath

# Interactive environment setup (only if -Interactive flag is used)
$skipCondaActivation = $false
if ($Interactive) {
    $setupSuccess = Invoke-InteractiveEnvironmentSetup -Name $EnvName
    if (-not $setupSuccess) {
        Info "Continuing without conda environment activation."
        $skipCondaActivation = $true
    }
}

if (-not $skipCondaActivation) {
    Activate-CondaEnv -Name $EnvName
}
Check-PromptDupes
Set-SessionPrompt

# cd into repo root
if (Test-Path $Repo) {
    Set-Location $Repo
    if (-not $Quiet) { Info "Changed directory to $Repo" }
}

if (-not $Quiet) {
    Write-Host ""
    Ok  "Dev shell ready (pwsh $($PSVersionTable.PSVersion) x64)."
    $cl = (Get-Command cl   -ErrorAction SilentlyContinue).Source
    $nv = (Get-Command nvcc -ErrorAction SilentlyContinue).Source
    if ($cl) { Write-Host ("cl.exe : " + $cl) -ForegroundColor DarkGray }
    if ($nv) { Write-Host ("nvcc  : " + $nv) -ForegroundColor DarkGray }
    if ($env:CONDA_DEFAULT_ENV) { Write-Host ("env    : " + $env:CONDA_DEFAULT_ENV) -ForegroundColor DarkGray }
}


# === repo-aware CLI shortcuts (session-scoped, global funcs) ===

# Resolve repo root from this script's location; fallback to current dir
try {
    $scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
    $repoRoot   = Resolve-Path (Join-Path $scriptDir '..') -ErrorAction Stop
} catch {
    $repoRoot = Get-Location
}

# Persist paths for this pwsh session
$global:IONO_ROOT = "$repoRoot"
$global:IONO_CLI  = Join-Path $global:IONO_ROOT 'scripts\cli.ps1'

function global:iono {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args)
    if (-not (Test-Path $global:IONO_CLI)) {
        Write-Error "cli.ps1 not found at $global:IONO_CLI"
        return
    }

    # Only allow commands that actually exist in simplified CLI
    $validCommands = @('setup','build','test','coverage','lint','format','clean','doctor','ui','run','help','profile')
    if ($Args.Count -gt 0 -and $Args[0] -notin $validCommands) {
        Write-Warning "Command '$($Args[0])' not available. Use 'iono help' for available commands."
        Write-Host "💡 For research workflows, use direct tools:" -ForegroundColor Cyan
        Write-Host "   python benchmarks/run_latency.py experiment=baseline +benchmark=latency" -ForegroundColor Gray
        Write-Host "   python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput" -ForegroundColor Gray
        Write-Host "   snakemake --cores 4 --snakefile experiments/Snakefile" -ForegroundColor Gray
        Write-Host "   mlflow ui --backend-store-uri artifacts/mlruns" -ForegroundColor Gray
        return
    }

    if ($Args.Count -eq 0) {
        & $global:IONO_CLI
        return
    }

    $lowerArgs = @()
    foreach ($arg in $Args) {
        if ($null -ne $arg) {
            $lowerArgs += $arg.ToString().ToLowerInvariant()
        }
    }

    $injected = @()
    if ($PSBoundParameters.ContainsKey('Debug') -and -not ($lowerArgs -contains '--debug' -or $lowerArgs -contains '-debug')) {
        $injected += '--debug'
    }
    if ($PSBoundParameters.ContainsKey('Verbose') -and -not ($lowerArgs -contains '--verbose' -or $lowerArgs -contains '-verbose')) {
        $injected += '--verbose'
    }

    $processedArgs = @($Args[0])
    if ($injected.Count -gt 0) {
        $processedArgs += $injected
    }
    if ($Args.Count -gt 1) {
        $processedArgs += $Args[1..($Args.Count-1)]
    }

    & $global:IONO_CLI @processedArgs
}


# Essential CLI shortcuts (only for commands that actually exist)
function global:ib {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args)

    $common = @{}
    foreach ($name in @('Debug','Verbose')) {
        if ($PSBoundParameters.ContainsKey($name)) {
            $common[$name] = $PSBoundParameters[$name]
        }
    }

    if ($common.Count -gt 0) {
        iono @common build @Args
    } else {
        iono build @Args
    }
}
function global:it {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args)

    $common = @{}
    foreach ($name in @('Debug','Verbose')) {
        if ($PSBoundParameters.ContainsKey($name)) {
            $common[$name] = $PSBoundParameters[$name]
        }
    }

    if ($common.Count -gt 0) {
        iono @common test @Args
    } else {
        iono test @Args
    }
}
function global:ilint {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args)

    $common = @{}
    foreach ($name in @('Debug','Verbose')) {
        if ($PSBoundParameters.ContainsKey($name)) {
            $common[$name] = $PSBoundParameters[$name]
        }
    }

    if ($common.Count -gt 0) {
        iono @common lint @Args
    } else {
        iono lint @Args
    }
}
function global:ifmt {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args)

    $common = @{}
    foreach ($name in @('Debug','Verbose')) {
        if ($PSBoundParameters.ContainsKey($name)) {
            $common[$name] = $PSBoundParameters[$name]
        }
    }

    if ($common.Count -gt 0) {
        iono @common format @Args
    } else {
        iono format @Args
    }
}
function global:iclean {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args)

    $common = @{}
    foreach ($name in @('Debug','Verbose')) {
        if ($PSBoundParameters.ContainsKey($name)) {
            $common[$name] = $PSBoundParameters[$name]
        }
    }

    if ($common.Count -gt 0) {
        iono @common clean @Args
    } else {
        iono clean @Args
    }
}
function global:iprof {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args)

    $common = @{}
    foreach ($name in @('Debug','Verbose')) {
        if ($PSBoundParameters.ContainsKey($name)) {
            $common[$name] = $PSBoundParameters[$name]
        }
    }

    if ($common.Count -gt 0) {
        iono @common profile @Args
    } else {
        iono profile @Args
    }
}


# Use direct research tools instead of custom wrappers:
# python benchmarks/run_latency.py experiment=baseline
# python benchmarks/run_latency.py --multirun experiment=nfft_scaling
# snakemake --cores 4 --snakefile experiments/Snakefile
# mlflow ui --backend-store-uri artifacts/mlruns
# dvc status

# Simple test shortcuts
function global:itp { it python }         # python tests
function global:itc { it cpp }            # c++ tests

# Recommended native research workflow:
# python benchmarks/run_latency.py experiment=baseline +benchmark=latency
# python benchmarks/run_latency.py --multirun experiment=nfft_scaling +benchmark=latency
# python benchmarks/run_throughput.py --multirun experiment=ionosphere_resolution +benchmark=throughput
# snakemake --cores 4 --snakefile experiments/Snakefile
# mlflow ui --backend-store-uri artifacts/mlruns
# dvc status && dvc repro

# Help shortcuts (use CLI help instead of removed learn commands)
function global:ihelp { iono help }

# Reload iono functions (useful when init_pwsh.ps1 is updated)
function global:ireload {
    Write-Host "Reloading iono functions..." -ForegroundColor Cyan
    . (Join-Path $global:IONO_ROOT 'scripts\init_pwsh.ps1') -Quiet
    Write-Host "Functions reloaded. Try: iono profile nsys latency" -ForegroundColor Green
}

# Tab-completion (only for commands that actually exist)
$global:IonoVerbs   = @('setup','build','test','coverage','lint','format','clean','doctor','ui','run','help','profile')
$global:IonoTargets = @('python','cpp','all','-Clean','--clean','-Verbose','--verbose','--debug','--release','-Fix','-Check','-Coverage','-Pattern','-All','nsys','ncu','latency','throughput','accuracy','realtime','custom','-Full','-NoOpen','-Mode','-Script','-Kernel','-Duration')

Register-ArgumentCompleter -CommandName iono,ib,it,ilint,ifmt,iclean,itp,itc,ihelp,iprof -ScriptBlock {
    param($commandName,$parameterName,$wordToComplete,$commandAst,$fakeBoundParameters)
    $tokens = @()
    foreach ($e in $commandAst.CommandElements) {
        if ($e.Extent.Text -ne $commandName) { $tokens += $e.Extent.Text }
    }
    if ($commandName -eq 'iono' -and $tokens.Count -eq 0) {
        $list = $global:IonoVerbs
    } else {
        $list = $global:IonoTargets + $global:IonoVerbs
    }
    foreach ($it in $list) {
        if ($it -like "$wordToComplete*") {
            [System.Management.Automation.CompletionResult]::new($it,$it,'ParameterValue',$it)
        }
    }
}

