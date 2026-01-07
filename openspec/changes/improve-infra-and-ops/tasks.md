# Tasks: 完善基础设施与运维体系（环境变量 / 备份 / CI/CD）

## Phase 1: 环境变量配置管理（P1 - 高优先级）

### 1.1 创建统一的环境变量模板

- [x] 1.1.1 创建 `env.template` 主模板文件，包含所有环境变量和详细注释
- [x] 1.1.2 创建 `scripts/generate-env-files.py` 脚本，支持生成不同环境的配置文件
- [x] 1.1.3 基于模板生成并更新 `env.example`
- [x] 1.1.4 基于模板生成并更新 `env.development.example`
- [x] 1.1.5 基于模板生成并更新 `env.production.example`
- [x] 1.1.6 基于模板生成并更新 `env.docker.example`（可选）

### 1.2 环境变量分类与文档化

- [x] 1.2.1 按优先级分类环境变量（P0 必须、P1 建议、P2 可选）
- [x] 1.2.2 按功能分类环境变量（数据库、安全、性能、日志、第三方服务等）
- [x] 1.2.3 更新 `docs/deployment/CLOUD_ENVIRONMENT_VARIABLES.md`
- [x] 1.2.4 创建 `docs/deployment/ENVIRONMENT_VARIABLES_REFERENCE.md`

### 1.3 配置验证工具与启动集成

- [x] 1.3.1 创建 `scripts/validate-env.py`，支持 `--env-file` 参数
- [x] 1.3.2 实现 P0/P1 分级检查逻辑
- [x] 1.3.3 实现变量格式检查（URL、端口、布尔值）
- [x] 1.3.4 实现默认密钥检测（`SECRET_KEY`、`JWT_SECRET_KEY`）
- [x] 1.3.5 更新 `run.py` 的 `start_services_with_docker_compose()` 函数，集成验证
- [x] 1.3.6 更新 `docker/scripts/start-prod.sh` 的 `check_environment()` 函数，集成验证
- [x] 1.3.7 更新 `docker/scripts/start-dev.sh`，按需集成或简化校验逻辑

### 1.4 密钥生成工具（P2 子阶段，可按需实现）

- [x] 1.4.1 创建 `scripts/generate-secrets.py`
- [x] 1.4.2 实现 `SECRET_KEY`、`JWT_SECRET_KEY`、`ACCOUNT_ENCRYPTION_KEY` 等密钥生成
- [x] 1.4.3 支持输出到文件或终端打印模式

---

## Phase 2: 数据备份策略（P1 - 高优先级）

### 2.1 统一备份脚本

- [x] 2.1.1 创建 `scripts/backup_all.sh`（统一入口脚本）
- [x] 2.1.2 实现数据库备份（通过 `docker exec xihong_erp_postgres pg_dump`）
- [x] 2.1.3 更新 `scripts/backup_database.sh`，支持 `BACKUP_MODE=host|container` 模式
- [x] 2.1.4 实现文件存储备份（`data/`、`uploads/`、`downloads/`、`temp/` 等）
- [x] 2.1.5 实现配置备份（`.env`、`config/` 等，注意脱敏）
- [x] 2.1.6 实现备份清单 `manifest.json` 生成
- [ ] 2.1.7 创建 `scripts/backup_files.sh`（可选）

### 2.2 自动化备份调度与告警

- [x] 2.2.1 创建 `scripts/setup_backup_cron.sh`（Linux cron 配置）
- [x] 2.2.2 创建 `docker/systemd/backup.service`
- [x] 2.2.3 创建 `docker/systemd/backup.timer`
- [ ] 2.2.4 创建 `scripts/setup_backup_task.ps1`（Windows 任务计划，P2，可选）
- [x] 2.2.5 更新 `backend/tasks/scheduled_tasks.py`，添加备份验证和清理任务

### 2.3 备份验证与恢复演练

- [x] 2.3.1 创建 `scripts/verify_backup.sh`（备份完整性验证）
- [x] 2.3.2 实现数据库备份验证（`pg_restore --list`）
- [x] 2.3.3 实现文件备份校验和比对（checksum）
- [x] 2.3.4 创建 `scripts/test_restore.sh`（恢复演练脚本）
- [x] 2.3.5 实现多重防护机制（环境变量 + 交互确认）

### 2.4 云存储与灾备策略（P2 子阶段）

- [ ] 2.4.1 创建 `scripts/upload_backup_to_cloud.py`
- [ ] 2.4.2 实现阿里云 OSS / AWS S3 / 腾讯云 COS 支持（至少 1 种）
- [ ] 2.4.3 实现存储后端适配层（`--backend s3|oss|cos`）
- [ ] 2.4.4 更新 `scripts/backup_all.sh`，集成云存储上传（`ENABLE_CLOUD_BACKUP` 开关）

### 2.5 备份与恢复文档

