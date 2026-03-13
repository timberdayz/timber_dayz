# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

西虹ERP系统 (XiHong ERP) — 现代企业级跨境电商ERP系统，遵循 SAP/Oracle ERP 标准。

- **当前版本**: v4.20.0
- **架构**: SSOT + Contract-First + 三层架构
- **数据库**: PostgreSQL 15+（55 张表，Docker 容器化）
- **Node.js**: 24+（项目与 GitHub 要求，见根目录 `.nvmrc`；禁止使用 18）
- **状态**: 生产就绪

> **权威开发规则**: `.cursorrules`（完整开发规范，所有 Agent 必读）

## Common Development Commands

### System Startup

**启动方式选择指南**

- **调试/优化采集脚本（有头浏览器，推荐）**：Docker 起 DB/Redis/Celery，本机起后端+前端——浏览器窗口出现在桌面上：
  ```bash
  python run.py --local
  ```
  前提：Docker Desktop 已启动。DB/Redis 全在 Docker 里，无需配本机数据库。`run.py --local` 会强制 `ENVIRONMENT=development`，本地采集默认有头；有头模式需本机已执行 `playwright install`（或 `playwright install chromium`），勿仅安装 `--only-shell`。

- **全 Docker 模式（后端也在容器，看不到浏览器）**：
  ```bash
  python run.py --use-docker --with-metabase
  ```
  可选 `--collection`（backend 使用带 Playwright 的镜像）。

- **纯本机模式（已配好本机 Postgres 时可用）**：
  ```bash
  python local_run.py
  ```
  需本机 Postgres 已就绪（可用 `python scripts/check_local_run_env.py` 检查）。

- **run.py 其他用法**：
  ```bash
  python run.py                    # 传统模式（需先启 Postgres/Redis）
  python run.py --backend-only     # 仅后端
  python run.py --frontend-only    # 仅前端
  python run_new.py                # CLI 菜单模式
  ```

### Database Operations
```bash
alembic revision --autogenerate -m "description"   # 创建迁移
alembic upgrade head                                # 应用迁移
alembic downgrade -1                                # 回滚一版
```

### Architecture Validation
```bash
python scripts/verify_architecture_ssot.py    # schema.py 变更后必须运行（期望 100%）
python scripts/check_historical_omissions.py  # 检查历史遗漏
python scripts/verify_root_md_whitelist.py    # 根目录文件白名单
```

### OpenSpec CLI（规格与变更）
项目通过 `package.json` 安装 `@fission-ai/openspec`，使用 `npx openspec` 或 `npm run openspec` 调用：
```bash
npx openspec list              # 列出进行中的变更
npx openspec list --specs      # 列出规格
npx openspec validate --strict # 严格验证
npx openspec update            # 更新指令文件到最新
# 或: npm run os:list / npm run os:update / npm run os:validate
```

### Testing & Code Quality
```bash
pytest                                              # 运行全部测试
pytest --cov=backend --cov=modules --cov-report=html # 覆盖率报告
black . --line-length 88 && isort .                 # 格式化
ruff check .                                        # Lint
mypy backend/                                       # 类型检查
```

## High-Level Architecture (Quick Reference)

| 层 | 位置 | 职责 |
|---|---|---|
| Core | `modules/core/` | SSOT：ORM 模型（`schema.py`）、配置、日志、密钥 |
| Backend | `backend/` | FastAPI API、Pydantic Schemas、业务服务 |
| Frontend | `frontend/` | Vue 3 + Element Plus + Pinia + Vite |

**SSOT 零容忍规则**（详见 `.cursorrules`）：
- ORM 模型只能定义在 `modules/core/db/schema.py`
- 禁止在 core 之外创建 `Base = declarative_base()`
- 禁止 Pinyin 字段名

## Key Files

| 文件/目录 | 用途 |
|---|---|
| `modules/core/db/schema.py` | 唯一 ORM 定义（55 张表） |
| `modules/core/db/__init__.py` | 模型导出（新增表时必须更新） |
| `backend/main.py` | FastAPI 唯一入口 |
| `backend/schemas/` | Pydantic 契约模型 |
| `backend/routers/` | API 路由 |
| `backend/services/` | 业务逻辑 |
| `backend/models/database.py` | 只含 engine/SessionLocal/get_db/init_db |
| `frontend/src/api/index.js` | 统一 API 客户端 |

## Common Pitfalls

1. **在 schema.py 之外定义模型** → 元数据不一致
2. **文件系统递归代替 DB 查询** → 慢 30,000 倍
3. **新增表忘记更新 `__init__.py` 导出**
4. **schema.py 变更后遗漏 Alembic 迁移**
5. **终端输出使用 Emoji**（Windows UnicodeEncodeError）
6. **修改采集组件不遵循规范** → 必读 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
7. **Node 版本使用 18 或低于 24** → 项目与 GitHub 要求 Node 24+，见 `.nvmrc` 与 `frontend/package.json` engines

## Documentation Map

| 文档 | 内容 |
|---|---|
| `.cursorrules` | **完整开发规范**（架构规则、Contract-First、API、采集、SQL、安全、测试等） |
| `openspec/AGENTS.md` | OpenSpec 工作流（提案 → 审核 → 执行 → 归档） |
| `openspec/project.md` | 项目上下文与约定 |
| `docs/DEVELOPMENT_RULES/` | 企业级详细规范（受保护目录） |
| `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` | 采集脚本编写规范 |
| `docs/architecture/V4_6_0_ARCHITECTURE_GUIDE.md` | 维度表设计 |
| `CHANGELOG.md` | 版本历史 |

---

**Remember**: `.cursorrules` 是本项目的权威开发规范。遇到不确定的情况，优先查阅 `.cursorrules`。
- 永远使用中文回复
