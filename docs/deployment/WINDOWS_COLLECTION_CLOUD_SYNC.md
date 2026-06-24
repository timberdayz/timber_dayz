# Windows Collection Machine Cloud Sync

## Scope

This runbook defines the Windows collection-machine topology for B-class cloud
sync.

Current pre-launch formal mode:
- Windows host Python backend process
- visible/headed Playwright browser on the laptop desktop
- Docker infrastructure only: `postgres`, `redis`, `celery-worker`, `celery-beat`

Future unattended mode:
- Docker `backend-collector` as the always-on owner
- use only after collection no longer needs a browser window visible on the
  Windows desktop

The current operational source of truth is
[`docs/guides/LOCAL_COLLECTION_TAKEOVER.md`](/F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/LOCAL_COLLECTION_TAKEOVER.md).

## Current Runtime Topology

Host:
- Windows laptop
- Docker Desktop
- a host-managed SSH tunnel that forwards the cloud PostgreSQL port to `127.0.0.1:15433`
- local Python backend process started by `python run.py --local`
- local Vite frontend
- visible Playwright browser

Docker containers:
- `postgres`
- `redis`
- `celery-worker`
- `celery-beat`

Do not keep these Docker backend containers running in current headed mode:
- `backend-api`
- `backend-collector`

Cloud sync data path:
1. collection work writes B-class rows into the local database
2. `DATA_INGESTED` enqueues cloud sync tasks
3. the host backend cloud-sync runtime claims tasks
4. canonical rows are upserted into `b_class.*` in the cloud database
5. the current checkpoint scope advances only for the active cloud target

## Required Configuration

Current headed formal mode uses:
- `.env`
- optional `.env.local`
- `.env.collection.local`

Required cloud sync variables:
- `DEPLOYMENT_ROLE=local`
- `APP_RUNTIME_MODE=collector`
- `ENABLE_COLLECTION=true`
- `CLOUD_SYNC_WORKER_ENABLED=true`
- `CLOUD_SYNC_WORKER_ID=<stable collector id>`
- `CLOUD_SYNC_POLL_INTERVAL_SECONDS=5`
- `CLOUD_DATABASE_URL=postgresql://...@127.0.0.1:15433/xihong_erp`
- `CLOUD_SYNC_TUNNEL_ENABLED=true`
- `CLOUD_SYNC_TUNNEL_HOST=127.0.0.1`
- `CLOUD_SYNC_TUNNEL_PORT=15433`
- `CLOUD_SYNC_SSH_HOST=134.175.222.171`
- `CLOUD_SYNC_SSH_USER=deploy`
- `CLOUD_SYNC_SSH_KEY=C:\Users\18689\.ssh\github_actions_deploy`
- `CLOUD_SYNC_REMOTE_DB_HOST=127.0.0.1`
- `CLOUD_SYNC_REMOTE_DB_PORT=15435`

Keep `DATABASE_URL` pointed at the local business database.
Keep `CLOUD_DATABASE_URL` pointed at the remote cloud target through the SSH
tunnel. Do not reuse one for the other.

## Startup

1. Start Docker Desktop.
2. Start formal headed collection mode. The script starts the SSH tunnel when it is not already reachable:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_collection_formal.ps1
```

3. Check the local backend:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/healthz/ready
```

4. Check Docker infrastructure:

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected Docker services:
- `xihong_erp_postgres`
- `xihong_erp_redis`
- `xihong_erp_celery_worker`
- `xihong_erp_celery_beat`

Unexpected in current headed mode:
- `xihong_erp_backend_api`
- `xihong_erp_backend_collector`

## Health And Recovery

Container health:
- use Docker health status for infrastructure containers only

Cloud sync operational health:
- use the admin-only `/api/cloud-sync/health`
- use `/api/cloud-sync/tables` to inspect the current checkpoint scope only

Expected degraded conditions:
- tunnel down
- cloud DB unreachable
- tasks accumulating in `pending`
- tasks in `retry_waiting`

Recovery actions:
- restore the SSH tunnel
- restart with `scripts/start_collection_formal.ps1`
- use retry for failed tasks
- use checkpoint repair only for the current active cloud target

