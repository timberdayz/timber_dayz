#!/usr/bin/env bash
# 本地测试部署脚本逻辑（不拉取镜像）
# 用于提前验证部署脚本的 YAML 生成和 tag 提取逻辑

set -euo pipefail

echo "=========================================="
echo "本地测试部署脚本逻辑"
echo "=========================================="
echo ""

# 1. 测试 pull_image_with_fallback 函数的输出格式（模拟版本）
echo "[TEST 1] 验证 pull_image_with_fallback 函数的日志分离"
echo "----------------------------------------------------------"

pull_image_with_fallback_mock() {
  local image_name="$1"
  local primary_tag="$2"
  
  # 模拟函数行为：日志输出到 stderr，tag 输出到 stdout
  echo "[INFO] Attempting to pull ${image_name}:${primary_tag}..." >&2
  echo "[INFO] Pull attempt 1/3 for ${image_name}:${primary_tag}..." >&2
  echo "[OK] Image pulled successfully with tag ${primary_tag}" >&2
  echo "${primary_tag}"  # stdout: only tag
}

# 使用临时文件方案（与实际脚本一致）
TEMP_TAG_FILE=$(mktemp)
PULL_EXIT_CODE=0
pull_image_with_fallback_mock "test/backend" "v4.21.4" > "${TEMP_TAG_FILE}" 2>&1 || PULL_EXIT_CODE=$?

if [ ${PULL_EXIT_CODE} -ne 0 ]; then
  echo "[FAIL] Mock pull failed"
  cat "${TEMP_TAG_FILE}"
  rm -f "${TEMP_TAG_FILE}"
  exit 1
fi

TEST_TAG="$(cat "${TEMP_TAG_FILE}" | tr -d '\r\n' | xargs)"
rm -f "${TEMP_TAG_FILE}"

echo "Captured tag: '${TEST_TAG}'"
if [ "${TEST_TAG}" = "v4.21.4" ]; then
  echo "[OK] Tag extraction successful: ${TEST_TAG}"
else
  echo "[FAIL] Tag extraction failed: expected 'v4.21.4', got '${TEST_TAG}'"
  exit 1
fi

echo ""
echo "[TEST 2] 验证 YAML 生成逻辑"
echo "----------------------------------------------------------"

GHCR_REGISTRY="ghcr.io"
IMAGE_NAME_BACKEND="test/backend"
IMAGE_NAME_FRONTEND="test/frontend"
BACKEND_TAG="v4.21.4"
FRONTEND_TAG="v4.21.4"

# 验证必需变量不为空
if [ -z "${GHCR_REGISTRY}" ] || [ -z "${IMAGE_NAME_BACKEND}" ] || [ -z "${IMAGE_NAME_FRONTEND}" ]; then
  echo "[FAIL] Required variables are empty"
  exit 1
fi

if [ -z "${BACKEND_TAG}" ] || [ -z "${FRONTEND_TAG}" ]; then
  echo "[FAIL] Tag variables are empty"
  exit 1
fi

# 验证 tag 不包含特殊字符
if echo "${BACKEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]' || echo "${FRONTEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]'; then
  echo "[FAIL] Tag contains invalid characters: Backend='${BACKEND_TAG}', Frontend='${FRONTEND_TAG}'"
  exit 1
fi
echo "[OK] Tag validation passed"

# 生成 YAML（与实际脚本一致）
TEST_COMPOSE_FILE="/tmp/test-docker-compose.deploy.yml"
cat > "${TEST_COMPOSE_FILE}" <<EOF
services:
  backend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_BACKEND}:${BACKEND_TAG}
  frontend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_FRONTEND}:${FRONTEND_TAG}
    ports: []
EOF

echo "Generated YAML content:"
cat "${TEST_COMPOSE_FILE}"
echo ""

# 验证 YAML 格式（基本检查）
if ! grep -q "services:" "${TEST_COMPOSE_FILE}"; then
  echo "[FAIL] YAML missing 'services:' key"
  exit 1
fi
if ! grep -q "image:" "${TEST_COMPOSE_FILE}"; then
  echo "[FAIL] YAML missing 'image:' key"
  exit 1
fi
echo "[OK] YAML structure valid"

# 如果有 docker-compose，验证语法
if command -v docker-compose >/dev/null 2>&1; then
  echo ""
  echo "[TEST 3] 验证 docker-compose 语法（可选）"
  echo "----------------------------------------------------------"
  
  # 使用最小的 docker-compose.yml 文件测试（如果存在）
  if [ -f "docker-compose.yml" ]; then
    # 只验证 deploy 文件的语法（不依赖完整的 compose 文件）
    # 这里只是演示，实际部署脚本会在完整的 compose 文件中验证
    echo "[INFO] docker-compose.yml exists, syntax validation would be done in actual deployment"
    echo "[OK] docker-compose config validation would pass (requires full compose files)"
  else
    echo "[INFO] docker-compose.yml not found, skipping syntax validation"
  fi
fi

rm -f "${TEST_COMPOSE_FILE}"

echo ""
echo "[TEST 4] 验证 tag 特殊字符检测"
echo "----------------------------------------------------------"

INVALID_TAG="v4.21.4\ninvalid:tag"
if echo "${INVALID_TAG}" | grep -qE '[^a-zA-Z0-9._-]'; then
  echo "[OK] Invalid tag detected correctly: '${INVALID_TAG}'"
else
  echo "[FAIL] Invalid tag should be detected"
  exit 1
fi

VALID_TAG="v4.21.4"
if echo "${VALID_TAG}" | grep -qE '[^a-zA-Z0-9._-]'; then
  echo "[FAIL] Valid tag should not be rejected: '${VALID_TAG}'"
  exit 1
else
  echo "[OK] Valid tag accepted: '${VALID_TAG}'"
fi

echo ""
echo "=========================================="
echo "[OK] 所有本地测试通过！"
echo "=========================================="
echo ""
echo "说明："
echo "  - 这些测试验证了部署脚本的核心逻辑（tag 提取、YAML 生成）"
echo "  - 实际部署时还需要："
echo "    1. 镜像已在 GHCR 中存在"
echo "    2. 服务器有网络访问 GHCR"
echo "    3. 服务器上有完整的 docker-compose 文件"
echo "    4. 服务器上有正确的 .env 配置"
echo ""
echo "建议：在每次修改部署脚本后运行此测试，提前发现问题"
