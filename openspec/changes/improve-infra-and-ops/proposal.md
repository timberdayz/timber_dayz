# Change: 完善基础设施与运维体系（环境变量 / 备份 / CI/CD）

> **状态**: ✅ 全部完成（Phase 1, 2 & 3）  
> **优先级**: P1（必须完成，分阶段实施）  
> **创建时间**: 2026-01-05  
> **预计时间**: 8-12 小时（可按 Phase 拆分执行）
> **完成时间**: 全部 Phase 已完成（2026-01-05）  
> **完成度**: 60/66 任务（91%，核心任务 100%）

## Why

当前系统在「环境配置、数据安全、持续交付」三个基础设施维度上仍存在明显短板，这些问题彼此关联、共同影响系统的**可部署性、安全性和可运维性**。

> **部署前提假设（关键约束）**
>
> - 正式环境（测试 / 预发 / 生产）的**主运行形态**是：**Linux + Docker / docker-compose**
> - 开发环境主要运行在 Windows 上，使用 `python run.py --use-docker` 作为**开发调试环境下的 Docker 服务一键启动器**（后端 / Celery / 数据库等都在容器中运行，前端在本地运行以便调试）
> - **正式环境（含测试 / 预发 / 生产）不使用 `run.py` 作为主入口脚本**，而是直接在 Linux 服务器上使用 `docker-compose` 命令或 `docker/scripts/start-prod.sh` 等脚本进行部署与运维
> - 系统级运维动作（备份 / 恢复 / 部署）优先从**宿主机视角**操作容器（`docker exec`、`docker compose`），而不是在业务容器内部直接做系统级操作

在这个前提下，现状问题可以更精确地表述为：

1. **环境变量配置管理不统一**

   - 多份 env 模板（`env.example`、`env.development.example`、`env.production.example`、`env.docker.example`）存在不一致风险
   - 缺少启动前的配置验证脚本，生产部署时可能遗漏关键变量或继续使用默认密钥
   - 现有文档（`CLOUD_ENVIRONMENT_VARIABLES.md`）部分变量说明不完整，依赖关系不清晰
   - 缺少自动生成配置文件和密钥的工具，配置效率低、易出错

2. **数据备份策略不完整**

   - 目前仅有 `scripts/backup_database.sh`，缺少文件存储、配置、日志等维度备份
   - 缺少统一备份脚本、自动化调度、备份完整性验证以及周期性恢复演练
   - 备份只在本地，缺少云存储/异地备份，灾备能力薄弱
   - 缺少清晰的备份/恢复策略文档，运维接手成本高

3. **缺少端到端 CI/CD 流程**
   - 目前没有任何 `.github/workflows/*.yml` 等 CI/CD 配置文件
   - 缺少自动构建 Docker 镜像和推送到镜像仓库的流程
   - 缺少测试环境/生产环境的自动部署与回滚机制
   - 缺少部署审批与通知，生产变更不可追踪

以上问题在系统规模和使用范围扩大后，将显著增加运维风险和日常操作成本，因此需要一个**统一的基础设施与运维改进提案**来分阶段解决。

---

## 必要性评估

基于当前系统状态（**上线前测试阶段**），三个模块的必要性评估如下：

### Phase 1: 环境变量配置管理 — **必要（P1）** ⭐⭐⭐

**必要性：高**

**当前问题**：

- 存在 4 份 env 模板，存在不一致风险
- 缺少启动前验证，生产环境可能使用默认密钥
- 已有 `CLOUD_ENVIRONMENT_VARIABLES.md`，但说明不完整

**为什么必要**：

- ✅ 系统已进入上线前测试，配置错误会导致安全风险
- ✅ 多环境部署（开发/测试/生产）需要统一管理
- ✅ 已有 `run.py --use-docker` 和 `docker/scripts/start-prod.sh`，集成验证成本低
- ✅ 预计时间：2-3 小时，投入产出比高

