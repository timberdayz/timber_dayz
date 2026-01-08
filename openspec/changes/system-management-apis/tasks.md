# 系统管理模块后端 API 实现 - 任务清单

> **状态**: 📝 待实施  
> **创建时间**: 2026-01-06

## Phase 1: 系统日志与审计日志增强 API（P0）

### 1.1 系统日志 API

- [ ] 检查是否需要新增系统日志表（或使用现有日志系统）
- [ ] 如需新增：在 `modules/core/db/schema.py` 定义 `SystemLog` 模型
- [ ] 创建 Alembic 迁移：`alembic revision --autogenerate -m "add_system_logs_table"`
- [ ] 在 `backend/schemas/system.py` 中定义 Pydantic 模型：
  - [ ] `SystemLogResponse`
  - [ ] `SystemLogListResponse`
  - [ ] `SystemLogFilterRequest`
  - [ ] `SystemLogExportRequest`
- [ ] 创建 `backend/routers/system_logs.py`，定义路由签名（带 response_model）：
  - [ ] `GET /api/system/logs` - 获取系统日志列表
  - [ ] `GET /api/system/logs/{log_id}` - 获取日志详情
  - [ ] `POST /api/system/logs/export` - 导出日志
  - [ ] `DELETE /api/system/logs` - 清空日志（可选）
- [ ] 实现业务逻辑：
  - [ ] 日志查询（支持级别、模块、时间范围筛选）
  - [ ] 日志导出（Excel/CSV 格式）
  - [ ] 日志详情查看
- [ ] 在 `backend/main.py` 中注册路由
- [ ] 编写单元测试

### 1.2 审计日志增强 API

- [ ] 在 `backend/schemas/auth.py` 中新增 Pydantic 模型：
  - [ ] `AuditLogFilterRequest`
  - [ ] `AuditLogExportRequest`
  - [ ] `AuditLogDetailResponse`
- [ ] 在 `backend/routers/auth.py` 中增强现有端点：
  - [ ] `GET /api/auth/audit-logs` - 增强筛选功能
  - [ ] `GET /api/auth/audit-logs/{log_id}` - 获取审计日志详情（新增）
  - [ ] `POST /api/auth/audit-logs/export` - 导出审计日志（新增）
- [ ] 实现业务逻辑：
  - [ ] 增强筛选功能（操作类型、用户、时间范围、IP）
  - [ ] 实现详情查看（包含变更前后对比）
  - [ ] 实现导出功能（Excel/CSV 格式）
- [ ] 编写单元测试

---

## Phase 2: 安全设置 API（P0）

### 2.1 密码策略 API

- [ ] 在 `modules/core/db/schema.py` 定义 `SecurityConfig` 模型（新建表，参考 design.md 中的定义）
- [ ] 创建 Alembic 迁移：`alembic revision --autogenerate -m "add_security_config_table"`
- [ ] 创建 `backend/schemas/security.py`，定义 Pydantic 模型：
  - [ ] `PasswordPolicyResponse`
  - [ ] `PasswordPolicyUpdate`
- [ ] 创建 `backend/routers/security.py`，定义路由签名（带 response_model）：
  - [ ] `GET /api/system/security/password-policy`
  - [ ] `PUT /api/system/security/password-policy`
- [ ] 创建 `backend/services/security_config_service.py`，实现：
  - [ ] `get_password_policy()`：从 `SecurityConfig` 读取密码策略（带默认值回退）
- [ ] 实现业务逻辑：
  - [ ] 密码策略 CRUD（存储到 `SecurityConfig` 表）
  - [ ] 密码策略验证（在用户修改密码时应用，改为通过 `SecurityConfigService` 读取配置）
- [ ] 在 `backend/main.py` 中注册路由
- [ ] 更新 `backend/routers/auth.py`（使用 `SecurityConfigService` 应用密码策略验证）
- [ ] 更新 `backend/services/auth_service.py`（使用 `SecurityConfigService` 应用密码策略验证）
- [ ] 编写单元测试

### 2.2 登录限制 API

- [ ] 在 `backend/schemas/security.py` 中定义 Pydantic 模型：
  - [ ] `LoginRestrictionsResponse`
  - [ ] `LoginRestrictionsUpdate`
  - [ ] `IPWhitelistResponse`
  - [ ] `IPWhitelistUpdate`
