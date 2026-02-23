# Change: 双启动器约定（run.py 与 local_run.py）

**状态**：提案。用于明确两个启动器的职责、使用场景与修改边界，避免误改、误用。

## Why

1. **职责混在一起导致反复改 run.py**：此前为同时支持「Docker 一键本地」「本机 Celery / Docker Celery」「uvicorn/编码/端口」等，对 `run.py` 做了大量修改，容易引入回归，且与「采集脚本有头运行」的核心需求（本机、非容器）纠缠在一起。
2. **需要稳定的本机入口**：本地优化采集脚本时，只需「本机起后端 + 前端（+ 可选 Celery）」、不依赖 Docker、逻辑简单即可；与「采集环境 / 生产环境用 Docker 测试」应分开入口，避免为本地 quirks 持续改 run.py。
3. **避免误用**：若没有成文约定，后续可能误在 run.py 上为「仅本机」加逻辑，或在 local_run.py 上为「Docker/生产」加逻辑，导致两个文件职责混乱。

因此本变更为**约定与文档类**：确立 **run.py** 与 **local_run.py** 的边界、使用场景与修改原则，并落地 local_run.py 与必要的最小修复（如 rate_limiter 读 .env 编码），使本地开发与 Docker/生产测试各用其道。

## What Changes

### 1. 两个启动器的定义与职责

| 启动器 | 主要用途 | 典型命令 | 依赖 |
|--------|----------|----------|------|
| **run.py** | 采集环境 / 生产环境 / 带 Docker 的完整编排 | `python run.py --use-docker --with-metabase`<br>`python run.py --use-docker --with-metabase --collection` | Docker、docker-compose、可选 Metabase |
| **local_run.py** | 本机开发、优化采集脚本（有头浏览器）、不依赖 Docker | `python local_run.py` | 本机已安装并启动的 Postgres、Redis（或选择跳过 Celery） |

- **run.py**：负责 Docker Compose 编排、多模式（--use-docker、--local、--collection）、Metabase、健康检查与等待等；**不应**为「仅本机、无 Docker」的 quirks（如 Windows 编码、uvicorn 子进程兼容）增加复杂分支，这些应放在 local_run.py 或后端/中间件一次性修复。
- **local_run.py**：仅负责「加载 .env（UTF-8）、启动本机后端、启动本机前端、可选启动本机 Celery」；**不**包含 Docker、不包含 --use-docker / --collection、不包含 Metabase 启动；逻辑尽量少，便于稳定用于本地采集脚本开发。

### 2. 使用场景对照

| 场景 | 使用 | 说明 |
|------|------|------|
| 本地优化采集脚本（有头浏览器） | **local_run.py** | 本机 Postgres/Redis 已就绪（或跳过 Celery）；只起后端 + 前端，专注改采集逻辑。 |
| 采集环境 / 生产环境测试（Docker） | **run.py --use-docker --with-metabase** | 完整 Docker 编排；可选 `--collection` 使用带 Playwright 的后端镜像。 |
| 仅想用 Docker 起库 + 本机起服务 | **run.py --local** | 保留以兼容已有用法；新用户或纯本机开发优先推荐 **local_run.py**，以保持 run.py 简洁。 |

### 3. 修改边界（避免误改、误用）

- **run.py**
  - **可以**：Docker 相关逻辑、compose 文件组合、--use-docker / --collection / --with-metabase、健康检查与等待、前端/后端/Celery 在 Docker 下的启动方式。
  - **避免**：为「仅本机、无 Docker」单独增加大量分支（如本机编码、本机 uvicorn 兼容）；若需修复，优先在**后端或中间件**一次性修（如 rate_limiter 读 .env 用 UTF-8 或独立配置文件），或把「纯本机」入口收敛到 local_run.py。
- **local_run.py**
  - **可以**：加载 .env（显式 UTF-8）、启动本机 uvicorn、启动本机前端、可选启动本机 Celery、简单提示（如 Postgres/Redis 未就绪时提示）。
  - **禁止**：启动 Docker、解析 --use-docker / --collection、启动 Metabase；不复制 run.py 的复杂编排逻辑。

### 4. 文档与可见性

- 在 **CLAUDE.md** 或 **README** 的「启动方式」中增加简短说明：
  - 本地开发 / 优化采集脚本：`python local_run.py`（需本机 Postgres/Redis 或选择跳过 Celery）。
  - 采集环境 / 生产环境测试：`python run.py --use-docker --with-metabase`（可选 `--collection`）。
- 本提案置于 `openspec/changes/add-local-run-launcher/`，供后续查阅与验收，避免误改、误用两个启动器。

## Impact

- **Affected specs**：无。本变更为约定与文档类，不涉及产品规格能力变更。
- **run.py**：保持为 Docker 与多模式入口；不要求因本变更而删除已有 --local 等逻辑，但新增「仅本机」逻辑时应谨慎，优先放到 local_run.py 或后端。
- **local_run.py**：新增文件，实现最小本机启动（.env 加载、后端、前端、可选 Celery）。
- **backend/middleware/rate_limiter.py**：若存在「starlette 读 .env 用系统编码导致 UnicodeDecodeError」的问题，应一次性修复（如 config_filename 指向仅 ASCII 的配置文件），使 run.py 与 local_run.py 共用后端时均不受影响。
- **文档**：CLAUDE.md 或 README 中补充双启动器说明。

## 验收

- [ ] 存在 `local_run.py`，可仅用其启动本机后端与前端（Postgres/Redis 已就绪或跳过 Celery）。
- [ ] 文档中明确写清「何时用 run.py、何时用 local_run.py」及修改边界。
- [ ] 本变更目录（proposal.md、tasks.md）保持可查阅，供团队与 AI 助手明确两个启动器的区别与修改边界，避免后续误改 run.py 或误用启动器。
