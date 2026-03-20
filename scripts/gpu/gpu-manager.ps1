#Requires -Version 7.0

<#
.SYNOPSIS
    GPU clock management for stable benchmarking.

.DESCRIPTION
    Provides functions to lock/unlock GPU clocks for benchmark stability.
    Requires administrator privileges and nvidia-smi in PATH.

.NOTES
    Author: Claude (AI Assistant)
    Date: 2025-10-15
    Version: 1.0.0
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

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$clockDbPath = Join-Path $scriptDir "gpu-clocks.json"

#region Helper Functions

function Test-AdminPrivileges {
    <#
    .SYNOPSIS
        Check if running with administrator privileges.
    #>
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-NvidiaSmiAvailable {
    <#
    .SYNOPSIS
        Check if nvidia-smi is available in PATH.
    #>
    try {
        $null = Get-Command nvidia-smi -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Get-GpuClockDatabase {
    <#
    .SYNOPSIS
        Load GPU clock database from JSON.
    #>
    if (-not (Test-Path $clockDbPath)) {
        throw "GPU clock database not found: $clockDbPath"
    }

    try {
        $json = Get-Content $clockDbPath -Raw | ConvertFrom-Json
        return $json
    } catch {
        throw "Failed to parse GPU clock database: $_"
    }
}

function Get-GpuInfo {
    <#
    .SYNOPSIS
        Query GPU information using nvidia-smi.

    .PARAMETER GpuIndex
        GPU index to query (default: 0)

    .OUTPUTS
        PSCustomObject with GPU information
    #>
    param(
        [int]$GpuIndex = 0
    )

    if (-not (Test-NvidiaSmiAvailable)) {
        throw "nvidia-smi not found in PATH. Please install NVIDIA drivers."
    }

    try {
        # Query GPU name
        $gpuName = nvidia-smi -i $GpuIndex --query-gpu=name --format=csv,noheader,nounits 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to query GPU $GpuIndex. Is the GPU index valid?"
        }

        # Query current clocks
        $graphicsClock = nvidia-smi -i $GpuIndex --query-gpu=clocks.current.graphics --format=csv,noheader,nounits 2>&1
        $memoryClock = nvidia-smi -i $GpuIndex --query-gpu=clocks.current.memory --format=csv,noheader,nounits 2>&1

        # Query max clocks
        $maxGraphicsClock = nvidia-smi -i $GpuIndex --query-gpu=clocks.max.graphics --format=csv,noheader,nounits 2>&1
        $maxMemoryClock = nvidia-smi -i $GpuIndex --query-gpu=clocks.max.memory --format=csv,noheader,nounits 2>&1

        # Query persistence mode
        $persistenceMode = nvidia-smi -i $GpuIndex --query-gpu=persistence_mode --format=csv,noheader,nounits 2>&1

        return [PSCustomObject]@{
            Index = $GpuIndex
            Name = $gpuName.Trim()
            CurrentGraphicsClock = [int]$graphicsClock
            CurrentMemoryClock = [int]$memoryClock
            MaxGraphicsClock = [int]$maxGraphicsClock
            MaxMemoryClock = [int]$maxMemoryClock
            PersistenceMode = $persistenceMode.Trim()
        }
    } catch {
        throw "Failed to query GPU info: $_"
    }
}

function Get-GpuClockProfile {
    <#
    .SYNOPSIS
        Get clock profile for a GPU model from database.

    .PARAMETER GpuName
        GPU name from nvidia-smi

    .OUTPUTS
        PSCustomObject with clock profile or $null if not found
    #>
    param(
        [string]$GpuName
    )

    $db = Get-GpuClockDatabase

    # Try to match GPU name to profile
    foreach ($rule in $db.matching_rules.rules) {
        if ($GpuName -match $rule.pattern) {
            $profileName = $rule.profile
            $profile = $db.gpu_models.$profileName

            if ($profile) {
                return [PSCustomObject]@{
                    ProfileName = $profileName
                    Name = $profile.name
                    Architecture = $profile.architecture
                    MaxGraphicsClock = $profile.max_graphics_clock_mhz
                    MaxMemoryClock = $profile.max_memory_clock_mhz
                    RecommendedGraphicsClock = $profile.recommended_graphics_clock_mhz
                    RecommendedMemoryClock = $profile.recommended_memory_clock_mhz
                    Notes = $profile.notes
                }
            }
        }
    }

    return $null
}

#endregion

#region Main Functions

function Lock-GpuClocks {
    <#
    .SYNOPSIS
        Lock GPU clocks to stable values for benchmarking.

    .PARAMETER GpuIndex
        GPU index to lock (default: 0)

    .PARAMETER UseRecommended
        Use recommended clocks (conservative) vs max clocks
    #>
    param(
        [int]$GpuIndex = 0,
        [bool]$UseRecommended = $true
    )

    Write-Host "🔒 Locking GPU $GpuIndex clocks..." -ForegroundColor Cyan

    # Check admin privileges
    if (-not (Test-AdminPrivileges)) {
        throw "Administrator privileges required to lock GPU clocks. Please run as administrator."
    }

    # Get GPU info
    $gpuInfo = Get-GpuInfo -GpuIndex $GpuIndex
    Write-Host "   GPU: $($gpuInfo.Name)" -ForegroundColor Gray

    # Get clock profile
    $profile = Get-GpuClockProfile -GpuName $gpuInfo.Name
    if (-not $profile) {
        Write-Warning "No clock profile found for '$($gpuInfo.Name)'. Using max clocks from GPU."
        $targetGraphicsClock = $gpuInfo.MaxGraphicsClock
        $targetMemoryClock = $gpuInfo.MaxMemoryClock
    } else {
        if ($UseRecommended) {
            $targetGraphicsClock = $profile.RecommendedGraphicsClock
            $targetMemoryClock = $profile.RecommendedMemoryClock
            Write-Host "   Profile: $($profile.ProfileName) (recommended)" -ForegroundColor Gray
        } else {
            $targetGraphicsClock = $profile.MaxGraphicsClock
            $targetMemoryClock = $profile.MaxMemoryClock
            Write-Host "   Profile: $($profile.ProfileName) (max)" -ForegroundColor Gray
        }

        if ($profile.Notes) {
            Write-Host "   Note: $($profile.Notes)" -ForegroundColor DarkGray
        }
    }

    Write-Host "   Target: Graphics=$targetGraphicsClock MHz, Memory=$targetMemoryClock MHz" -ForegroundColor Gray

    try {
        # Step 1: Enable persistence mode
        Write-Host "   [1/4] Enabling persistence mode..." -ForegroundColor Gray
        $result = nvidia-smi -i $GpuIndex -pm 1 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to enable persistence mode: $result"
        }

        # Step 2: Lock graphics clock
        Write-Host "   [2/4] Locking graphics clock to $targetGraphicsClock MHz..." -ForegroundColor Gray
        $result = nvidia-smi -i $GpuIndex -lgc $targetGraphicsClock 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to lock graphics clock: $result"
        }

        # Step 3: Lock memory clock
        Write-Host "   [3/4] Locking memory clock to $targetMemoryClock MHz..." -ForegroundColor Gray
        $result = nvidia-smi -i $GpuIndex -lmc $targetMemoryClock 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to lock memory clock: $result"
        }

        # Step 4: Validate
        Write-Host "   [4/4] Validating clock lock..." -ForegroundColor Gray
        Start-Sleep -Seconds 1  # Give GPU time to apply settings

        $newInfo = Get-GpuInfo -GpuIndex $GpuIndex
        Write-Host "   Current: Graphics=$($newInfo.CurrentGraphicsClock) MHz, Memory=$($newInfo.CurrentMemoryClock) MHz" -ForegroundColor Gray

        # Check if clocks are close to target (within 5%)
        $graphicsRatio = [Math]::Abs($newInfo.CurrentGraphicsClock - $targetGraphicsClock) / $targetGraphicsClock
        $memoryRatio = [Math]::Abs($newInfo.CurrentMemoryClock - $targetMemoryClock) / $targetMemoryClock

        if ($graphicsRatio -gt 0.05 -or $memoryRatio -gt 0.05) {
            Write-Warning "Clock lock validation failed. Clocks may not be stable."
            Write-Warning "  Expected: Graphics=$targetGraphicsClock MHz, Memory=$targetMemoryClock MHz"
            Write-Warning "  Actual: Graphics=$($newInfo.CurrentGraphicsClock) MHz, Memory=$($newInfo.CurrentMemoryClock) MHz"
        }

        Write-Host "✅ GPU clocks locked successfully" -ForegroundColor Green

        return [PSCustomObject]@{
            Success = $true
            GpuIndex = $GpuIndex
            OriginalGraphicsClock = $gpuInfo.CurrentGraphicsClock
            OriginalMemoryClock = $gpuInfo.CurrentMemoryClock
            LockedGraphicsClock = $newInfo.CurrentGraphicsClock
            LockedMemoryClock = $newInfo.CurrentMemoryClock
        }

    } catch {
        Write-Error "Failed to lock GPU clocks: $_"
        Write-Host ""
        Write-Host "Manual recovery (run as administrator):" -ForegroundColor Yellow
        Write-Host "  nvidia-smi -i $GpuIndex -pm 0" -ForegroundColor Yellow
        Write-Host "  nvidia-smi -i $GpuIndex -rgc" -ForegroundColor Yellow
        Write-Host "  nvidia-smi -i $GpuIndex -rmc" -ForegroundColor Yellow
        throw
    }
}