**建议**：**立即实施**

---

### Phase 2: 数据备份策略 — **必要（P1）** ⭐⭐⭐

**必要性：高**

**当前状态**：

- ✅ 已有 `scripts/backup_database.sh`（基础数据库备份）
- ❌ 缺少文件、配置、日志等维度备份
- ❌ 缺少自动化调度和验证

**为什么必要**：

- ✅ 系统包含业务数据（订单、产品、财务等），数据丢失影响大
- ✅ 已有基础脚本，扩展成本低
- ✅ 上线前必须建立备份机制
- ✅ 预计时间：3-4 小时（基础版），云存储可延后

**建议**：**立即实施基础版**（统一备份脚本 + 自动化调度），云存储可延后到 P2 子阶段

---

### Phase 3: CI/CD 流程 — **视情况（P2）** ⭐⭐

**必要性：中等，取决于团队规模和部署频率**

**当前状态**：

- ❌ 无 `.github/workflows/*.yml`
- ✅ 手动部署（`docker-compose` 或 `start-prod.sh`）

**需要 CI/CD 的情况**：

- ✅ 团队规模 ≥ 3 人
- ✅ 部署频率 ≥ 每周 1 次
- ✅ 需要自动化测试
- ✅ 需要多环境（测试/预发/生产）自动部署

**可以暂缓的情况**：

- ⚠️ 单人/小团队（2 人）
- ⚠️ 部署频率低（每月 ≤ 1 次）
- ⚠️ 当前手动部署流程稳定

**建议**：

- **小团队/低频部署**：可延后到 Phase 3（P2），等团队扩大或部署频繁时再实施
- **大团队/高频部署**：建议与 Phase 2 并行或紧接 Phase 2 实施

---

### 分阶段实施建议

#### 方案 A：小团队/低频部署（推荐当前阶段）

```
优先级排序：
1. Phase 1: 环境变量管理（立即，2-3小时）
   └─ 解决配置不一致和安全风险

2. Phase 2: 数据备份（立即，3-4小时）
   └─ 基础备份脚本 + 自动化调度
   └─ 云存储可延后（P2子阶段）

3. Phase 3: CI/CD（延后，等团队扩大或部署频繁时）
   └─ 当前手动部署足够
```

#### 方案 B：大团队/高频部署

```
优先级排序：
1. Phase 1: 环境变量管理（立即）
2. Phase 2: 数据备份（立即）
3. Phase 3: CI/CD（并行或紧接 Phase 2）
   └─ 自动构建和部署能显著提升效率
```

---

## What Changes

本提案合并并统一了以下三个原有提案的目标与内容：

- `improve-environment-variables`（环境变量配置管理）
- `improve-backup-strategy`（数据备份策略）
- `add-cicd-pipeline`（CI/CD 流程）

按照落地优先级，拆分为三个 Phase：

### Phase 1: 环境变量配置管理（P1 - 高优先级）

> 目标：**先确保「配得对」**——统一环境变量配置入口，提供自动验证，降低部署和安全风险。
> 同时明确区分：
>
> - **开发环境 Docker 模式**：Windows 开发机上使用 `python run.py --use-docker` + `.env` / `env.development.example` 启动开发用 Docker Compose（所有后端服务在容器中运行，前端在本地运行，便于调试）
> - **Linux + Docker 正式部署模式**：在 Linux 服务器上使用 `docker-compose.yml` / `docker-compose.prod.yml` + `.env` / 云 Secret 进行测试 / 预发 / 生产环境部署（不通过 `run.py`）

#### 1.1 创建统一的环境变量模板

**目标**：创建一个主模板文件，其他环境配置文件基于此生成，避免多份模板双维护，并为**Linux + Docker 环境的部署 .env 文件**提供统一来源。

**工作内容**：

