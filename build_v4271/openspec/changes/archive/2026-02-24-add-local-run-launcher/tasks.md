# Tasks: 启动器分工约定（run.py --local / local_run.py）

## 1. 一次性修复（后端共用）

- [x] 1.1 修复 rate_limiter 读 .env 的 UnicodeDecodeError：Limiter 的 config_filename 指向 `.env.limiter`（仅 ASCII），避免 Windows GBK 解码问题。

## 2. local_run.py（次选方案）

- [x] 2.1 在项目根新增 `local_run.py`：纯本机启动，不依赖 Docker。
- [x] 2.2 docstring 中明确标注为次选，推荐 `python run.py --local`。

## 3. .env 与 Playwright 配置

- [x] 3.1 `.env` 恢复 `POSTGRES_PORT=15432`、`DATABASE_URL` 指向 Docker Postgres。
- [x] 3.2 设置 `PLAYWRIGHT_HEADLESS=false`、`PLAYWRIGHT_SLOW_MO=100`（有头模式默认开启）。

## 4. 文档

- [x] 4.1 CLAUDE.md 更新启动指南：推荐 `run.py --local`，列出三种模式对比。
- [x] 4.2 proposal.md 更新经验教训，明确推荐混合模式。

## 5. 清理

- [x] 5.1 删除调试过程中产生的临时脚本（fix_alembic_version_local.py、verify_local_db.py、compare_local_vs_docker_pg.py）。
