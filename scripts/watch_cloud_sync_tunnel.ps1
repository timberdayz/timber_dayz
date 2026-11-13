<#
.SYNOPSIS
    Watchdog for the cloud-sync SSH tunnel - keeps "is the tunnel still up?"
    a machine-checked fact instead of something a human has to remember.

.DESCRIPTION
    Why this exists
    ---------------
    The collection machine reaches the cloud database through one SSH tunnel:

        ssh -N -L 15433:127.0.0.1:15435 -i <key> deploy@<host>

    The account, the key, the defaults, and the read-only production
    verification commands are defined in docs/guides/SSH_ACCESS.md (SSOT).
    NOTE: `deploy@` is the ONLY interactive production identity; `root@` belongs
       to the deployment pipeline and its key is intentionally absent locally.
       A `root@` failure is NOT evidence that this machine has no key.

    Two properties of that tunnel matter:
      * the ssh process dies on its own after ~90s of upstream silence
        (ServerAliveInterval=30 / ServerAliveCountMax=3);
      * it never comes back by itself.

    => once the tunnel dies, cloud sync silently stops. The hourly integrity
       check can only *record* that it cannot reach the cloud - it cannot heal.

    What this script does
    ----------------------
    1. PROBE  : is the local forwarded port really connectable?
                (when the ssh process dies its local listener disappears,
                 so "port not connectable" is equivalent to "tunnel is dead")
    2. HEAL   : when it is down, first kill the STALE ssh process that still
                holds the port (otherwise the new process exits immediately
                because of ExitOnForwardFailure=yes), then reconnect using the
                SAME ssh options as Ensure-CloudSyncTunnel in
                scripts/start_collection_formal.ps1.
    3. TRACE  : append one line per run to the watchdog log, so we can tell
                afterwards when the tunnel died and for how long.

    Idempotent
    ----------
    If the port is already reachable the script exits 0 WITHOUT touching the
    running tunnel - safe to run every minute.

    It never touches containers
    ---------------------------
    This script manages the tunnel ONLY. It does not start or stop the
    backend / celery / frontend containers, so it can be run at any time
    without interrupting collection.

    NOTE ON ENCODING
    ----------------
    This file is intentionally ASCII-only. PowerShell 5.1 reads BOM-less
    .ps1 files using the system ANSI code page, so non-ASCII comments get
    decoded with the wrong code page and can break parsing. Every .ps1 in
    this repository is BOM-less, so ASCII-only is the house style here.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/watch_cloud_sync_tunnel.ps1

.EXAMPLE
    # Register a scheduled task (every 2 minutes) so the tunnel really persists
    # NOTE: the task action is "conhost.exe --headless powershell.exe ..." so the
    #       task never flashes a console window at the user (see the comment in
    #       Install-WatchdogScheduledTask).
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/watch_cloud_sync_tunnel.ps1 -InstallScheduledTask

.EXAMPLE
    # Report status only, do not heal
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/watch_cloud_sync_tunnel.ps1 -Status
#>
[CmdletBinding()]
param(
    # Report status only, do not heal.
    [switch]$Status,
    # Register a Windows scheduled task so the watchdog runs on a timer.
    [switch]$InstallScheduledTask,
    # Remove the scheduled task.
    [switch]$UninstallScheduledTask,
    # Scheduled task interval, in minutes.
    [int]$IntervalMinutes = 2,
    # Scheduled task name.
    [string]$TaskName = "XihongCloudSyncTunnelWatchdog"
)

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$logPath = Join-Path $repoRoot "logs\cloud-sync-tunnel-watchdog.log"

# ---------------------------------------------------------------------------
# Basic helpers (kept in sync with scripts/start_collection_formal.ps1)
# ---------------------------------------------------------------------------

function Import-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    # NOTE (2026-11-11): -Encoding UTF8 is REQUIRED, not cosmetic.
    # Windows PowerShell 5.1 decodes a BOM-less file with the system ANSI code
    # page (GBK on a zh-CN machine). The .env files carry Chinese comment
    # blocks; decoding them as GBK corrupts those lines and the parser stops
    # early, so EVERY variable below the first Chinese comment is dropped
    # silently. Kept in sync with scripts/start_collection_formal.ps1.
    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Get-EnvOrDefault {
    param(
        [string]$Name,
        [string]$DefaultValue
    )

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $DefaultValue
    }
    return $value
}

