#!/bin/bash
# ===================================================
# 西虹ERP系统 - 健康检查脚本
# ===================================================
# 功能：检查所有服务的健康状态
# 使用方式：./docker/scripts/health-check.sh
# ===================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 检查结果计数
total_checks=0
passed_checks=0
failed_checks=0

print_header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
    echo ""
}

print_check() {
    total_checks=$((total_checks + 1))
    echo -n "$1 ... "
}

print_ok() {
    passed_checks=$((passed_checks + 1))
    echo -e "${GREEN}✓ OK${NC}"
}

print_fail() {
    failed_checks=$((failed_checks + 1))
    echo -e "${RED}✗ FAIL${NC}"
    if [ -n "$1" ]; then
        echo -e "  ${RED}错误: $1${NC}"
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠ WARNING: $1${NC}"
}

# 检查Docker服务
check_docker() {
    print_check "检查Docker服务"
    if docker info >/dev/null 2>&1; then
        print_ok
    else
        print_fail "Docker服务未运行"
        exit 1
    fi
}

# 检查容器状态
check_containers() {
    print_header "容器状态检查"
    
    containers=("xihong_erp_postgres" "xihong_erp_backend" "xihong_erp_frontend")
    
    for container in "${containers[@]}"; do
        print_check "容器 $container"
        if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
            status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null)
            if [ "$status" == "running" ]; then
                print_ok
            else
                print_fail "容器状态: $status"
            fi
        else
            print_fail "容器不存在或未运行"
        fi
    done
}

# 检查PostgreSQL
check_postgres() {
    print_header "PostgreSQL检查"
    
    print_check "PostgreSQL连接"
    if docker-compose exec -T postgres pg_isready -U erp_user -d xihong_erp >/dev/null 2>&1; then
        print_ok
    else
        print_fail "无法连接到PostgreSQL"
        return
    fi
    
    print_check "数据库版本"
    version=$(docker-compose exec -T postgres psql -U erp_user -d xihong_erp -t -c "SELECT version();" 2>/dev/null | head -1)
    if [ -n "$version" ]; then
        echo -e "${GREEN}✓ OK${NC} - ${version}"
        passed_checks=$((passed_checks + 1))
    else
        print_fail
    fi
    
    print_check "数据库大小"
    size=$(docker-compose exec -T postgres psql -U erp_user -d xihong_erp -t -c "SELECT pg_size_pretty(pg_database_size('xihong_erp'));" 2>/dev/null)
    if [ -n "$size" ]; then
        echo -e "${GREEN}✓ OK${NC} - ${size}"
        passed_checks=$((passed_checks + 1))
    else
        print_fail
    fi
    
    print_check "活动连接数"
    connections=$(docker-compose exec -T postgres psql -U erp_user -d xihong_erp -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null)
    if [ -n "$connections" ]; then
        echo -e "${GREEN}✓ OK${NC} - $connections 个连接"
        passed_checks=$((passed_checks + 1))
    else
        print_fail
    fi
}

# 检查后端API
check_backend() {
    print_header "后端API检查"
    
    print_check "健康检查端点"
    if curl -sf http://localhost:8001/health >/dev/null 2>&1; then
        print_ok
    else
        print_fail "健康检查端点无响应"
        return
    fi
    
    print_check "API响应时间"
    response_time=$(curl -o /dev/null -s -w '%{time_total}' http://localhost:8001/health 2>/dev/null)
    if [ -n "$response_time" ]; then
        echo -e "${GREEN}✓ OK${NC} - ${response_time}秒"
        passed_checks=$((passed_checks + 1))
        
        # 如果响应时间大于2秒，发出警告
        if (( $(echo "$response_time > 2" | bc -l) )); then
            print_warning "响应时间较慢 (>2秒)"
        fi
    else
        print_fail
    fi
    
    print_check "API文档访问"
    if curl -sf http://localhost:8001/api/docs >/dev/null 2>&1; then
        print_ok
    else
        print_fail "API文档无法访问"
    fi
}

# 检查前端服务
check_frontend() {
    print_header "前端服务检查"
    
    print_check "前端页面访问"
    if curl -sf http://localhost:5174 >/dev/null 2>&1; then
        print_ok
    else
        print_fail "前端页面无法访问"
        return
    fi
    
    print_check "前端响应时间"
    response_time=$(curl -o /dev/null -s -w '%{time_total}' http://localhost:5174 2>/dev/null)
    if [ -n "$response_time" ]; then
        echo -e "${GREEN}✓ OK${NC} - ${response_time}秒"
        passed_checks=$((passed_checks + 1))
    else
        print_fail
    fi
}

# 检查资源使用
check_resources() {
    print_header "资源使用检查"
    
    echo "容器资源使用情况："
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
        xihong_erp_postgres xihong_erp_backend xihong_erp_frontend 2>/dev/null
    echo ""
}

# 检查数据持久化
check_data() {
    print_header "数据持久化检查"
    
    print_check "PostgreSQL数据卷"
    if docker volume inspect xihong_erp_postgres_data >/dev/null 2>&1; then
        size=$(docker volume inspect xihong_erp_postgres_data --format '{{.Mountpoint}}' | xargs sudo du -sh 2>/dev/null | cut -f1)
        if [ -n "$size" ]; then
            echo -e "${GREEN}✓ OK${NC} - 大小: $size"
            passed_checks=$((passed_checks + 1))
        else
            print_ok
        fi
    else
        print_fail "数据卷不存在"
    fi
    
    print_check "应用数据目录"
    if [ -d "data" ]; then
        size=$(du -sh data 2>/dev/null | cut -f1)
        echo -e "${GREEN}✓ OK${NC} - 大小: $size"
        passed_checks=$((passed_checks + 1))
    else
        print_fail "数据目录不存在"
    fi
    
    print_check "日志目录"
    if [ -d "logs" ]; then
        size=$(du -sh logs 2>/dev/null | cut -f1)
        echo -e "${GREEN}✓ OK${NC} - 大小: $size"
        passed_checks=$((passed_checks + 1))
    else
        print_fail "日志目录不存在"
    fi
}

# 生成检查报告
generate_report() {
    print_header "健康检查报告"
    
    echo "总检查项: $total_checks"
    echo -e "${GREEN}通过: $passed_checks${NC}"
    echo -e "${RED}失败: $failed_checks${NC}"
    echo ""
    
    if [ $failed_checks -eq 0 ]; then
        echo -e "${GREEN}✅ 所有检查通过，系统运行正常！${NC}"
        return 0
    else
        echo -e "${RED}❌ 有 $failed_checks 项检查失败，请查看上述详情${NC}"
        return 1
    fi
}

# 主函数
main() {
    clear
    print_header "西虹ERP系统 - 健康检查"
    echo "检查时间: $(date '+%Y-%m-%d %H:%M:%S')"
    
    # 检查是否在项目根目录
    if [ ! -f "docker-compose.yml" ]; then
        echo -e "${RED}错误: 请在项目根目录执行此脚本${NC}"
        exit 1
    fi
    
    # 执行检查
    check_docker
    check_containers
    check_postgres
    check_backend
    check_frontend
    check_resources
    check_data
    
    # 生成报告
    generate_report
}

# 执行主函数
main
exit $?

