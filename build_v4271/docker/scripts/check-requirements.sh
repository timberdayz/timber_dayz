#!/bin/bash
# ===================================================
# 西虹ERP系统 - 环境检查脚本
# ===================================================
# 功能：检查Docker部署所需的环境和依赖
# 使用方式：./docker/scripts/check-requirements.sh
# ===================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 检查计数
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
    echo -n "检查 $1 ... "
}

print_ok() {
    passed_checks=$((passed_checks + 1))
    echo -e "${GREEN}✓ OK${NC}"
}

print_fail() {
    failed_checks=$((failed_checks + 1))
    echo -e "${RED}✗ FAIL${NC}"
    if [ -n "$1" ]; then
        echo -e "  ${RED}$1${NC}"
    fi
}

print_warning() {
    echo -e "${YELLOW}⚠ WARNING: $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ INFO: $1${NC}"
}

# 主标题
clear
print_header "西虹ERP系统 - Docker环境检查"
echo "检查时间: $(date '+%Y-%m-%d %H:%M:%S')"

# 1. 检查操作系统
print_header "操作系统检查"

print_check "操作系统"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo -e "${GREEN}✓ OK${NC} - Linux"
    passed_checks=$((passed_checks + 1))
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${GREEN}✓ OK${NC} - macOS"
    passed_checks=$((passed_checks + 1))
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
    echo -e "${GREEN}✓ OK${NC} - Windows (Git Bash)"
    passed_checks=$((passed_checks + 1))
else
    print_fail "未知操作系统: $OSTYPE"
fi

# 2. 检查Docker
print_header "Docker环境检查"

print_check "Docker是否安装"
if command -v docker &> /dev/null; then
    version=$(docker --version)
    echo -e "${GREEN}✓ OK${NC} - $version"
    passed_checks=$((passed_checks + 1))
else
    print_fail "Docker未安装"
    print_info "请访问 https://www.docker.com/get-started 安装Docker"
fi

print_check "Docker是否运行"
if docker info &> /dev/null; then
    print_ok
else
    print_fail "Docker未运行"
    print_info "请启动Docker服务"
fi

print_check "Docker Compose是否安装"
if command -v docker-compose &> /dev/null; then
    version=$(docker-compose --version)
    echo -e "${GREEN}✓ OK${NC} - $version"
    passed_checks=$((passed_checks + 1))
else
    print_fail "Docker Compose未安装"
fi

# 3. 检查系统资源
print_header "系统资源检查"

print_check "可用磁盘空间"
if command -v df &> /dev/null; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        space=$(df -h . | awk 'NR==2 {print $4}')
    else
        space=$(df -h . | awk 'NR==2 {print $4}')
    fi
    echo -e "${GREEN}✓ OK${NC} - 可用空间: $space"
    passed_checks=$((passed_checks + 1))
else
    print_warning "无法检查磁盘空间"
fi

print_check "可用内存"
if command -v free &> /dev/null; then
    mem=$(free -h | awk 'NR==2 {print $7}')
    echo -e "${GREEN}✓ OK${NC} - 可用内存: $mem"
    passed_checks=$((passed_checks + 1))
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${GREEN}✓ OK${NC} - macOS (跳过内存检查)"
    passed_checks=$((passed_checks + 1))
else
    print_warning "无法检查可用内存"
fi

# 4. 检查端口占用
print_header "端口占用检查"

check_port() {
    port=$1
    name=$2
    
    print_check "端口 $port ($name)"
    
    if command -v lsof &> /dev/null; then
        if lsof -i:$port &> /dev/null; then
            print_fail "端口已被占用"
            lsof -i:$port | tail -1
        else
            print_ok
        fi
    elif command -v netstat &> /dev/null; then
        if netstat -an | grep ":$port " | grep LISTEN &> /dev/null; then
            print_fail "端口已被占用"
        else
            print_ok
        fi
    else
        print_warning "无法检查端口占用"
    fi
}

check_port 5432 "PostgreSQL"
check_port 8001 "Backend API"
check_port 5174 "Frontend"
check_port 5051 "pgAdmin"

# 5. 检查项目文件
print_header "项目文件检查"

print_check "docker-compose.yml"
if [ -f "docker-compose.yml" ]; then
    print_ok
else
    print_fail "文件不存在"
fi

print_check "Dockerfile.backend"
if [ -f "Dockerfile.backend" ]; then
    print_ok
else
    print_fail "文件不存在"
fi

print_check "Dockerfile.frontend"
if [ -f "Dockerfile.frontend" ]; then
    print_ok
else
    print_fail "文件不存在"
fi

print_check "环境变量示例文件"
if [ -f "env.example" ]; then
    print_ok
else
    print_fail "文件不存在"
fi

# 6. 检查Docker配置语法
print_header "Docker配置语法检查"

print_check "docker-compose.yml语法"
if docker-compose config &> /dev/null; then
    print_ok
else
    print_fail "配置文件语法错误"
    docker-compose config 2>&1 | head -5
fi

# 7. 检查Python环境
print_header "Python环境检查"

print_check "Python是否安装"
if command -v python3 &> /dev/null; then
    version=$(python3 --version)
    echo -e "${GREEN}✓ OK${NC} - $version"
    passed_checks=$((passed_checks + 1))
else
    print_warning "Python未安装（如需本地开发则需要）"
fi

print_check "pip是否安装"
if command -v pip3 &> /dev/null || command -v pip &> /dev/null; then
    print_ok
else
    print_warning "pip未安装（如需本地开发则需要）"
fi

# 8. 检查Node.js环境
print_header "Node.js环境检查"

print_check "Node.js是否安装"
if command -v node &> /dev/null; then
    version=$(node --version)
    echo -e "${GREEN}✓ OK${NC} - $version"
    passed_checks=$((passed_checks + 1))
else
    print_warning "Node.js未安装（如需本地前端开发则需要）"
fi

print_check "npm是否安装"
if command -v npm &> /dev/null; then
    version=$(npm --version)
    echo -e "${GREEN}✓ OK${NC} - v$version"
    passed_checks=$((passed_checks + 1))
else
    print_warning "npm未安装（如需本地前端开发则需要）"
fi

# 生成检查报告
print_header "检查报告"

echo "总检查项: $total_checks"
echo -e "${GREEN}通过: $passed_checks${NC}"
echo -e "${RED}失败: $failed_checks${NC}"
echo ""

if [ $failed_checks -eq 0 ]; then
    echo -e "${GREEN}✅ 所有关键检查通过，可以开始Docker部署！${NC}"
    echo ""
    echo "下一步："
    echo "  1. 配置环境变量: cp env.example .env"
    echo "  2. 启动开发环境: ./docker/scripts/start-dev.sh"
    echo "  3. 或启动生产环境: ./docker/scripts/start-prod.sh"
    echo ""
    exit 0
else
    echo -e "${RED}❌ 有 $failed_checks 项检查失败${NC}"
    echo ""
    echo "请解决上述问题后再次运行此脚本"
    echo ""
    exit 1
fi

