# Design: 本地与云端部署角色区分

## Context

- 同一套西虹 ERP 代码库需部署为两种角色：**本地**（负责采集、数据同步、本地→云端同步）与**云端**（仅系统运作、看板与报表）。两边均为 Docker 部署，且通过 git push tag 触发云端一键部署；本地采集环境在单独机器上部署。
- 本地需运行 Playwright 与浏览器，云端不需要；需在不维护两套 Dockerfile 的前提下产出两种镜像，并与现有镜像仓库与 CI 流程兼容。

## Goals / Non-Goals

- **Goals**：用环境变量区分本地/云端；用构建参数控制是否安装 Playwright；CI 对同一 tag 构建默认 + full 两镜像；文档化部署流程与日常运作流程。
- **Non-Goals**：不改变 git push 触发云端部署的方式；不在此设计中实现采集与 Backend 进程解耦。

## Decisions

### 1. 角色由环境变量区分，不维护两套代码

- **决策**：使用 `ENABLE_COLLECTION`（true/false）或 `DEPLOYMENT_ROLE`（local/cloud）在运行时区分。后端在启动时读取该变量，若为 false 或 cloud 则不创建/不启动 CollectionScheduler。
- **理由**：同一镜像（或同一代码）在不同环境用不同配置即可切换角色，无需分支或两套镜像逻辑差异。
- **替代**：用不同代码分支或不同仓库部署——增加维护成本，不采纳。

### 2. 一个 Dockerfile + ARG INSTALL_PLAYWRIGHT

- **决策**：在用于运行后端（及采集）的 Dockerfile 中增加 `ARG INSTALL_PLAYWRIGHT=false`；仅在为 true 时执行 `pip install playwright` 与 `playwright install chromium`（或等价步骤）。默认不安装，供云端构建使用；本地或 CI 构建 full 时传 true。
- **理由**：单 Dockerfile 易维护；与现有「git push → CI 构建一个镜像」兼容，仅需在 CI 中显式传 false，并增加一次传 true 的构建打 -full tag。
- **落点**：若生产实际使用 Dockerfile.backend，则在该文件中增加 ARG 与条件安装；若使用根 Dockerfile 的 backend target，则在对应阶段增加。Playwright 可能仅在「采集」场景需要，需与现有 Dockerfile.collection 或后端依赖关系对齐，由实现时确定具体文件与层级。

### 3. 有镜像仓库时 CI 构建两个镜像

- **决策**：对同一版本 tag，CI 执行两次构建并推送：默认（INSTALL_PLAYWRIGHT=false）打主 tag（如 xihong-erp:v4.XX.XX），完整（INSTALL_PLAYWRIGHT=true）打 -full tag（如 xihong-erp:v4.XX.XX-full）。云端流水线只拉主 tag；本地采集环境拉 -full。
- **理由**：版本一一对应，本地与云端可对齐同一发布；本地机无需安装构建环境，拉取即用。
- **替代**：仅在本地机从源码构建 full——可行但本地需 Git 与构建环境，且与「有镜像仓库」的现状不符，不采纳为首选。

### 4. 部署与日常运作流程写入文档

- **决策**：在 docs/deployment/ 下新增或更新文档，包含：（1）发布新版本步骤（打 tag、push、CI 构建两镜像）；（2）云端部署步骤（拉默认镜像、环境变量、启动）；（3）本地采集环境部署步骤（拉 -full、环境变量、Cron 配置、启动）；（4）日常运作流程（四时段采集与数据同步、错峰本地→云端同步、云端只读）。
- **理由**：便于运维与交接按步骤核对，减少角色混用或漏配（如云端误开采集、本地未配 Cron）。

## 部署核心流程（文档中应包含）

1. 发布：`git tag v4.XX.XX` → `git push origin v4.XX.XX` → CI 构建默认 + full 镜像并推送。
2. 云端：拉取默认镜像 → ENABLE_COLLECTION=false、DATABASE_URL=云端库 → 启动。
3. 本地：拉取 -full 镜像 → ENABLE_COLLECTION=true、DATABASE_URL=本地库、CLOUD_DATABASE_URL=云端库 → 配置 Cron（本地→云端同步脚本）→ 启动。

## 日常运作核心流程（文档中应包含）

1. 四时段（如 6:00、12:00、18:00、22:00）：本地执行采集 → 数据同步写入本地 b_class。
2. 错峰（如 6:30、12:30、18:30、22:30）：本地执行本地→云端同步脚本。
3. 云端：应用只读云端库，不跑采集、不跑同步脚本。

## Open Questions

- ENABLE_COLLECTION 与 DEPLOYMENT_ROLE 二选一或两者并存（一个为主、一个兼容）由实现时确定。
- Playwright 安装的具体落点（Dockerfile.backend 新增 stage 还是复用 Dockerfile.collection）需结合现有构建与采集运行时确定。
