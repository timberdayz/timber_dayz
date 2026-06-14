# Local Collection Takeover

This guide describes the supported way for a Windows development machine to
temporarily take over collection, auto-sync, and cloud-sync duties without
abandoning normal development work.

## Files

- Base development values stay in `.env` or `.env.local`
- Temporary collection takeover values go in `.env.collection.local`
- Start from [env.collection.local.example](/F:/Vscode/python_programme/AI_code/xihong_erp/env.collection.local.example)

The runtime now loads files in this order:

1. `.env`
2. `.env.local`
3. `.env.collection.local` when `XIHONG_ENV_PROFILE=collection`

Later files override earlier files.

## Required Collection Overrides

At minimum, `.env.collection.local` should provide:

- `ENABLE_COLLECTION=true`
- `DEPLOYMENT_ROLE=local`
- `APP_RUNTIME_MODE=collector`
- `REDIS_PORT=16379`
- `REDIS_URL=redis://:redis_pass_2025@localhost:16379/0`
- `CELERY_BROKER_URL=redis://:redis_pass_2025@localhost:16379/0`
- `CELERY_RESULT_BACKEND=redis://:redis_pass_2025@localhost:16379/0`
- `CLOUD_SYNC_WORKER_ENABLED=true`
- `CLOUD_DATABASE_URL=postgresql://...`

If the cloud database is reached through a host tunnel, also set:

- `CLOUD_SYNC_TUNNEL_ENABLED=true`
- `CLOUD_SYNC_TUNNEL_HOST=127.0.0.1`
- `CLOUD_SYNC_TUNNEL_PORT=15433`

## Startup

Use the wrapper script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_collection_mode.ps1
```

The wrapper:

1. sets `XIHONG_ENV_PROFILE=collection`
2. runs `python scripts/check_local_run_env.py --profile collection`
3. starts `python run.py --local`

To skip the preflight check:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_collection_mode.ps1 -SkipChecks
```

## Required Docker Service Topology

When local collection takeover is active, Docker should keep only the
infrastructure and background queue support services:

- `xihong_erp_postgres`
- `xihong_erp_redis`
- `xihong_erp_celery_worker`
- `xihong_erp_celery_beat`

Do not keep these containers running at the same time:

- `xihong_erp_backend_api`
- `xihong_erp_backend_collector`

Local Redis in this mode is a temporary broker/cache for the takeover runtime.
It should not be treated as durable queue storage. Production Redis persistence
requirements remain separate.

Reason:

- `python run.py --local` starts the backend as a local Python process
- the frontend dev proxy still targets `http://localhost:8001`
- if Docker `backend-api` remains on `8001`, the UI and health checks can hit the
  wrong backend instance
- if Docker `backend-collector` remains active, scheduled collection can be
  consumed by the container instead of the local takeover process

Before starting local takeover, stop the conflicting containers:

```powershell
docker stop xihong_erp_backend_api xihong_erp_backend_collector
```

Before shutting down the Windows machine, stop local Docker infra cleanly:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml stop
```

## Verification

After startup, verify:

- `xihong_erp_postgres` is healthy
- `xihong_erp_redis` is healthy
- `xihong_erp_celery_worker` is healthy
- `xihong_erp_celery_beat` is healthy
- `xihong_erp_backend_api` is stopped
- `xihong_erp_backend_collector` is stopped
- `http://localhost:8001/healthz/ready` returns `200`

Check Redis port mapping:

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String "xihong_erp_redis"
```

Expected:

```text
0.0.0.0:16379->6379/tcp
```

## Redis Recovery

If `start_local_collection_mode.ps1` or `python run.py --local` reports Redis
AOF or appendonly corruption after an abnormal shutdown, recover the local Redis
volume before retrying startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\repair_local_redis.ps1 -FixAof
```

If repair fails, rebuild the local Redis volume:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\repair_local_redis.ps1 -Rebuild
```

`-Rebuild` clears local Redis queue and cache data and is only intended for the
local development volume `xihong_erp_redis_data`.

## Session Rules

- Always open and save formal platform sessions with `-AccountId`
- Never use a temporary no-account `pwcli` session as the formal collection session source
- Do not run the same formal account concurrently on multiple machines
- Keep collection browser profiles separate from everyday development browsing