- [ ] 在 `backend/routers/security.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/security/login-restrictions`
  - [ ] `PUT /api/system/security/login-restrictions`
  - [ ] `GET /api/system/security/ip-whitelist`
  - [ ] `POST /api/system/security/ip-whitelist`
  - [ ] `DELETE /api/system/security/ip-whitelist/{ip}`
- [ ] 更新 `backend/services/security_config_service.py`，实现：
  - [ ] `get_login_restrictions()`：从 `SecurityConfig` 读取登录限制配置（失败次数、锁定时间等，带默认值回退）
- [ ] 实现业务逻辑：
  - [ ] 登录限制配置 CRUD（存储到 `SecurityConfig` 表）
  - [ ] IP 白名单管理（存储到 `SecurityConfig` 表）
- [ ] 更新 `backend/routers/auth.py`（使用 `SecurityConfigService.get_login_restrictions()` 应用登录限制，移除硬编码常量）
- [ ] 编写单元测试

### 2.3 会话管理 API

- [ ] 在 `backend/schemas/security.py` 中定义 Pydantic 模型：
  - [ ] `SessionConfigResponse`
  - [ ] `SessionConfigUpdate`
- [ ] 在 `backend/routers/security.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/security/session-config`
  - [ ] `PUT /api/system/security/session-config`
- [ ] 更新 `backend/services/security_config_service.py`，实现：
  - [ ] `get_session_config()`：从 `SecurityConfig` 读取会话配置（超时时间、并发会话数，带默认值回退）
- [ ] 实现业务逻辑：
  - [ ] 会话配置 CRUD（存储到 `SecurityConfig` 表）
  - [ ] 在 JWT Token 生成时应用会话配置（修改登录逻辑）
  - [ ] 实现并发会话限制（登录时检查）
  - [ ] 实现会话超时检查（请求时检查，修改 `get_current_user` 依赖）
- [ ] 更新 `backend/routers/auth.py`（使用 `SecurityConfigService.get_session_config()` 应用会话配置）
- [ ] 更新 `backend/services/auth_service.py`（会话相关逻辑使用动态配置替代硬编码）
- [ ] 编写单元测试

### 2.4 2FA 配置 API（P2 - 可选）

- [ ] 在 `backend/schemas/security.py` 中定义 Pydantic 模型：
  - [ ] `TwoFactorConfigResponse`
  - [ ] `TwoFactorConfigUpdate`
- [ ] 在 `backend/routers/security.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/security/2fa-config`
  - [ ] `PUT /api/system/security/2fa-config`
- [ ] 实现业务逻辑：
  - [ ] 2FA 配置 CRUD
  - [ ] 2FA 验证逻辑（使用 TOTP 库）
- [ ] 编写单元测试

---

## Phase 3: 数据备份与恢复 API（P1）

### 3.1 数据备份 API

- [ ] 在 `modules/core/db/schema.py` 定义 `BackupRecord` 模型
- [ ] 创建 Alembic 迁移：`alembic revision --autogenerate -m "add_backup_records_table"`
- [ ] 创建 `backend/schemas/backup.py`，定义 Pydantic 模型：
  - [ ] `BackupCreateRequest`
  - [ ] `BackupResponse`
  - [ ] `BackupListResponse`
- [ ] 创建 `backend/routers/backup.py`，定义路由签名（带 response_model）：
  - [ ] `POST /api/system/backup` - 创建备份
  - [ ] `GET /api/system/backup` - 获取备份列表
  - [ ] `GET /api/system/backup/{backup_id}` - 获取备份详情
  - [ ] `GET /api/system/backup/{backup_id}/download` - 下载备份文件
- [ ] 实现业务逻辑：
  - [ ] Docker环境实现（容器内执行）：
    - [ ] 数据库备份：使用 `pg_dump` 连接 `postgres:5432`（Docker网络内）
    - [ ] 文件备份：备份挂载的volume（`/app/data`、`/app/downloads`、`/app/logs`、`/app/config`）
    - [ ] 备份存储：保存到 `/app/backups`（容器内路径）
  - [ ] 记录备份信息到数据库（生成备份清单和校验和SHA-256）
  - [ ] 备份列表查询（分页、筛选）
  - [ ] 备份文件下载
  - [ ] 备份文件完整性验证（校验和）
