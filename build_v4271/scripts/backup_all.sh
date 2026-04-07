#!/bin/bash
# =====================================================
# 西虹ERP系统 - 统一备份脚本（Linux 宿主机视角）
# =====================================================
# 功能：统一备份数据库、文件、配置
# 使用方式：./scripts/backup_all.sh
# 环境：在 Linux 宿主机上执行，通过 docker exec 操作容器
# =====================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_message() {
    echo -e "${GREEN}[备份]${NC} $1"
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

# 配置
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-./backups}"
BACKUP_DIR="${BACKUP_BASE_DIR}/backup_${TIMESTAMP}"
PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"

# Docker 容器名称（与 docker-compose.yml 一致）
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-xihong_erp_postgres}"

# 创建备份目录
mkdir -p "$BACKUP_DIR"
BACKUP_LOG="${BACKUP_DIR}/backup.log"

# 日志函数
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$BACKUP_LOG"
}

# 生成备份清单
generate_manifest() {
    local manifest_file="${BACKUP_DIR}/manifest.json"
    local files_list=()
    
    print_message "生成备份清单..."
    
    # 收集文件信息
    if [ -f "${BACKUP_DIR}/database.sql.gz" ]; then
        local db_size=$(du -h "${BACKUP_DIR}/database.sql.gz" | cut -f1)
        files_list+=("{\"type\":\"database\",\"file\":\"database.sql.gz\",\"size\":\"${db_size}\"}")
    fi
    
    if [ -f "${BACKUP_DIR}/files.tar.gz" ]; then
        local files_size=$(du -h "${BACKUP_DIR}/files.tar.gz" | cut -f1)
        files_list+=("{\"type\":\"files\",\"file\":\"files.tar.gz\",\"size\":\"${files_size}\"}")
    fi
    
    if [ -f "${BACKUP_DIR}/config.tar.gz" ]; then
        local config_size=$(du -h "${BACKUP_DIR}/config.tar.gz" | cut -f1)
        files_list+=("{\"type\":\"config\",\"file\":\"config.tar.gz\",\"size\":\"${config_size}\"}")
    fi
    
    # 生成 JSON
    local files_json=$(IFS=,; echo "${files_list[*]}")
    cat > "$manifest_file" <<EOF
{
  "backup_timestamp": "${TIMESTAMP}",
  "backup_date": "$(date -Iseconds)",
  "backup_type": "full",
  "files": [${files_json}],
  "system_info": {
    "hostname": "$(hostname)",
    "user": "$(whoami)"
  }
}
EOF
    
    log_message "备份清单已生成: $manifest_file"
}

# 备份数据库
backup_database() {
    print_message "备份数据库..."
    
    # 使用 host 模式（通过 docker exec）
    export BACKUP_MODE=host
    export BACKUP_DIR="$BACKUP_DIR"
    
    # 调用数据库备份脚本
    if [ -f "${PROJECT_ROOT}/scripts/backup_database.sh" ]; then
        bash "${PROJECT_ROOT}/scripts/backup_database.sh"
        
        # 移动备份文件到统一目录
        if [ -f "${BACKUP_BASE_DIR}/xihong_erp_${TIMESTAMP}.sql.gz" ]; then
            mv "${BACKUP_BASE_DIR}/xihong_erp_${TIMESTAMP}.sql.gz" "${BACKUP_DIR}/database.sql.gz"
            log_message "数据库备份完成: ${BACKUP_DIR}/database.sql.gz"
        fi
    else
        print_error "数据库备份脚本不存在: ${PROJECT_ROOT}/scripts/backup_database.sh"
        return 1
    fi
}

