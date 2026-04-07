#!/bin/bash
# =====================================================
# 西虹ERP系统 - 备份 Cron 配置脚本（Linux）
# =====================================================
# 功能：在 Linux 宿主机上配置 cron 定时备份任务
# 使用方式：./scripts/setup_backup_cron.sh
# =====================================================

set -e

# 颜色输出
GREEN='\033[0;32m'
YELLON='\033[1;33m'
NC='\033[0m'

print_message() {
    echo -e "${GREEN}[配置]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[警告]${NC} $1"
}

# 获取脚本所在目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_SCRIPT="${PROJECT_ROOT}/scripts/backup_all.sh"

# 检查备份脚本是否存在
if [ ! -f "$BACKUP_SCRIPT" ]; then
    print_warning "备份脚本不存在: $BACKUP_SCRIPT"
    exit 1
fi

# 配置备份时间（默认：每天凌晨 2 点）
BACKUP_HOUR="${BACKUP_HOUR:-2}"
BACKUP_MINUTE="${BACKUP_MINUTE:-0}"

# Cron 表达式
CRON_EXPRESSION="${BACKUP_MINUTE} ${BACKUP_HOUR} * * *"

# 生成 cron 任务
CRON_TASK="${CRON_EXPRESSION} cd ${PROJECT_ROOT} && bash ${BACKUP_SCRIPT} >> ${PROJECT_ROOT}/logs/backup_cron.log 2>&1"

print_message "配置备份 Cron 任务..."
print_message "备份时间: 每天 ${BACKUP_HOUR}:${BACKUP_MINUTE}"
print_message "备份脚本: ${BACKUP_SCRIPT}"

# 检查是否已存在相同的 cron 任务
if crontab -l 2>/dev/null | grep -q "$BACKUP_SCRIPT"; then
    print_warning "备份任务已存在，将更新..."
    # 删除旧任务
    crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" | crontab -
fi

# 添加新任务
(crontab -l 2>/dev/null; echo "$CRON_TASK") | crontab -

print_message "Cron 任务配置完成"
print_message "查看任务: crontab -l"
print_message "编辑任务: crontab -e"
print_message "删除任务: crontab -e（手动删除对应行）"