- [ ] 在 `backend/main.py` 中注册路由
- [ ] 编写单元测试

### 3.2 数据恢复 API

- [ ] 在 `backend/schemas/backup.py` 中定义 Pydantic 模型：
  - [ ] `RestoreRequest` - 恢复请求
    - [ ] `confirmed: bool` - 二次确认标志（必须为 True）
    - [ ] `confirmed_by: List[int]` - 确认的管理员ID列表（至少2个不同的管理员ID）
    - [ ] `force_outside_window: bool` - 是否在维护窗口外强制执行（默认 False）
    - [ ] `reason: Optional[str]` - 恢复原因说明（可选，最多500字符）
  - [ ] `RestoreResponse` - 恢复响应模型
    - [ ] `backup_id: int` - 备份ID
    - [ ] `status: str` - 恢复状态（pending/completed/failed）
    - [ ] `emergency_backup_id: Optional[int]` - 恢复前创建的紧急备份ID
    - [ ] `started_at: datetime` - 恢复开始时间
    - [ ] `completed_at: Optional[datetime]` - 恢复完成时间
    - [ ] `message: str` - 恢复结果消息
- [ ] 在 `backend/routers/backup.py` 中定义路由签名（带 response_model）：
  - [ ] `POST /api/system/backup/{backup_id}/restore` - 恢复备份
  - [ ] `GET /api/system/backup/{backup_id}/restore/status` - 获取恢复状态
- [ ] 实现业务逻辑：
  - [ ] 多重安全防护（必须全部满足）：
    - [ ] 维护窗口检查（默认凌晨2-4点，可配置，通过SystemConfig表）
    - [ ] 管理员权限（使用 `require_admin` 依赖）
    - [ ] 多重确认（至少2名管理员确认，验证管理员ID不同且都有管理员权限）
    - [ ] 交互确认（`RestoreRequest.confirmed == True`）
    - [ ] 备份文件完整性验证（验证备份文件存在性和校验和SHA-256）
    - [ ] 恢复前自动备份（自动创建紧急备份）
    - [ ] 超时控制（恢复操作最多1小时超时，超时自动回滚）
    - [ ] 操作通知（恢复前后发送通知给所有管理员）
  - [ ] Docker环境实现（容器内执行）：
    - [ ] 数据库恢复：使用 `psql` 连接 `postgres:5432` 执行SQL恢复
    - [ ] 文件恢复：解压文件备份到对应目录（`/app/data`、`/app/downloads`、`/app/logs`、`/app/config`）
  - [ ] 记录恢复操作到审计日志（包含恢复前后状态对比）
  - [ ] 恢复状态查询（支持实时进度，使用Celery异步任务）
- [ ] 编写单元测试

### 3.3 自动备份配置 API

- [ ] 在 `backend/schemas/backup.py` 中定义 Pydantic 模型：
  - [ ] `AutoBackupConfigResponse`
  - [ ] `AutoBackupConfigUpdate`
- [ ] 在 `backend/routers/backup.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/backup/config` - 获取自动备份配置
  - [ ] `PUT /api/system/backup/config` - 更新自动备份配置
- [ ] 实现业务逻辑：
  - [ ] 自动备份配置 CRUD
- [ ] 更新 `backend/tasks/scheduled_tasks.py`（集成自动备份）
- [ ] 编写单元测试

---

## Phase 4: 系统维护 API（P1）

### 4.1 缓存清理 API

- [ ] 创建 `backend/schemas/maintenance.py`，定义 Pydantic 模型：
  - [ ] `CacheClearRequest`
  - [ ] `CacheClearResponse`
  - [ ] `CacheStatusResponse`
- [ ] 创建 `backend/routers/maintenance.py`，定义路由签名（带 response_model）：
  - [ ] `GET /api/system/maintenance/cache/status` - 获取缓存状态
  - [ ] `POST /api/system/maintenance/cache/clear` - 清理缓存
- [ ] 实现业务逻辑：
  - [ ] Redis 缓存清理
  - [ ] 应用缓存清理
  - [ ] 缓存状态查询