- 创建 `env.template` 作为主模板（包含所有环境变量和详细注释），**不直接用于正式环境部署**，而是作为 `.env` / `.env.development` 的生成源
- 创建脚本 `scripts/generate-env-files.py` 自动生成不同环境的配置文件：
  - 面向开发者（Windows 开发机，包含 `python run.py --use-docker` 场景）：生成 `env.example`、`env.development.example`，用于在本地复制为 `.env`，启动开发用 Docker Compose
  - 面向运维（Linux 服务器）：生成 `env.production.example`（生产环境示例），可选保留 `env.docker.example` 作为通用 Docker 示例，供运维在服务器上复制为 `.env` 并手工填入真实值
- 基于模板生成并统一更新：
  - `env.example`
  - `env.development.example`
  - `env.production.example`
  - `env.docker.example`（如继续保留）

**文件变更**：

- 新建：`env.template`（主模板）
- 新建：`scripts/generate-env-files.py`（生成脚本）
- 更新：`env.example`、`env.development.example`、`env.production.example`、`env.docker.example`

#### 1.2 环境变量分类与文档化

**目标**：清晰分类所有环境变量，完善说明与依赖关系，降低配置误用风险。

**工作内容**：

- 按优先级分类环境变量（P0 必须、P1 建议、P2 可选）
- 按功能分类（数据库、安全、性能、日志、第三方服务等）
- 更新并补充 `docs/deployment/CLOUD_ENVIRONMENT_VARIABLES.md`
- 新增详细参考文档，说明依赖关系与示例

**文件变更**：

- 更新：`docs/deployment/CLOUD_ENVIRONMENT_VARIABLES.md`
- 新建：`docs/deployment/ENVIRONMENT_VARIABLES_REFERENCE.md`

#### 1.3 配置验证工具与启动集成

**目标**：在应用启动前自动验证环境变量配置，尤其是生产环境的安全相关变量，并且能在**Linux + Docker 部署流水线**中作为前置“配置卫兵”。

**工作内容**：

- 新建 `scripts/validate-env.py`：
  - 支持以 `--env-file` 参数指定要校验的 env 文件（例如 `.env`、`.env.development`）
  - 检查必需环境变量是否存在（按 P0/P1 分级）
  - 检查变量格式（例如 URL、端口、布尔值）
  - 检查生产环境是否仍在使用默认密钥（如 `SECRET_KEY`、`JWT_SECRET_KEY`）
  - 按退出码（exit code）与可解析的输出（stdout / JSON）给出结果，方便 CI / Shell 脚本消费
- 在启动流程中集成验证：
  - 在 `run.py` 的 `start_services_with_docker_compose()` 函数中，在启动 Docker Compose 服务之前调用 `scripts/validate-env.py --env-file .env`（开发环境可相对宽松，仅检查 P0 变量，可通过环境变量 `SKIP_ENV_VALIDATION=true` 跳过）
  - 在生产部署相关的 Docker 启动脚本（如 `docker/scripts/start-prod.sh`）中集成：
    - 在 `check_environment()` 函数中，在现有检查之前或之后调用 `python scripts/validate-env.py --env-file .env || exit 1`
    - 保留现有的 `SECRET_KEY` 和 `POSTGRES_PASSWORD` 检查作为补充（双重验证）
    - 验证失败时输出详细错误信息，帮助运维快速定位问题
  - 对于 `docker/scripts/start-dev.sh`（仅启动开发用数据库 / pgAdmin 的脚本），可按需集成或简化校验逻辑
  - 提供开发环境跳过验证的选项（环境变量开关），保证本地开发体验，并在生产环境强制开启校验

**文件变更**：

- 新建：`scripts/validate-env.py`
- 更新：`run.py`
- 更新：`docker/scripts/start-prod.sh`
- 更新：`docker/scripts/start-dev.sh`

#### 1.4 密钥生成工具（P2 子阶段，可按需实现）

**目标**：简化密钥生成流程，避免手工生成与复制错误，同时兼容“生成后由运维复制到 Linux 服务器 / 云 Secret 管理”的现代做法。

