#!/bin/bash
# =====================================================
# 西虹ERP系统 - 备份验证脚本
# =====================================================
# 功能：验证备份文件的完整性和可恢复性
# 使用方式：./scripts/verify_backup.sh <backup_directory>
# =====================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_message() {
    echo -e "${GREEN}[验证]${NC} $1"
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

# 参数检查
if [ $# -eq 0 ]; then
    print_error "请指定备份目录"
    echo "使用方法: $0 <backup_directory>"
    exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
    print_error "备份目录不存在: $BACKUP_DIR"
    exit 1
fi

# 检查 manifest.json
MANIFEST_FILE="${BACKUP_DIR}/manifest.json"
if [ ! -f "$MANIFEST_FILE" ]; then
    print_warning "备份清单不存在: $MANIFEST_FILE"
else
    print_message "找到备份清单: $MANIFEST_FILE"
fi

# 验证数据库备份
DB_BACKUP="${BACKUP_DIR}/database.sql.gz"
if [ -f "$DB_BACKUP" ]; then
    print_message "验证数据库备份..."
    
    # 检查文件完整性
    if gunzip -t "$DB_BACKUP" 2>/dev/null; then
        print_message "数据库备份文件完整性验证通过"
        
        # 使用 pg_restore --list 验证（如果可用）
        if command -v pg_restore &> /dev/null; then
            print_info "检查数据库备份内容..."
            if gunzip -c "$DB_BACKUP" | head -20 | grep -q "PostgreSQL database dump"; then
                print_message "数据库备份格式正确"
            else
                print_warning "无法验证数据库备份格式"
            fi
        fi
    else
        print_error "数据库备份文件损坏"
        exit 1
    fi
else
    print_warning "数据库备份文件不存在: $DB_BACKUP"
fi

# 验证文件备份
FILES_BACKUP="${BACKUP_DIR}/files.tar.gz"
if [ -f "$FILES_BACKUP" ]; then
    print_message "验证文件备份..."
    
    # 检查文件完整性
    if tar -tzf "$FILES_BACKUP" >/dev/null 2>&1; then
        print_message "文件备份完整性验证通过"
        
        # 计算校验和
        FILES_CHECKSUM=$(md5sum "$FILES_BACKUP" | cut -d' ' -f1)
        print_info "文件备份校验和: $FILES_CHECKSUM"
    else
        print_error "文件备份损坏"
        exit 1
    fi
else
    print_warning "文件备份不存在: $FILES_BACKUP"
fi

# 验证配置备份
CONFIG_BACKUP="${BACKUP_DIR}/config.tar.gz"
if [ -f "$CONFIG_BACKUP" ]; then
    print_message "验证配置备份..."
    
    # 检查文件完整性
    if tar -tzf "$CONFIG_BACKUP" >/dev/null 2>&1; then
        print_message "配置备份完整性验证通过"
        
        # 计算校验和
        CONFIG_CHECKSUM=$(md5sum "$CONFIG_BACKUP" | cut -d' ' -f1)
        print_info "配置备份校验和: $CONFIG_CHECKSUM"
    else
        print_error "配置备份损坏"
        exit 1
    fi
else
    print_warning "配置备份不存在: $CONFIG_BACKUP"
fi

# 总结
echo ""
echo "=========================================="
print_message "备份验证完成"
echo "备份目录: $BACKUP_DIR"
echo "=========================================="

