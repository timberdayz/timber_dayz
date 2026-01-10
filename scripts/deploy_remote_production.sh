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

  # [FIX] 所有日志输出到 stderr，stdout 只输出 tag（避免命令替换捕获日志）
  echo "[INFO] Attempting to pull ${full_image}..." >&2
  for retry in 1 2 3; do
    echo "[INFO] Pull attempt ${retry}/3 for ${full_image}..." >&2
    docker pull "${full_image}" >&2 || true
    if docker image inspect "${full_image}" >/dev/null 2>&1; then
      echo "[OK] Image pulled successfully with tag ${primary_tag}" >&2
      echo "${primary_tag}"  # stdout: only tag (no newline/whitespace)
      return 0
    fi
    sleep 5
  done

  if [ "${primary_tag}" != "${fallback_tag}" ]; then
    local full_image_fallback="${GHCR_REGISTRY}/${image_name}:${fallback_tag}"
    echo "[WARN] Primary tag ${primary_tag} failed, trying fallback tag ${fallback_tag}..." >&2
    for retry in 1 2 3; do
      echo "[INFO] Fallback pull attempt ${retry}/3 for ${full_image_fallback}..." >&2
      docker pull "${full_image_fallback}" >&2 || true
      if docker image inspect "${full_image_fallback}" >/dev/null 2>&1; then
        echo "[OK] Image pulled successfully with fallback tag ${fallback_tag}" >&2
        echo "${fallback_tag}"  # stdout: only tag (no newline/whitespace)
        return 0
      fi
      sleep 5
    done
  fi

  echo "[FAIL] Failed to pull image ${image_name} with tag ${primary_tag} (and fallback ${fallback_tag})" >&2
  echo "[INFO] Please verify the tag exists in GHCR and server has network access." >&2
  return 1
}

echo "[INFO] Pulling backend image..."
# [FIX] 使用进程替换（process substitution）方案：stderr（日志）通过 tee 输出到终端，stdout（tag）被捕获
# 函数内部所有日志通过 >&2 输出到 stderr，stdout 只输出 tag
# 使用 2> >(tee >&2) 让 stderr 同时显示在终端和管道中，但实际捕获时只捕获 stdout
# 更简单的方法：先执行并捕获所有输出，然后从 stdout 中提取 tag，stderr 已经在执行时显示了
# 但实际上，由于函数内部日志都输出到 stderr（>&2），stdout 只有 tag，所以直接捕获 stdout 即可
# 但为了能看到 stderr 日志，我们需要使用 tee 或者让 stderr 保持原样
# 最简单可靠的方法：将 stdout 和 stderr 都重定向，然后从 stdout 部分提取 tag，stderr 部分显示日志
# 但由于我们在函数内部已经明确分离了 stdout 和 stderr，所以可以这样：
TEMP_OUTPUT_FILE=$(mktemp)
TEMP_STDERR_FILE=$(mktemp)
# 将 stdout 和 stderr 分别捕获，stderr 同时显示在终端
if ! pull_image_with_fallback "${IMAGE_NAME_BACKEND}" "${IMAGE_TAG}" > "${TEMP_OUTPUT_FILE}" 2> "${TEMP_STDERR_FILE}"; then
  # 拉取失败，显示错误日志
  cat "${TEMP_STDERR_FILE}" >&2
  echo "[FAIL] Failed to pull backend image" >&2
  rm -f "${TEMP_OUTPUT_FILE}" "${TEMP_STDERR_FILE}"
  exit 1
fi
# 显示拉取进度日志（stderr）
cat "${TEMP_STDERR_FILE}" >&2
# 从 stdout 中提取 tag（过滤掉可能的日志行，以防万一）
BACKEND_TAG="$(grep -v '^\[.*\]' "${TEMP_OUTPUT_FILE}" | tail -n 1 | tr -d '\r\n' | xargs)"
rm -f "${TEMP_OUTPUT_FILE}" "${TEMP_STDERR_FILE}"
if [ -z "${BACKEND_TAG}" ]; then
  echo "[FAIL] Backend tag is empty after pull (tag extraction failed)" >&2
  exit 1
fi

