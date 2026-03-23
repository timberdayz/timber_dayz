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
# - docker-compose.metabase.yml (legacy fallback/debug only; not part of PostgreSQL-first prod deploy)
# - .env (recommended)

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "[FAIL] Missing required env var: ${name}"
    exit 1
  fi
}

# GHCR 为 compose 镜像名与回退拉取所必需；GHCR_USER/TOKEN 回退时登录用（方案 A 下 CNB 全配置时可不先登录）
require_env "GHCR_REGISTRY"
require_env "GHCR_USER"
require_env "GHCR_TOKEN"
require_env "IMAGE_NAME_BACKEND"
require_env "IMAGE_NAME_FRONTEND"
require_env "IMAGE_TAG"

# CNB 全配置：优先仅用 CNB 拉取，不先连 GHCR，避免国内服务器访问 ghcr.io 超时（方案 A）
CNB_FULLY_CONFIGURED=0
if [ -n "${CNB_REGISTRY:-}" ] && [ -n "${CNB_TOKEN:-}" ] && [ -n "${CNB_IMAGE_NAME_BACKEND:-}" ] && [ -n "${CNB_IMAGE_NAME_FRONTEND:-}" ]; then
  CNB_FULLY_CONFIGURED=1
fi

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

# [方案 A] CNB 全配置时跳过 GHCR 登录，避免国内访问 ghcr.io 超时；仅在回退到 GHCR 拉取时再登录
if [ "${CNB_FULLY_CONFIGURED}" -eq 1 ]; then
  echo "[INFO] CNB fully configured: skipping GHCR login (will login to GHCR only if CNB pull fails)"
  echo "[INFO] CNB_REGISTRY=${CNB_REGISTRY}, CNB_IMAGE_NAME_BACKEND=${CNB_IMAGE_NAME_BACKEND}, CNB_IMAGE_NAME_FRONTEND=${CNB_IMAGE_NAME_FRONTEND}"
else
  echo "[INFO] Logging in to ${GHCR_REGISTRY}..."
  docker login "${GHCR_REGISTRY}" -u "${GHCR_USER}" --password-stdin <<<"${GHCR_TOKEN}"
  echo "[OK] Logged in to ${GHCR_REGISTRY}"
fi

# [NEW] CNB 配置状态显示（混合模式：优先使用 CNB，失败时回退到 GHCR）
echo "[INFO] CNB configuration (optional, for faster image pull in China):"
if [ -n "${CNB_REGISTRY:-}" ] && [ -n "${CNB_TOKEN:-}" ]; then
  echo "  CNB_REGISTRY: ${CNB_REGISTRY}"
  echo "  CNB_TOKEN: ***set"
  if [ -n "${CNB_IMAGE_NAME_BACKEND:-}" ] && [ -n "${CNB_IMAGE_NAME_FRONTEND:-}" ]; then
    echo "  CNB_IMAGE_NAME_BACKEND: ${CNB_IMAGE_NAME_BACKEND}"
    echo "  CNB_IMAGE_NAME_FRONTEND: ${CNB_IMAGE_NAME_FRONTEND}"
    echo "[OK] CNB configuration complete, will use CNB as primary source (GHCR as fallback)"
  else
    echo "[WARN] CNB_IMAGE_NAME_BACKEND or CNB_IMAGE_NAME_FRONTEND not set, CNB pull disabled"
  fi
else
  echo "[INFO] CNB not configured, will use GHCR only"
fi

