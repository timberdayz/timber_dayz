# Template data sync to the cloud database (option A: compressed transfer).
#
# ROLE SINCE 2026-11-14 (batch 3: template decision assets move into Git):
#   This script is NO LONGER the "templates live in Git" path.
#   The DECISION content of a template (column list, core field list, parse
#   rules, dimension) now lives in the repository under templates/definitions,
#   one JSON file per dimension, and is applied through:
#       python scripts/apply_template_definitions.py --apply
#   What this script still does is transfer the whole template TABLE, which
#   carries runtime state the Git directory deliberately does not hold
#   (version history, usage counters, audit fields). The cloud environment
#   still needs that table, so this script is kept -- but its scope is
#   "runtime state sync", not "decision asset sync".
#
#   See templates/README.md for the split between decision and runtime state.
#
# NOTE: this file is intentionally ASCII-only.
#   The repository form of .ps1 files has no BOM, and a workstation whose ANSI
#   code page is GBK will decode the UTF-8 bytes of non-ASCII text as GBK,
#   which can break string quoting and produce bogus syntax errors.
#   ASCII bytes decode identically under every code page.
#
# Local database credentials are NEVER stored in this repository.
#   They are resolved at runtime from the (untracked) .env DATABASE_URL, or
#   from explicit parameters / the PGPASSWORD environment variable.
#   See docs/guides/ENV_FILE_CONTRACT.md.