### Cloud Sync Worker Log Monitoring

The cloud sync worker runs inside the host Python backend process started by
`scripts\start_collection_formal.ps1`. It does **not** run inside the Docker
`celery-worker` container in current headed mode (the container's env block
does not receive `CLOUD_DATABASE_URL`).

To capture and tail the worker log:

```powershell
# Start in background with timestamped log
New-Item -ItemType Directory -Force C:\xihong_logs | Out-Null
powershell -ExecutionPolicy Bypass -File .\scripts\start_collection_formal.ps1 `
    *> C:\xihong_logs\formal_$(Get-Date -Format yyyyMMdd_HHmmss).log

# Tail latest
Get-Content (Get-ChildItem C:\xihong_logs\formal_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Wait -Tail 200
```

For live state without parsing logs, hit the admin-only API:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/api/cloud-sync/health | Select-Object -ExpandProperty Content
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/api/cloud-sync/tables | Select-Object -ExpandProperty Content
```

Healthy baseline:
- a `poll cycle completed in <N>ms` line every `CLOUD_SYNC_POLL_INTERVAL_SECONDS` (default 5s)
- zero `retry_waiting` transitions for more than 2 minutes after collection activity stops

Error classification quick-reference (definitions in
`backend/services/cloud_b_class_auto_sync_worker.py`):

| Error code | Meaning |
|---|---|
| `cloud_db_unavailable` | cloud PostgreSQL refused connection |
| `cloud_db_connection_closed` | TCP succeeded, socket died mid-query |
| `tunnel_unhealthy` | local forwarded port stopped accepting |
| `ssh_process_failed` | the local `ssh.exe` process exited |

Backoff ladder when retryable: 1m → 5m → 15m → 60m, then the task stays in
`retry_waiting` until manual recovery or until the tunnel is restored.

### SSH Orphan Process Cleanup

`Ensure-CloudSyncTunnel` (in `scripts\start_collection_formal.ps1`) only
respawns the SSH tunnel when the local forwarded port (`127.0.0.1:15433`) is
**not** TCP-reachable. If a previous PowerShell session left a healthy
`ssh.exe` running, the launcher reuses it without re-verifying the SSH
session itself. That process will eventually die (after
`ServerAliveCountMax=3` × 30s = ~90s of upstream silence) and the worker will
discover it via `tunnel_unhealthy` or `ssh_process_failed` classifications.

If you need to manually clean up the tunnel:

```powershell
# 1. List every ssh.exe in your session
Get-Process ssh -ErrorAction SilentlyContinue |
    Where-Object { $_.SessionId -eq (Get-Process -Id $PID).SessionId } |
    Select-Object Id, ProcessName, StartTime |
    Format-Table -AutoSize

# 2. Find which PID owns the 15433 forward
Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
    Where-Object { $_.CommandLine -like '*-L 15433:*' } |
    Select-Object ProcessId, CommandLine

# 3. Kill only that PID
Stop-Process -Id <PID> -Force

# 4. Confirm 15433 is no longer LISTEN
Get-NetTCPConnection -LocalPort 15433 -State Listen -ErrorAction SilentlyContinue
# Expected: empty

# 5. Restart formal mode; it will spawn a fresh tunnel
powershell -ExecutionPolicy Bypass -File .\scripts\start_collection_formal.ps1
```

Only kill `ssh.exe` processes that belong to your session and that own the
`15433` forward. Do **not** touch `ssh.exe` belonging to other users or
serving other ports (Git, WSL, remote shells, etc.).

## Important Behavior

- `sync_now` only evaluates catch-up against the current `CLOUD_DATABASE_URL` scope
- `repair_checkpoint` only resets checkpoints in the current scope
- table state queries only show checkpoints for the current scope
- replay is safe because cloud writes remain idempotent upserts

## Future Docker Collector Mode

When headed browser visibility is no longer required, the Docker collector path
can become the formal always-on topology again:

```powershell
docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-cloud-sync.yml --profile collection-cloud-sync up -d postgres redis migrate backend-collector
```

For that future mode, use `host.docker.internal:15433` in `CLOUD_DATABASE_URL`
and `CLOUD_SYNC_TUNNEL_HOST`.
