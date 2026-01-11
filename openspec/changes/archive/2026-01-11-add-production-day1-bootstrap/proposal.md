# Change: 生产环境 Day-1 Bootstrap 与 Secrets 标准化（自动部署可用闭环）

## Why

当前生产发布已经实现“tag 发布自动部署 + 基础健康检查 + 迁移”，但仍存在两个会反复拖慢上线、降低可用性的痛点：

- **首次上线（新机器/新库）缺少一键可用闭环**：部署后仍需要人工手动创建管理员、初始化必要数据/角色、验证关键配置，导致“部署成功但系统不可登录/不可用”的灰区。
- **Secrets 与配置载入不够标准化**：生产依赖 `.env` 与人工维护，容易受格式（CRLF/空格）、日志泄露、变量缺失影响，且缺少统一的“可验证入口”。

本变更目标是把生产发布提升到现代化主流的可用闭环：**一次发布即可达到“可访问 + 可登录 + 可运行任务”的最小可用状态**，并将敏感配置治理纳入标准流程。

## What Changes

- **新增 Day-1 Bootstrap 入口**：提供幂等的生产初始化流程，在部署时自动执行（或可手动重复执行），确保：
  - 数据库迁移已完成（`alembic upgrade head`）
  - 必要的基础数据/角色存在（如 Admin 角色等）
  - 可选：创建/确认管理员账号（**默认关闭**，必须显式启用；且仅在“无任何 superuser”时允许创建）
  - 关键配置通过验证（P0 必需项）
- **Secrets 标准化**：
  - 明确生产敏感项来源优先级（GitHub Secrets/服务器端 secrets 文件/`.env`），并规定同名变量覆盖规则
  - 生产环境禁止使用默认占位 secrets（如默认 JWT/SECRET_KEY）
  - 所有部署与启动日志严禁输出明文 secrets（只允许输出“是否设置/长度/掩码”）
  - 统一对 `.env` 读取做兼容处理（CRLF、尾随空格、换行）
- **部署流程固化**：在 `Deploy to Production (Tag Release)` 中加入 bootstrap 阶段（在基础设施健康后、应用层启动前），失败即阻断发布，避免“半可用”状态。
 - **迁移失败恢复路径**：文档化并固化“迁移失败如何恢复/回滚/重试”的最小流程，确保可运维。

> 说明：本提案聚焦 P0/P1 的可用闭环与安全基线。可观测性、备份演练、回滚策略将作为后续独立 change 推进（或在本提案 Phase 2 作为可选扩展）。

## Impact

- **Affected specs**:
  - 新增 capability：`deployment-ops`（生产部署与运维基线）
- **Affected code (planned)**:
  - `.github/workflows/deploy-production.yml`（新增 bootstrap 阶段与 secrets 处理约束）
  - `Dockerfile.backend`（内置必要运维脚本）
  - `scripts/`（新增/完善幂等 bootstrap 脚本；或迁移至 `backend/` 以便更清晰的运行入口）
  - `docs/CI_CD_DEPLOYMENT_GUIDE.md`（补充 Day-1 Bootstrap 与 secrets 标准）

## Non-Goals

- 不在本提案中引入 Kubernetes、Helm 或复杂的蓝绿/金丝雀发布。
- 不强制将所有 `.env` 替换为云厂商 Secret Manager（先做到流程标准化与最小风险）。
- 不在本提案中重构现有业务域、API 契约或 ORM（仅涉及部署与运维入口）。