echo "[INFO] Pulling frontend image..."
TEMP_OUTPUT_FILE=$(mktemp)
TEMP_STDERR_FILE=$(mktemp)
if ! pull_image_with_fallback "${IMAGE_NAME_FRONTEND}" "${IMAGE_TAG}" > "${TEMP_OUTPUT_FILE}" 2> "${TEMP_STDERR_FILE}"; then
  cat "${TEMP_STDERR_FILE}" >&2
  echo "[FAIL] Failed to pull frontend image" >&2
  rm -f "${TEMP_OUTPUT_FILE}" "${TEMP_STDERR_FILE}"
  exit 1
fi
cat "${TEMP_STDERR_FILE}" >&2
FRONTEND_TAG="$(grep -v '^\[.*\]' "${TEMP_OUTPUT_FILE}" | tail -n 1 | tr -d '\r\n' | xargs)"
rm -f "${TEMP_OUTPUT_FILE}" "${TEMP_STDERR_FILE}"
if [ -z "${FRONTEND_TAG}" ]; then
  echo "[FAIL] Frontend tag is empty after pull (tag extraction failed)" >&2
  exit 1
fi

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

# [FIX] 验证所有必需变量不为空且不包含特殊字符（防止 YAML 注入和格式错误）
if [ -z "${GHCR_REGISTRY}" ] || [ -z "${IMAGE_NAME_BACKEND}" ] || [ -z "${IMAGE_NAME_FRONTEND}" ]; then
  echo "[FAIL] Required variables are empty:"
  echo "  GHCR_REGISTRY='${GHCR_REGISTRY}'"
  echo "  IMAGE_NAME_BACKEND='${IMAGE_NAME_BACKEND}'"
  echo "  IMAGE_NAME_FRONTEND='${IMAGE_NAME_FRONTEND}'"
  exit 1
fi

if [ -z "${BACKEND_TAG}" ] || [ -z "${FRONTEND_TAG}" ]; then
  echo "[FAIL] Tag variables are empty: Backend='${BACKEND_TAG}', Frontend='${FRONTEND_TAG}'"
  exit 1
fi

# [FIX] 验证 tag 不包含特殊字符（防止 YAML 注入）
if echo "${BACKEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]' || echo "${FRONTEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]'; then
  echo "[FAIL] Tag contains invalid characters: Backend='${BACKEND_TAG}', Frontend='${FRONTEND_TAG}'"
  echo "[INFO] Tags must only contain alphanumeric characters, dots, underscores, and hyphens"
  exit 1
fi

# [FIX] 使用 cat 和 heredoc 创建 YAML（更安全，避免 printf 转义问题）
cat > docker-compose.deploy.yml <<EOF
services:
  backend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_BACKEND}:${BACKEND_TAG}
  frontend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_FRONTEND}:${FRONTEND_TAG}
    ports: []
EOF

echo "[OK] Temporary compose file created"

# [BOOTSTRAP] Phase 0.5: Clean .env file (remove CRLF and trailing whitespace)
# Note: PRODUCTION_PATH is the working directory (set by caller or defaults to current directory)
PRODUCTION_PATH="${PRODUCTION_PATH:-$(pwd)}"
echo "[INFO] Phase 0.5: Cleaning .env file (removing CRLF and trailing whitespace)..."
if [ -f "${PRODUCTION_PATH}/.env" ]; then
  sed -e 's/\r$//' -e 's/[ \t]*$//' "${PRODUCTION_PATH}/.env" > "${PRODUCTION_PATH}/.env.cleaned"
  echo "[OK] .env file cleaned: ${PRODUCTION_PATH}/.env.cleaned"
else
  echo "[WARN] .env file not found at ${PRODUCTION_PATH}/.env, skipping cleaning"
  # Create empty .env.cleaned to avoid errors in subsequent docker-compose commands
  touch "${PRODUCTION_PATH}/.env.cleaned"
fi

# [FIX] 立即验证 YAML 语法（更稳的防护，提前发现问题）
echo "[INFO] Validating docker-compose config..."
compose_cmd_base=(docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.deploy.yml --profile production)
if [ -f docker-compose.cloud.yml ]; then
  compose_cmd_base=(docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.deploy.yml --profile production)
fi

# [BOOTSTRAP] Add --env-file to all docker-compose commands (use cleaned .env file)
compose_cmd_base=("${compose_cmd_base[@]}" "--env-file" "${PRODUCTION_PATH}/.env.cleaned")

