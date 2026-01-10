#!/usr/bin/env bash
set -euo pipefail

# Remote deployment script for production server.
# This script is executed on the production server inside ${PRODUCTION_PATH}.
#
# Required env vars (provided by GitHub Actions via ssh):
# - GHCR_REGISTRY (e.g. ghcr.io)
# - GHCR_USER (github actor)
# - GHCR_TOKEN (passed via stdin/read in workflow then exported)
# - IMAGE_NAME_BACKEND
# - IMAGE_NAME_FRONTEND
# - IMAGE_TAG (requested tag, e.g. v4.20.4)
#
# Optional files in current dir:
# - docker-compose.yml (required)
# - docker-compose.prod.yml (required in prod)
# - docker-compose.cloud.yml (optional)
# - docker-compose.metabase.yml (required in prod)
# - .env (recommended)

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "[FAIL] Missing required env var: ${name}"
    exit 1
  fi
}

require_env "GHCR_REGISTRY"
require_env "GHCR_USER"
require_env "GHCR_TOKEN"
require_env "IMAGE_NAME_BACKEND"
require_env "IMAGE_NAME_FRONTEND"
require_env "IMAGE_TAG"

echo "[INFO] Working directory: $(pwd)"
echo "[INFO] Requested image tag: ${IMAGE_TAG}"

if [ -f ".env" ]; then
  echo "[INFO] Loading environment variables from .env ..."
  set -a
  if ! . ./.env 2>/dev/null; then
    echo "[ERROR] Failed to source .env. Please verify .env file syntax and line endings."
    echo "[INFO] Tip: run 'bash -n <(cat .env)' and 'sed -i \"s/\\r$//\" .env' on server"
    exit 1
  fi
  set +a
  echo "[INFO] .env loaded: POSTGRES_USER=${POSTGRES_USER:-erp_user}, POSTGRES_DB=${POSTGRES_DB:-xihong_erp}, REDIS_PASSWORD=${REDIS_PASSWORD:+***set}"
else
  echo "[WARN] .env not found; using defaults where applicable"
fi

# Normalize variables that are frequently affected by CRLF/whitespace.
POSTGRES_USER_VAL="${POSTGRES_USER:-erp_user}"
POSTGRES_DB_VAL="${POSTGRES_DB:-xihong_erp}"
REDIS_PASSWORD_VAL="${REDIS_PASSWORD:-redis_pass_2025}"
POSTGRES_USER_VAL="$(echo "${POSTGRES_USER_VAL}" | tr -d '\r' | tr -d '\n' | xargs)"
POSTGRES_DB_VAL="$(echo "${POSTGRES_DB_VAL}" | tr -d '\r' | tr -d '\n' | xargs)"
REDIS_PASSWORD_VAL="$(echo "${REDIS_PASSWORD_VAL}" | tr -d '\r' | tr -d '\n')"

echo "[INFO] Logging in to ${GHCR_REGISTRY}..."
docker login "${GHCR_REGISTRY}" -u "${GHCR_USER}" --password-stdin <<<"${GHCR_TOKEN}"
echo "[OK] Logged in to ${GHCR_REGISTRY}"