# [IMAGE_CLEANUP] Clean up old Docker images (keep latest N versions)
cleanup_old_images() {
  local keep_count="${KEEP_IMAGES_COUNT:-5}"  # 默认保留 5 个版本，可通过环境变量覆盖
  local registry="${GHCR_REGISTRY}"
  
  echo "[INFO] Cleaning up old images (keeping latest ${keep_count} versions)..."
  
  # 安全措施：只清理版本号格式的 tag（如 v4.20.5），避免误删 latest、sha-* 等特殊标签
  local version_pattern="v[0-9]+\.[0-9]+\.[0-9]+$"
  
  # 清理 backend 镜像
  local backend_images
  backend_images=$(docker images --format "{{.Repository}}:{{.Tag}}" | \
    grep "^${registry}/${IMAGE_NAME_BACKEND}:" | \
    grep -E "${version_pattern}" | \
    sort -V -r 2>/dev/null || echo "")
  
  if [ -n "${backend_images}" ]; then
    local backend_count
    backend_count=$(echo "${backend_images}" | wc -l | tr -d ' \n\r')
    echo "[INFO] Found ${backend_count} backend version(s)"
    
    if [ "${backend_count}" -gt "${keep_count}" ]; then
      local to_remove_count=$((backend_count - keep_count))
      echo "[INFO] Removing ${to_remove_count} old backend image(s)..."
      echo "${backend_images}" | tail -n +$((keep_count + 1)) | \
        while read -r img; do
          if [ -n "${img}" ]; then
            echo "  [INFO] Removing: ${img}"
            docker rmi "${img}" 2>/dev/null || echo "  [WARN] Failed to remove ${img} (may be in use)"
          fi
        done
    else
      echo "[INFO] Backend images count (${backend_count}) <= keep count (${keep_count}), skipping cleanup"
    fi
  else
    echo "[INFO] No backend version images found to clean"
  fi
  
  # 清理 frontend 镜像
  local frontend_images
  frontend_images=$(docker images --format "{{.Repository}}:{{.Tag}}" | \
    grep "^${registry}/${IMAGE_NAME_FRONTEND}:" | \
    grep -E "${version_pattern}" | \
    sort -V -r 2>/dev/null || echo "")
  
  if [ -n "${frontend_images}" ]; then
    local frontend_count
    frontend_count=$(echo "${frontend_images}" | wc -l | tr -d ' \n\r')
    echo "[INFO] Found ${frontend_count} frontend version(s)"
    
    if [ "${frontend_count}" -gt "${keep_count}" ]; then
      local to_remove_count=$((frontend_count - keep_count))
      echo "[INFO] Removing ${to_remove_count} old frontend image(s)..."
      echo "${frontend_images}" | tail -n +$((keep_count + 1)) | \
        while read -r img; do
          if [ -n "${img}" ]; then
            echo "  [INFO] Removing: ${img}"
            docker rmi "${img}" 2>/dev/null || echo "  [WARN] Failed to remove ${img} (may be in use)"
          fi
        done
    else
      echo "[INFO] Frontend images count (${frontend_count}) <= keep count (${keep_count}), skipping cleanup"
    fi
  else
    echo "[INFO] No frontend version images found to clean"
  fi
  
  # [方案 A] 同时清理 CNB 镜像（若配置了 CNB），避免 docker.cnb.cool 侧旧版本堆积导致系统盘占满
  if [ -n "${CNB_REGISTRY:-}" ] && [ -n "${CNB_IMAGE_NAME_BACKEND:-}" ] && [ -n "${CNB_IMAGE_NAME_FRONTEND:-}" ]; then
    echo "[INFO] Cleaning up old CNB images (keeping latest ${keep_count} versions)..."
    local cnb_backend_images
    cnb_backend_images=$(docker images --format "{{.Repository}}:{{.Tag}}" | \
      grep "^${CNB_REGISTRY}/${CNB_IMAGE_NAME_BACKEND}:" | \
      grep -E "${version_pattern}" | \
      sort -V -r 2>/dev/null || echo "")
    if [ -n "${cnb_backend_images}" ]; then
      local cnb_backend_count
      cnb_backend_count=$(echo "${cnb_backend_images}" | wc -l | tr -d ' \n\r')
      if [ "${cnb_backend_count}" -gt "${keep_count}" ]; then
        local to_remove=$((cnb_backend_count - keep_count))
        echo "[INFO] Removing ${to_remove} old CNB backend image(s)..."
        echo "${cnb_backend_images}" | tail -n +$((keep_count + 1)) | \
          while read -r img; do
            [ -n "${img}" ] && { echo "  [INFO] Removing: ${img}"; docker rmi "${img}" 2>/dev/null || echo "  [WARN] Failed to remove ${img} (may be in use)"; }
          done
      else
        echo "[INFO] CNB backend images count (${cnb_backend_count}) <= keep count (${keep_count}), skipping"
      fi
    fi
    local cnb_frontend_images
    cnb_frontend_images=$(docker images --format "{{.Repository}}:{{.Tag}}" | \
      grep "^${CNB_REGISTRY}/${CNB_IMAGE_NAME_FRONTEND}:" | \
      grep -E "${version_pattern}" | \
      sort -V -r 2>/dev/null || echo "")
    if [ -n "${cnb_frontend_images}" ]; then
      local cnb_frontend_count
      cnb_frontend_count=$(echo "${cnb_frontend_images}" | wc -l | tr -d ' \n\r')
      if [ "${cnb_frontend_count}" -gt "${keep_count}" ]; then
        local to_remove=$((cnb_frontend_count - keep_count))
        echo "[INFO] Removing ${to_remove} old CNB frontend image(s)..."
        echo "${cnb_frontend_images}" | tail -n +$((keep_count + 1)) | \
          while read -r img; do
            [ -n "${img}" ] && { echo "  [INFO] Removing: ${img}"; docker rmi "${img}" 2>/dev/null || echo "  [WARN] Failed to remove ${img} (may be in use)"; }
          done
      else
        echo "[INFO] CNB frontend images count (${cnb_frontend_count}) <= keep count (${keep_count}), skipping"
      fi
    fi
    echo "[OK] CNB image cleanup completed"
  else
    echo "[INFO] CNB not configured, skipping CNB image cleanup"
  fi
  
  # 清理 dangling 镜像（未标记的中间层，这些通常是构建过程中的临时层）
  echo "[INFO] Cleaning up dangling images..."
  local pruned_size
  pruned_size=$(docker image prune -f 2>&1 | grep -i "space" | grep -oE "[0-9]+\.[0-9]+ [KMGT]B" || echo "unknown")
  echo "[OK] Dangling images cleaned (freed: ${pruned_size})"
  
  echo "[OK] Image cleanup completed"
}

