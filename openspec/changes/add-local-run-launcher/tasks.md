# Tasks: 双启动器约定（run.py 与 local_run.py）

## 1. 一次性修复（后端共用）

- [ ] 1.1 修复 rate_limiter 读 .env 的 UnicodeDecodeError：使 Limiter 的 config_filename 指向仅 ASCII 的配置文件（如 `.env.limiter`）或不存在路径，避免 starlette 在 Windows 下用 gbk 解码 UTF-8 的 .env；若新建 `.env.limiter`，内容仅保留 `RATE_LIMIT_ENABLED=true` 等英文即可，该文件可提交至版本库供所有人共用。

## 2. 新增 local_run.py

- [ ] 2.1 在项目根新增 `local_run.py`：用 UTF-8 加载 `.env`，启动本机后端（uvicorn）、本机前端（npm run dev），可选启动本机 Celery（Redis 可用时）；不启动 Docker、不解析 --use-docker/--collection、不启动 Metabase。
- [ ] 2.2 逻辑尽量少：可检查 Postgres/Redis 并提示，Redis 不可用时询问是否跳过 Celery；不复制 run.py 的 Docker 与多模式逻辑。

## 3. 文档

- [ ] 3.1 在 CLAUDE.md 或 README 的启动方式中补充：本地开发/优化采集脚本用 `python local_run.py`；采集/生产环境测试用 `python run.py --use-docker --with-metabase`（可选 `--collection`）。
- [ ] 3.2 注明修改边界：run.py 专注 Docker 与多模式；local_run.py 仅本机、不碰 Docker；避免误改、误用。

## 4. 验收

- [ ] 4.1 执行 `python local_run.py` 可启动本机后端与前端（在 Postgres/Redis 已就绪或跳过 Celery 的前提下）。
- [ ] 4.2 文档与本变更目录（proposal.md）可供查阅，明确两个启动器的区别与使用方法。