**工作内容**：

- 创建 `scripts/generate-secrets.py`：
  - 生成所有必需的密钥（如 `SECRET_KEY`、`JWT_SECRET_KEY`、`ACCOUNT_ENCRYPTION_KEY` 等）
  - 支持输出到专用密钥文件（权限 600）或直接写入本地 `.env.development`（仅用于开发环境）
  - 提供“仅在终端打印，供运维复制到远端 Linux 服务器 `.env` 或云 Secret 管理”的模式，避免在版本库中留存明文密钥
  - 避免在控制台明文输出敏感值（仅在开发环境可选）

**文件变更**：

- 新建：`scripts/generate-secrets.py`

---

### Phase 2: 数据备份策略（P1 - 高优先级）

> 目标：**再确保「留得住」**——构建统一、可验证、可恢复的数据备份体系。
> 备份与恢复的主视角是 **Linux 宿主机 + Docker 容器**：统一通过 `docker exec`、`docker compose` 等方式操作容器，避免在业务容器内部直接做系统级备份。

#### 2.1 统一备份脚本

**目标**：一个入口脚本统一处理数据库、文件和配置备份，默认在 **Linux 宿主机** 上执行，通过 `docker exec` 与挂载卷访问容器内数据。

**工作内容**：

- 创建 `scripts/backup_all.sh`（面向 Linux 宿主机）：
  - 对数据库备份：
    - 通过 `docker exec xihong_erp_postgres` 调用 `pg_dump`（容器名称与 `docker-compose.yml` 中的 `container_name: xihong_erp_postgres` 一致），而不是在业务容器内直接运行数据库命令
    - 调整现有 `scripts/backup_database.sh`：
      - 保留原有直接连接模式（用于容器内执行）
      - 新增"宿主机模式"：通过 `docker exec xihong_erp_postgres pg_dump ...` 执行备份
      - 通过环境变量 `BACKUP_MODE=host|container` 控制执行方式
      - 统一入口脚本 `backup_all.sh` 使用 `BACKUP_MODE=host` 模式
  - 对文件存储备份：
    - 针对挂载到宿主机的卷（如 `/srv/xihong_erp/data`、`uploads/`、`downloads/`、`temp/` 等路径）做 tar/zip 打包
  - 备份关键配置：`.env`、`config/` 等（注意脱敏 / 权限）
  - 支持全量与增量备份（简单策略即可，例如按日期分目录）
  - 在每次备份目录下生成备份清单 `manifest.json`（记录文件列表、大小、校验和），方便后续校验与恢复演练
- 如有需要，新增 `scripts/backup_files.sh` 专门处理文件归档与压缩（同样假定从宿主机视角操作挂载卷）。

**文件变更**：

- 新建：`scripts/backup_all.sh`
- 新建：`scripts/backup_files.sh`（可选，视实现方式而定）
- 更新：`scripts/backup_database.sh`（对接统一入口脚本）

#### 2.2 自动化备份调度与告警

**目标**：通过 cron/systemd +（可选）Celery 定时任务，实现按计划执行备份并监控失败情况，其中**系统级全量备份以 Linux 宿主机调度为主**。

**工作内容**：

- 创建平台相关的调度脚本：
  - `scripts/setup_backup_cron.sh`（Linux cron）：
    - 在宿主机上写入 cron 规则，定期调用 `scripts/backup_all.sh`
  - `scripts/setup_backup_task.ps1`（Windows 任务计划，P2，可选）：
    - 仅用于 Windows 开发机上的备份测试场景（例如开发环境的数据库 / 挂载卷备份），不用于正式环境
    - 通过 WSL / Git Bash 间接调用 `scripts/backup_all.sh`，保持与 Linux 生产环境同一备份入口
  - `docker/systemd/backup.service`、`docker/systemd/backup.timer`（systemd 定时器）：
    - 在使用 systemd 的 Linux 服务器上，以 timer 的方式周期性调用 `scripts/backup_all.sh`