pull_image_with_fallback() {
  local image_name="$1"
  local primary_tag="$2"
  local fallback_tag="${primary_tag#v}"
  
  # [NEW] 混合模式：优先从 CNB 拉取（如果配置了 CNB_REGISTRY 和 CNB_IMAGE_NAME）
  # 注意：CNB 镜像路径格式：docker.cnb.cool/timberdayz/xihong_erp/backend 或 frontend
  if [ -n "${CNB_REGISTRY:-}" ] && [ -n "${CNB_TOKEN:-}" ] && [ -n "${CNB_IMAGE_NAME_BACKEND:-}" ] && [ -n "${CNB_IMAGE_NAME_FRONTEND:-}" ]; then
    # 根据 image_name 判断是 backend 还是 frontend
    local cnb_image_name=""
    if [ "${image_name}" = "${IMAGE_NAME_BACKEND}" ]; then
      cnb_image_name="${CNB_IMAGE_NAME_BACKEND}"
    elif [ "${image_name}" = "${IMAGE_NAME_FRONTEND}" ]; then
      cnb_image_name="${CNB_IMAGE_NAME_FRONTEND}"
    else
      echo "[WARN] Unknown image name: ${image_name}, skipping CNB pull" >&2
    fi
    
    if [ -n "${cnb_image_name}" ]; then
      local cnb_image="${CNB_REGISTRY}/${cnb_image_name}:${primary_tag}"
      echo "[INFO] Attempting to pull from CNB (primary source): ${cnb_image}..." >&2
      
      # 先尝试登录 CNB（如果还没有登录）
      if ! docker info 2>/dev/null | grep -q "docker.cnb.cool" || ! docker image inspect "${cnb_image}" >/dev/null 2>&1; then
        echo "[INFO] Logging in to CNB registry..." >&2
        echo "${CNB_TOKEN}" | docker login "${CNB_REGISTRY}" -u cnb --password-stdin >&2 || true
      fi
      
      # 尝试从 CNB 拉取（最多3次重试，每次超时5分钟）
      for retry in 1 2 3; do
        echo "[INFO] CNB pull attempt ${retry}/3 for ${cnb_image}..." >&2
        # [FIX] 添加超时机制（5分钟），避免无限等待
        timeout 300 docker pull "${cnb_image}" >&2 || true
        if docker image inspect "${cnb_image}" >/dev/null 2>&1; then
          echo "[OK] Image pulled from CNB successfully with tag ${primary_tag}" >&2
          # [国内优先] 打上 GHCR 名，使 docker-compose.deploy.yml 中的 ghcr.io 镜像名指向本地镜像，避免再向 ghcr.io 拉取
          ghcr_image="${GHCR_REGISTRY}/${image_name}:${primary_tag}"
          if docker tag "${cnb_image}" "${ghcr_image}" 2>/dev/null; then
            echo "[INFO] Tagged CNB image as ${ghcr_image} (compose will use local image)" >&2
          fi
          echo "${primary_tag}"  # stdout: only tag
          return 0
        fi
        if [ ${retry} -lt 3 ]; then
          echo "[WARN] CNB pull attempt ${retry}/3 failed, retrying in 10 seconds..." >&2
          sleep 10
        fi
      done
      
      # CNB 拉取失败，尝试 fallback tag
      if [ "${primary_tag}" != "${fallback_tag}" ]; then
        local cnb_image_fallback="${CNB_REGISTRY}/${cnb_image_name}:${fallback_tag}"
        echo "[WARN] CNB primary tag ${primary_tag} failed, trying fallback tag ${fallback_tag}..." >&2
        for retry in 1 2 3; do
          echo "[INFO] CNB fallback pull attempt ${retry}/3 for ${cnb_image_fallback}..." >&2
          # [FIX] 添加超时机制（5分钟），避免无限等待
          timeout 300 docker pull "${cnb_image_fallback}" >&2 || true
          if docker image inspect "${cnb_image_fallback}" >/dev/null 2>&1; then
            echo "[OK] Image pulled from CNB successfully with fallback tag ${fallback_tag}" >&2
            # [国内优先] 打上 GHCR 名，使 compose 使用本地镜像
            ghcr_image_fb="${GHCR_REGISTRY}/${image_name}:${fallback_tag}"
            if docker tag "${cnb_image_fallback}" "${ghcr_image_fb}" 2>/dev/null; then
              echo "[INFO] Tagged CNB image as ${ghcr_image_fb} (compose will use local image)" >&2
            fi
            echo "${fallback_tag}"  # stdout: only tag
            return 0
          fi
          if [ ${retry} -lt 3 ]; then
            echo "[WARN] CNB fallback pull attempt ${retry}/3 failed, retrying in 10 seconds..." >&2
            sleep 10
          fi
        done
      fi
      
      echo "[WARN] CNB pull failed, falling back to GHCR..." >&2
    fi
  fi
  
  # 方案2：从 GHCR 拉取（原有逻辑，作为备选）。方案 A：回退到 GHCR 时再登录，避免国内先连 ghcr.io 超时
  if [ -n "${GHCR_REGISTRY:-}" ] && [ -n "${GHCR_USER:-}" ] && [ -n "${GHCR_TOKEN:-}" ]; then
    echo "[INFO] Logging in to ${GHCR_REGISTRY} for GHCR pull..." >&2
    echo "${GHCR_TOKEN}" | docker login "${GHCR_REGISTRY}" -u "${GHCR_USER}" --password-stdin >&2 || true
  fi
  local full_image="${GHCR_REGISTRY}/${image_name}:${primary_tag}"
  echo "[INFO] Attempting to pull ${full_image} from GHCR..." >&2
  for retry in 1 2 3; do
    echo "[INFO] GHCR pull attempt ${retry}/3 for ${full_image}..." >&2
    # [FIX] 添加超时机制（5分钟），避免无限等待
    timeout 300 docker pull "${full_image}" >&2 || true
    if docker image inspect "${full_image}" >/dev/null 2>&1; then
      echo "[OK] Image pulled successfully with tag ${primary_tag}" >&2
      echo "${primary_tag}"  # stdout: only tag
      return 0
    fi
    if [ ${retry} -lt 3 ]; then
      echo "[WARN] GHCR pull attempt ${retry}/3 failed, retrying in 10 seconds..." >&2
      sleep 10
    fi
  done

  if [ "${primary_tag}" != "${fallback_tag}" ]; then
    local full_image_fallback="${GHCR_REGISTRY}/${image_name}:${fallback_tag}"
    echo "[WARN] Primary tag ${primary_tag} failed, trying fallback tag ${fallback_tag}..." >&2
    for retry in 1 2 3; do
      echo "[INFO] GHCR fallback pull attempt ${retry}/3 for ${full_image_fallback}..." >&2
      # [FIX] 添加超时机制（5分钟），避免无限等待
      timeout 300 docker pull "${full_image_fallback}" >&2 || true
      if docker image inspect "${full_image_fallback}" >/dev/null 2>&1; then
        echo "[OK] Image pulled successfully with fallback tag ${fallback_tag}" >&2
        echo "${fallback_tag}"  # stdout: only tag
        return 0
      fi
      if [ ${retry} -lt 3 ]; then
        echo "[WARN] GHCR fallback pull attempt ${retry}/3 failed, retrying in 10 seconds..." >&2
        sleep 10
      fi
    done
  fi

  echo "[FAIL] Failed to pull image ${image_name} with tag ${primary_tag} (and fallback ${fallback_tag})" >&2
  echo "[INFO] Please verify the tag exists in both CNB and GHCR, and server has network access." >&2
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

# [FIX] 额外清理：确保 tag 不包含换行符、制表符等控制字符
BACKEND_TAG="$(echo "${BACKEND_TAG}" | tr -d '\r\n\t' | xargs)"
FRONTEND_TAG="$(echo "${FRONTEND_TAG}" | tr -d '\r\n\t' | xargs)"

# [FIX] 验证 tag 不包含特殊字符（防止 YAML 注入）
if echo "${BACKEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]' || echo "${FRONTEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]'; then
  echo "[FAIL] Tag contains invalid characters: Backend='${BACKEND_TAG}', Frontend='${FRONTEND_TAG}'"
  echo "[INFO] Tags must only contain alphanumeric characters, dots, underscores, and hyphens"
  exit 1
fi

# [DEBUG] 显示变量值（用于诊断）
echo "[DEBUG] Variables before YAML generation:"
echo "  GHCR_REGISTRY='${GHCR_REGISTRY}'"
echo "  IMAGE_NAME_BACKEND='${IMAGE_NAME_BACKEND}'"
echo "  IMAGE_NAME_FRONTEND='${IMAGE_NAME_FRONTEND}'"
echo "  BACKEND_TAG='${BACKEND_TAG}' (length: ${#BACKEND_TAG})"
echo "  FRONTEND_TAG='${FRONTEND_TAG}' (length: ${#FRONTEND_TAG})"

# [FIX] 使用 cat 和 heredoc 创建 YAML（更安全，避免 printf 转义问题）
# [FIX] 显式添加 networks 配置，确保一次性容器（docker-compose run）能正确连接到 Docker 网络
cat > docker-compose.deploy.yml <<EOF
services:
  backend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_BACKEND}:${BACKEND_TAG}
    networks:
      - erp_network
  frontend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_FRONTEND}:${FRONTEND_TAG}
    ports: []
    networks:
      - erp_network
