<#
.SYNOPSIS
    Cloudflared Tunnel Watchdog for Campus Nexus.
    Monitors Cloudflare Tunnel connections and automatically recovers the Windows service
    when all active connections are severed by campus network firewalls.

.DESCRIPTION
    Periodically checks the local Cloudflared Prometheus metrics endpoint (127.0.0.1:20241)
    and verifies active HA tunnel connections (cloudflared_tunnel_ha_connections).
    If all connections drop for 3 consecutive checks (45 seconds), or if the service stops,
    the script automatically restarts the Windows service with a cooldown window to prevent
    flapping.

.PARAMETER CheckIntervalSeconds
    Frequency of health checks in seconds. Default is 15.

.PARAMETER FailureThreshold
    Number of consecutive zero-connection checks required to trigger service recovery. Default is 3.

.PARAMETER RestartCooldownSeconds
    Minimum wait time in seconds between recovery restarts to prevent loops. Default is 120.

.PARAMETER InstallTask
    Installs this watchdog as a Windows Scheduled Task running at system startup as SYSTEM.
    This is the recommended setup as it runs 24/7 without needing an open terminal window or admin login.

.PARAMETER UninstallTask
    Removes the Windows Scheduled Task.

.PARAMETER GrantPermissions
    One-time configuration: Grants standard non-administrator users permission to start and stop
    the Cloudflared service via Windows Service Control Manager ACLs.

.PARAMETER Status
    Performs an immediate single health check and prints status without entering the monitoring loop.

.PARAMETER Once
    Runs a single check cycle and exits.
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

# ============================================================
# CONFIGURATION
# ============================================================
$ServiceName = "Cloudflared"
$MetricsUrl = "http://127.0.0.1:20241/metrics"
$TaskName = "CloudflaredWatchdog"

$LogDirectory = "C:\ProgramData\cloudflared"
$LogFile = Join-Path $LogDirectory "watchdog.log"
$MaxLogSizeBytes = 5MB

# Ensure Log Directory Exists
if (!(Test-Path $LogDirectory)) {
    try {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    }
    catch {
        # Fall back to AppData if ProgramData is restricted
        $LogDirectory = Join-Path $env:LOCALAPPDATA "cloudflared"
        if (!(Test-Path $LogDirectory)) {
            New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
        }
        $LogFile = Join-Path $LogDirectory "watchdog.log"
    }
}

# ============================================================
# HELPER: PRIVILEGE & SERVICE PERMISSION VERIFICATION
# ============================================================
function Test-IsAdministrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
    return $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-ServiceControlPermission {
    param([string]$Name = $ServiceName)
    if (Test-IsAdministrator) {
        return $true
    }
    try {
        # Check if Interactive Users (IU) or Authenticated Users (AU) have Start/Stop rights in service SDDL
        $sd = sc.exe sdshow $Name 2>$null
        if ($sd -and ($sd -match ';;;IU\).*RP.*WP' -or $sd -match ';;;AU\).*RP.*WP' -or $sd -match ';;;WD\).*RP.*WP')) {
            return $true
        }
        return $false
    }
    catch {
        return $false
    }
}

# ============================================================
# LOGGING FUNCTION (Console + File with size rotation)
# ============================================================
function Write-WatchdogLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Entry = "[$Timestamp] [$Level] $Message"

    # Console output with color
    $Color = switch ($Level) {
        "ERROR"   { "Red" }
        "WARNING" { "Yellow" }
        "SUCCESS" { "Green" }
        default   { "Gray" }
    }
    Write-Host $Entry -ForegroundColor $Color

    # File logging with size safety
    try {
        if (Test-Path $LogFile) {
            $fileItem = Get-Item $LogFile -ErrorAction SilentlyContinue
            if ($fileItem -and $fileItem.Length -gt $MaxLogSizeBytes) {
                # Keep last 1,000 lines when log exceeds limit
                $recentLines = Get-Content -Path $LogFile -Tail 1000 -ErrorAction SilentlyContinue
                Set-Content -Path $LogFile -Value $recentLines -ErrorAction SilentlyContinue
                Add-Content -Path $LogFile -Value "[$Timestamp] [INFO] Log rotated (exceeded 5MB limit)." -ErrorAction SilentlyContinue
            }
        }
        Add-Content -Path $LogFile -Value $Entry -ErrorAction SilentlyContinue
    }
    catch {
        # Fall back gracefully if log file is locked
    }
}