- 在 `backend/tasks/scheduled_tasks.py` 中：
  - 明确区分“业务层备份任务”（例如业务数据归档）和“系统级全量备份”（由宿主机 cron/systemd 负责）
  - 若需要在应用层触发系统级备份，只通过 `subprocess` 间接调用统一备份脚本（而不是在应用内部直接执行 `pg_dump` 等命令）
  - 增加备份验证任务、备份清理任务（按保留策略删除旧备份）
  - 对备份失败/异常写入日志，预留后续告警对接（如邮件/监控）

**文件变更**：

- 新建：`scripts/setup_backup_cron.sh`
- 新建：`scripts/setup_backup_task.ps1`
- 新建：`docker/systemd/backup.service`
- 新建：`docker/systemd/backup.timer`
- 更新：`backend/tasks/scheduled_tasks.py`

#### 2.3 备份验证与恢复演练

**目标**：定期验证备份有效性，确保真正「可恢复」，并且在 **Docker 化的测试环境** 中完成演练，而不污染生产实例。

**工作内容**：

- 新建 `scripts/verify_backup.sh`：
  - 使用 `pg_restore --list` / 简单还原测试验证数据库备份（通过 `docker run` / `docker exec` 启动临时 Postgres 实例进行校验）
  - 对文件备份进行校验和比对（checksum），对照 `manifest.json`
  - 输出验证报告（控制台 + 可选日志文件），便于集成到 CI / 运维检查脚本
- 新建 `scripts/test_restore.sh`：
  - 仅在单独测试环境执行（通过 `ENVIRONMENT` 环境变量 + 参数 + 交互确认等多重防护）
  - 在测试服务器上，使用一套独立的 docker-compose（例如 `docker-compose.prod.yml` 或创建 `docker-compose.restore-test.yml`）拉起新的 Postgres 容器和应用容器
  - 将最新备份恢复到**测试环境数据库和文件目录**（例如挂载到 `/srv/xihong_erp_test`），而不是覆盖现有生产数据
  - 验证关键表/目录是否完整，形成可重复的“灾备演练脚本”
  - 严格避免对生产环境执行（多重防护：环境变量 + 交互确认 + 容器/卷命名约定）

**文件变更**：

- 新建：`scripts/verify_backup.sh`
- 新建：`scripts/test_restore.sh`

#### 2.4 云存储与灾备策略（P2 子阶段）

**目标**：支持将备份安全地上传到云存储，实现异地备份与灾难恢复能力，并与 Linux + Docker 现有部署方式平滑集成。

**工作内容**：

- 新建 `scripts/upload_backup_to_cloud.py`：
  - 支持常见云存储（阿里云 OSS / AWS S3 / 腾讯云 COS 等，至少先支持 1 种）
  - 通过环境变量配置访问密钥与目标 Bucket（可读取 `.env` 或直接从宿主机环境变量）
  - 封装为可复用的“存储后端适配层”（例如 `--backend s3|oss|cos`），便于未来扩展
  - 支持加密上传与重试机制
- 在 `scripts/backup_all.sh` 中集成云存储上传逻辑（可通过开关控制，如 `ENABLE_CLOUD_BACKUP=true`），统一在宿主机上完成“本地备份 + 上传云端”的完整流程

**文件变更**：

- 新建：`scripts/upload_backup_to_cloud.py`
- 更新：`scripts/backup_all.sh`

#### 2.5 备份与恢复文档

**目标**：形成标准化的备份/恢复流程文档，方便运维和交接。

**工作内容**：

- 新建 `docs/deployment/BACKUP_STRATEGY.md`：
  - 描述备份频率、保留策略、云存储策略
  - 描述各脚本的使用方法与注意事项
