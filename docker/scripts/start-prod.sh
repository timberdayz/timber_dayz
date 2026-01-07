#!/bin/bash
# ===================================================
# 西虹ERP系统 - 生产环境启动脚本（Linux/Mac）
# ===================================================
# 功能：构建并启动完整的生产环境（前端+后端+数据库）
# 使用方式：./docker/scripts/start-prod.sh
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

# 检查环境
check_environment() {
    print_message "检查环境..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker未安装"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose未安装"
        exit 1
    fi
    
    # 检查.env文件
    if [ ! -f .env ]; then
        print_error "未找到.env文件"
        print_info "请复制env.production.example为.env并修改配置"
        exit 1
    fi
    
    # ⭐ Phase 1.3: 环境变量验证（生产环境强制检查）
    print_message "验证环境变量配置..."
    if [ -f "scripts/validate-env.py" ]; then
        if python3 scripts/validate-env.py --env-file .env --strict; then
            print_message "✅ 环境变量验证通过"
        else
            print_error "环境变量验证失败，请检查配置"
            print_info "提示: 运行 'python3 scripts/validate-env.py --env-file .env --strict' 查看详细错误"
            exit 1
        fi
    else
        print_warning "环境变量验证脚本不存在，使用基础检查"
    fi
    
    # 检查关键环境变量（双重验证，作为补充）
    source .env
    if [ "$SECRET_KEY" == "your-secret-key-change-this-in-production-please-use-strong-random-string" ] || \
       [ "$SECRET_KEY" == "xihong-erp-secret-key-2025" ] || \
       [ "$SECRET_KEY" == "docker-secret-key-change-in-production" ]; then
        print_error "请修改.env文件中的SECRET_KEY（禁止使用默认密钥）"
        exit 1
    fi
    
    if [ "$POSTGRES_PASSWORD" == "erp_pass_2025" ] || [ "$POSTGRES_PASSWORD" == "YOUR_SECURE_PASSWORD_HERE" ]; then
        print_error "请修改.env文件中的POSTGRES_PASSWORD（禁止使用默认密码）"
        exit 1
    fi
    
    print_message "✅ 环境检查通过"
}

# 备份数据
backup_data() {
    print_message "备份现有数据..."
    
    if [ -d "data" ] && [ "$(ls -A data)" ]; then
        backup_dir="backups/before_deploy_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        cp -r data "$backup_dir/"
        print_message "✅ 数据已备份到: $backup_dir"
    else
        print_info "无需备份（数据目录为空）"
    fi
}

# 构建镜像
build_images() {
    print_message "构建Docker镜像..."
    print_info "这可能需要几分钟时间..."
    
    # 构建后端镜像
    print_message "构建后端镜像..."
    docker build -f Dockerfile.backend -t xihong-erp-backend:latest .
    
    # 构建前端镜像
    print_message "构建前端镜像..."
    docker build -f Dockerfile.frontend -t xihong-erp-frontend:latest .
    
    print_message "✅ 镜像构建完成"
}

# 启动服务
start_services() {
    print_message "启动生产环境服务..."
    
    # 使用production profile
    docker-compose --profile production up -d
    
    print_message "✅ 服务启动完成"
}

# 健康检查
health_check() {
    print_message "执行健康检查..."
    
    # 等待PostgreSQL
    print_info "等待PostgreSQL..."
    for i in {1..60}; do
        if docker-compose exec -T postgres pg_isready -U erp_user -d xihong_erp &> /dev/null; then
            print_message "✅ PostgreSQL健康"
            break
        fi
        if [ $i -eq 60 ]; then
            print_error "PostgreSQL启动超时"
            return 1
        fi
        echo -n "."
        sleep 1
    done
    echo ""
    
    # 等待后端API
    print_info "等待后端API..."
    for i in {1..60}; do
        if curl -f http://localhost:8001/health &> /dev/null; then
            print_message "✅ 后端API健康"
            break
        fi
        if [ $i -eq 60 ]; then
            print_error "后端API启动超时"
            return 1
        fi
        echo -n "."
        sleep 1
    done
    echo ""
    
    # 等待前端
    print_info "等待前端服务..."
    for i in {1..30}; do
        if curl -f http://localhost:5174 &> /dev/null; then
            print_message "✅ 前端服务健康"
            break
        fi
        if [ $i -eq 30 ]; then
            print_error "前端服务启动超时"
            return 1
        fi
        echo -n "."
        sleep 1
    done
    echo ""
    
    print_message "✅ 所有服务健康检查通过"
}

# 显示部署信息
show_info() {
    source .env
    
    echo ""
    echo "=========================================="
    echo "🎉 西虹ERP系统 - 生产环境部署成功！"
    echo "=========================================="
    echo ""
    echo "📊 服务状态："
    docker-compose ps
    echo ""
    echo "🌐 访问地址："
    echo "  前端:        http://localhost:${FRONTEND_PORT:-5174}"
    echo "  后端API:     http://localhost:${BACKEND_PORT:-8001}"
    echo "  API文档:     http://localhost:${BACKEND_PORT:-8001}/api/docs"
    echo "  健康检查:    http://localhost:${BACKEND_PORT:-8001}/health"
    echo ""
    echo "📂 数据持久化："
    echo "  PostgreSQL数据: Docker卷 xihong_erp_postgres_data"
    echo "  应用数据:       ./data"
    echo "  日志文件:       ./logs"
    echo ""
    echo "⚙️  管理命令："
    echo "  查看日志:   docker-compose logs -f"
    echo "  停止服务:   docker-compose down"
    echo "  重启服务:   docker-compose restart"
    echo "  查看状态:   docker-compose ps"
    echo ""
    echo "🔧 高级操作："
    echo "  进入容器:   docker-compose exec backend /bin/bash"
    echo "  数据库备份: docker-compose exec postgres pg_dump ..."
    echo "  查看资源:   docker stats"
    echo ""
    echo "=========================================="
}

# 主函数
main() {
    clear
    echo "=========================================="
    echo "西虹ERP系统 - 生产环境部署"
    echo "=========================================="
    echo ""
    
    # 检查是否在项目根目录
    if [ ! -f "docker-compose.yml" ]; then
        print_error "请在项目根目录执行此脚本"
        exit 1
    fi
    
    # 执行部署步骤
    check_environment
    backup_data
    build_images
    start_services
    health_check
    
    if [ $? -eq 0 ]; then
        show_info
    else
        print_error "部署过程中出现错误，请查看日志"
        docker-compose logs
        exit 1
    fi
}

# 执行主函数
main