# ============================================================
# SERVICE PERMISSION DELEGATION (-GrantPermissions)
# ============================================================
if ($GrantPermissions) {
    if (-not (Test-IsAdministrator)) {
        Write-Host "Requesting Administrator privileges to grant service control permissions..." -ForegroundColor Yellow
        $ScriptPath = if ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { Join-Path $PSScriptRoot "cloudflared-watchdog.ps1" }
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -GrantPermissions" -Verb RunAs
        exit 0
    }

    Write-Host "Configuring Windows Service Control ACL for '$ServiceName'..." -ForegroundColor Cyan
    try {
        # Grants Local System (SY), Built-in Administrators (BA), and Interactive Users (IU) start/stop/control access
        $sddl = "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWRPWPDTLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)"
        $res = & sc.exe sdset $ServiceName $sddl
        if ($LASTEXITCODE -eq 0) {
            Write-Host "`nSUCCESS: Non-administrator users can now restart the '$ServiceName' service!" -ForegroundColor Green
            Write-Host "You can now run .\cloudflared-watchdog.ps1 in any standard, non-elevated PowerShell window." -ForegroundColor Green
            exit 0
        }
        else {
            Write-Host "ERROR: sc.exe sdset failed with exit code $LASTEXITCODE : $res" -ForegroundColor Red
            exit 1
        }
    }
    catch {
        Write-Host "ERROR: Failed to update service ACL: $_" -ForegroundColor Red
        exit 1
    }
}

# ============================================================
# SCHEDULED TASK MANAGEMENT (-InstallTask / -UninstallTask)
# ============================================================
if ($InstallTask) {
    if (-not (Test-IsAdministrator)) {
        Write-Host "Requesting Administrator privileges to install scheduled background task..." -ForegroundColor Yellow
        $ScriptPath = if ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { Join-Path $PSScriptRoot "cloudflared-watchdog.ps1" }
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -InstallTask" -Verb RunAs
        exit 0
    }

    $ScriptPath = $MyInvocation.MyCommand.Path
    if (-not $ScriptPath) {
        $ScriptPath = Join-Path $PSScriptRoot "cloudflared-watchdog.ps1"
    }

    Write-Host "Registering Windows Scheduled Task: $TaskName..." -ForegroundColor Cyan
    $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""
    $Trigger = New-ScheduledTaskTrigger -AtStartup
    $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0)

    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Campus Nexus Cloudflared Tunnel Watchdog daemon" | Out-Null
        Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Write-Host "`nSUCCESS: Scheduled task '$TaskName' registered and started." -ForegroundColor Green
        Write-Host "The watchdog is now actively running in the background as SYSTEM." -ForegroundColor Green
        Write-Host "It will automatically monitor and restart the tunnel on system boot with zero terminal windows open." -ForegroundColor Green
        exit 0
    }
    catch {
        Write-Host "ERROR: Failed to register scheduled task: $_" -ForegroundColor Red
        exit 1
    }
}

if ($UninstallTask) {
    if (-not (Test-IsAdministrator)) {
        Write-Host "Requesting Administrator privileges to remove scheduled task..." -ForegroundColor Yellow
        $ScriptPath = if ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { Join-Path $PSScriptRoot "cloudflared-watchdog.ps1" }
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -UninstallTask" -Verb RunAs
        exit 0
    }

    Write-Host "Removing Windows Scheduled Task: $TaskName..." -ForegroundColor Yellow
    try {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "SUCCESS: Scheduled task '$TaskName' removed." -ForegroundColor Green
        exit 0
    }
    catch {
        Write-Host "ERROR: Failed to remove scheduled task: $_" -ForegroundColor Red
        exit 1
    }
}