pull_image_with_fallback() {
  local image_name="$1"
  local primary_tag="$2"
  local fallback_tag="${primary_tag#v}"
  local full_image="${GHCR_REGISTRY}/${image_name}:${primary_tag}"

  echo "[INFO] Attempting to pull ${full_image}..."
  for retry in 1 2 3; do
    echo "[INFO] Pull attempt ${retry}/3 for ${full_image}..."
    docker pull "${full_image}" 2>&1 || true
    if docker image inspect "${full_image}" >/dev/null 2>&1; then
      echo "[OK] Image pulled successfully with tag ${primary_tag}"
      echo "${primary_tag}"
      return 0
    fi
    sleep 5
  done

  if [ "${primary_tag}" != "${fallback_tag}" ]; then
    local full_image_fallback="${GHCR_REGISTRY}/${image_name}:${fallback_tag}"
    echo "[WARN] Primary tag ${primary_tag} failed, trying fallback tag ${fallback_tag}..."
    for retry in 1 2 3; do
      echo "[INFO] Fallback pull attempt ${retry}/3 for ${full_image_fallback}..."
      docker pull "${full_image_fallback}" 2>&1 || true
      if docker image inspect "${full_image_fallback}" >/dev/null 2>&1; then
        echo "[OK] Image pulled successfully with fallback tag ${fallback_tag}"
        echo "${fallback_tag}"
        return 0
      fi
      sleep 5
    done
  fi

  echo "[FAIL] Failed to pull image ${image_name} with tag ${primary_tag} (and fallback ${fallback_tag})"
  echo "[INFO] Please verify the tag exists in GHCR and server has network access."
  return 1
}

echo "[INFO] Pulling backend image..."
BACKEND_TAG="$(pull_image_with_fallback "${IMAGE_NAME_BACKEND}" "${IMAGE_TAG}")" || exit 1
echo "[INFO] Pulling frontend image..."
FRONTEND_TAG="$(pull_image_with_fallback "${IMAGE_NAME_FRONTEND}" "${IMAGE_TAG}")" || exit 1
echo "[OK] Resolved tags: Backend=${BACKEND_TAG}, Frontend=${FRONTEND_TAG}"

echo "[INFO] Cleaning up old containers that might conflict with port 80..."
docker stop xihong_erp_frontend 2>/dev/null || true
docker rm xihong_erp_frontend 2>/dev/null || true
PORT_80_CONTAINER="$(docker ps --format "{{.Names}}" --filter "publish=80" 2>/dev/null | head -1 || echo "")"
if [ -n "${PORT_80_CONTAINER}" ] && [ "${PORT_80_CONTAINER}" != "xihong_erp_nginx" ]; then
  echo "[WARN] Found container ${PORT_80_CONTAINER} using port 80, stopping it..."
  docker stop "${PORT_80_CONTAINER}" 2>/dev/null || true
fi
echo "[OK] Cleanup completed"

export APP_ENV=production
export COMPOSE_PROJECT_NAME=xihong_erp

echo "[INFO] Creating temporary docker-compose.deploy.yml..."
printf "services:\n  backend:\n    image: %s/%s:%s\n  frontend:\n    image: %s/%s:%s\n    ports: []\n" \
  "${GHCR_REGISTRY}" "${IMAGE_NAME_BACKEND}" "${BACKEND_TAG}" \
  "${GHCR_REGISTRY}" "${IMAGE_NAME_FRONTEND}" "${FRONTEND_TAG}" \
  > docker-compose.deploy.yml
echo "[OK] Temporary compose file created"

compose_cmd_base=(docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.deploy.yml --profile production)
if [ -f docker-compose.cloud.yml ]; then
  compose_cmd_base=(docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.deploy.yml --profile production)
fi

echo "[INFO] Phase 1: starting infrastructure (PostgreSQL, Redis)..."
"${compose_cmd_base[@]}" up -d postgres redis

