# Windows Collection Machine Cloud Sync

## Scope

This runbook defines the formal Windows collection-machine topology for B-class cloud sync.

Formal always-on role:
- `backend-collector` only

Not part of the formal always-on topology:
- local frontend
- local business API for interactive development

Development-time local API is allowed temporarily, but it must not take over cloud sync ownership.

## Runtime Topology

Host:
- Windows laptop
- Docker Desktop
- a host-managed SSH tunnel that forwards the cloud PostgreSQL port to `127.0.0.1:15433`

Containers:
- `postgres`
- `redis`
- `migrate`
- `backend-collector`

Cloud sync data path:
1. collection work writes B-class rows into the local database
2. `DATA_INGESTED` enqueues cloud sync tasks
3. `backend-collector` claims tasks
4. canonical rows are upserted into `cloud_b_class.*` in the cloud database
5. the current checkpoint scope advances only for the active cloud target

## Required Configuration

Use:
- [docker-compose.collection-cloud-sync.yml](/F:/Vscode/python_programme/AI_code/xihong_erp/docker-compose.collection-cloud-sync.yml)
- [env.collection.cloud-sync.example](/F:/Vscode/python_programme/AI_code/xihong_erp/env.collection.cloud-sync.example)

Required cloud sync variables:
- `DEPLOYMENT_ROLE=collector`
- `APP_RUNTIME_MODE=collector`
- `ENABLE_COLLECTION=true`
- `CLOUD_SYNC_WORKER_ENABLED=true`
- `CLOUD_SYNC_WORKER_ID=<stable collector id>`
- `CLOUD_SYNC_POLL_INTERVAL_SECONDS=5`
- `CLOUD_DATABASE_URL=postgresql://...@host.docker.internal:15433/xihong_erp`
- `CLOUD_SYNC_TUNNEL_ENABLED=true`
- `CLOUD_SYNC_TUNNEL_HOST=host.docker.internal`
- `CLOUD_SYNC_TUNNEL_PORT=15433`

Keep `DATABASE_URL` pointed at the local business database.
Keep `CLOUD_DATABASE_URL` pointed at the remote cloud target through the SSH tunnel.
Do not reuse one for the other.

## Startup

1. Start the SSH tunnel on the Windows host and confirm `127.0.0.1:15433` is listening.
2. Start Docker Desktop.
3. Start the collector stack:

```powershell
docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-cloud-sync.yml --profile collection-cloud-sync up -d postgres redis migrate backend-collector
```

4. Check collector container status:

```powershell
docker ps --filter name=xihong_erp_backend_collector
```

5. Check startup logs:

```powershell
docker logs xihong_erp_backend_collector --tail 200
```

The collector now runs cloud sync startup checks at boot. Logs should include:
- local database connectivity
- cloud sync state table availability
- cloud database URL validation
- tunnel/cloud TCP reachability

## Health And Recovery

Container health:
- use `/healthz/ready` for Docker healthcheck only

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
- use retry for failed tasks
- use checkpoint repair only for the current active cloud target

## Important Behavior

- `sync_now` only evaluates catch-up against the current `CLOUD_DATABASE_URL` scope
- `repair_checkpoint` only resets checkpoints in the current scope
- table state queries only show checkpoints for the current scope
- replay is safe because cloud writes remain idempotent upserts

## Development Exception

You may temporarily run a local API process on the collection laptop for debugging or development.

That exception does not change the formal ownership rules:
- `backend-collector` remains the only always-on cloud sync owner
- development API processes must not become the cloud sync worker host
