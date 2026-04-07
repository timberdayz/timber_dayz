#!/bin/bash
# =====================================================
# 西虹ERP系统 - 恢复演练脚本（仅测试环境）
# =====================================================
# 功能：在测试环境中演练备份恢复流程
# ⚠️ 警告：仅在测试环境使用，多重防护机制防止误操作
# 使用方式：ENVIRONMENT=test ./scripts/test_restore.sh <backup_directory>
# =====================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_message() {
    echo -e "${GREEN}[恢复]${NC} $1"
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

# ⭐ 多重防护机制
# 1. 环境变量检查
if [ "$ENVIRONMENT" != "test" ]; then
    print_error "此脚本仅在测试环境执行（ENVIRONMENT=test）"
    print_error "当前环境: ${ENVIRONMENT:-未设置}"
    exit 1
fi

# 2. 参数检查
if [ $# -eq 0 ]; then
    print_error "请指定备份目录"
    echo "使用方法: ENVIRONMENT=test $0 <backup_directory>"
    exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
    print_error "备份目录不存在: $BACKUP_DIR"
    exit 1
fi

# 3. 交互确认
echo "=========================================="
print_warning "⚠️  恢复演练确认"
echo "=========================================="
echo "备份目录: $BACKUP_DIR"
echo "环境: $ENVIRONMENT"
echo ""
print_warning "此操作将在测试环境中恢复备份数据"
print_warning "请确认："
echo "  1. 当前环境是测试环境（不是生产环境）"
echo "  2. 已备份当前测试数据（如果需要）"
echo "  3. 已确认备份目录正确"
echo ""
read -p "输入 'YES' 继续，其他任何内容将取消: " confirm

if [ "$confirm" != "YES" ]; then
    print_message "用户取消操作"
    exit 0
fi

# 4. 容器/卷命名约定检查（防止误操作生产环境）
RESTORE_TEST_PREFIX="xihong_erp_test"
if docker ps --format "{{.Names}}" | grep -q "^xihong_erp_postgres$"; then
    print_warning "检测到生产环境容器，请使用测试环境容器"
    print_info "建议使用容器名称前缀: ${RESTORE_TEST_PREFIX}"
    read -p "继续执行？(y/N): " continue_confirm
    if [ "$continue_confirm" != "y" ] && [ "$continue_confirm" != "Y" ]; then
        print_message "用户取消操作"
        exit 0
    fi
fi

# 恢复目录
RESTORE_DIR="./restore_test_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESTORE_DIR"

print_message "开始恢复演练..."
print_info "恢复目录: $RESTORE_DIR"

# 恢复数据库（如果存在）
DB_BACKUP="${BACKUP_DIR}/database.sql.gz"
if [ -f "$DB_BACKUP" ]; then
    print_message "恢复数据库..."
    print_warning "数据库恢复需要手动执行（使用 pg_restore 或 psql）"
    print_info "备份文件: $DB_BACKUP"
    print_info "恢复命令示例:"
    echo "  gunzip -c $DB_BACKUP | psql -U erp_user -d xihong_erp_test"
else
    print_warning "数据库备份不存在，跳过"
fi

# 恢复文件
FILES_BACKUP="${BACKUP_DIR}/files.tar.gz"
if [ -f "$FILES_BACKUP" ]; then
    print_message "恢复文件..."
    tar -xzf "$FILES_BACKUP" -C "$RESTORE_DIR"
    print_message "文件已恢复到: $RESTORE_DIR"
else
    print_warning "文件备份不存在，跳过"
fi

# 恢复配置
CONFIG_BACKUP="${BACKUP_DIR}/config.tar.gz"
if [ -f "$CONFIG_BACKUP" ]; then
    print_message "恢复配置..."
    tar -xzf "$CONFIG_BACKUP" -C "$RESTORE_DIR"
    print_message "配置已恢复到: $RESTORE_DIR"
else
    print_warning "配置备份不存在，跳过"
fi

# 验证恢复结果
print_message "验证恢复结果..."
if [ -d "$RESTORE_DIR" ] && [ -n "$(ls -A "$RESTORE_DIR" 2>/dev/null)" ]; then
    print_message "恢复演练完成"
    print_info "恢复目录: $RESTORE_DIR"
    print_info "请手动验证恢复的数据是否正确"
else
    print_warning "恢复目录为空，可能恢复失败"
fi

echo ""
echo "=========================================="
print_message "恢复演练完成"
echo "=========================================="

