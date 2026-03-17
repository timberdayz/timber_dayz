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

> 架构与零容忍规则的**权威描述**请以 `.cursorrules` 为准，这里只做一屏内的快速提示。

| 层 | 位置 | 职责 |
|---|---|---|
| Core | `modules/core/` | 统一 ORM / 配置 / 日志 / 密钥（SSOT） |
| Backend | `backend/` | FastAPI API、Pydantic Schemas、业务服务 |
| Frontend | `frontend/` | Vue 3 + Element Plus + Pinia + Vite |

常用入口文件（详情和完整清单见 `.cursorrules`）：

| 文件/目录 | 用途 |
|---|---|
| `modules/core/db/schema.py` | 唯一 ORM 定义 |
| `backend/main.py` | FastAPI 入口 |
| `backend/schemas/` | Pydantic 契约模型 |
| `backend/routers/` | API 路由 |
| `backend/services/` | 业务逻辑 |
| `frontend/src/api/index.js` | 统一 API 客户端 |

## Common Pitfalls（摘要版）

> 完整零容忍清单见 `.cursorrules`，这里只列 Agent 最容易踩的坑。

1. 在 `schema.py` 之外定义 ORM 模型
2. 递归扫描文件系统代替使用 `catalog_files` 表
3. 新增表后忘记维护 Alembic 迁移和 `modules/core/db/__init__.py`
4. 终端/日志中输出 Emoji（Windows 会触发 UnicodeEncodeError）
5. 编写采集组件未遵守 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
6. Node 版本低于 24（项目与 CI 都要求 24+）

## User-Level Skills（用户级 Skill）

以下 Skill 安装在用户目录 `~/.cursor/skills/`，对本机所有项目生效；与本项目规则**叠加使用，不替代**。

> **冲突解决规则**：`.cursorrules` > OpenSpec > Superpowers > 其他 Skill。详细映射见 `.cursor/rules/skill-integration.mdc`。

### 核心 Skill（日常开发高频使用）

| Skill | 来源 | 本项目用法 |
|-------|------|-----------|
| **superpowers** | [obra/superpowers](https://github.com/obra/superpowers) | 工作方法论：brainstorming（需求澄清）、writing-plans（实施计划）、TDD（测试驱动）、systematic-debugging（根因定位）、code-review（审查）等 14 个子 skill |
| **planning-with-files** | [OthmanAdi/planning-with-files](https://github.com/OthmanAdi/planning-with-files) | 复杂单人任务（非 OpenSpec 级别）时用 task_plan.md / findings.md / progress.md 做持久化规划 |
| **frontend-design** | [anthropics/skills](https://github.com/anthropics/skills) | 前端审美方向（排版、色彩、动效、空间构图）；本项目实现用 **Vue 3 + Element Plus** |
| **webapp-testing** | [anthropics/skills](https://github.com/anthropics/skills) | Playwright 测本地 Web 应用；独立脚本可用 `sync_playwright`，FastAPI 内必须 `async_playwright` |
| **ui-ux-pro-max** | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 设计体系生成器：色板/字体/UX 准则/图表推荐；本项目技术栈为 Vue 3（忽略 React Native 相关建议） |

### 按需 Skill（anthropics 全集附带，特定场景使用）

| Skill | 场景 |
|-------|------|
| theme-factory / canvas-design | 主题生成、画布设计 |
| docx / pdf / pptx / xlsx | 文档/报表生成 |
| mcp-builder / skill-creator | 构建 MCP 服务器、创建新 Skill |
| 其余（algorithmic-art、brand-guidelines 等） | 按需查阅 |

### 更新方式

```bash
cd ~/.cursor/skills/superpowers && git pull                    # superpowers
git clone --depth 1 https://github.com/anthropics/skills /tmp/s && cp -r /tmp/s/skills/* ~/.cursor/skills/  # anthropics
```

## Documentation Map (三层规则体系)

| 层级 | 文件 | 用途 |
|---|---|---|
| L1 快速入口 | `CLAUDE.md`（本文件） | 命令速查 + 架构概览 + 文档导航 |
| L2 开发规范 | `.cursorrules` | 零容忍规则 + 架构约束（权威来源） |
| L3 详细参考 | `docs/DEVELOPMENT_RULES/` | 按主题的深度参考 + 代码模板 |

**L3 核心文件:**

| 文件 | 内容 |
|---|---|
| `CODE_PATTERNS.md` | 代码模板（Service/Router/Schema/conftest/事务/缓存） |
| `API_AND_CONTRACTS.md` | API设计、代码审查、HTTP状态码迁移策略 |
| `DATABASE.md` | 数据库设计、迁移、SQL编写规范 |
| `TESTING_AND_QUALITY.md` | 测试策略、覆盖率、代码质量 |
| `ERROR_AND_LOGGING.md` | 错误处理、日志规范 |
| `SECURITY_AND_DEPLOYMENT.md` | 安全、部署、CI/CD、监控 |
| `UI_DESIGN.md` | UI设计、局部loading、后台刷新 |

**其他文档:**

| 文档 | 内容 |
|---|---|
| `openspec/AGENTS.md` | OpenSpec 工作流（提案 -> 审核 -> 执行 -> 归档） |
| `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` | 采集脚本编写完整规范 |
| `docs/architecture/V4_6_0_ARCHITECTURE_GUIDE.md` | 维度表设计 |
| `CHANGELOG.md` | 版本历史 |

---

**Remember**: `.cursorrules` 是本项目的权威开发规范。遇到不确定的情况，优先查阅 `.cursorrules`。
- 永远使用中文回复
