<#
.SYNOPSIS
    Root launcher for the Campus Nexus Cloudflared Tunnel Watchdog.
    Delegates to scripts/cloudflared-watchdog.ps1 with all supplied parameters.
#>

[CmdletBinding()]
param(
    [int]$CheckIntervalSeconds = 15,
    [int]$FailureThreshold = 3,
    [int]$RestartCooldownSeconds = 120,
    [int]$MetricsTimeoutSeconds = 5,
    [switch]$InstallTask,
    [switch]$UninstallTask,
    [switch]$GrantPermissions,
    [switch]$Status,
    [switch]$Once
)

$targetScript = Join-Path $PSScriptRoot "scripts\cloudflared-watchdog.ps1"

if (-not (Test-Path $targetScript)) {
    Write-Host "ERROR: Target script not found at $targetScript" -ForegroundColor Red
    exit 1
}

& $targetScript `
    -CheckIntervalSeconds $CheckIntervalSeconds `
    -FailureThreshold $FailureThreshold `
    -RestartCooldownSeconds $RestartCooldownSeconds `
    -MetricsTimeoutSeconds $MetricsTimeoutSeconds `
    -InstallTask:$InstallTask `
    -UninstallTask:$UninstallTask `
    -GrantPermissions:$GrantPermissions `
    -Status:$Status `
    -Once:$Once