EOF

# [DEBUG] 显示生成的 YAML 内容（用于诊断）
echo "[DEBUG] Generated docker-compose.deploy.yml content:"
cat docker-compose.deploy.yml
echo "[DEBUG] End of docker-compose.deploy.yml"

echo "[OK] Temporary compose file created"

# [BOOTSTRAP] Phase 0.5: Clean .env file (remove CRLF, trailing whitespace, and strip outer double quotes)
# Note: PRODUCTION_PATH is the working directory (set by caller or defaults to current directory)
# .env.production 中含 |、%、@ 等字符的值用双引号包裹，便于 source 时不被 bash 误解析；
# 此处去掉 .env.cleaned 中值两侧的双引号，使 docker-compose --env-file 得到裸值
PRODUCTION_PATH="${PRODUCTION_PATH:-$(pwd)}"
echo "[INFO] Phase 0.5: Cleaning .env file (removing CRLF, trailing whitespace, stripping outer double quotes)..."
if [ -f "${PRODUCTION_PATH}/.env" ]; then
  sed -e 's/\r$//' -e 's/[ \t]*$//' "${PRODUCTION_PATH}/.env" > "${PRODUCTION_PATH}/.env.cleaned"
  # Strip one level of double quotes: KEY="value" -> KEY=value (so docker-compose gets unquoted value)
  sed -i 's/^\([A-Za-z_][A-Za-z0-9_]*\)="\(.*\)"$/\1=\2/' "${PRODUCTION_PATH}/.env.cleaned" 2>/dev/null || true
  echo "[OK] .env file cleaned: ${PRODUCTION_PATH}/.env.cleaned"
