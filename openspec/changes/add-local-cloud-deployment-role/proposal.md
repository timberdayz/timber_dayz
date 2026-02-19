# Change: 本地与云端部署角色区分（同一代码库、双镜像）

## Why

1. **同一套系统、两种部署**：本地环境负责数据采集（Playwright/API）与数据同步，并将 b_class 推送到云端；云端环境仅负责系统运作（看板、报表、多端访问）。两边使用同一代码库与同一 Docker 构建体系，需通过配置与镜像变体区分角色，避免云端误跑采集或安装多余依赖。
2. **运行时差异**：本地需安装并运行 Playwright 与浏览器（Chromium）；云端不跑采集，无需 Playwright。若云端也带 Playwright，镜像体积大且增加攻击面，故采用「一个 Dockerfile + 构建参数」产出两种镜像（默认/slim 与 full），在有镜像仓库时由 CI 统一构建，云端拉默认、本地拉 full。
3. **一键云端部署不变**：继续通过 `git push origin v4.XX.XX` 触发云端部署；CI 对同一 tag 构建「默认」（INSTALL_PLAYWRIGHT=false）与「full」（INSTALL_PLAYWRIGHT=true）两个镜像并推送仓库，云端流水线只拉默认镜像；本地采集环境在那台机器上拉 full 镜像并配置 ENABLE_COLLECTION=true 与 CLOUD_DATABASE_URL、Cron 等。

## What Changes

### 1. 部署角色：环境变量区分

- **ENABLE_COLLECTION**（或 DEPLOYMENT_ROLE=local|cloud）：用于区分「本地（负责采集）」与「云端（负责运作）」。
- **本地**：`ENABLE_COLLECTION=true`（或 `DEPLOYMENT_ROLE=local`）→ 启动采集调度器，可配置 4 时段采集；需配置 `CLOUD_DATABASE_URL` 并在该机配置 Cron 执行本地→云端同步脚本。
- **云端**：`ENABLE_COLLECTION=false`（或 `DEPLOYMENT_ROLE=cloud`）→ 不启动采集调度器（或启动但不加载采集任务），仅提供看板、报表与 API。

### 2. Docker：一个 Dockerfile + 构建参数

- **ARG INSTALL_PLAYWRIGHT**（默认 false）：仅在 `INSTALL_PLAYWRIGHT=true` 时安装 Playwright 及浏览器依赖（如 `playwright install chromium`）。
- **默认构建**（云端用）：`docker build --build-arg INSTALL_PLAYWRIGHT=false`（或不传），产出不包含 Playwright 的镜像，用于云端部署。
- **完整构建**（本地用）：`docker build --build-arg INSTALL_PLAYWRIGHT=true`，产出带 Playwright 的镜像，用于本地采集环境。
- 具体落点可为根 Dockerfile 或 Dockerfile.backend / 实际用于运行后端的 Dockerfile，由实现时确定。

### 3. CI：同一 tag 构建两个镜像（有镜像仓库时）

- 对同一版本 tag（如 v4.XX.XX）执行两次构建：
  - **默认镜像**：`INSTALL_PLAYWRIGHT=false`，打 tag 如 `xihong-erp:v4.XX.XX`，推送到镜像仓库；云端部署拉取此镜像。
  - **完整镜像**：`INSTALL_PLAYWRIGHT=true`，打 tag 如 `xihong-erp:v4.XX.XX-full`，推送到镜像仓库；本地采集环境拉取此镜像。
- 若当前 CI 仅构建一个镜像，则增加一次构建并推送 -full 的步骤；`INSTALL_PLAYWRIGHT=false` 在现有云端构建命令中显式或默认使用。

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

## Impact

### 受影响的规格

- **deployment-ops**：ADDED 本地与云端部署角色区分（ENABLE_COLLECTION 或 DEPLOYMENT_ROLE）、Docker 构建参数 INSTALL_PLAYWRIGHT、双镜像构建与拉取策略、部署与日常运作流程文档化。

### 受影响的代码与文档

| 类型     | 位置/模块                               | 修改内容 |
|----------|------------------------------------------|----------|
| 后端     | `backend/main.py`（或采集调度器入口）   | 根据 ENABLE_COLLECTION 或 DEPLOYMENT_ROLE 决定是否创建/启动 CollectionScheduler |
| Docker   | Dockerfile 或 Dockerfile.backend（等）  | 增加 ARG INSTALL_PLAYWRIGHT，条件安装 Playwright 与浏览器 |
| CI       | 流水线配置（如 .github/workflows/*.yml）| 云端构建使用 INSTALL_PLAYWRIGHT=false；增加 full 镜像构建并打 -full tag 推送 |
| 文档     | `docs/deployment/`                      | 新增或更新「本地与云端部署」「部署流程」「日常运作流程」章节 |
| 配置示例 | .env.example 或部署说明                 | 增加 ENABLE_COLLECTION、DEPLOYMENT_ROLE 等说明（不含敏感值） |

### 不修改

- 采集逻辑、数据同步逻辑、本地→云端同步脚本逻辑不变；仅通过配置与镜像变体控制「谁跑采集、谁不跑」。
- 前端功能可选：可根据同一配置隐藏/展示采集入口，非本变更强制要求。

### 依赖关系

- 与 `add-local-to-cloud-sync`、`add-hybrid-collection-api-playwright` 无强依赖；本变更可独立落地，并为两者提供清晰的部署与运作上下文。

## Non-Goals

- 不在此变更中实现采集执行与 Backend 解耦（本地 Agent 独立进程等）。
- 不强制要求前端根据角色隐藏采集菜单；可后续按需补充。
- 不改变现有云端一键部署的触发方式（仍为 git push tag）。
