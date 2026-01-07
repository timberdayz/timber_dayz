#!/bin/bash
# =====================================================
# Docker 镜像构建测试脚本
# =====================================================
# 用于本地测试 Docker 镜像构建，验证 Dockerfile 是否正确
# =====================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_message() {
    echo -e "${GREEN}[测试]${NC} $1"
}

print_error() {
    echo -e "${RED}[错误]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[警告]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[信息]${NC} $1"
}

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

print_message "开始 Docker 镜像构建测试"
echo ""

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    print_error "Docker 未运行，请启动 Docker"
    exit 1
fi

# 测试后端镜像构建
print_message "测试后端镜像构建..."
if docker build -f Dockerfile.backend -t xihong_erp_backend:test \
    --build-arg PYTHON_VERSION=3.11 \
    . > /tmp/docker_build_backend.log 2>&1; then
    print_message "后端镜像构建成功"
    docker images | grep xihong_erp_backend:test
else
    print_error "后端镜像构建失败"
    print_info "查看构建日志:"
    tail -20 /tmp/docker_build_backend.log
    exit 1
fi

echo ""

# 测试前端镜像构建
print_message "测试前端镜像构建..."
if docker build -f Dockerfile.frontend -t xihong_erp_frontend:test \
    --target production \
    --build-arg NODE_VERSION=18 \
    --build-arg VITE_API_URL=http://localhost:8001 \
    . > /tmp/docker_build_frontend.log 2>&1; then
    print_message "前端镜像构建成功"
    docker images | grep xihong_erp_frontend:test
else
    print_error "前端镜像构建失败"
    print_info "查看构建日志:"
    tail -20 /tmp/docker_build_frontend.log
    exit 1
fi

echo ""
print_message "所有镜像构建测试通过！"
print_info "清理测试镜像:"
print_info "  docker rmi xihong_erp_backend:test xihong_erp_frontend:test"