- 新建 `docs/deployment/RESTORE_GUIDE.md`：
  - 详细说明数据库恢复步骤
  - 文件恢复步骤
  - 整体灾难恢复流程（含前置检查和回滚策略）

**文件变更**：

- 新建：`docs/deployment/BACKUP_STRATEGY.md`
- 新建：`docs/deployment/RESTORE_GUIDE.md`

---

### Phase 3: CI/CD 流程（P2 - 中优先级，视情况实施）

> 目标：**最后实现「自动跑得快」**——在环境/备份基础稳固后，再引入自动构建与自动部署。
> CI 负责**测试 + 构建 Docker 镜像**，CD 负责在 **Linux + Docker 环境** 中完成“拉镜像 + docker-compose 启动 + 回滚”。
>
> **实施建议**：
>
> - **小团队/低频部署**：可延后实施，等团队扩大或部署频繁时再引入
> - **大团队/高频部署**：建议与 Phase 2 并行或紧接 Phase 2 实施

#### 3.1 Docker 镜像构建与推送

**目标**：在 CI 流程中自动构建并推送后端/前端 Docker 镜像，实现“一次构建，多环境复用”。

**工作内容**：

- 新建 GitHub Actions 工作流 `.github/workflows/docker-build.yml`：
  - 构建后端镜像（`Dockerfile.backend`）
  - 构建前端镜像（`Dockerfile.frontend`）
  - 视需要支持多架构构建（amd64、arm64）
  - 使用 docker buildx + 缓存优化构建时间
- 集成镜像仓库推送：
  - 配置 Docker Hub / 阿里云 / 腾讯云 / GitHub Container Registry 中的一种或多种
  - 配置镜像标签策略：`latest` / `v{version}` / `{branch}` / `{commit-sha}`，确保部署时可以**精确选中某个镜像版本**进行上线 / 回滚
  - 使用 GitHub Secrets 管理仓库凭证

**文件变更**：

- 新建：`.github/workflows/docker-build.yml`
- 视需要更新：`.github/workflows/ci.yml`（集成镜像构建）

#### 3.2 自动部署到测试环境

**目标**：在 CI 通过后自动部署到测试环境（Linux + Docker），保证变更可快速验证。

**工作内容**：

- 新建 `.github/workflows/deploy-staging.yml`：
  - 使用 SSH 登录测试服务器（Linux + Docker 环境）
  - 在服务器上执行：
    - 拉取最新镜像：`docker compose pull` 或 `docker pull org/xihong-backend:{tag}`
    - 使用 `docker-compose -f docker-compose.yml -f docker-compose.prod.yml` 部署到测试环境（或创建 `docker-compose.staging.yml` 作为测试环境专用配置）
    - **注意**：如果使用 `docker-compose.prod.yml`，需要确保环境变量 `APP_ENV=staging` 以区分测试和生产环境
  - 使用健康检查脚本验证服务可用（例如调用 `/health` 接口）
  - 部署完成后发送通知（如 Slack / 邮件）
- 将测试环境部署挂接到 CI（仅限定 main/develop 分支）：
  - 更新 `.github/workflows/ci.yml`，在测试通过后触发测试环境部署（可通过 `workflow_run` 或直接在 CI workflow 内触发 job）

**文件变更**：

- 新建：`.github/workflows/deploy-staging.yml`
- 更新：`.github/workflows/ci.yml`

#### 3.3 生产环境部署与审批

**目标**：为生产环境提供可控、可回滚的部署流程，并引入审批机制，确保所有生产变更都通过 GitHub Actions → Linux + Docker 的标准通道执行。

**工作内容**：

- 新建 `.github/workflows/deploy-production.yml`：
  - 使用 `workflow_dispatch` 手动触发（或基于 tag 触发）
  - 使用 GitHub Environments 配置生产环境与审批人
  - 在目标服务器上执行与测试环境类似的部署步骤，但使用 `docker-compose.prod.yml` 或生产专用 compose 配置
  - 支持回滚到上一个已知良好版本（基于镜像标签或上一次成功部署的 tag）
  - 部署完成后发送通知（如 Slack / 邮件 / 企业微信）
