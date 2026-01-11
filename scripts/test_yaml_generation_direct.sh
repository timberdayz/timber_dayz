#!/usr/bin/env bash
# 直接测试 YAML 生成逻辑

set -euo pipefail

echo "[TEST] Testing YAML generation with actual variable values..."

# 模拟实际环境变量
GHCR_REGISTRY="ghcr.io"
IMAGE_NAME_BACKEND="timberdayz/timber_dayz/backend"
IMAGE_NAME_FRONTEND="timberdayz/timber_dayz/frontend"
BACKEND_TAG="v4.21.4"
FRONTEND_TAG="v4.21.4"

echo "[INFO] Test variables:"
echo "  GHCR_REGISTRY='${GHCR_REGISTRY}'"
echo "  IMAGE_NAME_BACKEND='${IMAGE_NAME_BACKEND}'"
echo "  IMAGE_NAME_FRONTEND='${IMAGE_NAME_FRONTEND}'"
echo "  BACKEND_TAG='${BACKEND_TAG}'"
echo "  FRONTEND_TAG='${FRONTEND_TAG}'"
echo ""

# 验证变量不为空
if [ -z "${GHCR_REGISTRY}" ] || [ -z "${IMAGE_NAME_BACKEND}" ] || [ -z "${IMAGE_NAME_FRONTEND}" ]; then
  echo "[FAIL] Required variables are empty"
  exit 1
fi

if [ -z "${BACKEND_TAG}" ] || [ -z "${FRONTEND_TAG}" ]; then
  echo "[FAIL] Tag variables are empty"
  exit 1
fi

# 额外清理（与 deploy_remote_production.sh 一致）
BACKEND_TAG="$(echo "${BACKEND_TAG}" | tr -d '\r\n\t' | xargs)"
FRONTEND_TAG="$(echo "${FRONTEND_TAG}" | tr -d '\r\n\t' | xargs)"

# 验证 tag 不包含特殊字符
if echo "${BACKEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]' || echo "${FRONTEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]'; then
  echo "[FAIL] Tag contains invalid characters"
  exit 1
fi

# 生成 YAML（与 deploy_remote_production.sh 完全一致）
TEST_YAML_FILE="/tmp/test-docker-compose.deploy.yml"
cat > "${TEST_YAML_FILE}" <<EOF
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

echo "[INFO] Generated YAML content:"
cat "${TEST_YAML_FILE}"
echo ""
echo "[INFO] YAML file line count: $(wc -l < "${TEST_YAML_FILE}")"
echo ""

# 验证 YAML 基本结构
if ! grep -q "services:" "${TEST_YAML_FILE}"; then
  echo "[FAIL] YAML missing 'services:' key"
  exit 1
fi

if ! grep -q "image:" "${TEST_YAML_FILE}"; then
  echo "[FAIL] YAML missing 'image:' key"
  exit 1
fi

if ! grep -q "networks:" "${TEST_YAML_FILE}"; then
  echo "[FAIL] YAML missing 'networks:' key"
  exit 1
fi

# 检查第 4 行（应该是 backend image 行）
LINE_4="$(sed -n '4p' "${TEST_YAML_FILE}")"
echo "[INFO] Line 4 content: '${LINE_4}'"

if ! echo "${LINE_4}" | grep -q "image:"; then
  echo "[FAIL] Line 4 should contain 'image:', but got: '${LINE_4}'"
  exit 1
fi

if ! echo "${LINE_4}" | grep -q ":"; then
  echo "[FAIL] Line 4 should contain ':', but got: '${LINE_4}'"
  exit 1
fi

echo "[OK] YAML structure validation passed"
echo "[OK] Line 4 contains ':' as expected"

# 清理
rm -f "${TEST_YAML_FILE}"

echo ""
echo "[OK] All YAML generation tests passed!"