if ! "${compose_cmd_base[@]}" config >/dev/null 2>&1; then
  echo "[FAIL] docker-compose config validation failed"
  echo "[INFO] docker-compose.deploy.yml content (first 20 lines):"
  head -20 docker-compose.deploy.yml | nl -ba || true
  echo "[INFO] docker-compose config error output:"
  "${compose_cmd_base[@]}" config 2>&1 | head -30 || true
  exit 1
fi
echo "[OK] docker-compose config validated"

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

# [SCHEMA MIGRATION] Phase 2: 运行 Alembic 迁移（必须成功）
echo "[INFO] Phase 2: Running Alembic migrations (alembic upgrade head)..."
"${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade head
MIGRATION_EXIT_CODE=$?

if [ ${MIGRATION_EXIT_CODE} -ne 0 ]; then
  echo "[FAIL] Alembic migrations failed (exit code: ${MIGRATION_EXIT_CODE})"
  echo "[INFO] Deployment blocked due to migration failure"
  echo "[INFO] Please check migration logs and fix errors before retrying"
  exit 1
fi
echo "[OK] Alembic migrations completed successfully"

# [SCHEMA VERIFICATION] Phase 2.5: 验证表结构完整性（新增）
echo "[INFO] Phase 2.5: Verifying schema completeness..."
SCHEMA_VERIFY_OUTPUT=$("${compose_cmd_base[@]}" run --rm --no-deps backend python3 -c "
from backend.models.database import verify_schema_completeness
import json
import sys

try:
    result = verify_schema_completeness()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if not result['all_tables_exist']:
        print(f\"[FAIL] Missing tables: {', '.join(result['missing_tables'][:10])}\", file=sys.stderr)
        if len(result['missing_tables']) > 10:
            print(f\"[FAIL] ... and {len(result['missing_tables']) - 10} more tables\", file=sys.stderr)
        sys.exit(1)
    
    if result['migration_status'] not in ['up_to_date', 'not_initialized']:
        print(f\"[FAIL] Migration status: {result['migration_status']}\", file=sys.stderr)
        print(f\"[FAIL] Current revision: {result.get('current_revision', 'N/A')}\", file=sys.stderr)
        print(f\"[FAIL] Head revision: {result.get('head_revision', 'N/A')}\", file=sys.stderr)
        sys.exit(1)
    
    print(f\"[OK] Schema verification passed: {result['actual_table_count']} tables\", file=sys.stderr)
    sys.exit(0)
except Exception as e:
    print(f\"[FAIL] Schema verification error: {e}\", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
" 2>&1)

VERIFY_EXIT_CODE=$?

# 显示验证输出（包括错误信息）
echo "${SCHEMA_VERIFY_OUTPUT}"

if [ ${VERIFY_EXIT_CODE} -ne 0 ]; then
  echo "[FAIL] Schema verification failed (exit code: ${VERIFY_EXIT_CODE})"
  echo "[INFO] Deployment blocked due to schema incompleteness"
  echo "[INFO] Please check migration logs and verify all tables are created"
  exit 1
fi

echo "[OK] Schema verification completed successfully"

# [BOOTSTRAP] Phase 2.5: Bootstrap initialization (after migrations, before application layer)
echo "[INFO] Phase 2.5: Running production bootstrap..."
"${compose_cmd_base[@]}" run --rm --no-deps backend python3 /app/scripts/bootstrap_production.py
if [ $? -ne 0 ]; then
  echo "[FAIL] Bootstrap execution failed, deployment blocked"
  echo "[INFO] Bootstrap failure diagnostics (without sensitive information):"
  echo "  - Check bootstrap script logs above for details"
  echo "  - Verify environment variables in .env file"
  echo "  - Check database connection settings"
  exit 1
fi
echo "[OK] Bootstrap completed successfully"

echo "[INFO] Phase 3: starting Metabase (required before Nginx)..."
if [ -f docker-compose.metabase.yml ]; then
  docker-compose -f docker-compose.metabase.yml --env-file "${PRODUCTION_PATH}/.env.cleaned" --profile production up -d metabase
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
# [BOOTSTRAP] Clean up .env.cleaned file after successful deployment
if [ -f "${PRODUCTION_PATH}/.env.cleaned" ]; then
  rm -f "${PRODUCTION_PATH}/.env.cleaned"
  echo "[OK] Cleaned up .env.cleaned file"
fi
echo "[OK] Deployment completed. Tags: Backend=${BACKEND_TAG}, Frontend=${FRONTEND_TAG}"