function Test-TcpPort {
    param(
        [string]$TargetHost,
        [int]$Port,
        [int]$TimeoutMs = 1500
    )

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $connectTask = $client.ConnectAsync($TargetHost, $Port)
        $completed = $connectTask.Wait($TimeoutMs)
        $connected = $completed -and $client.Connected
        $client.Close()
        return $connected
    } catch {
        return $false
    }
}

function Write-WatchdogLog {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    try {
        $dir = Split-Path -Parent $logPath
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        # Use .NET append instead of Add-Content: the latter injects a BOM.
        [System.IO.File]::AppendAllText(
            $logPath,
            $line + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )
    } catch {
        Write-Host "[WARN] failed to write watchdog log: $($_.Exception.Message)"
    }
}

function Get-TunnelSshProcesses {
    param([string]$LocalPort)

    $result = @()
    try {
        $result = Get-CimInstance -ClassName Win32_Process -Filter "Name='ssh.exe'" |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine.Contains("-L ") -and
                $_.CommandLine.Contains("${LocalPort}:")
            }
    } catch {
        Write-WatchdogLog "[WARN] failed to enumerate ssh processes: $($_.Exception.Message)"
    }
    return @($result)
}

# ---------------------------------------------------------------------------
# Tunnel healing
# ---------------------------------------------------------------------------

function Get-TunnelConfig {
    $localHost = Get-EnvOrDefault "CLOUD_SYNC_TUNNEL_HOST" "127.0.0.1"
    $localPortRaw = Get-EnvOrDefault "CLOUD_SYNC_TUNNEL_PORT" "15433"
    $sshHost = Get-EnvOrDefault "CLOUD_SYNC_SSH_HOST" "134.175.222.171"
    $sshUser = Get-EnvOrDefault "CLOUD_SYNC_SSH_USER" "deploy"
    $sshKey = Get-EnvOrDefault "CLOUD_SYNC_SSH_KEY" "$env:USERPROFILE\.ssh\github_actions_deploy"
    $remoteDbHost = Get-EnvOrDefault "CLOUD_SYNC_REMOTE_DB_HOST" "127.0.0.1"
    $remoteDbPortRaw = Get-EnvOrDefault "CLOUD_SYNC_REMOTE_DB_PORT" "15435"

    return [PSCustomObject]@{
        LocalHost    = $localHost
        LocalPort    = [int]$localPortRaw
        SshHost      = $sshHost
        SshUser      = $sshUser
        SshKey       = $sshKey
        RemoteDbHost = $remoteDbHost
        RemoteDbPort = [int]$remoteDbPortRaw
    }
}

function Remove-StaleTunnelProcesses {
    param([string]$LocalPort)

    $stale = Get-TunnelSshProcesses -LocalPort $LocalPort
    if (-not $stale -or $stale.Count -eq 0) {
        return 0
    }

    foreach ($process in $stale) {
        Write-WatchdogLog "[Tunnel] killing stale tunnel process pid=$($process.ProcessId)"
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        } catch {
            Write-WatchdogLog "[WARN] failed to kill pid=$($process.ProcessId): $($_.Exception.Message)"
        }
    }
    Start-Sleep -Seconds 1
    return $stale.Count
}

