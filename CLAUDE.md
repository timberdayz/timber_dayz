# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## Project Overview

西虹ERP系统 (XiHong ERP) is a **modern enterprise-grade cross-border e-commerce ERP system** following SAP/Oracle ERP standards. It provides complete data collection, field mapping, product management, financial management, and data dashboards for multi-platform e-commerce operations.

**Current Version**: v4.7.0 (Contract-First Development + Data Collection Refactor)
**Architecture**: Single Source of Truth (SSOT) + Enterprise ERP Standards
**Database**: PostgreSQL 15+ (55 tables, Docker containerized)
**Status**: Production ready

## Common Development Commands

### System Startup
```bash
# Unified startup (recommended)
python run.py

# Backend only
python run.py --backend-only

# Frontend only
python run.py --frontend-only

# CLI menu mode
python run_new.py
```

### Database Operations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

### Architecture Validation
```bash
# CRITICAL: Run after any schema.py changes (expect 100% compliance)
python scripts/verify_architecture_ssot.py

# Check for historical omissions
python scripts/check_historical_omissions.py

# Verify root directory file whitelist
python scripts/verify_root_md_whitelist.py
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend --cov=modules --cov-report=html

# Run specific test file
pytest tests/test_specific.py -v

# Run tests matching pattern
pytest -k "test_pattern"
```

### Code Quality
```bash
# Format code (Black + isort)
black . --line-length 88
isort .

# Lint code
ruff check .

# Type checking
mypy backend/
```

## High-Level Architecture

### Three-Layer Architecture

**Layer 1: Core Infrastructure** (`modules/core/`)
- **Single Source of Truth** for all shared infrastructure
- Database models: `modules/core/db/schema.py` (55 tables, ONLY place to define ORM models)
- Configuration: `modules/core/config.py` (ConfigManager)
- Secrets: `modules/core/secrets_manager.py`
- Logger: `modules/core/logger.py` (get_logger factory)
- Base class: **ONLY** defined in `schema.py`

**Layer 2: Backend API** (`backend/`)
- Unified FastAPI application: `backend/main.py` (ONLY FastAPI entry point)
- API routes: `backend/routers/` (all API endpoints)
- Business services: `backend/services/`
- Backend-specific config: `backend/utils/config.py` (Settings class)

**Layer 3: Frontend** (`frontend/`)
- Vue.js 3 + Composition API + TypeScript
- UI Framework: Element Plus
- State Management: Pinia
- Build Tool: Vite
- API Client: `frontend/src/api/index.js`

### CRITICAL: SSOT Enforcement (Zero Tolerance)

**NEVER do these things:**
1. Define ORM models outside `modules/core/db/schema.py` ❌
2. Create new `Base = declarative_base()` anywhere ❌
3. Create duplicate config/logger classes ❌
4. Create `*_backup.py` or `legacy_*` directories ❌
5. Delete/move files in `docs/DEVELOPMENT_RULES/` ❌
6. Use Pinyin field names (must use English: `sales_amount` not `xiao_shou`) ❌

**Always do this:**
```python
# ✅ CORRECT: Import models from core
from modules.core.db import CatalogFile, FactOrder, Account

# ❌ WRONG: Define models elsewhere
from backend.models.database import CatalogFile  # NEVER!
```

### Contract-First Development (v4.7.0)

**Development order (MANDATORY):**
1. Define ORM models in `modules/core/db/schema.py`
2. Create Alembic migration: `alembic revision --autogenerate`
3. Define Pydantic request/response models (API contract)
4. Define API endpoint signatures with `response_model`
5. Define frontend API service functions
6. Implement business logic last

**Example:**
```python
# 1. ORM Model (schema.py)
class CollectionTask(Base):
    __tablename__ = 'collection_tasks'
    id = Column(Integer, primary_key=True)
    platform = Column(String(50), nullable=False)

# 2. Alembic migration
alembic revision --autogenerate -m "add_collection_tasks"

# 3. Pydantic models (API contract)
class TaskCreate(BaseModel):
    platform: str
    account_id: str

class TaskResponse(BaseModel):
    task_id: str
    status: str

    class Config:
        from_attributes = True  # Support ORM conversion

# 4. API endpoint
@router.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskCreate, db: Session = Depends(get_db)):
    # 5. Implement last
    task = CollectionTask(**request.dict())
    db.add(task)
    db.commit()
    return task
```

### Business Module System (`modules/apps/`)

Pluggable application architecture with zero coupling:

- `collection_center/` - Data collection orchestration
- `vue_field_mapping/` - Field mapping system with AI-driven suggestions
- `data_management_center/` - Data management operations
- `account_manager/` - Platform account management
- `shopee/`, `tiktok/`, `amazon/` - Platform-specific adapters

