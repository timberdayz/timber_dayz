# Change: 本地与云端部署角色区分（同一代码库、双镜像）

**实现状态**：§1 部署角色、§2 Docker 方案 A、§5 本机采集模式已落地。开发环境下可使用 `python run.py --use-docker --with-metabase --collection` 启动采集环境。CI 双镜像（§3）、部署文档（§4）待实施。

## Why

1. **同一套系统、两种部署**：本地环境负责数据采集（Playwright/API）与数据同步，并将 b_class 推送到云端；云端环境仅负责系统运作（看板、报表、多端访问）。两边使用同一代码库与同一 Docker 构建体系，需通过配置与镜像变体区分角色，避免云端误跑采集或安装多余依赖。
2. **运行时差异**：本地需安装并运行 Playwright 与浏览器（Chromium）；云端不跑采集，无需 Playwright。若云端也带 Playwright，镜像体积大且增加攻击面。采用**方案 A**：沿用现有 `Dockerfile.collection`（带 Playwright）作为采集/本机开发用镜像，`Dockerfile.backend` 保持无 Playwright；CI 对同一 tag 可构建默认镜像（backend）与 full 镜像（由 Dockerfile.collection 构建），云端拉默认、本地/采集环境拉 full。
3. **一键云端部署不变**：继续通过 `git push origin v4.XX.XX` 触发云端部署；云端流水线只拉默认后端镜像；本地采集环境（含本机开发测试）使用带 Playwright 的镜像，并配置 ENABLE_COLLECTION=true、CLOUD_DATABASE_URL、Cron 等。

## What Changes

### 原则：单后端、按角色选镜像

- 云端与本地（含本机开发）均只运行**一个**后端服务；不出现「起两个后端再停一个」的流程。
- 差异仅由「使用默认镜像还是 full 镜像」以及运行时 `ENABLE_COLLECTION` 决定。

### 1. 部署角色：环境变量区分

- **ENABLE_COLLECTION**（或 DEPLOYMENT_ROLE=local|cloud）：用于区分「本地（负责采集）」与「云端（负责运作）」。
- **本地**：`ENABLE_COLLECTION=true`（或 `DEPLOYMENT_ROLE=local`）→ 启动采集调度器，可配置 4 时段采集；需配置 `CLOUD_DATABASE_URL` 并在该机配置 Cron 执行本地→云端同步脚本。
- **云端**：`ENABLE_COLLECTION=false`（或 `DEPLOYMENT_ROLE=cloud`）→ 不启动采集调度器（或启动但不加载采集任务），仅提供看板、报表与 API。

### 2. Docker：方案 A（沿用现有 Dockerfile.collection）

- **Dockerfile.backend**：保持现状，不包含 Playwright，用于云端及默认 Docker Compose 下的后端。
- **Dockerfile.collection**：已存在，包含 Playwright 与浏览器依赖，用于采集环境及本机采集开发。
- **本机采集开发**：通过 Compose 覆盖文件 `docker-compose.collection-dev.yml` 将 **backend** 服务的 build 指向 `Dockerfile.collection`，保持单后端、端口与日常一致（如 8001）；可选为 backend 增加 `ENABLE_COLLECTION=true`、`shm_size: "2gb"` 等。
- 不修改 Dockerfile.backend 增加 INSTALL_PLAYWRIGHT 构建参数；CI 双镜像时 full 镜像由 Dockerfile.collection 构建并打 -full tag。

### 3. CI：同一 tag 构建两个镜像（有镜像仓库时）

- 对同一版本 tag（如 v4.XX.XX）执行两次构建（方案 A）：
  - **默认镜像**：由 Dockerfile.backend 构建，打 tag 如 `xihong-erp:v4.XX.XX`，推送到镜像仓库；云端部署拉取此镜像。
  - **完整镜像**：由 **Dockerfile.collection** 构建，打 tag 如 `xihong-erp:v4.XX.XX-full`，推送到镜像仓库；本地/服务器采集环境拉取此镜像。
- 若当前 CI 仅构建一个镜像，则增加一次基于 Dockerfile.collection 的构建并推送 -full 的步骤。

### 4. 部署流程与日常运作流程（文档化）

