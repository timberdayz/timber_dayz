param(
    [switch]$SkipChecks,
    [switch]$SkipTunnel,
    [switch]$TunnelOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Write-StageResult {
    param(
        [string]$Stage,
        [string]$Status
    )
    Write-Host "XIHONG_STAGE=${Stage}:${Status}"
}

function Write-FailureResult {
    param(
        [string]$Code,
        [string]$Summary,
        [string]$Hint,
        [int]$SourceExitCode = 0
    )
    Write-Host "XIHONG_FAILURE_CODE=$Code"
    Write-Host "XIHONG_FAILURE_SUMMARY=$Summary"
    Write-Host "XIHONG_RECOVERY_HINT=$Hint"
    Write-Host "XIHONG_SOURCE_EXIT_CODE=$SourceExitCode"
}

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
    $remoteDbPortRaw = Get-EnvOrDefault "CLOUD_SYNC_REMOTE_DB_PORT" "15435"

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

function Invoke-LocalCurrentSchemaMigration {
    Write-StageResult -Stage "migration_preflight" -Status "started"
    Write-StageResult -Stage "backup" -Status "started"
    Write-Host "[Migration] Running fail-closed current-schema migration before backend startup..."
    Push-Location $repoRoot
    try {
        $migrationOutput = & python "$repoRoot\scripts\run_current_schema_migrations.py" 2>&1
        $migrationOutput | ForEach-Object { Write-Host $_ }
        $migrationExitCode = $LASTEXITCODE
        if ($migrationExitCode -ne 0) {
            $existingFailureCode = ($migrationOutput | Select-String -Pattern '^XIHONG_FAILURE_CODE=' | Select-Object -Last 1).Line
            $existingFailureSummary = ($migrationOutput | Select-String -Pattern '^XIHONG_FAILURE_SUMMARY=' | Select-Object -Last 1).Line
            $existingRecoveryHint = ($migrationOutput | Select-String -Pattern '^XIHONG_RECOVERY_HINT=' | Select-Object -Last 1).Line
            $diagnosticJson = & python "$repoRoot\scripts\run_current_schema_migrations.py" --diagnose --json 2>$null
            $diagnosis = $null
            try {
                $diagnosis = $diagnosticJson | ConvertFrom-Json
            } catch {
                $diagnosis = $null
            }
            $failureCode = if ($existingFailureCode) { $existingFailureCode.Substring("XIHONG_FAILURE_CODE=".Length) } elseif ($diagnosis -and $diagnosis.failure_code) { $diagnosis.failure_code } else { "migration_failed" }
            $failureSummary = if ($existingFailureSummary) { $existingFailureSummary.Substring("XIHONG_FAILURE_SUMMARY=".Length) } elseif ($diagnosis -and $diagnosis.failure_summary) { $diagnosis.failure_summary } else { "Current-schema migration was rejected before write." }
            $recoveryHint = if ($existingRecoveryHint) { $existingRecoveryHint.Substring("XIHONG_RECOVERY_HINT=".Length) } elseif ($diagnosis -and $diagnosis.recommended_action) { $diagnosis.recommended_action } else { "Review the migration diagnostic and request schema approval if required." }
            if (
                $failureCode -eq "migration_schema_drift" -and
                $diagnosis -and
                $diagnosis.actual_fingerprint -and
                $diagnosis.approved_fingerprint
            ) {
                $failureSummary = "$failureSummary Actual fingerprint: $($diagnosis.actual_fingerprint); approved fingerprint: $($diagnosis.approved_fingerprint)."
            }
            Write-StageResult -Stage "migration_write" -Status "failed"
            Write-FailureResult -Code $failureCode -Summary $failureSummary -Hint $recoveryHint -SourceExitCode $migrationExitCode
            exit $migrationExitCode
        }
        Write-StageResult -Stage "backup" -Status "passed"
        Write-StageResult -Stage "migration_write" -Status "passed"
        Write-Host "[OK] Local database migration passed current-schema preflight"
    } finally {
        Pop-Location
    }
}

$env:XIHONG_ENV_PROFILE = "collection"
$env:XIHONG_REQUIRE_LOCAL_MIGRATION_BACKUP = "1"

Import-EnvFile "$repoRoot\.env"
Import-EnvFile "$repoRoot\.env.local"
Import-EnvFile "$repoRoot\.env.collection.local"

Write-Host "[Mode] Formal collection laptop mode: local headed backend, Docker infrastructure only"
Write-Host "[Guard] Docker backend-api/backend-collector will be stopped before startup"

try {
    Write-StageResult -Stage "stop_conflicting_backend" -Status "started"
    docker stop xihong_erp_backend_api xihong_erp_backend_collector | Out-Null
    Write-StageResult -Stage "stop_conflicting_backend" -Status "passed"
} catch {
    Write-Host "[INFO] skip docker backend stop: $($_.Exception.Message)"
    Write-StageResult -Stage "stop_conflicting_backend" -Status "skipped"
}

if (-not $SkipTunnel) {
    try {
        Write-StageResult -Stage "tunnel" -Status "started"
        Ensure-CloudSyncTunnel
        Write-StageResult -Stage "tunnel" -Status "passed"
    } catch {
        Write-StageResult -Stage "tunnel" -Status "failed"
        Write-FailureResult -Code "tunnel_unavailable" -Summary "Cloud sync tunnel is unavailable." -Hint "Confirm the SSH key, tunnel settings, and remote database reachability."
        exit 2
    }
}

if ($TunnelOnly) {
    Write-Host "[OK] TunnelOnly requested; cloud sync tunnel is ready."
    exit 0
}

if (-not $SkipChecks) {
    Invoke-LocalCurrentSchemaMigration
    Write-StageResult -Stage "environment" -Status "started"
    & python "$repoRoot\scripts\check_local_run_env.py" --profile collection --require-cloud-tunnel
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] Formal collection preflight failed. Confirm the SSH tunnel is running and CLOUD_SYNC_TUNNEL_HOST:CLOUD_SYNC_TUNNEL_PORT is reachable."
        Write-StageResult -Stage "environment" -Status "failed"
        Write-FailureResult -Code "environment_invalid" -Summary "Local collection environment validation failed." -Hint "Confirm the SSH tunnel and required local environment settings." -SourceExitCode $LASTEXITCODE
        exit $LASTEXITCODE
    }
    Write-StageResult -Stage "environment" -Status "passed"
}

Write-StageResult -Stage "backend" -Status "started"
try {
    & python "$repoRoot\run.py" --local
    $backendExitCode = $LASTEXITCODE
    if ($backendExitCode -ne 0) {
        Write-StageResult -Stage "backend" -Status "failed"
        Write-FailureResult -Code "backend_start_failed" -Summary "Local backend exited before startup completed." -Hint "Review the bounded Local Console logs." -SourceExitCode $backendExitCode
    }
    exit $backendExitCode
} catch {
    Write-StageResult -Stage "backend" -Status "failed"
    Write-FailureResult -Code "backend_start_failed" -Summary "Local backend startup raised an exception." -Hint "Review the bounded Local Console logs."
    exit 1
}
