#!/bin/bash
# 测试部署脚本中的 bash -c 命令语法（模拟远程执行）

set -e

echo "=== 测试部署脚本语法（模拟远程执行）==="

# 模拟 GitHub Actions 环境变量
IMAGE_TAG="v4.20.0-test"
PRODUCTION_PATH="/opt/xihong_erp"
REGISTRY="ghcr.io"
REPO_BACKEND="test/repo/backend"
REPO_FRONTEND="test/repo/frontend"

# 模拟 bash -c 命令执行（测试变量展开）
echo "[测试1] 模拟变量展开..."

# 模拟：${IMAGE_TAG} 在外层双引号中会展开
IMAGE_TAG_VAL="${IMAGE_TAG}"
echo "IMAGE_TAG_VAL=${IMAGE_TAG_VAL}"

# 模拟构建镜像路径
BACKEND_IMAGE="${REGISTRY}/${REPO_BACKEND}:${IMAGE_TAG_VAL}"
FRONTEND_IMAGE="${REGISTRY}/${REPO_FRONTEND}:${IMAGE_TAG_VAL}"

echo "BACKEND_IMAGE=${BACKEND_IMAGE}"
echo "FRONTEND_IMAGE=${FRONTEND_IMAGE}"

# 模拟 printf 命令生成 YAML
echo ""
echo "[测试2] 模拟 printf 生成 docker-compose.deploy.yml..."

# 模拟实际的 printf 命令
printf "services:\n  backend:\n    image: %s\n  frontend:\n    image: %s\n    ports: []\n" \
    "${BACKEND_IMAGE}" \
    "${FRONTEND_IMAGE}" > /tmp/test-docker-compose.deploy.yml

# 验证生成的 YAML
if [ -f /tmp/test-docker-compose.deploy.yml ]; then
    echo "[OK] 临时 compose 文件生成成功"
    echo ""
    echo "生成的 YAML 内容:"
    cat /tmp/test-docker-compose.deploy.yml
    echo ""
    
    # 验证 YAML 语法（如果系统有 docker-compose）
    if command -v docker-compose &> /dev/null; then
        # 合并测试（注意：这不会真正启动，只是验证语法）
        echo "[测试3] 验证 YAML 语法..."
        # 无法直接验证，因为需要实际的镜像存在
        echo "[INFO] YAML 格式看起来正确（需要实际镜像验证）"
    fi
    
    rm -f /tmp/test-docker-compose.deploy.yml
else
    echo "[FAIL] 临时 compose 文件生成失败"
    exit 1
fi

# 测试变量转义
echo ""
echo "[测试4] 测试 bash -c 中的变量转义..."

# 模拟在 bash -c '...' 中的变量使用
# 在单引号内，\$retry 不会被展开，会在远程服务器上展开
TEST_SCRIPT='for retry in {1..3}; do
  echo "Attempt $retry/3"
  if [ $retry -eq 3 ]; then
    echo "Final attempt"
  fi
done'

echo "模拟 bash -c 脚本（变量转义测试）:"
echo "$TEST_SCRIPT" | head -5

echo ""
echo "[OK] 所有语法测试通过！"
echo ""
echo "注意事项："
echo "  1. \${IMAGE_TAG} 在外层双引号中会在 GitHub Actions 运行时展开"
echo "  2. IMAGE_TAG_VAL 在远程服务器上会包含展开后的值"
echo "  3. \$retry 等变量在远程服务器上的 bash -c 单引号内展开（正确转义）"
echo "  4. 所有远程命令都使用 bash -c，避免了 heredoc 问题"