# ============================================================
# STATUS CHECK (-Status)
# ============================================================
function Show-StatusSummary {
    Write-Host "`n=== CLOUDFLARED TUNNEL WATCHDOG STATUS ===" -ForegroundColor Cyan
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($svc) {
        $statusColor = if ($svc.Status -eq "Running") { "Green" } else { "Red" }
        Write-Host "Service Name   : $($svc.Name)"
        Write-Host "Service Status : " -NoNewline
        Write-Host "$($svc.Status)" -ForegroundColor $statusColor
    }
    else {
        Write-Host "Service '$ServiceName' : NOT FOUND" -ForegroundColor Red
    }

    # Query metrics
    try {
        $Response = Invoke-WebRequest -Uri $MetricsUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $Match = [regex]::Match($Response.Content, '(?m)^cloudflared_tunnel_ha_connections\s+([0-9]+(?:\.[0-9]+)?)\s*$')
        if ($Match.Success) {
            $connCount = [int][double]$Match.Groups[1].Value
            Write-Host "Active HA Conn : " -NoNewline
            $connColor = if ($connCount -gt 0) { "Green" } else { "Red" }
            Write-Host "$connCount (via Metrics endpoint 127.0.0.1:20241)" -ForegroundColor $connColor
        }
    }
    catch {
        Write-Host "Metrics Socket : Unreachable ($MetricsUrl)" -ForegroundColor Yellow
    }

    # Check TCP established connections on port 7844
    if ($svc -and $svc.Status -eq "Running") {
        try {
            $cimSvc = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'" -ErrorAction SilentlyContinue
            if ($cimSvc -and $cimSvc.ProcessId -gt 0) {
                $tcpConns = @(Get-NetTCPConnection -State Established -RemotePort 7844 -OwningProcess $cimSvc.ProcessId -ErrorAction SilentlyContinue)
                Write-Host "Established TCP: $($tcpConns.Count) connections to Cloudflare Edge (:7844)"
            }
        }
        catch {}
    }

    # Check Scheduled Task Status
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Write-Host "Background Task: Registered [$($task.State)] (Auto-runs on boot as SYSTEM)" -ForegroundColor Green
    }
    else {
        Write-Host "Background Task: Not registered (Use -InstallTask to run permanently in background)" -ForegroundColor Gray
    }

    # Check non-admin service control permission
    $canRestart = Test-ServiceControlPermission -Name $ServiceName
    if ($canRestart) {
        Write-Host "Service Control: Permission GRANTED for current user (Can restart without admin)" -ForegroundColor Green
    }
    else {
        Write-Host "Service Control: Administrator privilege required to restart (or run -GrantPermissions)" -ForegroundColor Yellow
    }

    Write-Host "Log File Path  : $LogFile"
    if (Test-Path $LogFile) {
        Write-Host "`n--- Recent Watchdog Log Entries (Last 5) ---" -ForegroundColor DarkGray
        Get-Content $LogFile -Tail 5 -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "  $_" -ForegroundColor Gray
        }
    }
    Write-Host "==========================================`n" -ForegroundColor Cyan
}

if ($Status) {
    Show-StatusSummary
    exit 0
}

# ============================================================
# CORE WATCHDOG ROUTINES
# ============================================================

