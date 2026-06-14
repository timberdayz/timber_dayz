param(
    [switch]$SkipChecks,
    [switch]$SkipTunnel,
    [switch]$TunnelOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Import-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
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

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMs = 1000
    )

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $connectTask = $client.ConnectAsync($HostName, $Port)
        $completed = $connectTask.Wait($TimeoutMs)
        $connected = $completed -and $client.Connected
        $client.Close()
        return $connected
    } catch {
        return $false
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

function Ensure-CloudSyncTunnel {
    $localHost = Get-EnvOrDefault "CLOUD_SYNC_TUNNEL_HOST" "127.0.0.1"
    $localPortRaw = Get-EnvOrDefault "CLOUD_SYNC_TUNNEL_PORT" "15433"
    $sshHost = Get-EnvOrDefault "CLOUD_SYNC_SSH_HOST" "134.175.222.171"
    $sshUser = Get-EnvOrDefault "CLOUD_SYNC_SSH_USER" "deploy"
    $sshKey = Get-EnvOrDefault "CLOUD_SYNC_SSH_KEY" "$env:USERPROFILE\.ssh\github_actions_deploy"
    $remoteDbHost = Get-EnvOrDefault "CLOUD_SYNC_REMOTE_DB_HOST" "127.0.0.1"
    $remoteDbPortRaw = Get-EnvOrDefault "CLOUD_SYNC_REMOTE_DB_PORT" "5432"

    $localPort = [int]$localPortRaw
    $remoteDbPort = [int]$remoteDbPortRaw

    if (Test-TcpPort -HostName $localHost -Port $localPort) {
        Write-Host "[OK] Cloud sync tunnel already reachable: ${localHost}:${localPort}"
        return
    }

    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        throw "ssh executable not found in PATH"
    }
    if (-not (Test-Path $sshKey)) {
        throw "CLOUD_SYNC_SSH_KEY not found: $sshKey"
    }

    Write-Host "[Tunnel] Starting SSH tunnel ${localHost}:${localPort} -> ${remoteDbHost}:${remoteDbPort} via ${sshUser}@${sshHost}"

    $forward = "${localPort}:${remoteDbHost}:${remoteDbPort}"
    $sshArgs = @(
        "-N",
        "-L", $forward,
        "-i", $sshKey,
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=accept-new",
        "${sshUser}@${sshHost}"
    )

    $process = Start-Process -FilePath "ssh" -ArgumentList $sshArgs -WindowStyle Hidden -PassThru
    for ($i = 1; $i -le 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-TcpPort -HostName $localHost -Port $localPort) {
            Write-Host "[OK] Cloud sync tunnel is reachable: ${localHost}:${localPort}"
            return
        }
        if ($process.HasExited) {
            throw "SSH tunnel process exited early with code $($process.ExitCode)"
        }
    }

    throw "Cloud sync tunnel did not become reachable within 20 seconds: ${localHost}:${localPort}"
}

$env:XIHONG_ENV_PROFILE = "collection"

Import-EnvFile "$repoRoot\.env"
Import-EnvFile "$repoRoot\.env.local"
Import-EnvFile "$repoRoot\.env.collection.local"

Write-Host "[Mode] Formal collection laptop mode: local headed backend, Docker infrastructure only"
Write-Host "[Guard] Docker backend-api/backend-collector will be stopped before startup"

try {
    docker stop xihong_erp_backend_api xihong_erp_backend_collector | Out-Null
} catch {
    Write-Host "[INFO] skip docker backend stop: $($_.Exception.Message)"
}

if (-not $SkipTunnel) {
    Ensure-CloudSyncTunnel
}

if ($TunnelOnly) {
    Write-Host "[OK] TunnelOnly requested; cloud sync tunnel is ready."
    exit 0
}

if (-not $SkipChecks) {
    & python "$repoRoot\scripts\check_local_run_env.py" --profile collection --require-cloud-tunnel
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] Formal collection preflight failed. Confirm the SSH tunnel is running and CLOUD_SYNC_TUNNEL_HOST:CLOUD_SYNC_TUNNEL_PORT is reachable."
        exit $LASTEXITCODE
    }
}

& python "$repoRoot\run.py" --local
exit $LASTEXITCODE
