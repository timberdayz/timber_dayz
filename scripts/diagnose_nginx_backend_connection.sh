#!/bin/bash
# Nginx 到后端连接诊断脚本

set -e

echo "=========================================="
echo "Nginx 到后端连接诊断脚本"
echo "=========================================="
echo ""

PROJECT_ROOT="${PROJECT_ROOT:-/opt/xihong_erp}"
cd "${PROJECT_ROOT}" || { echo "[ERROR] 无法进入项目目录: ${PROJECT_ROOT}"; exit 1; }

BACKEND_CONTAINER="xihong_erp_backend_api"
BACKEND_SERVICE_HOST="backend"
BACKEND_READY_PATH="/healthz/ready"

echo "=== 步骤1: 检查后端容器状态 ==="
if docker ps | grep -q "${BACKEND_CONTAINER}"; then
    echo "[OK] 后端容器正在运行"
    BACKEND_STATUS=$(docker ps --filter "name=${BACKEND_CONTAINER}" --format "{{.Status}}")
    echo "  状态: ${BACKEND_STATUS}"
else
    echo "[FAIL] 后端容器未运行"
    exit 1
fi

echo ""
echo "=== 步骤2: 检查后端容器环境变量 ==="
BACKEND_ALLOWED_HOSTS=$(docker exec "${BACKEND_CONTAINER}" env | grep "^ALLOWED_HOSTS=" | cut -d'=' -f2- || true)
if [ -z "${BACKEND_ALLOWED_HOSTS}" ]; then
    echo "[WARN] 后端容器环境变量中没有 ALLOWED_HOSTS"
else
    echo "  环境变量 ALLOWED_HOSTS: ${BACKEND_ALLOWED_HOSTS}"
fi

echo ""
echo "=== 步骤3: 检查后端应用实际使用的配置 ==="
docker exec "${BACKEND_CONTAINER}" python -c "
from backend.utils.config import get_settings
settings = get_settings()
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
" 2>&1 || true

echo ""
echo "=== 步骤4: 检查 Nginx 容器状态 ==="
if docker ps | grep -q "xihong_erp_nginx"; then
    echo "[OK] Nginx 容器正在运行"
else
    echo "[FAIL] Nginx 容器未运行"
    exit 1
fi

echo ""
echo "=== 步骤5: 检查 Nginx 健康检查代理配置 ==="
docker exec xihong_erp_nginx cat /etc/nginx/nginx.conf | grep -A 4 "location /health" || true

echo ""
echo "=== 步骤6: 测试 Nginx 到后端的连通性 ==="
docker exec xihong_erp_nginx wget -O- "http://${BACKEND_SERVICE_HOST}:8000${BACKEND_READY_PATH}" 2>&1 | head -10 || true

echo ""
echo "=== 步骤7: 检查后端日志中的错误 ==="
docker logs "${BACKEND_CONTAINER}" 2>&1 | tail -30 | grep -i "invalid host\|trustedhost\|400\|error" | head -10 || true

echo ""
echo "=== 步骤8: 检查本地健康检查端点 ==="
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/health || true

echo ""
echo "如需强制重建 API 服务："
echo "  docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate backend-api"
