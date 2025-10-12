#!/usr/bin/env pwsh
# create-dev-shortcut.ps1
# Creates a desktop shortcut for the ionosense-hpc development shell

#Requires -Version 7.0

param(
    [string]$ShortcutName = "ionosense-hpc Dev Shell"
)

$ErrorActionPreference = 'Stop'

# Resolve repo root from script location
$RepoRoot = (Get-Item -Path (Join-Path $PSScriptRoot "..")).FullName

# Verify we're in the right place
$InitScript = Join-Path $RepoRoot "scripts\init_pwsh.ps1"
if (-not (Test-Path $InitScript)) {
    Write-Error "Cannot find init_pwsh.ps1 at: $InitScript"
    Write-Error "This script must be run from the ionosense-hpc-lib/scripts directory"
    exit 1
}

# PowerShell 7 path
$PwshPath = "C:\Program Files\PowerShell\7\pwsh.exe"
if (-not (Test-Path $PwshPath)) {
    Write-Error "PowerShell 7 not found at: $PwshPath"
    Write-Error "Please install PowerShell 7 first: winget install Microsoft.Powershell"
    exit 1
}

# Create the shortcut
Write-Host "Creating desktop shortcut..." -ForegroundColor Cyan

$WshShell = New-Object -ComObject WScript.Shell
$ShortcutPath = Join-Path $env:USERPROFILE "Desktop\$ShortcutName.lnk"
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PwshPath
$Shortcut.Arguments = "-NoExit -ExecutionPolicy Bypass -File `"$InitScript`""
$Shortcut.WorkingDirectory = $RepoRoot
$Shortcut.IconLocation = "$PwshPath,0"
$Shortcut.Description = "ionosense-hpc Development Shell"
$Shortcut.Save()

Write-Host ":white_check_mark: Shortcut created successfully!" -ForegroundColor Green
Write-Host "   Location: $ShortcutPath" -ForegroundColor Gray
Write-Host "   Repo: $RepoRoot" -ForegroundColor Gray
Write-Host "   Script: $InitScript" -ForegroundColor Gray
Write-Host ""
Write-Host "Double-click the shortcut to launch your development environment!" -ForegroundColor Cyan