#!/bin/bash
# 西虹ERP系统 - 数据库备份脚本
# ⭐ Phase 2.1 更新：支持 host/container 模式

set -e

# 配置
BACKUP_MODE="${BACKUP_MODE:-container}"  # host 或 container
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RETENTION_DAYS=30

# 从环境变量读取数据库配置
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-xihong_erp}"
DB_USER="${POSTGRES_USER:-erp_user}"
DB_PASSWORD="${POSTGRES_PASSWORD:-erp_pass_2025}"

# Docker 容器名称（host 模式使用）
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-xihong_erp_postgres}"

# 备份文件名
BACKUP_FILE="${BACKUP_DIR}/xihong_erp_${TIMESTAMP}.sql.gz"
BACKUP_LOG="${BACKUP_DIR}/backup_${TIMESTAMP}.log"

echo "================================" | tee -a "$BACKUP_LOG"
echo "西虹ERP系统数据库备份" | tee -a "$BACKUP_LOG"
echo "模式: ${BACKUP_MODE}" | tee -a "$BACKUP_LOG"
echo "开始时间: $(date)" | tee -a "$BACKUP_LOG"
echo "================================" | tee -a "$BACKUP_LOG"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 执行备份
echo "正在备份数据库..." | tee -a "$BACKUP_LOG"

if [ "$BACKUP_MODE" = "host" ]; then
    # Host 模式：通过 docker exec 执行（Linux 宿主机视角）
    echo "使用 host 模式（docker exec）..." | tee -a "$BACKUP_LOG"
    
    # 检查容器是否存在
    if ! docker ps --format "{{.Names}}" | grep -q "^${POSTGRES_CONTAINER}$"; then
        echo "错误: PostgreSQL 容器未运行: ${POSTGRES_CONTAINER}" | tee -a "$BACKUP_LOG"
        exit 1
    fi
    
    # 通过 docker exec 执行 pg_dump
    if docker exec "$POSTGRES_CONTAINER" \
        pg_dump -U "$DB_USER" -d "$DB_NAME" \
        --format=plain --no-owner --no-acl | gzip > "$BACKUP_FILE"; then
        
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        echo "✓ 备份成功" | tee -a "$BACKUP_LOG"
        echo "  文件: $BACKUP_FILE" | tee -a "$BACKUP_LOG"
        echo "  大小: $BACKUP_SIZE" | tee -a "$BACKUP_LOG"
    else
        echo "✗ 备份失败" | tee -a "$BACKUP_LOG"
        exit 1
    fi
else
    # Container 模式：直接连接（容器内部执行）
    echo "使用 container 模式（直接连接）..." | tee -a "$BACKUP_LOG"
export PGPASSWORD="$DB_PASSWORD"

if pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --format=plain --no-owner --no-acl | gzip > "$BACKUP_FILE"; then
    
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "✓ 备份成功" | tee -a "$BACKUP_LOG"
    echo "  文件: $BACKUP_FILE" | tee -a "$BACKUP_LOG"
    echo "  大小: $BACKUP_SIZE" | tee -a "$BACKUP_LOG"
else
    echo "✗ 备份失败" | tee -a "$BACKUP_LOG"
    exit 1
    fi
fi

# 清理旧备份
echo "正在清理旧备份..." | tee -a "$BACKUP_LOG"
find "$BACKUP_DIR" -name "xihong_erp_*.sql.gz" -mtime +$RETENTION_DAYS -delete
REMAINING_BACKUPS=$(find "$BACKUP_DIR" -name "xihong_erp_*.sql.gz" | wc -l)
echo "✓ 保留 $REMAINING_BACKUPS 个备份文件" | tee -a "$BACKUP_LOG"

# 验证备份
echo "正在验证备份..." | tee -a "$BACKUP_LOG"
if gunzip -t "$BACKUP_FILE" 2>/dev/null; then
    echo "✓ 备份文件验证成功" | tee -a "$BACKUP_LOG"
else
    echo "✗ 备份文件验证失败" | tee -a "$BACKUP_LOG"
    exit 1
fi

echo "================================" | tee -a "$BACKUP_LOG"
echo "备份完成: $(date)" | tee -a "$BACKUP_LOG"
echo "================================" | tee -a "$BACKUP_LOG"

# 发送通知（可选）
# curl -X POST "your-webhook-url" -d "数据库备份完成: $BACKUP_FILE"

exit 0