else
  echo "[WARN] .env file not found at ${PRODUCTION_PATH}/.env, skipping cleaning"
  # Create empty .env.cleaned to avoid errors in subsequent docker-compose commands
  touch "${PRODUCTION_PATH}/.env.cleaned"
fi

# [FIX] 立即验证 YAML 语法（更稳的防护，提前发现问题）
# [PROD] 生产需要 Metabase：将 docker-compose.metabase.yml 纳入同一 project，避免 "Found orphan containers (xihong_erp_metabase)" 警告
# [4c8g] CLOUD_PROFILE=4c8g 时加载 cloud-4c8g、metabase.4c8g overlay
echo "[INFO] Validating docker-compose config..."
compose_cmd_base=(docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.deploy.yml --profile production)
if [ -f docker-compose.cloud.yml ]; then
  compose_cmd_base=(docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.deploy.yml --profile production)
  if [ "${CLOUD_PROFILE:-}" = "4c8g" ] && [ -f docker-compose.cloud-4c8g.yml ]; then
    compose_cmd_base=(docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud-4c8g.yml -f docker-compose.deploy.yml --profile production)
    echo "[INFO] CLOUD_PROFILE=4c8g: loading cloud-4c8g overlay"
  fi
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

# [SCHEMA MIGRATION] Phase 2: 智能数据库迁移
smart_database_migrate() {
  # [FIX] 容器名称配置化（支持不同环境）
  BACKEND_CONTAINER="xihong_erp_backend"
  POSTGRES_CONTAINER="xihong_erp_postgres"
  POSTGRES_USER_VAL="${POSTGRES_USER_VAL:-erp_user}"
  POSTGRES_DB_VAL="${POSTGRES_DB_VAL:-xihong_erp}"

  # [FIX] 检查 alembic_version 表是否存在（更准确的判断方式）
  ALEMBIC_VERSION_EXISTS=$("${compose_cmd_base[@]}" exec -T postgres psql -U "${POSTGRES_USER_VAL}" -d "${POSTGRES_DB_VAL}" -t -c \
      "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'alembic_version')" \
      2>/dev/null | tr -d ' \n\r' || echo "f")

  if [ "$ALEMBIC_VERSION_EXISTS" = "f" ] || [ -z "$ALEMBIC_VERSION_EXISTS" ]; then
    # 新数据库：使用 Schema 快照迁移
    echo "[INFO] 检测到全新数据库（alembic_version 表不存在），使用 Schema 快照迁移..."
    # [FIX] 验证快照迁移 revision ID 是否存在
    REVISION_EXISTS=$("${compose_cmd_base[@]}" run --rm --no-deps backend alembic history 2>&1 | grep -c "v5_0_0_schema_snapshot" || echo "0")
    if [ "$REVISION_EXISTS" -eq 0 ]; then
      echo "[WARN] 快照迁移 revision ID 'v5_0_0_schema_snapshot' 不存在"
      echo "[INFO] 尝试使用 alembic upgrade heads 作为降级方案..."
      "${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade heads || {
        echo "[ERROR] 无法执行迁移（快照迁移 revision 不存在且 heads 迁移失败）"
        echo "[INFO] 请检查迁移文件是否存在，或手动创建快照迁移"
        return 1
      }
    else
      "${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade v5_0_0_schema_snapshot || {
        echo "[ERROR] Schema 快照迁移失败"
        # [FIX] 检查表是否已部分创建
        TABLE_COUNT=$("${compose_cmd_base[@]}" exec -T postgres psql -U "${POSTGRES_USER_VAL}" -d "${POSTGRES_DB_VAL}" -t -c \
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'" \
            2>/dev/null | tr -d ' \n\r' || echo "0")
        if [ "$TABLE_COUNT" -gt 5 ]; then
          echo "[WARN] 检测到表已部分创建（$TABLE_COUNT 张表），可能需要清理或继续"
          echo "[INFO] 选项1: 清理数据库后重试"
          echo "[INFO] 选项2: 使用 alembic upgrade heads 继续迁移"
          # 尝试继续迁移
          "${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade heads || {
            echo "[ERROR] 继续迁移也失败，请手动检查"
            return 1
          }
        else
          return 1
        fi
      }
    fi
    # 继续执行后续增量迁移（如果有）
    # [FIX] 使用 heads（复数）以支持多头迁移分支
    "${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade heads || {
      echo "[WARN] 后续增量迁移失败，可能是快照迁移 revision ID 不正确或链接问题"
      echo "[INFO] 检查快照迁移的 revision ID 和后续迁移的 down_revision"
      echo "[INFO] 如果表已创建，可以继续部署；否则需要手动修复"
      # 不阻止部署，因为表可能已经通过快照迁移创建
    }
  else
    # 已有数据库：尝试增量迁移
    echo "[INFO] 检测到已有数据库（alembic_version 表存在），尝试增量迁移..."
    MIGRATE_LOG=$(mktemp)
    # [FIX] 使用 heads（复数）以支持多头迁移分支；捕获完整输出便于排查（如云服务器为旧版本表结构）
    "${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade heads 2> "${MIGRATE_LOG}"
    MIGRATE_EXIT=$?
    if [ ${MIGRATE_EXIT} -ne 0 ]; then
      echo "[WARN] 迁移命令返回非零 (exit ${MIGRATE_EXIT})，完整输出如下:"
      cat "${MIGRATE_LOG}"
      echo "[WARN] 迁移失败，检测缺失的表..."
      MISSING_TABLES=$("${compose_cmd_base[@]}" run --rm --no-deps backend python3 -c "
from backend.models.database import Base, engine
from sqlalchemy import inspect
import sys

try:
    # 直接检查表是否存在，不依赖 verify_schema_completeness（可能因为多头迁移失败）
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - existing_tables

    if missing_tables:
        missing = sorted(list(missing_tables))
        print(','.join(missing), file=sys.stdout)
        sys.exit(1)
    else:
        print('[INFO] 所有表都存在，迁移失败可能是其他原因', file=sys.stderr)
        sys.exit(0)
except Exception as e:
    print(f'[ERROR] 检测缺失表时出错: {e}', file=sys.stderr)
    sys.exit(2)
" 2>&1)

      DETECT_EXIT_CODE=$?

      if [ $DETECT_EXIT_CODE -eq 1 ] && [ -n "$MISSING_TABLES" ]; then
        echo "[INFO] 发现缺失的表，尝试补充: $MISSING_TABLES"
        # [FIX] 使用 Base.metadata.create_all() 只创建缺失的表
        # [FIX] 使用 tables 参数指定要创建的表，SQLAlchemy 会自动处理依赖顺序
        "${compose_cmd_base[@]}" run --rm --no-deps backend python3 -c "
from backend.models.database import Base, engine
from sqlalchemy import inspect, text
import sys

inspector = inspect(engine)
existing_tables = set(inspector.get_table_names())
expected_tables = set(Base.metadata.tables.keys())
missing_tables = expected_tables - existing_tables

if missing_tables:
    print(f'[INFO] 创建缺失的表: {missing_tables}')
    missing_table_objects = [Base.metadata.tables[t] for t in missing_tables if t in Base.metadata.tables]
    if len(missing_table_objects) < len(missing_tables):
        skipped = set(missing_tables) - set(Base.metadata.tables.keys())
        print(f'[WARN] 跳过不在 metadata 中的表: {skipped}', file=sys.stderr)
    if missing_table_objects:
        # [FIX] 补表前先创建缺失表所在的 schema，避免 schema \"core\" does not exist
        schemas_to_create = set()
        for t in missing_table_objects:
            s = getattr(t, 'schema', None)
            if s and s != 'public':
                schemas_to_create.add(s)
        for schema_name in sorted(schemas_to_create):
            with engine.connect() as conn:
                conn.execute(text('CREATE SCHEMA IF NOT EXISTS \"' + schema_name + '\"'))
                conn.commit()
        Base.metadata.create_all(bind=engine, tables=missing_table_objects, checkfirst=True)
    else:
        print('[WARN] 没有可创建的表（所有缺失的表都不在 metadata 中）', file=sys.stderr)
        sys.exit(1)
    print('[OK] 缺失表已创建')

    inspector_after = inspect(engine)
    existing_after = set(inspector_after.get_table_names())
    still_missing = expected_tables - existing_after
    if still_missing:
        print(f'[WARN] 部分表创建失败: {still_missing}', file=sys.stderr)
        sys.exit(1)
else:
    print('[INFO] 所有表都已存在')
" || {
          echo "[ERROR] 创建缺失表失败"
          rm -f "${MIGRATE_LOG}"
          return 1
        }

        # [FIX] 验证表结构完整性后再标记
        # [FIX] 直接检查表是否存在，不依赖 verify_schema_completeness()（可能因多头迁移失败）
        VERIFY_RESULT=$("${compose_cmd_base[@]}" run --rm --no-deps backend python3 -c "
from backend.models.database import Base, engine
from sqlalchemy import inspect
import json
import sys

try:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = expected_tables - existing_tables

    result = {
        'all_tables_exist': len(missing_tables) == 0,
        'missing_tables': sorted(list(missing_tables)),
        'expected_count': len(expected_tables),
        'actual_count': len(existing_tables)
    }
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({'error': str(e), 'all_tables_exist': False}), file=sys.stderr)
    sys.exit(1)
