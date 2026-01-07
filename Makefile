# ===================================================
# 西虹ERP系统 - Makefile
# ===================================================
# 简化Docker命令，提供便捷的管理接口
# 使用方式: make [command]
# ===================================================

.PHONY: help dev prod stop restart logs clean health build test

# 默认目标
.DEFAULT_GOAL := help

# 颜色输出
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m

# ===================================================
# 帮助信息
# ===================================================
help:  ## 显示帮助信息
	@echo "=========================================="
	@echo "西虹ERP系统 - Makefile命令"
	@echo "=========================================="
	@echo ""
	@echo "开发命令:"
	@echo "  ${GREEN}make dev${NC}        - 启动开发环境（PostgreSQL + pgAdmin）"
	@echo "  ${GREEN}make dev-full${NC}   - 启动完整开发环境（包括前后端）"
	@echo ""
	@echo "生产命令:"
	@echo "  ${GREEN}make prod${NC}       - 启动生产环境（构建并启动全部服务）"
	@echo "  ${GREEN}make build${NC}      - 构建Docker镜像"
	@echo ""
	@echo "管理命令:"
	@echo "  ${GREEN}make stop${NC}       - 停止所有服务"
	@echo "  ${GREEN}make restart${NC}    - 重启所有服务"
	@echo "  ${GREEN}make logs${NC}       - 查看所有服务日志"
	@echo "  ${GREEN}make health${NC}     - 执行健康检查"
	@echo "  ${GREEN}make ps${NC}         - 查看服务状态"
	@echo ""
	@echo "清理命令:"
	@echo "  ${GREEN}make clean${NC}      - 清理容器和网络"
	@echo "  ${GREEN}make clean-all${NC}  - 清理所有（包括数据卷和镜像）"
	@echo ""
	@echo "数据库命令:"
	@echo "  ${GREEN}make db-init${NC}    - 初始化数据库表"
	@echo "  ${GREEN}make db-backup${NC}  - 备份数据库"
	@echo "  ${GREEN}make db-shell${NC}   - 进入数据库shell"
	@echo ""
	@echo "测试命令:"
	@echo "  ${GREEN}make test${NC}       - 运行测试"
	@echo ""
	@echo "=========================================="

# ===================================================
# 开发环境
# ===================================================
dev:  ## 启动开发环境
	@echo "${GREEN}启动开发环境...${NC}"
	@chmod +x docker/scripts/start-dev.sh
	@./docker/scripts/start-dev.sh

dev-full:  ## 启动完整开发环境
	@echo "${GREEN}启动完整开发环境...${NC}"
	@docker-compose --profile dev-full up -d
	@echo "${GREEN}✓ 完整开发环境已启动${NC}"

# ===================================================
# 生产环境
# ===================================================
build:  ## 构建Docker镜像
	@echo "${GREEN}构建Docker镜像...${NC}"
	@docker build -f Dockerfile.backend -t xihong-erp-backend:latest .
	@docker build -f Dockerfile.frontend -t xihong-erp-frontend:latest .
	@echo "${GREEN}✓ 镜像构建完成${NC}"

prod:  ## 启动生产环境
	@echo "${GREEN}启动生产环境...${NC}"
	@chmod +x docker/scripts/start-prod.sh
	@./docker/scripts/start-prod.sh

# ===================================================
# 服务管理
# ===================================================
stop:  ## 停止所有服务
	@echo "${YELLOW}停止所有服务...${NC}"
	@docker-compose down
	@echo "${GREEN}✓ 服务已停止${NC}"

restart:  ## 重启所有服务
	@echo "${YELLOW}重启所有服务...${NC}"
	@docker-compose restart
	@echo "${GREEN}✓ 服务已重启${NC}"

ps:  ## 查看服务状态
	@docker-compose ps

logs:  ## 查看所有服务日志
	@docker-compose logs -f

logs-backend:  ## 查看后端日志
	@docker-compose logs -f backend

logs-frontend:  ## 查看前端日志
	@docker-compose logs -f frontend

logs-postgres:  ## 查看数据库日志
	@docker-compose logs -f postgres

# ===================================================
# 健康检查
# ===================================================
health:  ## 执行健康检查
	@echo "${GREEN}执行健康检查...${NC}"
	@chmod +x docker/scripts/health-check.sh
	@./docker/scripts/health-check.sh

# ===================================================
# 清理
# ===================================================
clean:  ## 清理容器和网络
	@echo "${YELLOW}清理容器和网络...${NC}"
	@docker-compose down
	@echo "${GREEN}✓ 清理完成${NC}"

clean-all:  ## 清理所有（包括数据卷和镜像）
	@echo "${YELLOW}⚠️  警告：这将删除所有数据！${NC}"
	@read -p "确认继续? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@docker-compose down -v
	@docker rmi xihong-erp-backend:latest xihong-erp-frontend:latest 2>/dev/null || true
	@echo "${GREEN}✓ 全部清理完成${NC}"

# ===================================================
# 数据库操作
# ===================================================
db-init:  ## 初始化数据库表
	@echo "${GREEN}初始化数据库表...${NC}"
	@python docker/postgres/init-tables.py
	@echo "${GREEN}✓ 数据库初始化完成${NC}"

db-backup:  ## 备份数据库
	@echo "${GREEN}备份数据库...${NC}"
	@mkdir -p backups
	@docker-compose exec -T postgres pg_dump -U erp_user xihong_erp > backups/postgres_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "${GREEN}✓ 数据库备份完成${NC}"

db-shell:  ## 进入数据库shell
	@docker-compose exec postgres psql -U erp_user -d xihong_erp

db-restore:  ## 恢复数据库
	@echo "${YELLOW}恢复数据库...${NC}"
	@read -p "备份文件路径: " backup_file && \
	 docker-compose exec -T postgres psql -U erp_user -d xihong_erp < $$backup_file
	@echo "${GREEN}✓ 数据库恢复完成${NC}"

# ===================================================
# 容器管理
# ===================================================
shell-backend:  ## 进入后端容器
	@docker-compose exec backend /bin/bash

shell-frontend:  ## 进入前端容器
	@docker-compose exec frontend /bin/sh

shell-postgres:  ## 进入数据库容器
	@docker-compose exec postgres /bin/bash

# ===================================================
# 测试
# ===================================================
test:  ## 运行测试
	@echo "${GREEN}运行测试...${NC}"
	@docker-compose exec backend pytest tests/
	@echo "${GREEN}✓ 测试完成${NC}"

test-coverage:  ## 运行测试并生成覆盖率报告
	@echo "${GREEN}运行测试（带覆盖率）...${NC}"
	@docker-compose exec backend pytest --cov=backend --cov-report=html tests/
	@echo "${GREEN}✓ 测试完成，覆盖率报告：htmlcov/index.html${NC}"

# ===================================================
# 监控
# ===================================================
stats:  ## 查看容器资源使用
	@docker stats --no-stream xihong_erp_postgres xihong_erp_backend xihong_erp_frontend

# ===================================================
# 安装
# ===================================================
install:  ## 安装依赖
	@echo "${GREEN}安装后端依赖...${NC}"
	@pip install -r requirements.txt
	@echo "${GREEN}安装前端依赖...${NC}"
	@cd frontend && npm install
	@echo "${GREEN}✓ 依赖安装完成${NC}"