- **部署核心流程**：在 `docs/deployment/` 中新增或更新文档，写明：
  - 发布新版本：打 tag、git push → CI 构建默认 + full 两个镜像并推送；
  - 云端部署：拉取默认镜像、ENABLE_COLLECTION=false、DATABASE_URL=云端库、启动；
  - 本地采集环境部署：在那台机器上拉取 -full 镜像、ENABLE_COLLECTION=true、DATABASE_URL=本地库、CLOUD_DATABASE_URL=云端库、配置 Cron（本地→云端同步脚本）、启动。
- **日常运作核心流程**：在同一文档中写明：
  - 四时段（如 6:00、12:00、18:00、22:00）本地执行采集 → 数据同步写入本地 b_class；
  - 错峰（如 6:30、12:30、18:30、22:30）在本地执行本地→云端同步脚本；
  - 云端应用只读云端库，不跑采集、不跑同步脚本。
- 便于运维与交接时按文档核对，避免角色混用或漏配。

### 5. 本机开发与测试（采集模式）

- **目标**：开发/测试采集与数据同步时，本机一键启动「完整系统、单后端、带 Playwright」，与正式采集环境一致，便于在开发环境下验证采集环境的 Docker 化架构，减少未来部署因环境差异导致的问题。
- **实现**（方案 A，二者同时落地）：
  - **docker-compose**：新增覆盖文件 `docker-compose.collection-dev.yml`，将 **backend** 服务的 build 指向现有 `Dockerfile.collection`，保持单后端、端口与日常一致（8001）；可选为 backend 增加 `ENABLE_COLLECTION=true`、`shm_size: "2gb"`。
  - **run.py**：增加参数 `--collection`；当与 `--use-docker` 同时使用时，将 `docker-compose.collection-dev.yml` 加入 compose 文件列表，与 base、dev、metabase 等一并使用，从而使用带 Playwright 的后端镜像。
- **启动命令**：开发环境下使用 **`python run.py --use-docker --with-metabase --collection`** 启动项目，进行采集环境下的项目测试；前端访问的同一后端（如 http://localhost:8001）即具备采集与同步能力，可直接验证。

## Impact

### 受影响的规格

- **deployment-ops**：ADDED 本地与云端部署角色区分（ENABLE_COLLECTION 或 DEPLOYMENT_ROLE）、Docker 方案 A（Dockerfile.collection 用于采集/本机开发）、双镜像构建与拉取策略、部署与日常运作流程文档化、本机采集测试启动命令。

### 受影响的代码与文档

| 类型     | 位置/模块                               | 修改内容 |
|----------|------------------------------------------|----------|
| 后端     | `backend/main.py`（或采集调度器入口）   | 根据 ENABLE_COLLECTION 或 DEPLOYMENT_ROLE 决定是否创建/启动 CollectionScheduler |
| Docker   | docker-compose.collection-dev.yml（新增）| 覆盖 backend 使用 Dockerfile.collection，可选 ENABLE_COLLECTION、shm_size；Dockerfile.backend 不改动 |
| CI       | 流水线配置（如 .github/workflows/*.yml）| 默认镜像由 Dockerfile.backend 构建；增加由 Dockerfile.collection 构建的 -full 镜像并推送 |
| 文档     | `docs/deployment/`                      | 新增或更新「本地与云端部署」「部署流程」「日常运作流程」章节；补充「本机采集测试」启动命令 |
| 配置示例 | .env.example 或部署说明                 | 增加 ENABLE_COLLECTION、DEPLOYMENT_ROLE 等说明（不含敏感值） |
| 启动脚本 | run.py                                 | 增加 --collection；与 --use-docker 同时使用时加载 docker-compose.collection-dev.yml，使 backend 使用 Dockerfile.collection（单后端） |

### 不修改

- 采集逻辑、数据同步逻辑、本地→云端同步脚本逻辑不变；仅通过配置与镜像变体控制「谁跑采集、谁不跑」。
- 前端功能可选：可根据同一配置隐藏/展示采集入口，非本变更强制要求。

### 依赖关系

- 与 `add-local-to-cloud-sync`、`add-hybrid-collection-api-playwright` 无强依赖；本变更可独立落地，并为两者提供清晰的部署与运作上下文。

## Non-Goals

- 不在此变更中实现采集执行与 Backend 解耦（本地 Agent 独立进程等）。
- 不强制要求前端根据角色隐藏采集菜单；可后续按需补充。
- 不改变现有云端一键部署的触发方式（仍为 git push tag）。