" 2>&1)

        if echo "$VERIFY_RESULT" | grep -q '"all_tables_exist": true'; then
          echo "[OK] 表结构验证通过，标记迁移为最新"
          # [FIX] 仅在验证通过后才标记为最新
          # [FIX] 检查 head 数量，根据情况选择 stamp 命令
          # [FIX] 使用更准确的检测方式：统计包含 "(head)" 的行数
          HEAD_COUNT=$("${compose_cmd_base[@]}" run --rm --no-deps backend alembic heads 2>&1 | grep -E "\(head\)" | wc -l | tr -d ' \n\r' || echo "0")
          if [ "$HEAD_COUNT" -eq 1 ]; then
            echo "[INFO] 检测到单个 head，使用 alembic stamp head"
            "${compose_cmd_base[@]}" run --rm --no-deps backend alembic stamp head || {
              echo "[WARN] alembic stamp head 失败，但表已创建"
            }
          else
            echo "[INFO] 检测到多个 head ($HEAD_COUNT 个)，使用 alembic stamp heads"
            "${compose_cmd_base[@]}" run --rm --no-deps backend alembic stamp heads || {
              echo "[WARN] alembic stamp heads 失败，但表已创建"
            }
          fi
        else
          echo "[ERROR] 表结构验证失败，不标记迁移"
          echo "[INFO] 请手动检查并修复表结构"
          rm -f "${MIGRATE_LOG}"
          return 1
        fi
      elif [ $DETECT_EXIT_CODE -eq 2 ]; then
        echo "[ERROR] 检测缺失表时出错"
        echo "[INFO] 请检查数据库连接和 Python 环境"
        rm -f "${MIGRATE_LOG}"
        return 1
      else
        # [P0] 所有表都存在：尝试补列后重试迁移（云上旧 schema 缺列时一次补齐）
        echo "[INFO] 所有表都存在，尝试补列后重试迁移..."
        if ! "${compose_cmd_base[@]}" run --rm --no-deps backend python3 /app/scripts/sync_schema_columns.py 2>/dev/null; then
          echo "[WARN] sync_schema_columns.py 执行失败或未找到，继续重试迁移"
        fi
        echo "[INFO] 重试 alembic upgrade heads..."
        "${compose_cmd_base[@]}" run --rm --no-deps backend alembic upgrade heads 2> "${MIGRATE_LOG}"
        RETRY_EXIT=$?
        if [ ${RETRY_EXIT} -eq 0 ]; then
          echo "[OK] 补列后迁移成功"
        else
          echo "[ERROR] 迁移失败且无法自动修复（所有表都存在）"
          echo "[INFO] 云服务器可能是旧版本表结构，与当前迁移不兼容；或存在字段/约束冲突、alembic_version 与代码不一致等。"
          echo "[INFO] 请根据下方「迁移命令原始错误」手动修复（如调整迁移脚本、在服务器执行 alembic 命令或联系运维）。"
          echo "[INFO] --- 迁移命令原始错误 ---"
          cat "${MIGRATE_LOG}"
          echo "[INFO] --- 结束 ---"
          rm -f "${MIGRATE_LOG}"
          return 1
        fi
      fi
      rm -f "${MIGRATE_LOG}"
    fi
    rm -f "${MIGRATE_LOG}"
  fi
}

