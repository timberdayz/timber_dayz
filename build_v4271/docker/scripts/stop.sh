#!/bin/bash
# ===================================================
# 西虹ERP系统 - 停止脚本（Linux/Mac）
# ===================================================
# 功能：优雅停止所有Docker服务
# 使用方式：./docker/scripts/stop.sh [--backup]
# ===================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_message() {
    echo -e "${GREEN}[西虹ERP]${NC} $1"
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

# 备份数据
backup_data() {
    print_message "备份数据..."
    
    backup_dir="backups/before_stop_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # 备份应用数据
    if [ -d "data" ]; then
        cp -r data "$backup_dir/"
        print_message "✅ 应用数据已备份"
    fi
    
    # 备份PostgreSQL数据
    if docker ps --format '{{.Names}}' | grep -q "xihong_erp_postgres"; then
        print_message "备份PostgreSQL数据库..."
        docker-compose exec -T postgres pg_dump -U erp_user xihong_erp > "$backup_dir/postgres_dump.sql"
        print_message "✅ PostgreSQL数据已备份"
    fi
    
    # 备份日志
    if [ -d "logs" ]; then
        cp -r logs "$backup_dir/"
        print_message "✅ 日志已备份"
    fi
    
    print_message "✅ 数据备份完成: $backup_dir"
}

# 停止服务
stop_services() {
    print_message "停止Docker服务..."
    
    # 显示当前运行的容器
    echo ""
    echo "当前运行的容器："
    docker-compose ps
    echo ""
    
    # 确认停止
    if [ "$AUTO_CONFIRM" != "true" ]; then
        read -p "确认停止所有服务? (y/N): " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            print_info "操作已取消"
            exit 0
        fi
    fi
    
    # 优雅停止
    print_message "正在停止服务..."
    docker-compose down
    
    print_message "✅ 服务已停止"
}

# 清理资源（可选）
cleanup_resources() {
    echo ""
    print_warning "清理资源"
    print_info "这将删除所有容器和网络，但保留数据卷和镜像"
    echo ""
    
    read -p "是否清理Docker资源? (y/N): " confirm
    if [ "$confirm" == "y" ] || [ "$confirm" == "Y" ]; then
        docker-compose down
        print_message "✅ 资源已清理"
        
        echo ""
        read -p "是否同时删除数据卷? ⚠️  这将删除所有数据! (y/N): " confirm_volumes
        if [ "$confirm_volumes" == "y" ] || [ "$confirm_volumes" == "Y" ]; then
            docker-compose down -v
            print_warning "数据卷已删除"
        fi
    fi
}

# 显示信息
show_info() {
    echo ""
    echo "=========================================="
    echo "服务停止完成"
    echo "=========================================="
    echo ""
    echo "📊 当前状态："
    docker-compose ps 2>/dev/null || echo "所有服务已停止"
    echo ""
    echo "💾 数据保留："
    echo "  - PostgreSQL数据卷: $(docker volume ls | grep xihong_erp_postgres_data >/dev/null 2>&1 && echo '✓ 保留' || echo '✗ 已删除')"
    echo "  - 应用数据目录: $([ -d 'data' ] && echo '✓ 保留' || echo '✗ 不存在')"
    echo "  - 日志目录: $([ -d 'logs' ] && echo '✓ 保留' || echo '✗ 不存在')"
    echo ""
    echo "🔄 重启服务："
    echo "  开发模式: ./docker/scripts/start-dev.sh"
    echo "  生产模式: ./docker/scripts/start-prod.sh"
    echo ""
    echo "=========================================="
}

# 主函数
main() {
    clear
    echo "=========================================="
    echo "西虹ERP系统 - 停止服务"
    echo "=========================================="
    echo ""
    
    # 检查是否在项目根目录
    if [ ! -f "docker-compose.yml" ]; then
        print_error "请在项目根目录执行此脚本"
        exit 1
    fi
    
    # 解析参数
    if [ "$1" == "--backup" ]; then
        backup_data
    elif [ "$1" == "--auto" ]; then
        AUTO_CONFIRM=true
    fi
    
    # 停止服务
    stop_services
    
    # 询问是否清理资源
    if [ "$AUTO_CONFIRM" != "true" ]; then
        cleanup_resources
    fi
    
    # 显示信息
    show_info
}

# 执行主函数
main "$@"

