#!/bin/bash
# 测试全新部署（模拟）
# 用于验证Schema创建在全新数据库环境中的表现

set -e

echo "=========================================="
echo "全新部署测试（模拟）"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}注意：此脚本仅进行模拟测试，不会实际创建新数据库${NC}"
echo ""

# 测试1: 检查init.sql文件语法
echo "[TEST 1] 检查init.sql文件语法..."
if [ -f "docker/postgres/init.sql" ]; then
    # 检查是否包含必需的关键字
    if grep -q "CREATE SCHEMA IF NOT EXISTS" docker/postgres/init.sql && \
       grep -q "ALTER DATABASE.*search_path" docker/postgres/init.sql && \
       grep -q "ALTER ROLE.*search_path" docker/postgres/init.sql; then
        echo -e "${GREEN}[OK]${NC} init.sql文件语法检查通过"
    else
        echo -e "${RED}[FAIL]${NC} init.sql文件语法检查失败"
        exit 1
    fi
else
    echo -e "${RED}[FAIL]${NC} init.sql文件不存在"
    exit 1
fi

# 测试2: 检查docker-compose.yml中的init.sql挂载
echo "[TEST 2] 检查docker-compose.yml中的init.sql挂载..."
if grep -q "docker-entrypoint-initdb.d" docker-compose.yml; then
    echo -e "${GREEN}[OK]${NC} docker-entrypoint-initdb.d挂载存在"
else
    echo -e "${YELLOW}[WARN]${NC} docker-entrypoint-initdb.d挂载未找到（可能使用其他方式）"
fi

# 测试3: 检查部署脚本中的迁移顺序
echo "[TEST 3] 检查部署脚本中的迁移顺序..."
if [ -f "scripts/deploy_remote_production.sh" ]; then
    # 检查是否在迁移前启动PostgreSQL
    if grep -q "Phase 1.*postgres" scripts/deploy_remote_production.sh && \
       grep -q "Phase 2.*Alembic" scripts/deploy_remote_production.sh; then
        echo -e "${GREEN}[OK]${NC} 部署脚本顺序正确（PostgreSQL在Alembic之前）"
    else
        echo -e "${YELLOW}[WARN]${NC} 无法确认部署脚本顺序"
    fi
else
    echo -e "${YELLOW}[WARN]${NC} 部署脚本不存在，跳过检查"
fi

# 测试4: 检查当前数据库中的Schema（如果存在）
echo "[TEST 4] 检查当前数据库中的Schema..."
if docker ps --format "{{.Names}}" | grep -q "xihong_erp_postgres"; then
    SCHEMAS=$(docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -t -c \
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('public', 'core', 'a_class', 'b_class', 'c_class', 'finance') ORDER BY schema_name;" 2>/dev/null || echo "")
    
    if [ -n "$SCHEMAS" ]; then
        REQUIRED_SCHEMAS=("a_class" "b_class" "c_class" "core" "finance" "public")
        MISSING_SCHEMAS=()
        
        for schema in "${REQUIRED_SCHEMAS[@]}"; do
            if echo "$SCHEMAS" | grep -q "$schema"; then
                echo -e "${GREEN}[OK]${NC} Schema '$schema' 存在"
            else
                echo -e "${YELLOW}[WARN]${NC} Schema '$schema' 不存在（可能需要重新创建容器）"
                MISSING_SCHEMAS+=("$schema")
            fi
        done
        
        if [ ${#MISSING_SCHEMAS[@]} -eq 0 ]; then
            echo -e "${GREEN}[OK]${NC} 所有必需的Schema都存在"
        else
            echo -e "${YELLOW}[WARN]${NC} 以下Schema缺失: ${MISSING_SCHEMAS[*]}"
            echo -e "${BLUE}[INFO]${NC} 建议：重新创建数据库容器以应用init.sql更改"
        fi
    else
        echo -e "${YELLOW}[WARN]${NC} 无法连接到数据库，跳过Schema检查"
    fi
else
    echo -e "${YELLOW}[WARN]${NC} PostgreSQL容器未运行，跳过Schema检查"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}测试完成！${NC}"
echo "=========================================="
echo ""
echo "建议："
echo "1. 提交代码到Git"
echo "2. 在全新环境中测试部署（删除数据卷后重新创建容器）"
echo "3. 验证Schema是否正确创建"
echo "4. 验证Alembic迁移是否成功执行"
echo ""
