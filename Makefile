# ===================================================
# Xihong ERP - Makefile (ASCII-only output)
# ===================================================

.PHONY: help dev dev-full prod stop restart logs clean clean-all health build \
	test test-full test-coverage test-smoke test-standard test-e2e test-backend-contract \
	lint typecheck ps stats db-init db-backup db-shell db-restore shell-backend shell-frontend shell-postgres install

.DEFAULT_GOAL := help

BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m

help:
	@echo "=========================================="
	@echo "Xihong ERP - Makefile"
	@echo "=========================================="
	@echo ""
	@echo "Dev:"
	@echo "  make dev              - start dev db (postgres + pgadmin)"
	@echo "  make dev-full         - start full dev stack"
	@echo ""
	@echo "Prod:"
	@echo "  make prod             - start prod stack"
	@echo "  make build            - build docker images"
	@echo ""
	@echo "Ops:"
	@echo "  make stop             - stop services"
	@echo "  make restart          - restart services"
	@echo "  make ps               - docker-compose ps"
	@echo "  make logs             - follow logs"
	@echo ""
	@echo "DB:"
	@echo "  make db-init          - init tables"
	@echo "  make db-backup        - dump database"
	@echo "  make db-restore       - restore from dump file"
	@echo ""
	@echo "Tests:"
	@echo "  make test             - smoke tests (default)"
	@echo "  make test-standard    - standard tests"
	@echo "  make test-e2e         - e2e tests"
	@echo "  make test-backend-contract - backend contract tests"
	@echo ""
	@echo "Quality:"
	@echo "  make lint             - ruff gate"
	@echo "  make typecheck        - mypy gate (subset)"

# ===================================================
# Dev / Prod
# ===================================================
dev:
	@echo "${GREEN}Starting dev environment...${NC}"
	@chmod +x docker/scripts/start-dev.sh
	@./docker/scripts/start-dev.sh

dev-full:
	@echo "${GREEN}Starting dev-full environment...${NC}"
	@docker-compose --profile dev-full up -d
	@echo "${GREEN}[OK] dev-full started${NC}"

build:
	@echo "${GREEN}Building docker images...${NC}"
	@docker build -f Dockerfile.backend -t xihong-erp-backend:latest .
	@docker build -f Dockerfile.frontend -t xihong-erp-frontend:latest .
	@echo "${GREEN}[OK] images built${NC}"

prod:
	@echo "${GREEN}Starting production...${NC}"
	@chmod +x docker/scripts/start-prod.sh
	@./docker/scripts/start-prod.sh

# ===================================================
# Service ops
# ===================================================
stop:
	@echo "${YELLOW}Stopping services...${NC}"
	@docker-compose down
	@echo "${GREEN}[OK] services stopped${NC}"

restart:
	@echo "${YELLOW}Restarting services...${NC}"
	@docker-compose restart
	@echo "${GREEN}[OK] services restarted${NC}"

ps:
	@docker-compose ps

logs:
	@docker-compose logs -f

logs-backend:
	@docker-compose logs -f backend

logs-frontend:
	@docker-compose logs -f frontend

logs-postgres:
	@docker-compose logs -f postgres

health:
	@echo "${GREEN}Running health-check...${NC}"
	@chmod +x docker/scripts/health-check.sh
	@./docker/scripts/health-check.sh

# ===================================================
# Clean
# ===================================================
clean:
	@echo "${YELLOW}Cleaning containers/network...${NC}"
	@docker-compose down
	@echo "${GREEN}[OK] cleaned${NC}"

clean-all:
	@echo "${YELLOW}[WARN] this will delete all data${NC}"
	@read -p "confirm? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@docker-compose down -v
	@docker rmi xihong-erp-backend:latest xihong-erp-frontend:latest 2>/dev/null || true
	@echo "${GREEN}[OK] clean-all completed${NC}"

# ===================================================
# Database
# ===================================================
db-init:
	@echo "${GREEN}Init database tables...${NC}"
	@python docker/postgres/init-tables.py
	@echo "${GREEN}[OK] db init completed${NC}"

db-backup:
	@echo "${GREEN}Backup database...${NC}"
	@mkdir -p backups
	@docker-compose exec -T postgres pg_dump -U erp_user xihong_erp > backups/postgres_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "${GREEN}[OK] db backup completed${NC}"

db-shell:
	@docker-compose exec postgres psql -U erp_user -d xihong_erp

db-restore:
	@echo "${YELLOW}Restore database...${NC}"
	@read -p "dump file path: " backup_file && \
	 docker-compose exec -T postgres psql -U erp_user -d xihong_erp < $$backup_file
	@echo "${GREEN}[OK] db restore completed${NC}"

# ===================================================
# Shell
# ===================================================
shell-backend:
	@docker-compose exec backend /bin/bash

shell-frontend:
	@docker-compose exec frontend /bin/sh

shell-postgres:
	@docker-compose exec postgres /bin/bash

# ===================================================
# Tests
# ===================================================
test:
	@echo "${GREEN}Running smoke tests...${NC}"
	@python scripts/run_smoke_tests.py
	@echo "${GREEN}[OK] smoke tests passed${NC}"

test-full:
	@echo "${GREEN}Running full tests in container...${NC}"
	@docker-compose exec backend pytest
	@echo "${GREEN}[OK] full tests completed${NC}"

test-coverage:
	@echo "${GREEN}Running coverage in container...${NC}"
	@docker-compose exec backend pytest --cov=backend --cov-report=html tests/
	@echo "${GREEN}[OK] coverage report: htmlcov/index.html${NC}"

test-smoke:
	@echo "${GREEN}Running smoke tests...${NC}"
	@python scripts/run_smoke_tests.py
	@echo "${GREEN}[OK] smoke tests passed${NC}"

test-standard:
	@echo "${GREEN}Running standard tests...${NC}"
	@python scripts/run_standard_tests.py
	@echo "${GREEN}[OK] standard tests passed${NC}"

test-e2e:
	@echo "${GREEN}Running e2e tests...${NC}"
	@python scripts/run_e2e_tests.py
	@echo "${GREEN}[OK] e2e tests passed${NC}"

test-backend-contract:
	@echo "${GREEN}Running backend contract tests...${NC}"
	@python -m pytest -q backend/tests -m "not slow and not requires_browser" --ignore=backend/tests/data_pipeline --ignore=backend/tests/archive
	@echo "${GREEN}[OK] backend contract tests passed${NC}"

# ===================================================
# Quality
# ===================================================
lint:
	@echo "${GREEN}Running lint gate...${NC}"
	@python scripts/run_lint.py
	@echo "${GREEN}[OK] lint completed${NC}"

typecheck:
	@echo "${GREEN}Running typecheck gate...${NC}"
	@python scripts/run_typecheck.py

# ===================================================
# Misc
# ===================================================
stats:
	@docker stats --no-stream xihong_erp_postgres xihong_erp_backend xihong_erp_frontend

install:
	@echo "${GREEN}Installing backend deps...${NC}"
	@pip install -r requirements.txt
	@echo "${GREEN}Installing frontend deps...${NC}"
	@cd frontend && npm install
	@echo "${GREEN}[OK] dependencies installed${NC}"

