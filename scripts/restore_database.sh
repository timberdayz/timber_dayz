#!/bin/bash
# 西虹ERP系统 - 数据库恢复脚本

set -e

# 从环境变量读取数据库配置
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-xihong_erp}"
DB_USER="${POSTGRES_USER:-erp_user}"
DB_PASSWORD="${POSTGRES_PASSWORD:-erp_pass_2025}"

# 检查参数
if [ -z "$1" ]; then
    echo "用法: $0 <backup_file.sql.gz>"
    echo ""
    echo "可用的备份文件:"
    ls -lh /backups/xihong_erp_*.sql.gz 2>/dev/null || echo "  没有找到备份文件"
    exit 1
fi

BACKUP_FILE="$1"

# 检查备份文件
if [ ! -f "$BACKUP_FILE" ]; then
    echo "✗ 备份文件不存在: $BACKUP_FILE"
    exit 1
fi

echo "================================"
echo "西虹ERP系统数据库恢复"
echo "备份文件: $BACKUP_FILE"
echo "目标数据库: $DB_NAME"
echo "================================"

# 确认操作
read -p "确认要恢复数据库吗？这将覆盖现有数据 (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "操作已取消"
    exit 0
fi

export PGPASSWORD="$DB_PASSWORD"

# 断开现有连接
echo "正在断开现有数据库连接..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();"

# 删除现有数据库
echo "正在删除现有数据库..."
dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" --if-exists "$DB_NAME"

# 创建新数据库
echo "正在创建新数据库..."
createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"

# 恢复数据
echo "正在恢复数据..."
if gunzip -c "$BACKUP_FILE" | psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" > /dev/null 2>&1; then
    echo "✓ 数据库恢复成功"
else
    echo "✗ 数据库恢复失败"
    exit 1
fi

# 验证恢复
echo "正在验证恢复..."
TABLE_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")

echo "✓ 恢复完成，共有 $TABLE_COUNT 个表"

echo "================================"
echo "恢复完成: $(date)"
echo "================================"

exit 0