echo "[INFO] Waiting for infrastructure health..."
for i in $(seq 1 60); do
  postgres_output="$(docker exec xihong_erp_postgres pg_isready -U "${POSTGRES_USER_VAL}" -d "${POSTGRES_DB_VAL}" 2>&1 || true)"
  redis_output="$(docker exec xihong_erp_redis redis-cli -a "${REDIS_PASSWORD_VAL}" ping 2>&1 || true)"

  postgres_ok=""
  redis_ok=""
  if echo "${postgres_output}" | grep -qi "accepting connections"; then
    postgres_ok="ok"
  fi
  if echo "${redis_output}" | grep -q "^PONG"; then
    redis_ok="ok"
  fi

  if [ -n "${postgres_ok}" ] && [ -n "${redis_ok}" ]; then
    echo "[OK] Infrastructure is healthy"
    break
  fi

  if [ "${i}" = "60" ]; then
    echo "[FAIL] Infrastructure startup timeout"
    echo "  - PostgreSQL: ${postgres_output}"
    echo "  - Redis: ${redis_output}"
    echo "[INFO] Container status:"
    docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "xihong_erp_(postgres|redis)" || true
    echo "[INFO] PostgreSQL logs (tail 30):"
    docker logs xihong_erp_postgres --tail 30 2>&1 | sed 's/^/  [PostgreSQL] /' || true
    echo "[INFO] Redis logs (tail 30):"
    docker logs xihong_erp_redis --tail 30 2>&1 | sed 's/^/  [Redis] /' || true
    exit 1
  fi

  if [ $((i % 10)) -eq 0 ]; then
    echo "[WARN] Still waiting... (${i}/60)"
    echo "  - PostgreSQL: ${postgres_output}"
    echo "  - Redis: ${redis_output}"
  fi
  sleep 2
done

echo "[INFO] Phase 2: running DB migrations (alembic upgrade head)..."
"${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade head
echo "[OK] DB migrations completed"

echo "[INFO] Phase 3: starting Metabase (required before Nginx)..."
if [ -f docker-compose.metabase.yml ]; then
  docker-compose -f docker-compose.metabase.yml --profile production up -d metabase
  # Do not require curl inside container; just ensure it's running.
  sleep 5
  if docker ps --format "{{.Names}}" | grep -q "^xihong_erp_metabase$"; then
    echo "[OK] Metabase container started"
  else
    echo "[WARN] Metabase container not found after start; check metabase logs"
    docker logs xihong_erp_metabase --tail 50 2>&1 || true
  fi
else
  echo "[FAIL] docker-compose.metabase.yml not found; Metabase is required in production"
  exit 1
fi

echo "[INFO] Phase 4: starting application layer (backend, celery)..."
"${compose_cmd_base[@]}" up -d backend celery-worker celery-beat celery-exporter

echo "[INFO] Waiting for backend health..."
for i in $(seq 1 60); do
  if docker exec xihong_erp_backend curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    echo "[OK] Backend is healthy"
    break
  fi
  if [ "${i}" = "60" ]; then
    echo "[FAIL] Backend startup timeout"
    docker logs xihong_erp_backend --tail 80 2>&1 || true
    exit 1
  fi
  sleep 2
done

echo "[INFO] Phase 4b: starting frontend..."
"${compose_cmd_base[@]}" up -d frontend

echo "[INFO] Frontend health check (best-effort)..."
if docker ps --format "{{.Names}}" | grep -q "^xihong_erp_frontend$"; then
  # Avoid depending on curl inside the frontend container.
  if docker exec xihong_erp_frontend sh -lc 'command -v curl >/dev/null 2>&1' >/dev/null 2>&1; then
    for i in $(seq 1 30); do
      if docker exec xihong_erp_frontend curl -fsS http://localhost:80 >/dev/null 2>&1; then
        echo "[OK] Frontend responded on container port 80"
        break
      fi
      sleep 2
    done
  else
    echo "[INFO] Frontend container has no curl; skipping container HTTP health check"
  fi
else
  echo "[INFO] Frontend container not found; skipping"
fi

echo "[INFO] Phase 5: starting gateway (Nginx, last)..."
"${compose_cmd_base[@]}" up -d nginx

echo "[INFO] Nginx health check (host, best-effort)..."
if command -v curl >/dev/null 2>&1; then
  for i in $(seq 1 30); do
    if curl -fsS http://localhost/health >/dev/null 2>&1; then
      echo "[OK] Nginx /health passed"
      break
    fi
    sleep 2
  done
else
  echo "[INFO] Host has no curl; skipping Nginx /health check"
fi

echo "[INFO] Cleaning up temporary files..."
rm -f docker-compose.deploy.yml || true
echo "[OK] Deployment completed. Tags: Backend=${BACKEND_TAG}, Frontend=${FRONTEND_TAG}"