param(
    [string]$SSH_KEY = "C:\Users\18689\.ssh\github_actions_deploy",
    [string]$SSH_USER = "deploy",
    [string]$SSH_HOST = "134.175.222.171",
    [string]$LOCAL_DB_HOST = "",
    [int]$LOCAL_DB_PORT = 0,
    [string]$LOCAL_DB_USER = "",
    [string]$LOCAL_DB_PASSWORD = "",
    [string]$LOCAL_DB_NAME = "",
    [string]$CLOUD_DB_USER = "erp_user",
    [string]$CLOUD_DB_NAME = "xihong_erp",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Project root (the parent of the scripts directory).
# NOTE: this used to walk up two levels, which pointed at the parent of the
#   repository. That made the .env lookup miss and the temp directory land
#   outside the repository.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TempDir = Join-Path $ProjectRoot "temp"

# ---------------------------------------------------------------------------
# Resolve local database settings at runtime (no credentials in the repo).
# ---------------------------------------------------------------------------
function Resolve-LocalDatabaseSettings {
    param(
        [string]$ProjectRoot,
        [string]$DbHost,
        [int]$DbPort,
        [string]$DbUser,
        [string]$DbPassword,
        [string]$DbName
    )

    $databaseUrl = $env:ERP_DATABASE_URL
    if (-not $databaseUrl) {
        $envFile = Join-Path $ProjectRoot ".env"
        if (Test-Path $envFile) {
            foreach ($line in (Get-Content $envFile -Encoding UTF8)) {
                $trimmed = $line.Trim()
                if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
                if ($trimmed -match '^(DATABASE_URL|ERP_DATABASE_URL)\s*=\s*(.+)$') {
                    $databaseUrl = $Matches[2].Trim().Trim('"').Trim("'")
                    break
                }
            }
        }
    }

    if ($databaseUrl) {
        $parsed = [regex]::Match(
            $databaseUrl,
            '^postgres(?:ql)?://(?<user>[^:@/]+)(?::(?<password>[^@]*))?@(?<host>[^:/]+)(?::(?<port>\d+))?/+(?<db>[^?/]+)'
        )
        if ($parsed.Success) {
            if ($parsed.Groups["host"].Value) { $DbHost = $parsed.Groups["host"].Value }
            if ($parsed.Groups["port"].Value) { $DbPort = [int]$parsed.Groups["port"].Value }
            if ($parsed.Groups["user"].Value) { $DbUser = $parsed.Groups["user"].Value }
            if ($parsed.Groups["db"].Value) { $DbName = $parsed.Groups["db"].Value }
            if ($parsed.Groups["password"].Success -and $parsed.Groups["password"].Value) {
                $DbPassword = [System.Uri]::UnescapeDataString($parsed.Groups["password"].Value)
            }
        } else {
            Write-Host "[WARN] DATABASE_URL format not recognized, falling back to explicit parameters" -ForegroundColor Yellow
        }
    }

    if (-not $DbPassword) { $DbPassword = $env:PGPASSWORD }
    if (-not $DbHost) { $DbHost = "localhost" }
    if (-not $DbPort) { $DbPort = 15432 }
    if (-not $DbUser) { $DbUser = "erp_user" }
    if (-not $DbName) { $DbName = "xihong_erp" }

    if (-not $DbPassword) {
        Write-Host "[FAIL] Local database password not found." -ForegroundColor Red
        Write-Host "      Set DATABASE_URL in the repository .env file, or set the PGPASSWORD / ERP_DATABASE_URL environment variable." -ForegroundColor Yellow
        exit 1
    }

    return @{
        Host     = $DbHost
        Port     = $DbPort
        User     = $DbUser
        Password = $DbPassword
        Name     = $DbName
    }
}

$dbSettings = Resolve-LocalDatabaseSettings -ProjectRoot $ProjectRoot `
    -DbHost $LOCAL_DB_HOST `
    -DbPort $LOCAL_DB_PORT `
    -DbUser $LOCAL_DB_USER `
    -DbPassword $LOCAL_DB_PASSWORD `
    -DbName $LOCAL_DB_NAME

$LOCAL_DB_HOST = $dbSettings.Host
$LOCAL_DB_PORT = $dbSettings.Port
$LOCAL_DB_USER = $dbSettings.User
$LOCAL_DB_PASSWORD = $dbSettings.Password
$LOCAL_DB_NAME = $dbSettings.Name

if (-not (Test-Path $TempDir)) {
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$SqlFile = Join-Path $TempDir "templates_export_$Timestamp.sql"
$GzFile = "$SqlFile.gz"
$RemoteFile = "/tmp/templates_export_$Timestamp.sql.gz"

Write-Host ""
Write-Host ("=" * 80) -ForegroundColor Cyan
Write-Host "Template data sync to cloud database (option A: compressed transfer)" -ForegroundColor Cyan
Write-Host ("=" * 80) -ForegroundColor Cyan
Write-Host ""
Write-Host "[Features]" -ForegroundColor Yellow
Write-Host "  - gzip compression reduces transfer time (typically 70-90%)" -ForegroundColor Gray
Write-Host "  - SSH compression accelerates the transfer" -ForegroundColor Gray
Write-Host "  - works for both domestic and overseas network environments" -ForegroundColor Gray
Write-Host ""

if ($DryRun) {
    Write-Host "[MODE] DRY-RUN (export only, no upload)" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  Local database: ${LOCAL_DB_HOST}:${LOCAL_DB_PORT}/${LOCAL_DB_NAME}" -ForegroundColor Gray
Write-Host "  Cloud server: ${SSH_USER}@${SSH_HOST}" -ForegroundColor Gray
Write-Host "  Cloud database: postgres:5432/${CLOUD_DB_NAME}" -ForegroundColor Gray
Write-Host ""

# Locate the pg_dump executable
$pgDumpPath = $null
if (Get-Command pg_dump -ErrorAction SilentlyContinue) {
    $pgDumpPath = "pg_dump"
} else {
    # Try the common install locations
    $possiblePaths = @(
        "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe",
        "C:\Program Files (x86)\PostgreSQL\*\bin\pg_dump.exe"
    )
    foreach ($path in $possiblePaths) {
        $found = Get-ChildItem -Path $path -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            $pgDumpPath = $found.FullName
            break
        }
    }
}

if (-not $pgDumpPath) {
    Write-Host "[FAIL] pg_dump not found. Install the PostgreSQL client tools and make sure they are on PATH." -ForegroundColor Red
    exit 1
}

# Step 1: export the local template data
Write-Host "[Step 1] Exporting local template data..." -ForegroundColor Cyan
try {
    $env:PGPASSWORD = $LOCAL_DB_PASSWORD
    $pgDumpArgs = @(
        "-h", $LOCAL_DB_HOST,
        "-p", $LOCAL_DB_PORT.ToString(),
        "-U", $LOCAL_DB_USER,
        "-d", $LOCAL_DB_NAME,
        "-t", "field_mapping_templates",
        "--data-only",
        "--column-inserts",
        "-f", $SqlFile
    )

    $pgDumpProcess = Start-Process -FilePath $pgDumpPath -ArgumentList $pgDumpArgs -Wait -PassThru -NoNewWindow

    if ($pgDumpProcess.ExitCode -ne 0) {
        throw "pg_dump failed with exit code $($pgDumpProcess.ExitCode)"
    }

    if (-not (Test-Path $SqlFile)) {
        throw "Export file was not produced: $SqlFile"
    }

    $sqlSize = (Get-Item $SqlFile).Length
    Write-Host "[OK] Template data exported: $SqlFile ($([math]::Round($sqlSize/1KB, 2)) KB)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Export failed: $_" -ForegroundColor Red
    exit 1
}

# Step 2: compress the SQL file
Write-Host ""
Write-Host "[Step 2] Compressing the export file..." -ForegroundColor Cyan
try {
    # .NET GZipStream (built into PowerShell)
    $inputFile = [System.IO.File]::OpenRead($SqlFile)
    $outputFile = [System.IO.File]::Create($GzFile)
    $gzipStream = New-Object System.IO.Compression.GZipStream($outputFile, [System.IO.Compression.CompressionMode]::Compress)

    $inputFile.CopyTo($gzipStream)
    $gzipStream.Close()
    $outputFile.Close()
    $inputFile.Close()

    $gzSize = (Get-Item $GzFile).Length
    $compressionRatio = [math]::Round((1 - $gzSize / $sqlSize) * 100, 1)
    Write-Host "[OK] File compressed: $GzFile ($([math]::Round($gzSize/1KB, 2)) KB, ratio ${compressionRatio}%)" -ForegroundColor Green

    # Remove the uncompressed SQL file
    Remove-Item $SqlFile -Force
    Write-Host "[INFO] Uncompressed file removed" -ForegroundColor Gray
} catch {
    Write-Host "[FAIL] Compression failed: $_" -ForegroundColor Red
    exit 1
}

if ($DryRun) {
    Write-Host ""
    Write-Host "[DRY-RUN] Simulated mode, skipping upload and import" -ForegroundColor Yellow
    Write-Host "[INFO] Compressed file location: $GzFile" -ForegroundColor Gray
    exit 0
}

# Step 3: upload to the cloud server
Write-Host ""
Write-Host "[Step 3] Uploading the file to the cloud server..." -ForegroundColor Cyan
if (Test-Path $GzFile) {
    $gzSize = (Get-Item $GzFile).Length
    Write-Host "[INFO] File size: $([math]::Round($gzSize/1KB, 2)) KB" -ForegroundColor Gray
} else {
    Write-Host "[FAIL] Compressed file does not exist: $GzFile" -ForegroundColor Red
    exit 1
}
try {
    $scpArgs = @(
        "-i", $SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "Compression=yes",
        $GzFile,
        "${SSH_USER}@${SSH_HOST}:${RemoteFile}"
    )

    $scpProcess = Start-Process -FilePath "scp" -ArgumentList $scpArgs -Wait -PassThru -NoNewWindow

    if ($scpProcess.ExitCode -ne 0) {
        throw "scp upload failed with exit code $($scpProcess.ExitCode)"
    }

    Write-Host "[OK] File uploaded to the cloud host: ${RemoteFile}" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Upload failed: $_" -ForegroundColor Red
    exit 1
}

# Step 4: import the template data on the cloud server
Write-Host ""
Write-Host "[Step 4] Importing template data on the cloud server..." -ForegroundColor Cyan
try {
    $importCmd = "cd /opt/xihong_erp && gunzip -c ${RemoteFile} | docker exec -i xihong_erp_postgres psql -U ${CLOUD_DB_USER} -d ${CLOUD_DB_NAME}"

    $sshArgs = @(
        "-i", $SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-o", "Compression=yes",
        "${SSH_USER}@${SSH_HOST}",
        $importCmd
    )

    $sshProcess = Start-Process -FilePath "ssh" -ArgumentList $sshArgs -Wait -PassThru -NoNewWindow -RedirectStandardOutput "$TempDir\import_output.txt" -RedirectStandardError "$TempDir\import_error.txt"

    if ($sshProcess.ExitCode -ne 0) {
        $errorContent = Get-Content "$TempDir\import_error.txt" -Raw -ErrorAction SilentlyContinue
        Write-Host "[FAIL] Import failed: $errorContent" -ForegroundColor Red
        exit 1
    }

    Write-Host "[OK] Template data imported into the cloud database" -ForegroundColor Green

    # Show the tail of the import output
    if (Test-Path "$TempDir\import_output.txt") {
        $output = Get-Content "$TempDir\import_output.txt" -Tail 5 -ErrorAction SilentlyContinue
        if ($output) {
            Write-Host "[INFO] Import output:" -ForegroundColor Gray
            $output | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
        }
    }
} catch {
    Write-Host "[FAIL] Import error: $_" -ForegroundColor Red
    exit 1
}

# Step 5: verify the template count on the cloud host
Write-Host ""
Write-Host "[Step 5] Verifying the cloud template counts..." -ForegroundColor Cyan
try {
    $verifyCmd = "docker exec xihong_erp_postgres psql -U ${CLOUD_DB_USER} -d ${CLOUD_DB_NAME} -t -c `"SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE status='published') as published FROM field_mapping_templates;`""

    $sshArgs = @(
        "-i", $SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "Compression=yes",
        "${SSH_USER}@${SSH_HOST}",
        $verifyCmd
    )

    $verifyOutput = & ssh $sshArgs 2>&1
    $verifyExitCode = $LASTEXITCODE

    if ($verifyExitCode -eq 0) {
        $verifyOutput = $verifyOutput.Trim()
        if ($verifyOutput -match '\s+(\d+)\s+\|\s+(\d+)') {
            $total = $matches[1]
            $published = $matches[2]
            Write-Host "[OK] Cloud template stats:" -ForegroundColor Green
            Write-Host "  total: $total" -ForegroundColor Gray
            Write-Host "  published: $published" -ForegroundColor Gray
        } else {
            Write-Host "[OK] Cloud templates: $verifyOutput" -ForegroundColor Green
        }
    } else {
        Write-Host "[WARN] Verification failed: $verifyOutput" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] Verification error: $_" -ForegroundColor Yellow
}