- [ ] 在 `backend/main.py` 中注册路由
- [ ] 编写单元测试

### 4.2 数据清理 API

- [ ] 在 `backend/schemas/maintenance.py` 中定义 Pydantic 模型：
  - [ ] `DataCleanRequest`
  - [ ] `DataCleanResponse`
  - [ ] `DataStatusResponse`
- [ ] 在 `backend/routers/maintenance.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/maintenance/data/status` - 获取数据状态
  - [ ] `POST /api/system/maintenance/data/clean` - 清理数据
- [ ] 实现业务逻辑：
  - [ ] 日志清理（按时间范围）
  - [ ] 临时数据清理
  - [ ] 数据状态查询
- [ ] 编写单元测试

### 4.3 系统升级 API（P2 - 可选）

- [ ] 在 `backend/schemas/maintenance.py` 中定义 Pydantic 模型：
  - [ ] `UpgradeCheckResponse`
  - [ ] `UpgradeRequest`
  - [ ] `UpgradeResponse`
- [ ] 在 `backend/routers/maintenance.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/maintenance/upgrade/check` - 检查系统升级
  - [ ] `POST /api/system/maintenance/upgrade` - 执行系统升级
- [ ] 实现业务逻辑：
  - [ ] 版本检查（从 GitHub/GitLab 获取最新版本）
  - [ ] 升级流程（备份、下载、安装、验证）
- [ ] 编写单元测试

---

## Phase 5: 通知配置 API（P2）

### 5.1 SMTP 配置 API

- [ ] 在 `modules/core/db/schema.py` 定义 `SMTPConfig` 模型
- [ ] 创建 Alembic 迁移：`alembic revision --autogenerate -m "add_smtp_config_table"`
- [ ] 创建 `backend/schemas/notification_config.py`，定义 Pydantic 模型：
  - [ ] `SMTPConfigResponse`
  - [ ] `SMTPConfigUpdate`
  - [ ] `TestEmailRequest`
- [ ] 创建 `backend/routers/notification_config.py`，定义路由签名（带 response_model）：
  - [ ] `GET /api/system/notification/smtp-config`
  - [ ] `PUT /api/system/notification/smtp-config`
  - [ ] `POST /api/system/notification/test-email`
- [ ] 实现业务逻辑：
  - [ ] SMTP 配置 CRUD
  - [ ] SMTP 连接测试
  - [ ] 测试邮件发送
- [ ] 在 `backend/main.py` 中注册路由
- [ ] 编写单元测试

### 5.2 通知模板 API

- [ ] 在 `modules/core/db/schema.py` 定义 `NotificationTemplate` 模型
- [ ] 创建 Alembic 迁移：`alembic revision --autogenerate -m "add_notification_templates_table"`
- [ ] 在 `backend/schemas/notification_config.py` 中定义 Pydantic 模型：
  - [ ] `NotificationTemplateResponse`
  - [ ] `NotificationTemplateCreate`
  - [ ] `NotificationTemplateUpdate`
- [ ] 在 `backend/routers/notification_config.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/notification/templates`
  - [ ] `POST /api/system/notification/templates`
  - [ ] `GET /api/system/notification/templates/{template_id}`
  - [ ] `PUT /api/system/notification/templates/{template_id}`
  - [ ] `DELETE /api/system/notification/templates/{template_id}`
- [ ] 实现业务逻辑：
  - [ ] 通知模板 CRUD
  - [ ] 变量替换（如 `{{user_name}}`、`{{order_id}}`）
- [ ] 编写单元测试

### 5.3 告警规则 API

- [ ] 在 `modules/core/db/schema.py` 定义 `AlertRule` 模型
- [ ] 创建 Alembic 迁移：`alembic revision --autogenerate -m "add_alert_rules_table"`
- [ ] 在 `backend/schemas/notification_config.py` 中定义 Pydantic 模型：
  - [ ] `AlertRuleResponse`
  - [ ] `AlertRuleCreate`
  - [ ] `AlertRuleUpdate`
- [ ] 在 `backend/routers/notification_config.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/notification/alert-rules`
  - [ ] `POST /api/system/notification/alert-rules`
  - [ ] `GET /api/system/notification/alert-rules/{rule_id}`
  - [ ] `PUT /api/system/notification/alert-rules/{rule_id}`
  - [ ] `DELETE /api/system/notification/alert-rules/{rule_id}`