- [x] 2.5.1 创建 `docs/deployment/BACKUP_STRATEGY.md`
- [x] 2.5.2 创建 `docs/deployment/RESTORE_GUIDE.md`

---

## Phase 3: CI/CD 流程（P2 - 中优先级，视情况实施）

### 3.1 Docker 镜像构建与推送

- [x] 3.1.1 创建 `.github/workflows/docker-build.yml`
- [x] 3.1.2 实现后端镜像构建（`Dockerfile.backend`）
- [x] 3.1.3 实现前端镜像构建（`Dockerfile.frontend`）
- [x] 3.1.4 配置 docker buildx + 缓存优化
- [x] 3.1.5 配置镜像仓库推送（Docker Hub / 阿里云 / GitHub Container Registry）
- [x] 3.1.6 配置镜像标签策略（`latest` / `v{version}` / `{branch}` / `{commit-sha}`）
- [x] 3.1.7 更新 `.github/workflows/ci.yml`（可选，集成镜像构建）

### 3.2 自动部署到测试环境

- [x] 3.2.1 创建 `.github/workflows/deploy-staging.yml`
- [x] 3.2.2 实现 SSH 登录测试服务器
- [x] 3.2.3 实现镜像拉取和 docker-compose 部署
- [x] 3.2.4 实现健康检查验证
- [x] 3.2.5 实现部署通知（Slack / 邮件）
- [x] 3.2.6 更新 `.github/workflows/ci.yml`，挂接测试环境部署

### 3.3 生产环境部署与审批

- [x] 3.3.1 创建 `.github/workflows/deploy-production.yml`
- [x] 3.3.2 实现 `workflow_dispatch` 手动触发
- [x] 3.3.3 配置 GitHub Environments `production`
- [x] 3.3.4 实现回滚机制（基于镜像标签）
- [x] 3.3.5 实现部署通知（Slack / 邮件 / 企业微信）
- [x] 3.3.6 设置审批人和保护规则

### 3.4 CI/CD 文档

- [x] 3.4.1 创建 `docs/deployment/CI_CD_GUIDE.md`
- [x] 3.4.2 描述 CI 工作流（测试、构建、镜像推送）
- [x] 3.4.3 描述测试/生产环境部署流程
- [x] 3.4.4 描述回滚操作与故障排查指南

---

## 实施优先级说明

### 当前阶段（上线前测试）— 必须完成

**Phase 1: 环境变量配置管理**

- 预计时间：2-3 小时
- 优先级：P1（高）
- 状态：立即实施

**Phase 2: 数据备份策略（基础版）**

- 预计时间：3-4 小时
- 优先级：P1（高）
- 状态：立即实施基础版（统一备份脚本 + 自动化调度）
- 云存储上传：可延后到 P2 子阶段

### 后续阶段（根据团队规模决定）

**Phase 3: CI/CD 流程**

- 预计时间：4-5 小时
- 优先级：P2（中）
- 状态：视情况实施
  - **小团队/低频部署**：可延后，等团队扩大或部署频繁时再实施
  - **大团队/高频部署**：建议与 Phase 2 并行或紧接 Phase 2 实施

---

## 任务统计

- **Phase 1**: 20 个任务（16 个核心 + 4 个可选）
  - ✅ 核心：1.1.1-1.1.5, 1.2.x, 1.3.x（16 个）**已完成**
  - ✅ 可选：1.1.6 env.docker.example + 1.4.x 密钥生成工具（4 个）**已完成**（密钥生成工具已实施）
- **Phase 2**: 23 个任务（17 个核心 + 6 个可选）
  - ✅ 核心：2.1.1-2.1.6, 2.2.1-2.2.3/2.2.5, 2.3.x, 2.5.x（17 个）**已完成**
  - ⏸️ 可选：2.1.7 backup_files.sh + 2.2.4 Windows 任务计划 + 2.4.x 云存储（6 个）**可延后**
- **Phase 3**: 23 个任务（全部可选，视情况实施）
  - ✅ 3.1.x Docker 构建（7 个）**已完成**
  - ✅ 3.2.x 测试环境部署（6 个）**已完成**
  - ✅ 3.3.x 生产环境部署（6 个）**已完成**
  - ✅ 3.4.x CI/CD 文档（4 个）**已完成**

**总计**: 66 个任务

**当前阶段必须完成**: 33 个任务（Phase 1 核心 16 个 + Phase 2 核心 17 个）
**已完成**: 60 个任务 ✅

- Phase 1 核心：16 个 ✅
- Phase 1 可选：4 个 ✅（包括密钥生成工具）
- Phase 2 核心：17 个 ✅
- Phase 3 全部：23 个 ✅

**可延后**: 6 个可选任务（Phase 2 可选：2.1.7, 2.2.4, 2.4.x）

---

## 更新记录

- **2026-01-05**: Phase 3 全部任务标记为已完成 ✅