**Module rules:**
- Apps MUST NOT import from each other (only from `modules.core`)
- Apps MUST provide class-level metadata (NAME, VERSION, DESCRIPTION)
- `__init__` MUST NOT have side effects (no I/O, no DB connections, no browser launches)
- Import-time side effects are FORBIDDEN

### Data Architecture

**Three-tier data classification:**
- **A-tier**: User configuration (campaigns, goals, weights)
- **B-tier**: Business data (orders, products, inventory, traffic - Excel collection + field mapping)
- **C-tier**: Calculated data (completion rates, health scores, rankings - system computed)

**Three-layer data storage:**
- **Raw layer**: Original files (`catalog_files` table)
- **Fact layer**: Fact tables (fact_orders, fact_order_items, etc.)
- **MV layer**: 18 materialized views (OLAP optimized)

**v4.6.0 Dimensional design (zero field explosion):**
- Dimensional tables instead of wide tables (e.g., `fact_order_amounts` with metric_type/metric_subtype/currency dimensions)
- Pattern-based field mapping: ONE regex rule handles infinite combinations
- Global currency support: 180+ currencies with CNY base currency

### PostgreSQL-First Performance Rule

**CRITICAL: Use PostgreSQL indexes, NOT filesystem recursion**

```python
# ❌ WRONG: Filesystem recursion (30,000x slower!)
for file_path in base_dir.rglob(filename):
    if file_path.is_file():
        return str(file_path)

# ✅ CORRECT: PostgreSQL index query (2ms)
catalog_record = db.execute(
    select(CatalogFile).where(CatalogFile.file_name == filename)
).scalar_one_or_none()
return catalog_record.file_path
```

**Performance comparison:**
- File path lookup: 60s → 2ms (30,000x faster)
- File filtering: Requires iteration → SQL WHERE (1,000x faster)

### Field Mapping System (v4.6.0)

**Four-layer mapping architecture:**
1. Raw field names (from Excel)
2. Chinese column layer
3. Standard field names
4. Database column names

**Key features:**
- Pattern-based mapping (one regex for infinite combinations)
- AI-driven suggestions with confidence scores
- 180+ currency support with auto-normalization
- Time field auto-detection and range splitting
- Template system with granularity matching

### Windows Platform Specifics

**Primary development environment: Windows 10/11**

**CRITICAL encoding rules:**
- ❌ **NEVER use Emoji in terminal output** (causes UnicodeEncodeError)
- ✅ Use ASCII symbols: `[OK]`, `[ERROR]`, `*`, `+`, `-`
- ✅ Use `safe_print()` function for all terminal output
- ✅ Markdown docs CAN use Emoji (files only, not code output)

**Path handling:**
```python
# ✅ CORRECT: Use pathlib
from pathlib import Path
backend_path = str(Path(__file__).parent / 'backend')
cmd = f"cd {backend_path}"

# ❌ WRONG: Direct Path concatenation in f-string
cmd = f"cd {Path(__file__).parent / 'backend'}"  # SyntaxError!
```

**Process management:**
- Use `shell=True` for npm commands on Windows
- Graceful shutdown: terminate() → wait 3s → kill()
- Use `taskkill` for cleanup

## Key Files and Their Purposes

### Core Infrastructure
- `modules/core/db/schema.py` - **ONLY place** to define all 55 database tables
- `modules/core/db/__init__.py` - Exports all models (must update when adding tables)
- `modules/core/config.py` - Module configuration management
- `modules/core/logger.py` - Unified logging factory
- `modules/core/secrets_manager.py` - Environment variables and secrets

### Backend API
- `backend/main.py` - Unified FastAPI application entry point
- `backend/routers/` - All API route definitions
- `backend/services/excel_parser.py` - Smart Excel parser (auto-detects xlsx/xls/html)
- `backend/utils/config.py` - Backend-specific Settings
- `backend/models/database.py` - ONLY contains: engine, SessionLocal, get_db, init_db (NO model definitions!)

### Frontend
- `frontend/src/api/index.js` - Unified API client
- `frontend/src/stores/` - Pinia state management
- `frontend/src/views/` - Page components
- `frontend/src/components/` - Reusable components

### Configuration & Docs
- `local_accounts.py` - Platform account configuration (NEVER commit!)
- `.env` - Environment variables (root directory, unified)
- `.cursorrules` - Complete development guidelines (1700+ lines)
- `openspec/project.md` - Project context and conventions
- `docs/DEVELOPMENT_RULES/` - **PROTECTED** detailed development standards