- [ ] 实现业务逻辑：
  - [ ] 告警规则 CRUD
  - [ ] 告警规则触发逻辑（与监控系统集成）
- [ ] 编写单元测试

---

## Phase 6: 系统配置增强 API（P1）

### 6.1 系统基础配置 API

- [ ] 在 `modules/core/db/schema.py` 定义 `SystemConfig` 模型
- [ ] 创建 Alembic 迁移：`alembic revision --autogenerate -m "add_system_config_table"`
- [ ] 在 `backend/schemas/system.py` 中定义 Pydantic 模型：
  - [ ] `SystemConfigResponse`
  - [ ] `SystemConfigUpdate`
- [ ] 在 `backend/routers/system.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/config` - 获取系统基础配置
  - [ ] `PUT /api/system/config` - 更新系统基础配置
- [ ] 实现业务逻辑：
  - [ ] 系统基础配置 CRUD（系统名称、版本、时区、语言、货币）
- [ ] 编写单元测试

### 6.2 数据库配置 API

- [ ] 在 `backend/schemas/system.py` 中定义 Pydantic 模型：
  - [ ] `DatabaseConfigResponse`
  - [ ] `DatabaseConfigUpdate`
  - [ ] `DatabaseConnectionTestResponse`
- [ ] 在 `backend/routers/system.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/database/config` - 获取数据库配置
  - [ ] `PUT /api/system/database/config` - 更新数据库配置
  - [ ] `POST /api/system/database/test-connection` - 测试数据库连接
- [ ] 实现业务逻辑：
  - [ ] 数据库配置 CRUD（连接信息）
  - [ ] 数据库连接测试
- [ ] 编写单元测试

---

## Phase 7: 权限管理增强 API（P1）

### 7.1 权限树 API

- [ ] 在 `backend/schemas/auth.py` 中定义 Pydantic 模型：
  - [ ] `PermissionTreeNode`
  - [ ] `PermissionTreeResponse`
- [ ] 创建或更新 `backend/routers/permissions.py`，定义路由签名（带 response_model）：
  - [ ] `GET /api/permissions/tree` - 获取权限树
- [ ] 实现业务逻辑：
  - [ ] 权限树构建（层级结构）
  - [ ] 支持按模块分组
- [ ] 在 `backend/main.py` 中注册路由
- [ ] 编写单元测试

### 7.2 权限配置 / 预定义权限查询 API

- [ ] 确认权限存储方案：默认使用 `DimRole.permissions` JSON 字段（不新增权限表）
- [ ] 如需要权限元数据（名称、描述、分类），评估是否新增 `DimPermission` 表（可选，P2）
- [ ] 在 `backend/schemas/permission.py` 中定义 Pydantic 模型：
  - [ ] `PermissionResponse`（权限代码、名称、描述、分类）
  - [ ] `PermissionTreeResponse`（如需要，以树形结构返回）
  - [ ] `PermissionListResponse`
- [ ] 在 `backend/routers/permission.py` 中定义路由签名（带 response_model）：
  - [ ] `GET /api/system/permissions` - 获取权限列表（系统预定义权限列表）
  - [ ] `GET /api/system/permissions/tree` - 获取权限树（层级结构）
- [ ] 实现业务逻辑：
  - [ ] 从系统预定义权限列表返回权限数据（可以是常量或配置）
  - [ ] 支持树形结构（按模块/功能分组）
  - [ ] **注意**：权限分配由角色管理 API 完成（通过 `/api/roles` 更新 `DimRole.permissions` 字段）
- [ ] 编写单元测试

---

## 通用任务（每个 Phase 完成后）

- [ ] 运行 SSOT 验证：`python scripts/verify_architecture_ssot.py`（期望: 100%）
- [ ] 运行 Contract-First 验证：`python scripts/verify_contract_first.py`
- [ ] 运行 Emoji 检查：`python scripts/verify_no_emoji.py`
- [ ] 更新 API 文档（OpenAPI 自动生成）
- [ ] 更新 CHANGELOG.md

---

**最后更新**: 2026-01-06  
**维护**: AI Agent Team  
**状态**: 📝 待实施
