# Local Dev Runtime Guide

## Goal

Keep `python run.py --local`, Docker infra, and local frontend/backend startup aligned.
This avoids Redis port conflicts, duplicate container names, and mixed manual startup paths.

## Recommended Topology

- PostgreSQL: Docker
- Redis: Docker
- Celery Worker: Docker
- Backend API: local process
- Frontend Vite: local process

Recommended command:

```powershell
python run.py --local
```

## Redis Port Convention

For local Windows development, use:

- Redis host port: `16379`
- Redis container port: `6379`

Required `.env` values:

```env
REDIS_PORT=16379
REDIS_URL=redis://:redis_pass_2025@localhost:16379/0
CELERY_BROKER_URL=redis://:redis_pass_2025@localhost:16379/0
CELERY_RESULT_BACKEND=redis://:redis_pass_2025@localhost:16379/0
```

## Why Not 6379

In the current Windows environment, Docker cannot reliably publish host port `6379`.
Typical symptoms:

- Redis container is healthy, but the backend cannot connect to `localhost:6379`
- The captcha resume API returns `503`
- `docker run -p 6379:6379` may fail with a host port permission error

Because of that, local development should use `16379`.

## Runtime Rules

### 1. Let compose own Redis

Do not create a duplicate Redis container manually:

```powershell
docker run --name xihong_erp_redis ...
```

That causes:

- name conflicts when `run.py --local` starts again
- compose losing ownership of the Redis lifecycle

### 2. Keep local infra on compose

These are the underlying compose commands:

```powershell
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d redis postgres
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d celery-worker
```

In normal usage, `python run.py --local` should handle this for you.

### 3. Restart the local backend after `.env` changes

If Redis host, port, or password changes, restart the local backend process.
Otherwise it will keep using the previous environment values.

## Verification

### Check the Redis container

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String "xihong_erp_redis"
```

Expected output should include:

```text
0.0.0.0:16379->6379/tcp
```

### Check host connectivity

```powershell
python - <<'PY'
import os
import redis
from dotenv import load_dotenv

load_dotenv(".env")
r = redis.from_url(
    os.getenv("REDIS_URL"),
    socket_connect_timeout=3,
    socket_timeout=3,
    decode_responses=True,
)
print(r.ping())
r.close()
PY
```

Expected output:

```text
True
```

### Check the captcha resume flow

1. Start a collection task that triggers a captcha
2. Enter the captcha in the Collection Tasks page
3. Click `Submit and Continue`
4. The request should no longer fail with Redis `503`

## Common Failures

### 1. `Captcha resume requires Redis, but Redis is unavailable`

Check:

- `.env` points `REDIS_URL` to `localhost:16379`
- the Redis container is running
- the backend was restarted after the env change

### 2. `container name "/xihong_erp_redis" is already in use`

That usually means a manual Redis container still exists or a previous failed run left it behind.

Remove the old container first, then restart with compose or `python run.py --local`.

### 3. `run.py --local` shows healthy containers, but captcha resume still fails

This usually means:

- Redis was restarted, but the local backend was not
- the backend process is still using the old `REDIS_URL`

## Recommended Recovery Order

```powershell
python run.py --local
```

If you need to reset local infra:

```powershell
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev down
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full down
python run.py --local
```