# 备份文件存储
backup_files() {
    print_message "备份文件存储..."
    
    local files_backup="${BACKUP_DIR}/files.tar.gz"
    local files_to_backup=()
    
    # 收集需要备份的目录
    if [ -d "${PROJECT_ROOT}/data" ]; then
        files_to_backup+=("data")
    fi
    
    if [ -d "${PROJECT_ROOT}/uploads" ]; then
        files_to_backup+=("uploads")
    fi
    
    if [ -d "${PROJECT_ROOT}/downloads" ]; then
        files_to_backup+=("downloads")
    fi
    
    # 备份 temp 目录（仅重要子目录）
    if [ -d "${PROJECT_ROOT}/temp" ]; then
        # 创建临时目录结构
        local temp_backup_dir="${BACKUP_DIR}/temp_backup"
        mkdir -p "$temp_backup_dir"
        
        # 仅备份重要子目录
        for subdir in "outputs" "cache" "logs"; do
            if [ -d "${PROJECT_ROOT}/temp/${subdir}" ]; then
                cp -r "${PROJECT_ROOT}/temp/${subdir}" "$temp_backup_dir/" 2>/dev/null || true
            fi
        done
        
        if [ -n "$(ls -A "$temp_backup_dir" 2>/dev/null)" ]; then
            files_to_backup+=("temp_backup")
        fi
    fi
    
    if [ ${#files_to_backup[@]} -eq 0 ]; then
        print_warning "没有找到需要备份的文件目录"
        return 0
    fi
    
    # 创建 tar 归档
    cd "$PROJECT_ROOT"
    tar -czf "$files_backup" "${files_to_backup[@]}" 2>/dev/null || {
        print_error "文件备份失败"
        return 1
    }
    
    # 清理临时目录
    rm -rf "${BACKUP_DIR}/temp_backup"
    
    local files_size=$(du -h "$files_backup" | cut -f1)
    log_message "文件备份完成: $files_backup (大小: $files_size)"
}

# 备份配置（注意脱敏）
backup_config() {
    print_message "备份配置（已脱敏）..."
    
    local config_backup="${BACKUP_DIR}/config.tar.gz"
    local config_backup_dir="${BACKUP_DIR}/config_backup"
    mkdir -p "$config_backup_dir"
    
    # 备份 .env 文件（脱敏处理）
    if [ -f "${PROJECT_ROOT}/.env" ]; then
        # 创建脱敏版本
        sed -E 's/(SECRET_KEY|JWT_SECRET_KEY|POSTGRES_PASSWORD|REDIS_PASSWORD|ACCOUNT_ENCRYPTION_KEY|SMTP_PASSWORD|METABASE_API_KEY)=.*/\1=***REDACTED***/g' \
            "${PROJECT_ROOT}/.env" > "${config_backup_dir}/.env.redacted"
        log_message "已备份 .env 文件（已脱敏）"
    fi
    
    # 备份 config 目录（排除敏感文件）
    if [ -d "${PROJECT_ROOT}/config" ]; then
        # 排除敏感配置文件
        rsync -av --exclude='*accounts_config.yaml' \
                  --exclude='*proxy_config.yaml' \
                  --exclude='*.key' \
                  --exclude='*.pem' \
                  "${PROJECT_ROOT}/config/" "${config_backup_dir}/config/" 2>/dev/null || true
    fi
    
    # 备份 docker-compose 文件
    for compose_file in "docker-compose.yml" "docker-compose.prod.yml" "docker-compose.dev.yml"; do
        if [ -f "${PROJECT_ROOT}/${compose_file}" ]; then
            cp "${PROJECT_ROOT}/${compose_file}" "${config_backup_dir}/" 2>/dev/null || true
        fi
    done
    
    # 创建 tar 归档
    cd "$BACKUP_DIR"
    tar -czf "$config_backup" "config_backup" 2>/dev/null || {
        print_error "配置备份失败"
        return 1
    }
    
    # 清理临时目录
    rm -rf "$config_backup_dir"
    
    local config_size=$(du -h "$config_backup" | cut -f1)
    log_message "配置备份完成: $config_backup (大小: $config_size)"
}

# 主函数
main() {
    echo "=========================================="
    echo "西虹ERP系统 - 统一备份"
    echo "=========================================="
    echo ""
    
    log_message "开始备份: ${TIMESTAMP}"
    log_message "备份目录: ${BACKUP_DIR}"
    
    # 检查 Docker 容器
    if ! docker ps --format "{{.Names}}" | grep -q "^${POSTGRES_CONTAINER}$"; then
        print_warning "PostgreSQL 容器未运行: ${POSTGRES_CONTAINER}"
        print_info "将跳过数据库备份"
        SKIP_DATABASE=true
    else
        SKIP_DATABASE=false
    fi
    
    # 执行备份
    local backup_failed=false
    
    # 1. 备份数据库
    if [ "$SKIP_DATABASE" != "true" ]; then
        if ! backup_database; then
            print_error "数据库备份失败"
            backup_failed=true
        fi
    fi
    
    # 2. 备份文件
    if ! backup_files; then
        print_error "文件备份失败"
        backup_failed=true
    fi
    
    # 3. 备份配置
    if ! backup_config; then
        print_error "配置备份失败"
        backup_failed=true
    fi
    
    # 4. 生成备份清单
    generate_manifest
    
    # 总结
    echo ""
    echo "=========================================="
    if [ "$backup_failed" = "true" ]; then
        print_error "备份完成（有错误）"
        log_message "备份完成（有错误）: ${TIMESTAMP}"
        exit 1
    else
        print_message "备份完成"
        log_message "备份完成: ${TIMESTAMP}"
        
        local total_size=$(du -sh "$BACKUP_DIR" | cut -f1)
        echo "备份位置: ${BACKUP_DIR}"
        echo "总大小: ${total_size}"
        echo "=========================================="
    fi
}

# 执行主函数
main