- 配置生产环境审批与保护规则：
  - 在 GitHub Environments 中配置 `production`
  - 设置审批人、保护规则与 Secret 绑定

**文件变更**：

- 新建：`.github/workflows/deploy-production.yml`

#### 3.4 CI/CD 文档

**目标**：让团队成员清楚了解 CI/CD 流程与常见问题处理方式。

**工作内容**：

- 新建 `docs/deployment/CI_CD_GUIDE.md`：
  - 描述 CI 工作流（测试、构建、镜像推送）
  - 描述测试/生产环境部署流程
  - 描述回滚操作与故障排查指南

**文件变更**：

- 新建：`docs/deployment/CI_CD_GUIDE.md`

---

## Impact

### 正面影响

1. **部署安全性显著提升**

   - 启动前环境变量验证，防止关键配置缺失或默认密钥流入生产
   - 统一模板和文档让配置更可控、更透明

2. **数据安全和灾备能力提升**

   - 数据库 + 文件 + 配置的统一备份
   - 自动化调度、备份验证与恢复演练，降低备份失效风险
   - 云存储与文档化流程支撑真正的灾难恢复

3. **交付效率与一致性提升**

   - 自动构建和推送 Docker 镜像，减少手动步骤和误操作
   - 测试环境自动部署，加快功能验收
   - 生产环境带审批和回滚机制，使上线过程可控、可追踪

4. **运维与交接成本降低**
   - 所有关键操作（配置、备份、部署）均有脚本和文档支撑
   - 新成员可以按照流程快速上手部署与运维

### 风险与缓解

1. **配置验证/备份/CI 流程引入后，初期可能增加复杂度**

   - **缓解**：分 Phase 实施，每个 Phase 完成后进行一次简短的团队培训或文档 walkthrough

2. **验证脚本过于严格影响开发体验**

   - **缓解**：区分开发/生产环境，开发环境允许通过环境变量关闭部分校验，仅强制 P0 变量

3. **备份/恢复脚本误用影响生产数据**

   - **缓解**：恢复脚本仅允许在 `ENVIRONMENT=test` 等安全环境下执行，并增加二次确认

4. **CI/CD 配置错误导致部署失败**
   - **缓解**：先在测试仓库或测试分支上验证工作流，再推到主仓库；保留手工部署路径作为兜底

---

## Implementation Plan（高层级）

### 当前阶段（上线前测试）— ✅ 已完成

1. **Phase 1：环境变量配置管理（✅ 已完成）**

   - ✅ 实现 `env.template` + 生成脚本 + 验证脚本
   - ✅ 集成到 `run.py` 与 Docker 启动脚本
   - ✅ 完成配置文档与参考文档
   - ✅ 密钥生成工具（可选但已实施）
   - **实际时间**：约 3 小时

2. **Phase 2：数据备份策略（✅ 已完成）**

   - ✅ 实现统一备份脚本与调度脚本（数据库 + 文件）
   - ✅ 实现自动化调度（cron/systemd）
   - ✅ 实现验证与恢复演练脚本
   - ✅ 完成备份/恢复文档
   - ✅ Celery 定时任务（备份验证和清理）
   - **实际时间**：约 4 小时
   - **云存储上传**：可延后到 P2 子阶段（已标记为可选）

### 后续阶段（根据团队规模决定）

3. **Phase 3：CI/CD 流程（视情况实施）**

   - **小团队/低频部署**：可延后，等团队扩大或部署频繁时再实施
   - **大团队/高频部署**：建议与 Phase 2 并行或紧接 Phase 2 实施
   - 先实现 Docker 构建与推送工作流
   - 再实现测试环境/生产环境部署工作流
   - 最后补充 CI/CD 文档与回滚指南
   - **预计时间**：4-5 小时