function Unlock-GpuClocks {
    <#
    .SYNOPSIS
        Restore GPU clocks to default (unlocked) state.

    .PARAMETER GpuIndex
        GPU index to unlock (default: 0)
    #>
    param(
        [int]$GpuIndex = 0
    )

    Write-Host "🔓 Unlocking GPU $GpuIndex clocks..." -ForegroundColor Cyan

    # Check admin privileges
    if (-not (Test-AdminPrivileges)) {
        throw "Administrator privileges required to unlock GPU clocks. Please run as administrator."
    }

    try {
        # Step 1: Reset graphics clock
        Write-Host "   [1/3] Resetting graphics clock..." -ForegroundColor Gray
        $result = nvidia-smi -i $GpuIndex -rgc 2>&1
        if ($LASTEXITCODE -ne 0) {
            # Not a fatal error - clock might not have been locked
            Write-Warning "Graphics clock reset returned: $result"
        }

        # Step 2: Reset memory clock
        Write-Host "   [2/3] Resetting memory clock..." -ForegroundColor Gray
        $result = nvidia-smi -i $GpuIndex -rmc 2>&1
        if ($LASTEXITCODE -ne 0) {
            # Not a fatal error - clock might not have been locked
            Write-Warning "Memory clock reset returned: $result"
        }

        # Step 3: Disable persistence mode
        Write-Host "   [3/3] Disabling persistence mode..." -ForegroundColor Gray
        $result = nvidia-smi -i $GpuIndex -pm 0 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Persistence mode disable returned: $result"
        }

        Write-Host "✅ GPU clocks unlocked successfully" -ForegroundColor Green

        return [PSCustomObject]@{
            Success = $true
            GpuIndex = $GpuIndex
        }

    } catch {
        Write-Error "Failed to unlock GPU clocks: $_"
        Write-Host ""
        Write-Host "Manual recovery (run as administrator):" -ForegroundColor Yellow
        Write-Host "  nvidia-smi -i $GpuIndex -pm 0" -ForegroundColor Yellow
        Write-Host "  nvidia-smi -i $GpuIndex -rgc" -ForegroundColor Yellow
        Write-Host "  nvidia-smi -i $GpuIndex -rmc" -ForegroundColor Yellow
        throw
    }
}

