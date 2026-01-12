#!/bin/bash
# Nginx 到后端连接诊断脚本
# 用于诊断 Nginx 代理到后端时的 400 Bad Request 错误

set -e

echo "=========================================="
echo "Nginx 到后端连接诊断脚本"
echo "=========================================="
echo ""

PROJECT_ROOT="${PROJECT_ROOT:-/opt/xihong_erp}"
cd "${PROJECT_ROOT}" || { echo "[ERROR] 无法进入项目目录: ${PROJECT_ROOT}"; exit 1; }

echo "=== 步骤1: 检查后端容器状态 ==="
if docker ps | grep -q "xihong_erp_backend"; then
    echo "[OK] 后端容器正在运行"
    BACKEND_STATUS=$(docker ps --filter "name=xihong_erp_backend" --format "{{.Status}}")
    echo "  状态: ${BACKEND_STATUS}"
else
    echo "[FAIL] 后端容器未运行"
    exit 1
fi

echo ""
echo "=== 步骤2: 检查后端容器环境变量 ==="
BACKEND_ALLOWED_HOSTS=$(docker exec xihong_erp_backend env | grep "^ALLOWED_HOSTS=" | cut -d'=' -f2-)
if [ -z "${BACKEND_ALLOWED_HOSTS}" ]; then
    echo "[WARN] 后端容器环境变量中没有 ALLOWED_HOSTS"
else
    echo "  环境变量 ALLOWED_HOSTS: ${BACKEND_ALLOWED_HOSTS}"
    if echo "${BACKEND_ALLOWED_HOSTS}" | grep -q "backend"; then
        echo "  [OK] 包含 'backend'"
    else
        echo "  [WARN] 不包含 'backend'（可能导致 400 错误）"
    fi
fi

echo ""
echo "=== 步骤3: 检查后端应用实际使用的配置 ==="
echo "  注意: 如果返回 ['localhost', '127.0.0.1']，说明代码还未更新"
BACKEND_CONFIG=$(docker exec xihong_erp_backend python -c "
from backend.utils.config import get_settings
settings = get_settings()
print('ALLOWED_HOSTS:', settings.ALLOWED_HOSTS)
" 2>&1)

if echo "${BACKEND_CONFIG}" | grep -q "ALLOWED_HOSTS:"; then
    echo "${BACKEND_CONFIG}"
    if echo "${BACKEND_CONFIG}" | grep -q "'backend'"; then
        echo "  [OK] 配置包含 'backend'"
    else
        echo "  [WARN] 配置不包含 'backend'"
        echo "  [INFO] 这通常意味着后端代码还未更新，需要重新构建镜像"
    fi
else
    echo "  [ERROR] 无法读取后端配置:"
    echo "${BACKEND_CONFIG}"
fi

echo ""
echo "=== 步骤4: 检查 Nginx 容器状态 ==="
if docker ps | grep -q "xihong_erp_nginx"; then
    echo "[OK] Nginx 容器正在运行"
    NGINX_STATUS=$(docker ps --filter "name=xihong_erp_nginx" --format "{{.Status}}")
    echo "  状态: ${NGINX_STATUS}"
else
    echo "[FAIL] Nginx 容器未运行"
    exit 1
fi

echo ""
echo "=== 步骤5: 检查 Nginx 配置中的 Host 头设置 ==="
NGINX_HOST_HEADER=$(docker exec xihong_erp_nginx cat /etc/nginx/nginx.conf | grep -A 3 "location /health" | grep "proxy_set_header Host" || echo "")
if [ -z "${NGINX_HOST_HEADER}" ]; then
    echo "  [WARN] 未找到 proxy_set_header Host 配置"
else
    echo "  ${NGINX_HOST_HEADER}"
    if echo "${NGINX_HOST_HEADER}" | grep -q "proxy_set_header Host backend"; then
        echo "  [OK] Nginx 配置正确（发送 Host: backend）"
    else
        echo "  [WARN] Nginx 配置可能不正确"
    fi
fi

echo ""
echo "=== 步骤6: 测试 Nginx 到后端的连接 ==="
NGINX_TEST=$(docker exec xihong_erp_nginx wget -O- http://backend:8000/health 2>&1 | head -10)
if echo "${NGINX_TEST}" | grep -q "200 OK\|{\"status\""; then
    echo "  [OK] 连接成功，返回 200 OK"
    echo "${NGINX_TEST}" | head -5
elif echo "${NGINX_TEST}" | grep -q "400 Bad Request"; then
    echo "  [FAIL] 返回 400 Bad Request"
    echo "${NGINX_TEST}"
    echo ""
    echo "  [诊断] 可能的原因："
    echo "    1. 后端代码未更新（ALLOWED_HOSTS 配置未生效）"
    echo "    2. 后端容器环境变量中 ALLOWED_HOSTS 不包含 'backend'"
    echo "    3. 后端应用使用的配置仍然是硬编码的默认值"
else
    echo "  [ERROR] 连接失败："
    echo "${NGINX_TEST}"
fi

echo ""
echo "=== 步骤7: 检查后端日志中的错误 ==="
BACKEND_LOGS=$(docker logs xihong_erp_backend 2>&1 | tail -30 | grep -i "invalid host\|trustedhost\|400\|error" | head -10 || echo "")
if [ -z "${BACKEND_LOGS}" ]; then
    echo "  [INFO] 后端日志中未发现相关错误"
else
    echo "  后端日志（最后30行中的错误）："
    echo "${BACKEND_LOGS}"
fi

echo ""
echo "=== 步骤8: 检查本地健康检查端点 ==="
LOCAL_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>&1 || echo "000")
if [ "${LOCAL_TEST}" = "200" ]; then
    echo "  [OK] 本地健康检查返回 200"
    curl -s http://localhost/health | head -3
elif [ "${LOCAL_TEST}" = "400" ]; then
    echo "  [FAIL] 本地健康检查返回 400"
    curl -s http://localhost/health
else
    echo "  [ERROR] 本地健康检查失败，HTTP 状态码: ${LOCAL_TEST}"
fi

echo ""
echo "=========================================="
echo "诊断完成"
echo "=========================================="
echo ""
echo "如果步骤3显示配置不包含 'backend'，需要："
echo "  1. 确认代码已提交并推送到仓库"
echo "  2. 触发 GitHub Actions 构建新镜像"
echo "  3. 在服务器上重新部署（使用新镜像）"
echo "  4. 重新创建后端容器："
echo "     docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate backend"
echo ""