echo "[INFO] Phase 2: Running smart database migration..."
if ! smart_database_migrate; then
  echo "[FAIL] Smart database migration failed"
  echo "[INFO] Deployment blocked due to migration failure"
  echo "[INFO] Please check migration logs and fix errors before retrying"
  exit 1
fi
echo "[OK] Smart database migration completed successfully"

# [BOOTSTRAP] Phase 2.5: Bootstrap initialization (after migrations, before application layer)
# Note: Schema verification is now integrated into smart_database_migrate() function above
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

echo "[INFO] Phase 3: starting application layer (backend, celery)..."
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

echo "[INFO] Phase 3b: starting frontend..."
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

echo "[INFO] Phase 4: starting gateway (Nginx, last)..."
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

# [NGINX] 重载配置以使本次部署上传的 nginx.prod.conf 生效（容器未重启时需 reload）
if docker ps --format '{{.Names}}' | grep -q 'xihong_erp_nginx'; then
  if docker exec xihong_erp_nginx nginx -t 2>/dev/null; then
    docker exec xihong_erp_nginx nginx -s reload && echo "[OK] Nginx config reloaded"
  else
    echo "[WARN] Nginx config test failed; skip reload"
  fi
fi

# [LEGACY CLEANUP] PostgreSQL Dashboard production no longer depends on Metabase.
if docker ps -a --format '{{.Names}}' | grep -q '^xihong_erp_metabase$'; then
  echo "[INFO] Removing legacy Metabase container..."
  docker stop xihong_erp_metabase 2>/dev/null || true
  docker rm xihong_erp_metabase 2>/dev/null || true
  echo "[OK] Legacy Metabase container removed"
fi

# [IMAGE_CLEANUP] Clean up old Docker images (keep latest N versions)
# 在部署成功后执行清理，释放磁盘空间
cleanup_old_images

echo "[INFO] Cleaning up temporary files..."
rm -f docker-compose.deploy.yml || true
# [BOOTSTRAP] Clean up .env.cleaned file after successful deployment
if [ -f "${PRODUCTION_PATH}/.env.cleaned" ]; then
  rm -f "${PRODUCTION_PATH}/.env.cleaned"
  echo "[OK] Cleaned up .env.cleaned file"
fi
echo "[OK] Deployment completed. Tags: Backend=${BACKEND_TAG}, Frontend=${FRONTEND_TAG}"