function Show-GpuClockInfo {
    <#
    .SYNOPSIS
        Display current GPU clock information.

    .PARAMETER GpuIndex
        GPU index to query (default: 0)
    #>
    param(
        [int]$GpuIndex = 0
    )

    $gpuInfo = Get-GpuInfo -GpuIndex $GpuIndex
    $profile = Get-GpuClockProfile -GpuName $gpuInfo.Name

    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  GPU Clock Information" -ForegroundColor Cyan
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "GPU Index       : $($gpuInfo.Index)" -ForegroundColor White
    Write-Host "GPU Name        : $($gpuInfo.Name)" -ForegroundColor White
    Write-Host "Persistence Mode: $($gpuInfo.PersistenceMode)" -ForegroundColor White
    Write-Host ""
    Write-Host "Current Clocks:" -ForegroundColor Yellow
    Write-Host "  Graphics      : $($gpuInfo.CurrentGraphicsClock) MHz" -ForegroundColor White
    Write-Host "  Memory        : $($gpuInfo.CurrentMemoryClock) MHz" -ForegroundColor White
    Write-Host ""
    Write-Host "Hardware Max:" -ForegroundColor Yellow
    Write-Host "  Graphics      : $($gpuInfo.MaxGraphicsClock) MHz" -ForegroundColor White
    Write-Host "  Memory        : $($gpuInfo.MaxMemoryClock) MHz" -ForegroundColor White

    if ($profile) {
        Write-Host ""
        Write-Host "Profile         : $($profile.ProfileName)" -ForegroundColor Green
        Write-Host "Architecture    : $($profile.Architecture)" -ForegroundColor White
        Write-Host ""
        Write-Host "Recommended (for stability):" -ForegroundColor Yellow
        Write-Host "  Graphics      : $($profile.RecommendedGraphicsClock) MHz" -ForegroundColor White
        Write-Host "  Memory        : $($profile.RecommendedMemoryClock) MHz" -ForegroundColor White
        Write-Host ""
        Write-Host "Max (for performance):" -ForegroundColor Yellow
        Write-Host "  Graphics      : $($profile.MaxGraphicsClock) MHz" -ForegroundColor White
        Write-Host "  Memory        : $($profile.MaxMemoryClock) MHz" -ForegroundColor White

        if ($profile.Notes) {
            Write-Host ""
            Write-Host "Notes:" -ForegroundColor DarkGray
            Write-Host "  $($profile.Notes)" -ForegroundColor DarkGray
        }
    } else {
        Write-Host ""
        Write-Host "Profile         : [NOT FOUND]" -ForegroundColor Red
        Write-Host "Note: No clock profile found for this GPU model." -ForegroundColor Yellow
        Write-Host "      You can still lock to hardware max clocks." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host ""
}

#endregion

#region Main Entry Point

# Execute action based on parameter
switch ($Action) {
    'Lock' {
        Lock-GpuClocks -GpuIndex $GpuIndex -UseRecommended $UseRecommended
    }
    'Unlock' {
        Unlock-GpuClocks -GpuIndex $GpuIndex
    }
    'Query' {
        Show-GpuClockInfo -GpuIndex $GpuIndex
    }
    'Validate' {
        # Check prerequisites
        Write-Host "Validating GPU clock management prerequisites..." -ForegroundColor Cyan
        Write-Host ""

        $allGood = $true

        # Check admin
        if (Test-AdminPrivileges) {
            Write-Host "✅ Administrator privileges" -ForegroundColor Green
        } else {
            Write-Host "❌ Administrator privileges" -ForegroundColor Red
            Write-Host "   Run as administrator to lock/unlock clocks" -ForegroundColor Yellow
            $allGood = $false
        }

        # Check nvidia-smi
        if (Test-NvidiaSmiAvailable) {
            Write-Host "✅ nvidia-smi available" -ForegroundColor Green
        } else {
            Write-Host "❌ nvidia-smi not found" -ForegroundColor Red
            Write-Host "   Install NVIDIA drivers" -ForegroundColor Yellow
            $allGood = $false
        }

        # Check database
        if (Test-Path $clockDbPath) {
            Write-Host "✅ GPU clock database found" -ForegroundColor Green
        } else {
            Write-Host "❌ GPU clock database missing" -ForegroundColor Red
            Write-Host "   Expected: $clockDbPath" -ForegroundColor Yellow
            $allGood = $false
        }

        Write-Host ""
        if ($allGood) {
            Write-Host "✅ All prerequisites met" -ForegroundColor Green
            Show-GpuClockInfo -GpuIndex $GpuIndex
        } else {
            Write-Host "❌ Some prerequisites not met" -ForegroundColor Red
            exit 1
        }
    }
}

#endregion