## Important Constraints

### Architecture Compliance
- Run `python scripts/verify_architecture_ssot.py` after ANY schema.py changes
- Expected result: **Compliance Rate: 100.0%**
- Any deviation from SSOT is a critical architecture regression

### Database Design
- All tables MUST have primary key
- Foreign keys MUST be explicitly declared
- Add `created_at`/`updated_at` timestamp fields (audit)
- Use DECIMAL(15,2) for currency amounts
- Use JSONB for structured attributes
- Index design: unique constraints, composite indexes, partial indexes

### API Design
- RESTful design with standard HTTP methods
- Unified response format with success/data/message/error_code
- Pydantic validation for all requests/responses
- OpenAPI 3.0 documentation (auto-generated at `/api/docs`)
- Rate limiting: 100 req/min/user (default)
- Pagination: `page`, `page_size` parameters (max 100)

### Security
- JWT authentication (Access: 15min, Refresh: 7 days)
- RBAC permissions (Admin/Manager/Operator/Viewer)
- OWASP Top 10 protection
- Sensitive data encryption (bcrypt for passwords)
- SQL injection prevention (SQLAlchemy ORM only)
- Complete audit logging

### Code Quality
- Test coverage: Core ≥80%, Auxiliary ≥50%, Critical 100%
- Function complexity ≤10 (cyclomatic)
- Function length ≤50 lines
- Class length ≤500 lines
- All public functions MUST have docstrings (Google style)
- All functions MUST have type annotations

### File Management
- Temporary files → `temp/` subdirectories (development/outputs/media/logs)
- Archived files → `backups/YYYYMMDD_description/`
- NEVER delete files directly, always move to backups
- Protected directory: `docs/DEVELOPMENT_RULES/` (NO auto-cleanup)

## Development Workflow

### Before Starting Any Task
1. Read relevant specs in `specs/[capability]/spec.md`
2. Check pending changes in `changes/` for conflicts
3. Read `openspec/project.md` for conventions
4. Run `openspec list` to see active changes
5. Run `openspec list --specs` to see existing capabilities

### For Planning Major Changes
Use OpenSpec workflow for features, breaking changes, architecture changes:
1. Create change proposal: `openspec/changes/[change-id]/proposal.md`
2. Define spec deltas with ADDED/MODIFIED/REMOVED requirements
3. Create tasks.md checklist
4. Validate: `openspec validate [change-id] --strict`
5. Get approval BEFORE implementing
6. After deployment: `openspec archive [change-id]`

### Module Boundary Rules
- `__init__` must be lightweight (no I/O, no side effects)
- Import-time side effects are FORBIDDEN
- Apps depend on: services → core (NOT other apps)
- Provide health_check() for all apps
- Use class-level metadata (avoid instantiation for discovery)

## Common Pitfalls

1. **Defining models outside schema.py** - This is the #1 cause of metadata inconsistency
2. **Using filesystem recursion instead of DB queries** - 30,000x slower
3. **Forgetting to update `__init__.py` exports** when adding new tables
4. **Missing Alembic migrations** after schema.py changes
5. **Using Emoji in terminal output** on Windows (UnicodeEncodeError)
6. **Creating duplicate functionality** instead of consolidating
7. **Modifying core without checking impact** - affects all apps
8. **Installing dependencies without authorization** - must update requirements.txt only when approved
9. **Deleting files from `docs/DEVELOPMENT_RULES/`** - this directory is protected

## References to Other Documentation

For comprehensive development standards, see:
- `.cursorrules` - Complete 1700-line development guide (master reference)
- `openspec/project.md` - Project conventions and tech stack details
- `openspec/AGENTS.md` - OpenSpec workflow for spec-driven development
- `docs/DEVELOPMENT_RULES/` - Detailed enterprise development standards (protected directory)
- `docs/V4_6_0_ARCHITECTURE_GUIDE.md` - Dimensional table design (v4.6.0)
- `docs/FINAL_ARCHITECTURE_STATUS.md` - 2025-01-30 architecture audit
- `CHANGELOG.md` - Version history and archived file tracking

## Key Technologies

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy 2.0+, Alembic, Celery, Playwright
- **Frontend**: Vue.js 3, Element Plus, Pinia, Vite, ECharts, Axios
- **Database**: PostgreSQL 15+ (Docker), 55 tables, 18 materialized views
- **Data Collection**: Playwright (replaces Selenium for anti-detection)
- **Infrastructure**: Docker, Redis, Nginx

---

**Remember**: When in doubt, check `.cursorrules` for the complete 1700-line development guide. It is the authoritative source for all development standards.
- 永远使用中文回复