# Clean up temporary files
Write-Host ""
Write-Host "[Cleanup] Removing temporary files..." -ForegroundColor Cyan
try {
    if (Test-Path $GzFile) {
        Remove-Item $GzFile -Force
        Write-Host "[OK] Local temporary file removed: $GzFile" -ForegroundColor Green
    }

    # Clean up the remote temporary file
    $cleanupCmd = "rm -f ${RemoteFile}"
    $sshArgs = @(
        "-i", $SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "${SSH_USER}@${SSH_HOST}",
        $cleanupCmd
    )
    Start-Process -FilePath "ssh" -ArgumentList $sshArgs -Wait -NoNewWindow | Out-Null
    Write-Host "[OK] Remote temporary file removed: ${RemoteFile}" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Cleanup error: $_" -ForegroundColor Yellow
}

# Clean up the import output files
if (Test-Path "$TempDir\import_output.txt") {
    Remove-Item "$TempDir\import_output.txt" -Force -ErrorAction SilentlyContinue
}
if (Test-Path "$TempDir\import_error.txt") {
    Remove-Item "$TempDir\import_error.txt" -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host ("=" * 80) -ForegroundColor Green
Write-Host "Sync completed." -ForegroundColor Green
Write-Host ("=" * 80) -ForegroundColor Green
Write-Host ""
