#Requires -Version 7.0

<#
.SYNOPSIS
    GPU clock management wrapper with automatic UAC elevation.

.DESCRIPTION
    This wrapper script handles UAC elevation automatically when GPU clock
    locking requires administrator privileges. It ensures that the user sees
    all output in their original PowerShell session, even when elevation occurs.

.NOTES
    Author: Kevin
    Date: 2025-10-17
    Version: 0.9.3

    This script is used by the Python GpuClockManager to provide the same
    auto-elevation behavior as the C++ ionoc bench --lock-clocks implementation.
#>

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('Lock', 'Unlock', 'Query', 'Validate')]
    [string]$Action = 'Query',

    [Parameter(Mandatory=$false)]
    [int]$GpuIndex = 0,

    [Parameter(Mandatory=$false)]
    [switch]$UseRecommended = $true
)

# Get the actual gpu-manager.ps1 script path
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$gpuManagerPath = Join-Path $scriptDir "gpu-manager.ps1"

if (-not (Test-Path $gpuManagerPath)) {
    Write-Error "GPU manager script not found: $gpuManagerPath"
    exit 1
}

# Check if we're already running as administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

# Actions that require admin privileges
$adminRequired = @('Lock', 'Unlock')

if (($Action -in $adminRequired) -and (-not $isAdmin)) {
    # Not admin and admin is required - re-launch elevated
    Write-Host ""
    Write-Host "⚠️  GPU clock $($Action.ToLower()) requires administrator privileges" -ForegroundColor Yellow
    Write-Host "    UAC prompt will appear - please approve to continue" -ForegroundColor Yellow
    Write-Host ""
    Start-Sleep -Seconds 1

    # Build arguments for elevated process
    $elevatedArgs = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $MyInvocation.MyCommand.Path,
        '-Action', $Action,
        '-GpuIndex', $GpuIndex
    )

    # Add UseRecommended switch with correct syntax
    if ($UseRecommended) {
        $elevatedArgs += '-UseRecommended:$true'
    } else {
        $elevatedArgs += '-UseRecommended:$false'
    }

    # Launch elevated process and wait for completion
    try {
        $process = Start-Process -FilePath 'pwsh' `
            -ArgumentList $elevatedArgs `
            -Verb RunAs `
            -Wait `
            -PassThru `
            -WindowStyle Normal

        exit $process.ExitCode
    } catch {
        Write-Error "Failed to elevate: $($_.Exception.Message)"
        Write-Host ""
        Write-Host "If UAC was cancelled, run PowerShell as administrator manually:" -ForegroundColor Yellow
        Write-Host "  Right-click PowerShell → 'Run as Administrator'" -ForegroundColor Yellow
        Write-Host "  Then re-run your command" -ForegroundColor Yellow
        exit 1
    }
}

# We're either:
# 1. Already admin (or action doesn't need admin)
# 2. This is the elevated instance after UAC prompt

# Call the actual GPU manager script
try {
    & $gpuManagerPath -Action $Action -GpuIndex $GpuIndex -UseRecommended:$UseRecommended
    exit $LASTEXITCODE
} catch {
    Write-Error "GPU manager failed: $($_.Exception.Message)"
    exit 1
}