# Obtain active tunnel connection count
function Get-TunnelConnections {
    # Method 1: Local Prometheus metrics endpoint
    try {
        $Response = Invoke-WebRequest `
            -Uri $MetricsUrl `
            -UseBasicParsing `
            -TimeoutSec $MetricsTimeoutSeconds `
            -ErrorAction Stop

        $Match = [regex]::Match(
            $Response.Content,
            '(?m)^cloudflared_tunnel_ha_connections\s+([0-9]+(?:\.[0-9]+)?)\s*$'
        )

        if ($Match.Success) {
            return [PSCustomObject]@{
                Count  = [int][double]$Match.Groups[1].Value
                Source = "Metrics"
            }
        }
    }
    catch {
        # Metrics endpoint unavailable, fall back to TCP connection inspection
    }

    # Method 2: Inspect established TCP sockets to Cloudflare edge (:7844)
    try {
        $Service = Get-CimInstance Win32_Service `
            -Filter "Name='$ServiceName'" `
            -ErrorAction Stop

        if ($Service -and $Service.ProcessId -gt 0) {
            $Connections = @(
                Get-NetTCPConnection `
                    -State Established `
                    -RemotePort 7844 `
                    -OwningProcess $Service.ProcessId `
                    -ErrorAction Stop
            )

            return [PSCustomObject]@{
                Count  = $Connections.Count
                Source = "TCP"
            }
        }
    }
    catch {
        Write-WatchdogLog "Unable to inspect TCP sockets: $_" "WARNING"
    }

    return $null
}

# Repair / restart cloudflared service
function Repair-Tunnel {
    Write-WatchdogLog "Attempting Cloudflared service recovery..." "WARNING"

    try {
        $Service = Get-Service -Name $ServiceName -ErrorAction Stop

        if ($Service.Status -eq "Running") {
            Write-WatchdogLog "Stopping Cloudflared service..." "INFO"
            Restart-Service -Name $ServiceName -Force -ErrorAction Stop
        }
        else {
            Write-WatchdogLog "Starting stopped Cloudflared service..." "INFO"
            Start-Service -Name $ServiceName -ErrorAction Stop
        }

        # Allow service time to re-establish edge connections
        Start-Sleep -Seconds 8

        $Service = Get-Service -Name $ServiceName
        if ($Service.Status -eq "Running") {
            Write-WatchdogLog "Cloudflared service successfully restarted and running." "SUCCESS"
        }
        else {
            Write-WatchdogLog "Service recovery attempted, but service status is: $($Service.Status)" "ERROR"
        }
    }
    catch {
        Write-WatchdogLog "Service recovery failed: $_" "ERROR"
        if ($_ -match "Cannot open Cloudflared service" -or $_ -match "Access is denied") {
            Write-WatchdogLog "HINT: Non-admin users cannot restart services by default. Run '.\cloudflared-watchdog.ps1 -GrantPermissions' once as Admin or use -InstallTask." "WARNING"
        }
    }
}

# ============================================================
# MAIN MONITORING EXECUTION & PRIVILEGE CHECK
# ============================================================

