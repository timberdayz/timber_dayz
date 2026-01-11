#!/usr/bin/env bash
# 测试 YAML 生成的边界情况

set -euo pipefail

echo "[TEST] Testing YAML generation edge cases..."

GHCR_REGISTRY="ghcr.io"
IMAGE_NAME_BACKEND="test/backend"
IMAGE_NAME_FRONTEND="test/frontend"

test_yaml_generation() {
  local backend_tag="$1"
  local frontend_tag="$2"
  local test_name="$3"
  
  echo ""
  echo "[TEST] ${test_name}"
  echo "  BACKEND_TAG='${backend_tag}'"
  echo "  FRONTEND_TAG='${frontend_tag}'"
  
  # 清理 tag（与 deploy_remote_production.sh 一致）
  BACKEND_TAG="$(echo "${backend_tag}" | tr -d '\r\n\t' | xargs)"
  FRONTEND_TAG="$(echo "${frontend_tag}" | tr -d '\r\n\t' | xargs)"
  
  # 验证 tag 不包含特殊字符
  if echo "${BACKEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]' || echo "${FRONTEND_TAG}" | grep -qE '[^a-zA-Z0-9._-]'; then
    echo "  [OK] Invalid tag correctly rejected"
    return 0
  fi
  
  # 生成 YAML
  TEST_YAML_FILE="/tmp/test-yaml-${RANDOM}.yml"
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
  
  # 验证第 4 行包含冒号
  LINE_4="$(sed -n '4p' "${TEST_YAML_FILE}")"
  if ! echo "${LINE_4}" | grep -q ":"; then
    echo "  [FAIL] Line 4 missing ':'"
    cat "${TEST_YAML_FILE}"
    rm -f "${TEST_YAML_FILE}"
    return 1
  fi
  
  # 验证第 4 行是 image 行
  if ! echo "${LINE_4}" | grep -q "image:"; then
    echo "  [FAIL] Line 4 should be image line"
    cat "${TEST_YAML_FILE}"
    rm -f "${TEST_YAML_FILE}"
    return 1
  fi
  
  echo "  [OK] YAML generation successful"
  rm -f "${TEST_YAML_FILE}"
  return 0
}

# 测试正常情况
test_yaml_generation "v4.21.4" "v4.21.4" "Normal tags"

# 测试不带 v 前缀
test_yaml_generation "4.21.4" "4.21.4" "Tags without 'v' prefix"

# 测试带下划线的 tag
test_yaml_generation "v4.21.4-beta" "v4.21.4-beta" "Tags with hyphens"

# 测试带点的 tag（已在正常情况中测试）

# 清理
rm -f /tmp/test-yaml-*.yml

echo ""
echo "[OK] All edge case tests passed!"
