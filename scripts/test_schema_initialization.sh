#!/bin/bash
# 测试Schema初始化脚本
# 用于验证docker/postgres/init.sql中的Schema创建是否正确

set -e

echo "=========================================="
echo "Schema初始化脚本测试"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试1: 检查init.sql文件是否存在
echo "[TEST 1] 检查init.sql文件是否存在..."
if [ -f "docker/postgres/init.sql" ]; then
    echo -e "${GREEN}[OK]${NC} init.sql文件存在"
else
    echo -e "${RED}[FAIL]${NC} init.sql文件不存在"
    exit 1
fi

# 测试2: 检查Schema创建语句是否存在
echo "[TEST 2] 检查Schema创建语句..."
SCHEMA_COUNT=$(grep -c "CREATE SCHEMA IF NOT EXISTS" docker/postgres/init.sql || echo "0")
if [ "$SCHEMA_COUNT" -ge 5 ]; then
    echo -e "${GREEN}[OK]${NC} 找到 $SCHEMA_COUNT 个Schema创建语句"
else
    echo -e "${RED}[FAIL]${NC} 只找到 $SCHEMA_COUNT 个Schema创建语句（预期至少5个）"
    exit 1
fi

# 测试3: 检查必需的Schema是否存在
echo "[TEST 3] 检查必需的Schema..."
REQUIRED_SCHEMAS=("a_class" "b_class" "c_class" "core" "finance")
for schema in "${REQUIRED_SCHEMAS[@]}"; do
    if grep -q "CREATE SCHEMA IF NOT EXISTS $schema" docker/postgres/init.sql; then
        echo -e "${GREEN}[OK]${NC} Schema '$schema' 创建语句存在"
    else
        echo -e "${RED}[FAIL]${NC} Schema '$schema' 创建语句不存在"
        exit 1
    fi
done

# 测试4: 检查搜索路径设置是否存在
echo "[TEST 4] 检查搜索路径设置..."
if grep -q "ALTER DATABASE.*SET search_path" docker/postgres/init.sql; then
    echo -e "${GREEN}[OK]${NC} 数据库级别搜索路径设置存在"
else
    echo -e "${RED}[FAIL]${NC} 数据库级别搜索路径设置不存在"
    exit 1
fi

if grep -q "ALTER ROLE erp_user SET search_path" docker/postgres/init.sql; then
    echo -e "${GREEN}[OK]${NC} erp_user搜索路径设置存在"
else
    echo -e "${RED}[FAIL]${NC} erp_user搜索路径设置不存在"
    exit 1
fi

# 测试5: 检查SQL语法（基本检查）
echo "[TEST 5] 检查SQL语法（基本检查）..."
if grep -q "CREATE SCHEMA IF NOT EXISTS" docker/postgres/init.sql && \
   grep -q "ALTER DATABASE" docker/postgres/init.sql && \
   grep -q "ALTER ROLE" docker/postgres/init.sql; then
    echo -e "${GREEN}[OK]${NC} SQL语法基本检查通过"
else
    echo -e "${RED}[FAIL]${NC} SQL语法基本检查失败"
    exit 1
fi

echo ""
echo "=========================================="
echo -e "${GREEN}所有测试通过！${NC}"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 提交代码到Git"
echo "2. 在全新数据库环境中测试部署"
echo "3. 验证Schema是否正确创建"
echo ""
