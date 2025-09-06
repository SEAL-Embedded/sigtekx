<# 
 open_dev_pwsh.ps1 — pwsh7 → MSVC (x64) + optional conda/mamba activation
 - No hardcoded user paths
 - No conda/mamba hook dot-sourcing (prevents prompt duplication)
 - Uses VS DevShell first; vcvars fallback (safe Set-Item Env:)
 - Enforces 64-bit session (CUDA/MSVC need x64)
#>

param(
    [string]$EnvName = 'ionosense-hpc',
    [ValidateSet('x64')][string]$VSArch = 'x64',   # lock to x64 for CUDA
    [string]$Repo = (Resolve-Path "$PSScriptRoot\.."),  # default: repo root (parent of /scripts)
    [switch]$NoConda,
    [switch]$Quiet
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

    $runner = $null
    if (Get-Command mamba -ErrorAction SilentlyContinue) { $runner = 'mamba' }
    elseif (Get-Command conda -ErrorAction SilentlyContinue) { $runner = 'conda' }

    if (-not $runner) { Warn "conda/mamba not found on PATH. Skipping env activation."; return }

    & $runner activate $Name
    if ($env:CONDA_DEFAULT_ENV -eq $Name) { Ok "Activated '$Name' via $runner." }
    else { Warn "Tried to activate '$Name' via $runner, but it didn’t stick." }
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

# ----- Run -----
Enter-VSDev
Ensure-CondaOnPath
Activate-CondaEnv -Name $EnvName
Check-PromptDupes

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
    & $global:IONO_CLI @Args
}

# Verb wrappers: prepend verb, then forward args (so ib → build, etc.)
function global:ib     { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono build    @Args }
function global:ir     { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono rebuild  @Args }
function global:it     { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono test     @Args }
function global:ilint  { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono lint     @Args }
function global:ifmt   { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono format   @Args }
function global:ibench { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono bench    @Args }
function global:iprof  { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono profile  @Args }
function global:ival   { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono validate @Args }
function global:imon   { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono monitor  @Args }
function global:iinfo  { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono info     @Args }
function global:iclean { param([Parameter(ValueFromRemainingArguments=$true)][object[]]$Args) iono clean    @Args }

# Optional tiny shorthands
function global:ibr { ir }                # rebuild (no args)
function global:itp { it py }             # python tests
function global:itc { it cpp }            # c++ tests
function global:ipq { iprof nsys quick }  # nsys quick
function global:ipf { iprof nsys full }   # nsys full

# Tab-completion (simple + resilient)
$global:IonoVerbs   = @('setup','build','rebuild','lint','format','test','list','bench','profile','validate','monitor','info','clean')
$global:IonoTargets = @('cpp','py','suite','latency','throughput','spectrogram','nsys','ncu','quick','full','windows-rel','--ui','--help')

Register-ArgumentCompleter -CommandName iono,ib,ir,it,ilint,ifmt,ibench,iprof,ival,imon,iinfo,iclean -ScriptBlock {
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
