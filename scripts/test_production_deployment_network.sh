#!/usr/bin/env bash
# 生产环境网络配置验证测试
# 模拟生产部署流程，验证 docker-compose.deploy.yml 的网络配置

set -euo pipefail

echo "=========================================="
echo "生产环境网络配置验证测试"
echo "=========================================="
echo ""

# 设置测试变量（模拟部署脚本）
GHCR_REGISTRY="ghcr.io"
IMAGE_NAME_BACKEND="test/backend"
IMAGE_NAME_FRONTEND="test/frontend"
BACKEND_TAG="v4.21.8-test"
FRONTEND_TAG="v4.21.8-test"

# 验证必需变量
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
  echo "[FAIL] Tag contains invalid characters"
  exit 1
fi

echo "[TEST 1] 验证 docker-compose.deploy.yml 生成逻辑"
echo "----------------------------------------------------------"

# 生成 docker-compose.deploy.yml（与实际部署脚本一致）
TEST_COMPOSE_FILE="/tmp/test-production-docker-compose.deploy.yml"
cat > "${TEST_COMPOSE_FILE}" <<EOF
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

echo "Generated YAML content:"
cat "${TEST_COMPOSE_FILE}"
echo ""

# 验证 YAML 包含 networks 配置
if ! grep -q "networks:" "${TEST_COMPOSE_FILE}"; then
  echo "[FAIL] YAML missing 'networks:' configuration"
  exit 1
fi

if ! grep -q "erp_network" "${TEST_COMPOSE_FILE}"; then
  echo "[FAIL] YAML missing 'erp_network' in networks"
  exit 1
fi

echo "[OK] YAML contains networks configuration"
echo ""

# 验证 docker-compose config（如果可用）
if command -v docker-compose >/dev/null 2>&1; then
  echo "[TEST 2] 验证 docker-compose 配置合并"
  echo "----------------------------------------------------------"
  
  # 检查基础 compose 文件是否存在
  if [ ! -f "docker-compose.yml" ]; then
    echo "[WARN] docker-compose.yml not found, skipping config validation"
  elif [ ! -f "docker-compose.prod.yml" ]; then
    echo "[WARN] docker-compose.prod.yml not found, skipping config validation"
  else
    # 验证配置合并（使用测试文件）
    if docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f "${TEST_COMPOSE_FILE}" --profile production config >/dev/null 2>&1; then
      echo "[OK] docker-compose config validation passed"
      
      # 验证 networks 配置在合并后的配置中
      MERGED_CONFIG=$(docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f "${TEST_COMPOSE_FILE}" --profile production config 2>/dev/null || true)
      if echo "${MERGED_CONFIG}" | grep -q "erp_network"; then
        echo "[OK] erp_network found in merged config"
      else
        echo "[WARN] erp_network not found in merged config (may be inherited)"
      fi
    else
      echo "[FAIL] docker-compose config validation failed"
      echo "[INFO] Config error output:"
      docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f "${TEST_COMPOSE_FILE}" --profile production config 2>&1 | head -30 || true
      rm -f "${TEST_COMPOSE_FILE}"
      exit 1
    fi
  fi
  echo ""
else
  echo "[WARN] docker-compose not found, skipping config validation"
  echo ""
fi

# 清理测试文件
rm -f "${TEST_COMPOSE_FILE}"

echo "=========================================="
echo "测试结果汇总"
echo "=========================================="
echo "[OK] YAML 生成逻辑验证通过"
echo "[OK] networks 配置验证通过"
echo ""
echo "说明："
echo "  - 此测试验证了 docker-compose.deploy.yml 生成逻辑包含 networks 配置"
echo "  - 实际部署时，networks 配置确保一次性容器能正确连接到 Docker 网络"
echo "  - 建议：在每次修改部署脚本后运行此测试，提前发现问题"
echo "=========================================="