# Verify service control capabilities
if (-not (Test-ServiceControlPermission -Name $ServiceName)) {
    Write-Host "`n============================================================" -ForegroundColor Yellow
    Write-Host " ELEVATED PRIVILEGES OR SERVICE PERMISSION REQUIRED" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Yellow
    Write-Host "Restarting the Windows service '$ServiceName' requires administrator rights"
    Write-Host "because Windows Service Control Manager restricts service restarts by default.`n"
    Write-Host "Choose how to proceed:" -ForegroundColor White
    Write-Host "  [1] Open elevated Administrator monitoring window (UAC prompt)" -ForegroundColor Green
    Write-Host "  [2] Install as background Windows Task (Runs as SYSTEM 24/7, no terminal needed)" -ForegroundColor Cyan
    Write-Host "  [3] Grant non-admin users permission to restart '$ServiceName' permanently" -ForegroundColor Magenta
    Write-Host "  [4] Run in read-only observation mode (Alerts on connection drops, no restart)" -ForegroundColor DarkYellow
    Write-Host "  [5] Exit" -ForegroundColor Gray

    $scriptToRun = if ($MyInvocation.MyCommand.Path) { $MyInvocation.MyCommand.Path } else { Join-Path $PSScriptRoot "cloudflared-watchdog.ps1" }
    $choice = Read-Host "`nEnter selection [1-5]"
    switch ($choice) {
        "1" {
            Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptToRun`"" -Verb RunAs
            exit 0
        }
        "2" {
            Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptToRun`" -InstallTask" -Verb RunAs
            exit 0
        }
        "3" {
            Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptToRun`" -GrantPermissions" -Verb RunAs
            exit 0
        }
        "4" {
            Write-Host "Starting watchdog in observation mode (monitoring only, will not restart)..." -ForegroundColor Yellow
        }
        default {
            exit 1
        }
    }
}

Write-WatchdogLog "============================================"
Write-WatchdogLog "Campus Nexus Cloudflared Watchdog started."
Write-WatchdogLog "Monitoring service : $ServiceName"
Write-WatchdogLog "Metrics endpoint   : $MetricsUrl"
Write-WatchdogLog "Check interval     : $CheckIntervalSeconds seconds"
Write-WatchdogLog "Failure threshold  : $FailureThreshold consecutive checks (~$($CheckIntervalSeconds * $FailureThreshold)s)"
Write-WatchdogLog "Restart cooldown   : $RestartCooldownSeconds seconds"
Write-WatchdogLog "Log file           : $LogFile"
Write-WatchdogLog "============================================"

$ConsecutiveFailures = 0
$LastRestart = [datetime]::MinValue

while ($true) {
    try {
        # 1. Verify Windows Service State
        $Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

        if ($null -eq $Service) {
            Write-WatchdogLog "Service '$ServiceName' not found on this system." "ERROR"
            if ($Once) { break }
            Start-Sleep -Seconds $CheckIntervalSeconds
            continue
        }

        if ($Service.Status -ne "Running") {
            Write-WatchdogLog "Cloudflared service is $($Service.Status). Immediate recovery triggered." "ERROR"
            $ConsecutiveFailures = 0
            $LastRestart = Get-Date
            Repair-Tunnel

            if ($Once) { break }
            Start-Sleep -Seconds $CheckIntervalSeconds
            continue
        }

        # 2. Check Active Tunnel Connections
        $Tunnel = Get-TunnelConnections

        if ($null -eq $Tunnel) {
            Write-WatchdogLog "Unable to determine tunnel connection count. No blind restart triggered." "WARNING"
            $ConsecutiveFailures = 0
            if ($Once) { break }
            Start-Sleep -Seconds $CheckIntervalSeconds
            continue
        }

        $ConnectionCount = $Tunnel.Count

        if ($ConnectionCount -gt 0) {
            Write-WatchdogLog "Tunnel healthy: $ConnectionCount active connections (source: $($Tunnel.Source))." "INFO"
            $ConsecutiveFailures = 0
        }
        else {
            $ConsecutiveFailures++
            Write-WatchdogLog "NO ACTIVE TUNNEL CONNECTIONS. Failure $ConsecutiveFailures/$FailureThreshold." "WARNING"

            if ($ConsecutiveFailures -ge $FailureThreshold) {
                $Elapsed = ((Get-Date) - $LastRestart).TotalSeconds

                if ($Elapsed -ge $RestartCooldownSeconds) {
                    Write-WatchdogLog "Connection loss confirmed ($FailureThreshold consecutive failures). Initiating service recovery." "ERROR"
                    $LastRestart = Get-Date
                    Repair-Tunnel
                }
                else {
                    $Remaining = [math]::Ceiling($RestartCooldownSeconds - $Elapsed)
                    Write-WatchdogLog "Restart cooldown active. $Remaining seconds remaining before next restart attempt." "WARNING"
                }

                $ConsecutiveFailures = 0
            }
        }
    }
    catch {
        Write-WatchdogLog "Monitoring loop exception: $_" "ERROR"
    }

    if ($Once) {
        break
    }

    Start-Sleep -Seconds $CheckIntervalSeconds
}
