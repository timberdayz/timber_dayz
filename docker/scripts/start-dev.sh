#!/bin/bash
# ===================================================
# 西虹ERP系统 - 开发环境启动脚本（Linux/Mac）
# ===================================================
# 功能：启动PostgreSQL和pgAdmin，供本地开发使用
# 使用方式：./docker/scripts/start-dev.sh
# ===================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
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

# 检查Docker是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi
    
    print_message "✅ Docker环境检查通过"
}

# 复制环境变量文件
setup_env() {
    print_message "设置环境变量..."
    
    if [ ! -f .env ]; then
        if [ -f env.development.example ]; then
            cp env.development.example .env
            print_message "✅ 已创建开发环境配置文件 .env"
        else
            print_warning "未找到env.development.example，使用env.example"
            cp env.example .env
        fi
    else
        print_info "环境变量文件已存在，跳过创建"
    fi
    
    # ⭐ Phase 1.3: 环境变量验证（开发环境简化检查，不阻止启动）
    if [ -f "scripts/validate-env.py" ] && [ -f .env ]; then
        print_info "验证环境变量配置（开发环境仅检查P0变量）..."
        if python3 scripts/validate-env.py --env-file .env --skip-p1 2>/dev/null; then
            print_message "✅ 环境变量验证通过"
        else
            print_warning "环境变量验证有警告（开发环境可忽略）"
        fi
    fi
}

# 创建必要的目录
create_directories() {
    print_message "创建必要的目录..."
    
    mkdir -p data
    mkdir -p temp/{outputs,cache,logs,development}
    mkdir -p logs/{postgres,nginx}
    mkdir -p downloads
    mkdir -p backups
    
    print_message "✅ 目录创建完成"
}

# 启动服务
start_services() {
    print_message "启动开发环境服务..."
    print_info "启动：PostgreSQL + pgAdmin"
    
    # 使用dev profile启动
    docker-compose --profile dev up -d
    
    print_message "✅ 服务启动完成"
}

# 等待数据库就绪
wait_for_database() {
    print_message "等待PostgreSQL就绪..."
    
    for i in {1..30}; do
        if docker-compose exec -T postgres pg_isready -U erp_user -d xihong_erp &> /dev/null; then
            print_message "✅ PostgreSQL已就绪"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    
    print_error "PostgreSQL启动超时"
    return 1
}

# 初始化数据库表
init_database_tables() {
    print_message "初始化数据库表..."
    
    # 检查是否需要初始化
    if docker-compose exec -T postgres psql -U erp_user -d xihong_erp -c "\dt" | grep -q "accounts"; then
        print_info "数据库表已存在，跳过初始化"
    else
        print_message "运行表初始化脚本..."
        python3 docker/postgres/init-tables.py
        print_message "✅ 数据库表初始化完成"
    fi
}

# 显示访问信息
show_info() {
    echo ""
    echo "=========================================="
    echo "🎉 西虹ERP系统 - 开发环境启动成功！"
    echo "=========================================="
    echo ""
    echo "📊 服务访问地址："
    echo "  PostgreSQL:  localhost:5432"
    echo "  pgAdmin:     http://localhost:5051"
    echo ""
    echo "🔐 数据库连接信息："
    echo "  数据库名: xihong_erp_dev"
    echo "  用户名:   erp_dev"
    echo "  密码:     dev_pass_2025"
    echo ""
    echo "🔐 pgAdmin登录信息："
    echo "  邮箱: dev@xihong.com"
    echo "  密码: dev123"
    echo ""
    echo "📝 下一步："
    echo "  1. 启动后端: cd backend && uvicorn main:app --reload"
    echo "  2. 启动前端: cd frontend && npm run dev"
    echo "  3. 访问系统: http://localhost:5173"
    echo ""
    echo "⚙️  常用命令："
    echo "  查看日志: docker-compose logs -f postgres"
    echo "  停止服务: docker-compose down"
    echo "  重启服务: docker-compose restart postgres"
    echo ""
    echo "=========================================="
}

# 主函数
main() {
    clear
    echo "=========================================="
    echo "西虹ERP系统 - 开发环境启动"
    echo "=========================================="
    echo ""
    
    # 检查是否在项目根目录
    if [ ! -f "docker-compose.yml" ]; then
        print_error "请在项目根目录执行此脚本"
        exit 1
    fi
    
    # 执行步骤
    check_docker
    setup_env
    create_directories
    start_services
    wait_for_database
    init_database_tables
    show_info
}

# 执行主函数
main

