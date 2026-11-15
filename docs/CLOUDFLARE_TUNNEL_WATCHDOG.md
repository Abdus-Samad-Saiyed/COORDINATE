# Cloudflare Tunnel Watchdog & Auto-Recovery Runbook

## Overview

Campus Nexus uses a Cloudflare Tunnel (`cloudflared` Windows Service) to route traffic from public edges (Anycast nodes in Mumbai and Delhi) to the local Daphne cluster (`127.0.0.1:8000`).

In enterprise and campus network environments (such as NIT Srinagar), institutional firewalls perform aggressive stateful connection tracking and state table timeouts. When outbound tunnel sockets to Cloudflare edge nodes (`:7844`) remain idle or hit firewall NAT session limits:
1. The campus firewall silently drops the NAT table entry, blackholing outbound packets.
2. Cloudflare Anycast servers can no longer route incoming visitor requests to the local host machine, producing **Cloudflare Error 1033** (`Argo Tunnel error / Unable to reach origin tunnel`).
3. The local `cloudflared` Windows Service may still show as "Running" even though all underlying HA connections have dropped.
4. Restarting the Windows service forces the creation of 4 fresh outbound TCP sockets on new ephemeral ports, which immediately establishes new state entries in the firewall NAT table and recovers traffic within seconds.

The **Cloudflared Watchdog** (`cloudflared-watchdog.ps1`) continuously monitors the tunnel and automates this recovery process.

---

## Watchdog Architecture

- **Metrics Endpoint**: Queries `http://127.0.0.1:20241/metrics` every 15 seconds.
- **Connection Gauge**: Inspects `cloudflared_tunnel_ha_connections`. Normal operation maintains 4 redundant connections.
- **Failure Threshold**: If all connections drop to 0 for **3 consecutive checks** (approximately 45 seconds), it triggers an automated restart (`Restart-Service Cloudflared -Force`).
- **Flapping Protection**: Enforces a **120-second cooldown** between service restarts to prevent restart loops.
- **TCP Fallback Inspection**: If the local metrics endpoint is temporarily unreachable, inspects established TCP sockets on remote port `7844` owned by the `cloudflared` process.
- **Automated Log Rotation**: Logs all checks, disconnections, and recoveries to `C:\ProgramData\cloudflared\watchdog.log`. If the log exceeds 5MB, older entries are automatically truncated to prevent disk growth.

---

## Usage

### 1. Check Watchdog & Tunnel Health Status (No Elevation Needed)
To inspect tunnel connections, service state, and recent watchdog logs:
```powershell
powershell -ExecutionPolicy Bypass -File .\cloudflared-watchdog.ps1 -Status
```

Output:
```text
=== CLOUDFLARED TUNNEL WATCHDOG STATUS ===
Service Name   : Cloudflared
Service Status : Running
Active HA Conn : 4 (via Metrics endpoint 127.0.0.1:20241)
Established TCP: 4 connections to Cloudflare Edge (:7844)
Log File Path  : C:\ProgramData\cloudflared\watchdog.log
==========================================
```

### 2. Run Watchdog Interactively (Elevated Terminal)
Open PowerShell as **Administrator**:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\cloudflared-watchdog.ps1
```
*Note: Keep this window open while testing. If you close the terminal, the watchdog terminates.*

### 3. Run Watchdog as an Autonomous Windows Scheduled Task (Recommended for Production)
To have the watchdog run permanently in the background without needing an open terminal window, and survive machine reboots:
```powershell
# Open PowerShell as Administrator
.\cloudflared-watchdog.ps1 -InstallTask
```
This registers a task named `CloudflaredWatchdog` running under the `SYSTEM` account at system startup with highest privileges.

To remove the scheduled task:
```powershell
.\cloudflared-watchdog.ps1 -UninstallTask
```

### 4. Running as a Non-Administrator User

By default, Windows Service Control Manager (SCM) prevents standard, non-elevated user accounts from stopping or restarting Windows services. If you run the watchdog in a standard PowerShell terminal, the script provides three straightforward solutions:

1. **Option A: Auto-Elevation (UAC Prompt)**:
   The script detects it lacks service restart permissions and offers to re-launch in an elevated Administrator window with one keystroke (`[1]`).

2. **Option B: Autonomous Background Task (Recommended)**:
   Run `.\cloudflared-watchdog.ps1 -InstallTask` once. The watchdog runs 24/7 as `NT AUTHORITY\SYSTEM`, which has native permission to restart the service on failure without any user needing to be logged in or running elevated terminals.

3. **Option C: One-Time Service ACL Grant (`-GrantPermissions`)**:
   If you want to run `.\cloudflared-watchdog.ps1` interactively inside regular, non-administrator PowerShell windows without ever seeing UAC prompts:
   ```powershell
   # Run once in an elevated Administrator PowerShell prompt:
   .\cloudflared-watchdog.ps1 -GrantPermissions
   ```
   This updates the Windows service security descriptor (via `sc.exe sdset`) to grant Interactive Users (`IU`) start and stop rights **specifically on the Cloudflared service only**. Once granted, standard non-admin terminals can restart `Cloudflared` freely.

---

### 5. Monitor Live Watchdog Logs
In any PowerShell terminal:
```powershell
Get-Content "C:\ProgramData\cloudflared\watchdog.log" -Wait -Tail 30
```

### 6. Via Campus Nexus Launcher (`launch.ps1`)
Run:
```powershell
.\launch.ps1
```
Select **[W]** from the main menu to view tunnel status, run the watchdog interactively, or manage the background scheduled task.

---

## Script Parameters Reference

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-CheckIntervalSeconds` | int | `15` | Polling frequency in seconds between health checks. |
| `-FailureThreshold` | int | `3` | Consecutive zero-connection checks required to trigger service recovery. |
| `-RestartCooldownSeconds`| int | `120` | Minimum wait time in seconds between recovery attempts. |
| `-MetricsTimeoutSeconds` | int | `5` | Timeout for the Prometheus metrics HTTP request. |
| `-Status` | switch | `false` | Outputs a quick health and status summary and exits immediately. |
| `-InstallTask` | switch | `false` | Registers and starts the Windows Scheduled Task (runs as SYSTEM). |
| `-UninstallTask` | switch | `false` | Unregisters the Windows Scheduled Task. |
| `-GrantPermissions` | switch | `false` | Grants non-administrator users permission to restart Cloudflared without elevation. |
| `-Once` | switch | `false` | Runs a single monitoring iteration and exits. |