function Start-CloudSyncTunnel {
    param($Config)

    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        Write-WatchdogLog "[FAIL] ssh executable not found in PATH"
        return $false
    }
    if (-not (Test-Path $Config.SshKey)) {
        Write-WatchdogLog "[FAIL] SSH private key not found: $($Config.SshKey)"
        return $false
    }

    $forward = "$($Config.LocalPort):$($Config.RemoteDbHost):$($Config.RemoteDbPort)"
    $sshArgs = @(
        "-N",
        "-L", $forward,
        "-i", $Config.SshKey,
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=accept-new",
        "$($Config.SshUser)@$($Config.SshHost)"
    )

    Write-WatchdogLog "[Tunnel] starting tunnel $($Config.LocalHost):$($Config.LocalPort) -> $forward via $($Config.SshUser)@$($Config.SshHost)"

    try {
        $process = Start-Process -FilePath "ssh" -ArgumentList $sshArgs -WindowStyle Hidden -PassThru
    } catch {
        Write-WatchdogLog "[FAIL] failed to start ssh: $($_.Exception.Message)"
        return $false
    }

    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-TcpPort -TargetHost $Config.LocalHost -Port $Config.LocalPort) {
            Write-WatchdogLog "[OK] tunnel restored: $($Config.LocalHost):$($Config.LocalPort) (pid=$($process.Id))"
            return $true
        }
        if ($process.HasExited) {
            Write-WatchdogLog "[FAIL] ssh exited early with code $($process.ExitCode)"
            return $false
        }
    }

    Write-WatchdogLog "[FAIL] tunnel did not come up within 20s: $($Config.LocalHost):$($Config.LocalPort)"
    return $false
}

# ---------------------------------------------------------------------------
# Scheduled task
# ---------------------------------------------------------------------------

function Install-WatchdogScheduledTask {
    param(
        [string]$Name,
        [int]$Minutes
    )

    $scriptPath = Join-Path $PSScriptRoot "watch_cloud_sync_tunnel.ps1"

    # NOTE (2026-11-12): the task action MUST go through "conhost.exe --headless".
    #   A plain "powershell.exe" action gives the task an interactive console.
    #   Windows Terminal is the default console host on this machine, so every
    #   fire pops a VISIBLE terminal window in front of the user. At a 2-minute
    #   interval that is a black window flashing in and out forever - and the
    #   user cannot tell it apart from a hijack.
    #   "conhost.exe --headless" runs the identical command line with NO window
    #   at all (verified: 0 visible console windows, same exit code, same
    #   watchdog log line written).
    #   NOTE: "-WindowStyle Hidden" is NOT enough here - it still flashes,
    #   because the window is created by the terminal host, not by PowerShell.
    $conhost = Join-Path $env:SystemRoot "System32\conhost.exe"
    $taskCommand = '"' + $conhost + '" --headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '"'

    & schtasks /Create /TN $Name /TR $taskCommand /SC MINUTE /MO $Minutes /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] schtasks create failed, exit code $LASTEXITCODE"
        return $false
    }
    Write-Host "[OK] scheduled task '$Name' registered - runs every $Minutes minute(s)"
    Write-Host "     query  : schtasks /Query /TN $Name"
    Write-Host "     remove : schtasks /Delete /TN $Name /F"
    return $true
}

function Remove-WatchdogScheduledTask {
    param([string]$Name)

    & schtasks /Delete /TN $Name /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] schtasks delete failed, exit code $LASTEXITCODE"
        return $false
    }
    Write-Host "[OK] scheduled task '$Name' removed"
    return $true
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

Import-EnvFile (Join-Path $repoRoot ".env")
Import-EnvFile (Join-Path $repoRoot ".env.local")
Import-EnvFile (Join-Path $repoRoot ".env.collection.local")

if ($InstallScheduledTask) {
    if (Install-WatchdogScheduledTask -Name $TaskName -Minutes $IntervalMinutes) {
        exit 0
    }
    exit 1
}

if ($UninstallScheduledTask) {
    if (Remove-WatchdogScheduledTask -Name $TaskName) {
        exit 0
    }
    exit 1
}

$config = Get-TunnelConfig
$reachable = Test-TcpPort -TargetHost $config.LocalHost -Port $config.LocalPort

if ($reachable) {
    Write-WatchdogLog "[OK] tunnel is up: $($config.LocalHost):$($config.LocalPort)"
    exit 0
}

if ($Status) {
    Write-WatchdogLog "[DOWN] tunnel is down: $($config.LocalHost):$($config.LocalPort) (status only, not healed)"
    exit 1
}

Write-WatchdogLog "[DOWN] tunnel is down: $($config.LocalHost):$($config.LocalPort) - trying to heal"
Remove-StaleTunnelProcesses -LocalPort $config.LocalPort | Out-Null

if (Start-CloudSyncTunnel -Config $config) {
    exit 0
}

Write-WatchdogLog "[FAIL] healing failed"
exit 1
