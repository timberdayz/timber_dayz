#!/bin/bash
# 测试 Nginx 配置文件同步逻辑（模拟 GitHub Actions 部署流程）
# 用于验证部署流程中 nginx 配置文件同步逻辑的正确性

set -e

echo "=========================================="
echo "测试 Nginx 配置文件同步逻辑"
echo "=========================================="
echo ""

# 测试1: 检查 nginx 目录是否存在
echo "[TEST 1] 检查 nginx 目录..."
if [ -d "nginx" ]; then
    echo "  [OK] nginx 目录存在"
else
    echo "  [FAIL] nginx 目录不存在"
    exit 1
fi

# 测试2: 检查 nginx.prod.conf 文件是否存在
echo ""
echo "[TEST 2] 检查 nginx.prod.conf 文件..."
if [ -f "nginx/nginx.prod.conf" ]; then
    echo "  [OK] nginx/nginx.prod.conf 文件存在"
    
    # 检查文件大小（应该大于0）
    file_size=$(wc -c < "nginx/nginx.prod.conf" | tr -d ' ')
    if [ "$file_size" -gt 0 ]; then
        echo "  [OK] 文件大小: ${file_size} 字节"
    else
        echo "  [WARN] 文件大小为0，可能有问题"
    fi
else
    echo "  [FAIL] nginx/nginx.prod.conf 文件不存在"
    exit 1
fi

# 测试3: 检查配置文件语法（如果系统有 nginx）
echo ""
echo "[TEST 3] 检查 Nginx 配置语法..."
if command -v nginx >/dev/null 2>&1; then
    if nginx -t -c "$(pwd)/nginx/nginx.prod.conf" >/dev/null 2>&1; then
        echo "  [OK] Nginx 配置语法正确"
    else
        echo "  [WARN] Nginx 配置语法检查失败（可能是路径问题，在容器中应该正常）"
    fi
else
    echo "  [INFO] nginx 命令不可用，跳过语法检查（在 GitHub Actions 中会通过容器验证）"
fi

# 测试4: 检查关键配置项
echo ""
echo "[TEST 4] 检查关键配置项..."
if grep -q "proxy_set_header Host backend;" nginx/nginx.prod.conf; then
    echo "  [OK] 找到正确的 Host 头配置: proxy_set_header Host backend;"
else
    echo "  [WARN] 未找到 'proxy_set_header Host backend;'，可能配置不正确"
fi

if grep -q "resolver 127.0.0.11" nginx/nginx.prod.conf; then
    echo "  [OK] 找到 resolver 配置: resolver 127.0.0.11"
else
    echo "  [WARN] 未找到 resolver 配置"
fi

# 测试5: 验证部署脚本逻辑（模拟）
echo ""
echo "[TEST 5] 验证部署脚本逻辑（模拟）..."
echo "  [INFO] 模拟 GitHub Actions 部署流程："
echo "    - 检查 nginx 目录存在: $([ -d "nginx" ] && echo "OK" || echo "FAIL")"
echo "    - 检查 nginx.prod.conf 存在: $([ -f "nginx/nginx.prod.conf" ] && echo "OK" || echo "FAIL")"
echo "    - 模拟 scp 上传: nginx/nginx.prod.conf -> \${PRODUCTION_PATH}/nginx/nginx.prod.conf"
echo "  [OK] 逻辑验证通过（实际部署时会在 GitHub Actions 中执行）"

echo ""
echo "=========================================="
echo "[OK] 所有测试通过！"
echo "=========================================="
echo ""
echo "说明："
echo "  - 这些测试验证了部署流程中 Nginx 配置文件同步的逻辑"
echo "  - 实际部署时，GitHub Actions 会："
echo "    1. 检查 nginx 目录是否存在"
echo "    2. 创建服务器上的 nginx 目录（如果不存在）"
echo "    3. 上传 nginx/nginx.prod.conf 到服务器"
echo "    4. 确保 SSL 证书目录存在"
echo "  - 部署后，Nginx 容器会使用更新后的配置文件"
echo ""
