# Collection Startup Modes

This guide defines the two supported Windows laptop startup paths for headed
collection and cloud sync. During the current pre-launch phase, the formal
collection laptop uses the host Python runtime so Playwright can open a visible
browser on the Windows desktop.

## Mode Selection

Use formal mode for daily collection work:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_collection_formal.ps1
```

Use development mode for local debugging:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_collection_mode.ps1
```

Both modes keep Docker `backend-api` and Docker `backend-collector` stopped.
Docker owns only `postgres`, `redis`, `celery-worker`, and `celery-beat`.
The Windows host owns the backend process, frontend dev server, visible
Playwright browser, and SSH tunnel.

## Files

- Base development values stay in `.env` or `.env.local`
- Temporary collection takeover values go in `.env.collection.local`
- Start from [env.collection.local.example](/F:/Vscode/python_programme/AI_code/xihong_erp/env.collection.local.example)

The runtime loads files in this order:

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

For formal collection, use the strict wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_collection_formal.ps1
```

The formal wrapper:

1. sets `XIHONG_ENV_PROFILE=collection`
2. stops Docker `backend-api` and Docker `backend-collector`
3. runs `python scripts/check_local_run_env.py --profile collection --require-cloud-tunnel`
4. starts `python run.py --local`

For development, use the flexible wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_collection_mode.ps1
```

The development wrapper:

1. sets `XIHONG_ENV_PROFILE=collection`
2. stops Docker `backend-api` and Docker `backend-collector`
3. runs `python scripts/check_local_run_env.py --profile collection`
4. starts `python run.py --local`

To skip the development preflight check:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_local_collection_mode.ps1 -SkipChecks
```

## Required Docker Service Topology

When either host-headed collection mode is active, Docker should keep only the
infrastructure and background queue support services:

- `xihong_erp_postgres`
- `xihong_erp_redis`
- `xihong_erp_celery_worker`
- `xihong_erp_celery_beat`

Do not keep these containers running at the same time:

- `xihong_erp_backend_api`
- `xihong_erp_backend_collector`

Reason:

- `python run.py --local` starts the backend as a local Python process
- the frontend dev proxy targets `http://localhost:8001`
- Docker `backend-api` on `8001` creates split-brain API behavior
- Docker `backend-collector` can consume scheduled collection instead of the local runtime

## Formal Mode Cloud Tunnel Requirement

Formal collection mode requires a reachable cloud database tunnel before the
application starts. The startup check fails when `CLOUD_SYNC_TUNNEL_ENABLED`,
`CLOUD_SYNC_TUNNEL_HOST`, `CLOUD_SYNC_TUNNEL_PORT`, or the actual TCP listener
is missing. For the current Windows laptop topology, the expected listener is:

```text
127.0.0.1:15433
```

Development mode validates the variables but does not require the tunnel TCP
probe to succeed before startup.

## Verification

After startup, verify:

- `xihong_erp_postgres` is healthy
- `xihong_erp_redis` is healthy
- `xihong_erp_celery_worker` is healthy
- `xihong_erp_celery_beat` is healthy
- `xihong_erp_backend_api` is stopped
- `xihong_erp_backend_collector` is stopped
- `http://localhost:8001/healthz/ready` returns `200`
- formal mode only: `/api/cloud-sync/health` no longer reports the cloud tunnel as unreachable

Check Redis port mapping:

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String "xihong_erp_redis"
```

Expected:

```text
0.0.0.0:16379->6379/tcp
```

## Redis Recovery

If either startup script reports Redis AOF or appendonly corruption after an
abnormal shutdown, recover the local Redis volume before retrying startup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\repair_local_redis.ps1 -FixAof
```

If repair fails, rebuild the local Redis volume:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\repair_local_redis.ps1 -Rebuild
```

`-Rebuild` clears local Redis queue and cache data and is only intended for the
local development volume `xihong_erp_redis_data`.

## Future Docker Collector Mode

Docker `backend-collector` remains the future unattended option. Do not use it
as the current formal headed collection path unless collection no longer needs
a browser window visible on the Windows desktop.

## Session Rules

- Always open and save formal platform sessions with `-AccountId`
- Never use a temporary no-account `pwcli` session as the formal collection session source
- Do not run the same formal account concurrently on multiple machines
- Keep collection browser profiles separate from everyday development browsing
