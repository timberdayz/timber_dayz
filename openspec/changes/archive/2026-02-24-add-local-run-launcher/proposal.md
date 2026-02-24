# Change: 启动器分工约定（run.py --local / local_run.py）

**状态**：已实施（含经验修正）。明确三种启动模式的职责与适用场景。

## Why

1. **核心需求：有头浏览器调试采集脚本**。开发者需要在桌面上看到 Playwright 浏览器窗口，以调试、优化数据采集流程。
2. **全 Docker（`run.py --use-docker`）无法满足**：后端在容器内运行时，Playwright 启动的浏览器在容器内部，桌面看不到。
3. **纯本机（`local_run.py`）过于复杂**：需要在本机安装、配置并同步 PostgreSQL 数据库，维护成本高，且容易因 schema 不一致、Alembic 版本不匹配等问题导致启动失败。
4. **混合模式（`run.py --local`）是最佳平衡**：Docker 负责基础设施（Postgres/Redis/Celery），本机只运行后端和前端——既能看到浏览器窗口，又无需配置本机数据库。

## What Changes

### 三种启动模式

| 模式 | 命令 | 适用场景 | Playwright 可见 | 需本机 DB |
|------|------|----------|----------------|-----------|
| **混合模式（推荐）** | `python run.py --local` | 调试采集脚本、日常开发 | 是 | 否（Docker） |
| **全 Docker** | `python run.py --use-docker` | CI/CD、生产环境模拟 | 否 | 否（Docker） |
| **纯本机** | `python local_run.py` | 离线开发、无 Docker 场景 | 是 | 是（需配置） |

### 推荐工作流：`python run.py --local`

1. 启动 Docker Desktop
2. 运行 `python run.py --local`
3. 自动完成：Docker 起 Postgres(15432)/Redis/Celery → 本机起后端(8001) + 前端(5173)
4. 在前端页面发起采集任务 → 桌面出现 Playwright 浏览器窗口

### .env 配置要点

- `DATABASE_URL` 保持 `localhost:15432`（Docker Postgres 映射端口）
- `PLAYWRIGHT_HEADLESS=false`（有头模式）
- `PLAYWRIGHT_SLOW_MO=100`（便于观察）
- 切换到全 Docker 模式（`--use-docker`）时无需改 .env，容器内有自己的环境变量

### 修改边界

- **run.py**：负责 Docker 编排与多模式（--use-docker / --local / --collection），不为纯本机场景增加复杂分支。
- **local_run.py**：仅负责纯本机启动（加载 .env + uvicorn + npm），不碰 Docker。文档中已标注为次选方案。
- **rate_limiter.py**：已修复 Windows GBK 编码问题（使用独立 `.env.limiter` 文件）。

## 经验教训

1. **纯本机数据库同步成本极高**：即使用 `pg_dump`/`pg_restore` 从 Docker 全量导入，仍可能因 Alembic 版本链、多 schema 结构差异导致后端启动失败。
2. **`run.py --local` 天然避免这些问题**：后端直连 Docker 内的 Postgres（15432），数据库状态与全 Docker 模式完全一致。
3. **有头浏览器的关键不是"本机数据库"，而是"本机后端进程"**：只要 uvicorn 在本机进程中运行，Playwright 就能弹出桌面浏览器。

## Impact

- **run.py**：已有 `--local` 参数，无需额外修改。
- **local_run.py**：保留但降级为次选方案，docstring 已更新。
- **.env**：`POSTGRES_PORT=15432`，`PLAYWRIGHT_HEADLESS=false`，默认即适用于混合模式。
- **CLAUDE.md**：已更新启动指南，推荐 `run.py --local`。

## 验收

- [x] `python run.py --local` 可启动 Docker Postgres/Redis/Celery + 本机后端/前端
- [x] `.env` 中 `PLAYWRIGHT_HEADLESS=false`，采集时浏览器出现在桌面
- [x] 文档（CLAUDE.md）清楚标注三种模式的选择指南
- [x] `local_run.py` 保留但标注为次选，docstring 含推荐提示
- [x] `rate_limiter.py` 编码问题已修复（`.env.limiter`）
