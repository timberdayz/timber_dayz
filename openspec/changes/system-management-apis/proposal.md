# Change: 系统管理模块后端 API 实现

> **状态**: 📝 提案阶段  
> **优先级**: P1（必须完成，分阶段实施）  
> **创建时间**: 2026-01-06  
> **预计时间**: 16-20 小时（可按 Phase 拆分执行）

## Why

当前系统管理模块前端设计已完成，但后端 API 实现不完整，存在以下问题：

1. **系统日志 API 缺失**

   - 前端需要查看系统日志（级别、模块、时间范围筛选）
   - 前端需要导出日志功能
   - 当前只有基础的审计日志 API，缺少系统日志 API

2. **安全设置 API 缺失**

   - 前端需要配置密码策略（最小长度、复杂度、过期时间）
   - 前端需要配置登录限制（失败次数、锁定时间、IP 白名单）
   - 前端需要配置会话管理（超时时间、并发限制）
   - 前端需要配置 2FA（可选）
   - 当前完全没有安全设置相关的 API

3. **数据备份与恢复 API 缺失**

   - 前端需要通过 API 进行数据备份（手动/自动）
   - 前端需要查看备份历史
   - 前端需要通过 API 恢复备份
   - 当前只有脚本层面的备份（`scripts/backup_database.sh`），缺少 API 接口

4. **系统维护 API 缺失**

   - 前端需要清理缓存（Redis 缓存、应用缓存）
   - 前端需要清理数据（日志、临时数据）
   - 前端需要系统升级功能
   - 当前完全没有系统维护相关的 API

5. **通知配置 API 缺失**

   - 前端需要配置 SMTP 服务器
   - 前端需要管理通知模板
   - 前端需要配置告警规则
   - 当前只有通知发送 API，缺少配置管理 API

6. **系统配置增强 API 缺失**

   - 前端需要系统基础配置 CRUD（系统名称、版本、时区、语言、货币）
   - 前端需要数据库配置 CRUD（连接信息、连接测试）
   - 当前只有系统常量 API（`/api/system/platforms`等），缺少配置 CRUD

7. **权限管理增强 API 缺失**

   - 前端需要权限树 API（层级结构）
   - 前端需要权限 CRUD API
   - 当前权限管理功能在角色管理 API 中，缺少独立的权限管理 API

8. **审计日志增强 API 缺失**
   - 前端需要审计日志筛选（操作类型、用户、时间范围、IP）
   - 前端需要审计日志导出功能
   - 前端需要审计日志详情查看
   - 当前只有基础的审计日志列表 API（`/api/auth/audit-logs`），缺少筛选和导出功能

以上问题导致前端系统管理模块无法完整实现，影响系统的可管理性和安全性。需要按照**Contract-First 原则**，先定义 API 契约，再实现业务逻辑。

---

## What Changes

本提案按照 Contract-First 开发原则，分阶段实现系统管理模块的后端 API。

### Contract-First 开发流程（强制）

每个 Phase 的开发顺序：

1. **定义数据模型** → `modules/core/db/schema.py` + Alembic 迁移
2. **定义 API 契约** → `backend/schemas/` 中的 Pydantic 模型（禁止在 routers/定义）
3. **定义路由签名** → `@router` + `response_model`（占位实现，response_model 必填）
4. **实现业务逻辑** → 填充路由函数
5. **编写测试** → 验证契约

### Phase 1: 系统日志与审计日志增强 API（P0 - 最高优先级）

> 目标：**先实现日志查看功能**——支持系统日志查看、筛选、导出，增强审计日志功能。

#### 1.1 系统日志 API

**目标**：提供系统日志查看、筛选、导出功能。

**工作内容**：

- **定义数据模型**：

  - 在 `modules/core/db/schema.py` 定义 `SystemLog` 模型（新建表）
  - **与现有日志系统的关系**：
    - **日志记录方式**：
      - **方案 A（推荐）**：修改 `modules/core/logger.py`，添加数据库日志处理器（DatabaseHandler），自动将日志写入 `SystemLog` 表
        - 优点：自动记录所有应用日志，无需手动调用
        - 缺点：需要修改核心日志模块，可能影响性能
        - 实现：使用 SQLAlchemy 异步写入，避免阻塞主线程
      - **方案 B（降级）**：`SystemLog` 表仅用于手动记录关键系统事件（通过 API 或服务层调用）
        - 优点：不影响现有日志系统，实现简单
        - 缺点：需要手动调用，可能遗漏重要日志
    - **文件日志**：`modules/core/logger.py` 的日志记录器继续写入文件日志（无论是否启用数据库日志）
    - **审计日志**：`FactAuditLog` 表用于记录用户操作审计，与系统日志（应用运行日志）不同
    - **任务日志**：`CollectionTaskLog` 表用于记录采集任务日志，与系统日志不同
    - **系统日志 API**：主要用于查询数据库中的系统日志，文件日志通过服务器日志文件查看
  - 创建 Alembic 迁移

- **定义 API 契约**：

  - 在 `backend/schemas/system.py` 中定义：
    - `SystemLogResponse` - 系统日志响应模型
    - `SystemLogListResponse` - 系统日志列表响应（分页）
    - `SystemLogFilterRequest` - 系统日志筛选请求
    - `SystemLogExportRequest` - 系统日志导出请求

- **定义路由签名**：

  - 在 `backend/routers/system_logs.py` 中定义（新建文件）：
    - `GET /api/system/logs` - 获取系统日志列表（分页、筛选）
    - `GET /api/system/logs/{log_id}` - 获取日志详情
    - `POST /api/system/logs/export` - 导出日志（Excel/CSV）
    - `DELETE /api/system/logs` - 清空日志（可选，谨慎使用）

  **注意**：路由前缀统一使用 `/api/system/*`，与现有路由保持一致。需要修改 `backend/main.py` 中 `system.router` 的注册方式，添加 `/api` 前缀（或修改 `backend/routers/system.py` 中的 router 定义，改为 `prefix="/api/system"`）。

- **实现业务逻辑**：
  - 实现日志查询（支持级别、模块、时间范围筛选）
  - 实现日志导出（Excel/CSV 格式）
  - 实现日志详情查看
  - **限流配置**：日志导出 API 需要添加限流（防止大量导出导致性能问题）
  - **输入验证**：时间范围、日志级别等参数需要验证格式

**文件变更**：

- 新建：`backend/schemas/system.py`（如果不存在）
- 新建：`backend/routers/system_logs.py`
- 更新：`backend/main.py`（注册路由）
- 更新：`modules/core/db/schema.py`（如需要新增表）

#### 1.2 审计日志增强 API

**目标**：增强现有审计日志 API，支持筛选、导出、详情查看。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/auth.py` 中新增：
    - `AuditLogFilterRequest` - 审计日志筛选请求
    - `AuditLogExportRequest` - 审计日志导出请求
    - `AuditLogDetailResponse` - 审计日志详情响应（包含变更前后对比）

- **定义路由签名**：

  - 在 `backend/routers/auth.py` 中增强现有端点：
    - `GET /api/auth/audit-logs` - 增强筛选功能（操作类型、用户、时间范围、IP）
    - `GET /api/auth/audit-logs/{log_id}` - 获取审计日志详情（新增）
    - `POST /api/auth/audit-logs/export` - 导出审计日志（新增）

- **实现业务逻辑**：
  - 增强筛选功能（支持多维度筛选）
  - 实现详情查看（包含变更前后对比）
  - 实现导出功能（Excel/CSV 格式）

**文件变更**：

- 更新：`backend/schemas/auth.py`
- 更新：`backend/routers/auth.py`

---

### Phase 2: 安全设置 API（P0 - 最高优先级）

> 目标：**实现安全配置功能**——支持密码策略、登录限制、会话管理、2FA 配置。

#### 2.1 密码策略 API

**目标**：提供密码策略配置功能。

**工作内容**：

- **定义数据模型**：

  - 在 `modules/core/db/schema.py` 定义 `SecurityConfig` 模型（新建表，参考 `design.md` 中的定义）
    - **表结构**：`config_key`（唯一）、`config_value`（JSONB）、`description`、`updated_at`、`updated_by`
    - **配置键**：`password_policy`、`login_restrictions`、`session_config`、`2fa_config`
  - 创建 Alembic 迁移

- **定义 API 契约**：

  - 在 `backend/schemas/security.py` 中定义（新建文件）：
    - `PasswordPolicyResponse` - 密码策略响应模型
    - `PasswordPolicyUpdate` - 密码策略更新请求

- **定义路由签名**：

  - 在 `backend/routers/security.py` 中定义（新建文件）：
    - `GET /api/system/security/password-policy` - 获取密码策略
    - `PUT /api/system/security/password-policy` - 更新密码策略
  - **注意**：所有路由必须使用 `require_admin` 依赖（从 `backend.routers.users` 导入，不要重新定义）

- **实现业务逻辑**：
  - 实现密码策略 CRUD（存储到 `SecurityConfig` 表）
  - **重要**：修改现有硬编码密码策略，改为从 `SecurityConfig` 表读取配置
    - 现有代码：`backend/routers/auth.py` 和 `backend/services/auth_service.py` 中可能有硬编码的密码策略
    - 修改方案：创建 `SecurityConfigService`，提供 `get_password_policy()` 方法
    - 向后兼容：如果配置不存在，使用默认值（最小长度8、需要数字和字母、90天过期）
  - 实现密码策略验证（在用户修改密码时应用）

**文件变更**：

- 新建：`backend/schemas/security.py`
- 新建：`backend/routers/security.py`
- 新建：`backend/services/security_config_service.py`（安全配置服务类，提供 `get_password_policy()` 等方法）
- 更新：`modules/core/db/schema.py`（添加 `SecurityConfig` 模型）
- 更新：`backend/main.py`（注册路由）
- 更新：`backend/routers/auth.py`（修改密码策略验证逻辑，使用 `SecurityConfigService`）
- 更新：`backend/services/auth_service.py`（修改密码策略验证逻辑，使用 `SecurityConfigService`）

#### 2.2 登录限制 API

**目标**：提供登录限制配置功能。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/security.py` 中定义：
    - `LoginRestrictionsResponse` - 登录限制响应模型
    - `LoginRestrictionsUpdate` - 登录限制更新请求
    - `IPWhitelistResponse` - IP 白名单响应模型
    - `IPWhitelistUpdate` - IP 白名单更新请求

- **定义路由签名**：

  - 在 `backend/routers/security.py` 中定义：
    - `GET /api/system/security/login-restrictions` - 获取登录限制配置
    - `PUT /api/system/security/login-restrictions` - 更新登录限制配置
    - `GET /api/system/security/ip-whitelist` - 获取 IP 白名单
    - `POST /api/system/security/ip-whitelist` - 添加 IP 到白名单
    - `DELETE /api/system/security/ip-whitelist/{ip}` - 从白名单移除 IP
  - **路由命名规范**：统一使用连字符（kebab-case），如 `/api/system/security/ip-whitelist`
  - **限流配置**：所有安全配置 API 需要添加限流（使用 `@role_based_rate_limit`）

- **实现业务逻辑**：
  - 实现登录限制配置 CRUD（存储到 `SecurityConfig` 表）
  - **重要**：修改现有硬编码登录限制策略，改为从 `SecurityConfig` 表读取配置
    - 现有代码：`backend/routers/auth.py` 中有硬编码的登录限制（`MAX_FAILED_ATTEMPTS = 5`、`LOCKOUT_DURATION_MINUTES = 30`）
    - 修改方案：使用 `SecurityConfigService.get_login_restrictions()` 方法获取配置
    - 向后兼容：如果配置不存在，使用默认值（5次失败、锁定30分钟）
  - 实现 IP 白名单管理（存储到 `SecurityConfig` 表，JSON 数组格式）
  - 在登录逻辑中应用登录限制（失败次数、锁定时间、IP 白名单，修改 `backend/routers/auth.py` 中的登录逻辑，使用动态配置）

**文件变更**：

- 更新：`backend/schemas/security.py`
- 更新：`backend/routers/security.py`
- 更新：`backend/services/security_config_service.py`（添加 `get_login_restrictions()` 方法）
- 更新：`backend/routers/auth.py`（修改登录逻辑，使用动态配置替代硬编码策略）

#### 2.3 会话管理 API

**目标**：提供会话管理配置功能。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/security.py` 中定义：
    - `SessionConfigResponse` - 会话配置响应模型
    - `SessionConfigUpdate` - 会话配置更新请求

- **定义路由签名**：

  - 在 `backend/routers/security.py` 中定义：
    - `GET /api/system/security/session-config` - 获取会话配置
    - `PUT /api/system/security/session-config` - 更新会话配置

- **实现业务逻辑**：
  - 实现会话配置 CRUD（存储到 `SecurityConfig` 表）
  - **重要**：修改现有会话管理逻辑，改为从 `SecurityConfig` 表读取配置
    - 现有代码：`backend/routers/auth.py` 和 `backend/services/auth_service.py` 中可能有硬编码的会话超时时间
    - 修改方案：使用 `SecurityConfigService.get_session_config()` 方法获取配置
    - 向后兼容：如果配置不存在，使用默认值（15分钟超时、最多5个并发会话）
  - 在 JWT Token 生成时应用会话配置（超时时间，修改 `backend/routers/auth.py` 中的登录逻辑）
  - 实现并发会话限制（在登录时检查，修改登录逻辑）
  - 实现会话超时检查（在用户请求时验证，修改 `get_current_user` 依赖）

**文件变更**：

- 更新：`backend/schemas/security.py`
- 更新：`backend/routers/security.py`
- 更新：`backend/services/security_config_service.py`（添加 `get_session_config()` 方法）
- 更新：`backend/routers/auth.py`（修改会话管理逻辑，使用动态配置替代硬编码策略）
- 更新：`backend/services/auth_service.py`（修改会话管理逻辑，使用动态配置替代硬编码策略）

#### 2.4 2FA 配置 API（P2 - 可选）

**目标**：提供 2FA 配置功能（可选实现）。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/security.py` 中定义：
    - `TwoFactorConfigResponse` - 2FA 配置响应模型
    - `TwoFactorConfigUpdate` - 2FA 配置更新请求

- **定义路由签名**：

  - 在 `backend/routers/security.py` 中定义：
    - `GET /api/system/security/2fa-config` - 获取 2FA 配置
    - `PUT /api/system/security/2fa-config` - 更新 2FA 配置

- **实现业务逻辑**：
  - 实现 2FA 配置 CRUD
  - 实现 2FA 验证逻辑（可选，使用 TOTP 库）

**文件变更**：

- 更新：`backend/schemas/security.py`
- 更新：`backend/routers/security.py`

---

### Phase 3: 数据备份与恢复 API（P1 - 高优先级）

> 目标：**实现数据备份管理功能**——支持通过 API 进行备份、恢复、备份历史管理。

#### 3.1 数据备份 API

**目标**：提供数据备份管理功能（优先调用脚本层功能，如果脚本不存在则直接实现备份逻辑）。

**工作内容**：

- **定义数据模型**：

  - 在 `modules/core/db/schema.py` 定义 `BackupRecord` 模型
  - 创建 Alembic 迁移

- **定义 API 契约**：

  - 在 `backend/schemas/backup.py` 中定义（新建文件）：
    - `BackupCreateRequest` - 创建备份请求
    - `BackupResponse` - 备份响应模型
    - `BackupListResponse` - 备份列表响应（分页）

- **定义路由签名**：

  - 在 `backend/routers/backup.py` 中定义（新建文件）：
    - `POST /api/system/backup` - 创建备份
    - `GET /api/system/backup` - 获取备份列表
    - `GET /api/system/backup/{backup_id}` - 获取备份详情
    - `GET /api/system/backup/{backup_id}/download` - 下载备份文件

- **实现业务逻辑**：
  - 实现备份创建：
    - **优先方案**：如果 `scripts/backup_all.sh` 存在（由 `improve-infra-and-ops` 提案实现），则调用脚本执行备份
      - **注意**：`improve-infra-and-ops` 提案中计划创建统一备份脚本，但文件名可能为 `backup_all.sh` 或其他名称
      - **实现时**：需要检查脚本是否存在，如果不存在则使用降级方案
    - **降级方案**：如果脚本不存在，API 直接实现备份逻辑（数据库备份使用 `pg_dump`，文件备份使用 `tar`/`zip`）
      - 数据库备份：使用 `pg_dump` 命令导出 PostgreSQL 数据库
      - 文件备份：使用 `tar`/`zip` 压缩关键目录（如 `uploads/`、`logs/` 等）
      - 备份文件命名：`backup_{timestamp}_{type}.tar.gz` 或 `backup_{timestamp}_{type}.zip`
    - 备份完成后记录到 `BackupRecord` 表，生成备份清单和校验和
  - 实现备份列表查询（分页、筛选）
  - 实现备份记录管理（删除、详情）
  - 实现备份文件完整性验证（校验和）
  - 实现备份文件下载

**文件变更**：

- 新建：`backend/schemas/backup.py`
- 新建：`backend/routers/backup.py`
- 更新：`modules/core/db/schema.py`
- 更新：`backend/main.py`（注册路由）

#### 3.2 数据恢复 API

**目标**：提供数据恢复功能（谨慎实现，多重安全防护）。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/backup.py` 中定义：
    - `RestoreRequest` - 恢复请求
    - `RestoreResponse` - 恢复响应模型

- **定义路由签名**：

  - 在 `backend/routers/backup.py` 中定义：
    - `POST /api/system/backup/{backup_id}/restore` - 恢复备份
    - `GET /api/system/backup/{backup_id}/restore/status` - 获取恢复状态

- **实现业务逻辑**：
  - **多重安全防护**（必须全部满足）：
    1. 环境变量检查：禁止在生产环境执行（`ENVIRONMENT == "production"` 时拒绝）
    2. 管理员权限：仅管理员可执行（使用 `require_admin` 依赖）
    3. 交互确认：需要二次确认（`RestoreRequest.confirmed == True`）
    4. 备份文件完整性验证：验证备份文件存在性和校验和
    5. 恢复前自动备份：执行恢复前自动创建紧急备份
    6. 超时控制：恢复操作最多 1 小时超时
  - 调用恢复脚本执行恢复
  - 记录恢复操作到审计日志（包含恢复前后状态对比）
  - 实现恢复状态查询（支持实时进度）

**文件变更**：

- 更新：`backend/schemas/backup.py`
- 更新：`backend/routers/backup.py`

#### 3.3 自动备份配置 API

**目标**：提供自动备份配置功能。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/backup.py` 中定义：
    - `AutoBackupConfigResponse` - 自动备份配置响应模型
    - `AutoBackupConfigUpdate` - 自动备份配置更新请求

- **定义路由签名**：

  - 在 `backend/routers/backup.py` 中定义：
    - `GET /api/system/backup/config` - 获取自动备份配置
    - `PUT /api/system/backup/config` - 更新自动备份配置

- **实现业务逻辑**：
  - 实现自动备份配置 CRUD
  - 与 Celery 定时任务集成（`backend/tasks/scheduled_tasks.py`）

**文件变更**：

- 更新：`backend/schemas/backup.py`
- 更新：`backend/routers/backup.py`
- 更新：`backend/tasks/scheduled_tasks.py`（集成自动备份）

---

### Phase 4: 系统维护 API（P1 - 高优先级）

> 目标：**实现系统维护功能**——支持缓存清理、数据清理、系统升级。

#### 4.1 缓存清理 API

**目标**：提供缓存清理功能。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/maintenance.py` 中定义（新建文件）：
    - `CacheClearRequest` - 缓存清理请求
    - `CacheClearResponse` - 缓存清理响应模型
    - `CacheStatusResponse` - 缓存状态响应模型

- **定义路由签名**：

  - 在 `backend/routers/maintenance.py` 中定义（新建文件）：
    - `GET /api/system/maintenance/cache/status` - 获取缓存状态
    - `POST /api/system/maintenance/cache/clear` - 清理缓存

- **实现业务逻辑**：
  - 实现 Redis 缓存清理
  - 实现应用缓存清理
  - 实现缓存状态查询

**文件变更**：

- 新建：`backend/schemas/maintenance.py`
- 新建：`backend/routers/maintenance.py`
- 更新：`backend/main.py`（注册路由）

#### 4.2 数据清理 API

**目标**：提供数据清理功能。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/maintenance.py` 中定义：
    - `DataCleanRequest` - 数据清理请求
    - `DataCleanResponse` - 数据清理响应模型
    - `DataStatusResponse` - 数据状态响应模型

- **定义路由签名**：

  - 在 `backend/routers/maintenance.py` 中定义：
    - `GET /api/system/maintenance/data/status` - 获取数据状态
    - `POST /api/system/maintenance/data/clean` - 清理数据

- **实现业务逻辑**：
  - **可清理的数据类型**：
    1. **系统日志**（`system_logs` 表）：按时间范围清理（保留最近 N 天，默认 30 天）
    2. **任务日志**（`collection_task_logs` 表）：清理已完成任务的历史日志（保留最近 N 天，默认 90 天）
    3. **临时数据**：
       - `temp/` 目录下的临时文件（按时间清理，默认 7 天）
       - `staging_*` 表数据（清理已处理的数据，保留最近 N 天，默认 7 天）
    4. **审计日志**：**禁止清理**（审计日志必须永久保留，仅支持归档）
  - **清理策略**：
    - 按时间范围清理（保留最近 N 天）
    - 按数据大小清理（可选，当数据超过阈值时）
    - 清理前必须二次确认（防止误操作）
    - 清理操作记录到审计日志
  - **不可逆性警告**：所有清理操作不可逆，清理前必须明确提示用户
  - 实现数据状态查询（显示各类型数据的数量和大小）

**文件变更**：

- 更新：`backend/schemas/maintenance.py`
- 更新：`backend/routers/maintenance.py`

#### 4.3 系统升级 API（P3 - 不推荐实现）

**目标**：提供系统升级功能（**不推荐通过 API 实现**，安全风险极高）。

**安全警告**：

- ⚠️ **高风险操作**：通过 API 执行系统升级存在严重安全风险（恶意代码注入、系统破坏）
- ⚠️ **建议方案**：系统升级应通过 CI/CD 流程或手动操作完成，不建议通过 API 实现

**如果必须实现，需要以下安全措施**：

- **定义 API 契约**：

  - 在 `backend/schemas/maintenance.py` 中定义：
    - `UpgradeCheckResponse` - 升级检查响应模型
    - `UpgradeRequest` - 升级请求（必须包含多重确认）
    - `UpgradeResponse` - 升级响应模型

- **定义路由签名**：

  - 在 `backend/routers/maintenance.py` 中定义：
    - `GET /api/system/maintenance/upgrade/check` - 检查系统升级（仅查看，不执行）
    - `POST /api/system/maintenance/upgrade` - 执行系统升级（需要多重管理员确认）

- **实现业务逻辑**（必须全部实现）：
  1. **版本验证**：仅允许从可信源（GitHub Release）下载，验证发布者签名
  2. **多重确认**：需要至少 2 名管理员确认才能执行
  3. **自动备份**：升级前自动创建完整备份
  4. **沙箱测试**：在独立沙箱环境中测试升级包
  5. **回滚机制**：升级失败时自动回滚到上一个版本
  6. **审计日志**：记录所有升级操作（包含升级前后版本对比）

**文件变更**：

- 更新：`backend/schemas/maintenance.py`
- 更新：`backend/routers/maintenance.py`

**注意**：本功能标记为 P3，建议在 Phase 7 之后评估是否需要实现。

---

### Phase 5: 通知配置 API（P2 - 中优先级）

> 目标：**实现通知配置功能**——支持 SMTP 配置、通知模板、告警规则。

**与现有通知 API 的关系**：

- **现有 API**：`/api/notifications`（`backend/routers/notifications.py`）用于通知管理（CRUD 操作）
  - 获取通知列表、标记已读、删除通知等
  - 管理用户接收到的通知消息
- **本提案 API**：`/api/system/notification/*` 用于通知配置（系统配置）
  - SMTP 服务器配置（发送通知的邮件服务器）
  - 通知模板管理（通知内容的模板）
  - 告警规则配置（何时触发通知）
- **关系**：通知配置 API 配置了"如何发送通知"，通知管理 API 管理"已发送的通知消息"

#### 5.1 SMTP 配置 API

**目标**：提供 SMTP 配置功能。

**工作内容**：

- **定义数据模型**：

  - 在 `modules/core/db/schema.py` 定义 `SMTPConfig` 模型
  - 创建 Alembic 迁移

- **定义 API 契约**：

  - 在 `backend/schemas/notification_config.py` 中定义（新建文件）：
    - `SMTPConfigResponse` - SMTP 配置响应模型
    - `SMTPConfigUpdate` - SMTP 配置更新请求
    - `TestEmailRequest` - 测试邮件请求

- **定义路由签名**：

  - 在 `backend/routers/notification_config.py` 中定义（新建文件）：
    - `GET /api/system/notification/smtp-config` - 获取 SMTP 配置
    - `PUT /api/system/notification/smtp-config` - 更新 SMTP 配置
    - `POST /api/system/notification/test-email` - 发送测试邮件

- **实现业务逻辑**：
  - 实现 SMTP 配置 CRUD
  - **敏感数据加密**：SMTP 密码必须加密存储（使用 `EncryptionService`）
  - 实现 SMTP 连接测试（更新配置前必须测试连接）
  - 实现测试邮件发送
  - **输入验证**：SMTP 服务器地址、端口、邮箱格式等需要验证

**文件变更**：

- 新建：`backend/schemas/notification_config.py`
- 新建：`backend/routers/notification_config.py`
- 更新：`modules/core/db/schema.py`
- 更新：`backend/main.py`（注册路由）

#### 5.2 通知模板 API

**目标**：提供通知模板管理功能。

**工作内容**：

- **定义数据模型**：

  - 在 `modules/core/db/schema.py` 定义 `NotificationTemplate` 模型
  - 创建 Alembic 迁移

- **定义 API 契约**：

  - 在 `backend/schemas/notification_config.py` 中定义：
    - `NotificationTemplateResponse` - 通知模板响应模型
    - `NotificationTemplateCreate` - 通知模板创建请求
    - `NotificationTemplateUpdate` - 通知模板更新请求

- **定义路由签名**：

  - 在 `backend/routers/notification_config.py` 中定义：
    - `GET /api/system/notification/templates` - 获取通知模板列表
    - `POST /api/system/notification/templates` - 创建通知模板
    - `GET /api/system/notification/templates/{template_id}` - 获取通知模板详情
    - `PUT /api/system/notification/templates/{template_id}` - 更新通知模板
    - `DELETE /api/system/notification/templates/{template_id}` - 删除通知模板

- **实现业务逻辑**：
  - 实现通知模板 CRUD
  - 支持变量替换（如 `{{user_name}}`、`{{order_id}}`）

**文件变更**：

- 更新：`backend/schemas/notification_config.py`
- 更新：`backend/routers/notification_config.py`
- 更新：`modules/core/db/schema.py`

#### 5.3 告警规则 API

**目标**：提供告警规则配置功能。

**工作内容**：

- **定义数据模型**：

  - 在 `modules/core/db/schema.py` 定义 `AlertRule` 模型
  - 创建 Alembic 迁移

- **定义 API 契约**：

  - 在 `backend/schemas/notification_config.py` 中定义：
    - `AlertRuleResponse` - 告警规则响应模型
    - `AlertRuleCreate` - 告警规则创建请求
    - `AlertRuleUpdate` - 告警规则更新请求

- **定义路由签名**：

  - 在 `backend/routers/notification_config.py` 中定义：
    - `GET /api/system/notification/alert-rules` - 获取告警规则列表
    - `POST /api/system/notification/alert-rules` - 创建告警规则
    - `GET /api/system/notification/alert-rules/{rule_id}` - 获取告警规则详情
    - `PUT /api/system/notification/alert-rules/{rule_id}` - 更新告警规则
    - `DELETE /api/system/notification/alert-rules/{rule_id}` - 删除告警规则

- **实现业务逻辑**：
  - 实现告警规则 CRUD
  - 实现告警规则触发逻辑（与监控系统集成）

**文件变更**：

- 更新：`backend/schemas/notification_config.py`
- 更新：`backend/routers/notification_config.py`
- 更新：`modules/core/db/schema.py`

---

### Phase 6: 系统配置增强 API（P1 - 高优先级）

> 目标：**增强系统配置功能**——支持系统基础配置和数据库配置的 CRUD。

#### 6.1 系统基础配置 API

**目标**：提供系统基础配置 CRUD 功能。

**工作内容**：

- **定义数据模型**：

  - 在 `modules/core/db/schema.py` 定义 `SystemConfig` 模型
  - 创建 Alembic 迁移

- **定义 API 契约**：

  - 在 `backend/schemas/system.py` 中定义：
    - `SystemConfigResponse` - 系统配置响应模型
    - `SystemConfigUpdate` - 系统配置更新请求

- **定义路由签名**：

  - 在 `backend/routers/system.py` 中增强现有端点：
    - `GET /api/system/config` - 获取系统基础配置
    - `PUT /api/system/config` - 更新系统基础配置

  **重要：路由前缀统一**：

  - 现有 `system.router` 使用 `prefix="/system"`，在 `main.py` 中注册时没有添加 `/api` 前缀
  - 实际路径：`/system/platforms`、`/system/data-domains` 等
  - **需要修改**：将 `backend/routers/system.py` 中的 router 定义改为 `prefix="/api/system"`
  - **需要修改**：`backend/main.py` 中 `system.router` 的注册方式，移除 `prefix` 参数（或设为空）
  - **向后兼容**：现有路由（`/system/platforms` 等）需要迁移到 `/api/system/platforms`
  - **前端更新**：需要更新前端调用这些路由的代码（如果有）

- **实现业务逻辑**：
  - 实现系统基础配置 CRUD（系统名称、版本、时区、语言、货币）

**文件变更**：

- 更新：`backend/schemas/system.py`
- 更新：`backend/routers/system.py`（修改 router 前缀为 `/api/system`，迁移现有路由）
- 更新：`backend/main.py`（修改 system.router 注册方式）
- 更新：`modules/core/db/schema.py`
- 更新：前端代码（如果有调用 `/system/*` 路由的代码，需要更新为 `/api/system/*`）

#### 6.2 数据库配置 API

**目标**：提供数据库配置 CRUD 功能（仅查看和测试，不直接修改数据库连接）。

**工作内容**：

- **定义数据模型**：

  - 在 `modules/core/db/schema.py` 定义 `SystemConfig` 模型（复用，添加数据库配置字段）
  - 创建 Alembic 迁移

- **定义 API 契约**：

  - 在 `backend/schemas/system.py` 中定义：
    - `DatabaseConfigResponse` - 数据库配置响应模型（敏感字段加密）
    - `DatabaseConfigUpdate` - 数据库配置更新请求（仅用于预览，不直接应用）
    - `DatabaseConfigTestRequest` - 数据库连接测试请求
    - `DatabaseConnectionTestResponse` - 数据库连接测试响应模型

- **定义路由签名**：

  - 在 `backend/routers/system.py` 中定义（与 Phase 6.1 使用同一个 router）：
    - `GET /api/system/database/config` - 获取数据库配置（从 `.env` 或环境变量读取，敏感字段加密返回）
    - `PUT /api/system/database/config` - 更新数据库配置（保存到 `SystemConfig` 表，标记为 `pending` 状态，需要重启应用后生效）
    - `POST /api/system/database/test-connection` - 测试数据库连接（使用提供的配置测试连接，不保存）

  **注意**：与 Phase 6.1 使用同一个 `system.router`，路由前缀已统一为 `/api/system`。

- **实现业务逻辑**：
  - 实现数据库配置查看（从 `.env` 或环境变量读取，敏感字段使用 `EncryptionService` 加密后返回）
  - 实现数据库配置更新：
    - 将新配置保存到 `SystemConfig` 表，状态标记为 `pending`
    - 记录配置变更到审计日志
    - **重要**：配置不会立即生效，需要重启应用后从 `SystemConfig` 表读取并应用到数据库连接
    - 提供配置回滚功能（恢复到上一个有效配置）
  - 实现数据库连接测试（使用提供的配置测试连接，不保存到数据库或 `.env`）
  - **安全措施**（必须全部实现）：
    1. **配置验证**：验证数据库配置格式（URL、端口、用户名等）
    2. **连接测试**：更新配置前必须测试新配置的连接性
    3. **旧配置保存**：保存旧配置用于回滚
    4. **敏感数据加密**：数据库密码必须加密存储（使用 `EncryptionService`）
    5. **配置状态管理**：新配置标记为"pending"，需要重启系统才能生效
    6. **审计日志**：记录所有配置变更（包含变更前后对比）
  - 实现数据库配置 CRUD（连接信息）
  - 实现数据库连接测试（更新前和更新后都要测试）

**文件变更**：

- 更新：`backend/schemas/system.py`
- 更新：`backend/routers/system.py`

---

### Phase 7: 权限管理增强 API（P1 - 高优先级）

> 目标：**增强权限管理功能**——支持权限树、权限 CRUD。

#### 7.1 权限树 API

**目标**：提供权限树查询功能。

**工作内容**：

- **定义 API 契约**：

  - 在 `backend/schemas/auth.py` 中定义：
    - `PermissionTreeNode` - 权限树节点模型
    - `PermissionTreeResponse` - 权限树响应模型

- **定义路由签名**：

  - 在 `backend/routers/permissions.py` 中定义（新建文件，或合并到 roles.py）：
    - `GET /api/permissions/tree` - 获取权限树

- **实现业务逻辑**：
  - 实现权限树构建（层级结构）
  - 支持按模块分组

**文件变更**：

- 更新：`backend/schemas/auth.py`
- 新建或更新：`backend/routers/permissions.py`
- 更新：`backend/main.py`（注册路由）

#### 7.2 权限 CRUD API

**目标**：提供权限 CRUD 功能（管理 `DimRole.permissions` JSON 字段中的权限项）。

**工作内容**：

- **定义数据模型**：

  - **不需要新增权限表**：权限存储在 `DimRole.permissions` 字段中（JSON 数组格式，如：`["view_sales", "edit_inventory"]`）
  - 权限管理通过管理 `DimRole` 表的 `permissions` 字段实现
  - 如果需要权限元数据（权限名称、描述、分类），可以新增 `DimPermission` 表（可选，P2 功能）

- **定义 API 契约**：

  - 在 `backend/schemas/permission.py` 中定义（新建文件）：
    - `PermissionResponse` - 权限响应模型（权限代码、名称、描述、分类）
    - `PermissionTreeResponse` - 权限树响应（支持层级结构）
    - `PermissionListResponse` - 权限列表响应

- **定义路由签名**：

  - 在 `backend/routers/permission.py` 中定义（新建文件）：
    - `GET /api/system/permissions` - 获取权限列表（从系统预定义权限列表返回，支持树形结构）
    - `GET /api/system/permissions/tree` - 获取权限树（层级结构）
    - **注意**：权限的 CRUD 通过角色管理 API（`/api/roles`）实现，此 API 仅用于查询系统预定义权限列表

- **实现业务逻辑**：
  - 实现权限列表查询（从系统预定义权限列表返回，如：`["view_sales", "edit_inventory", "view_finance", ...]`）
  - 实现权限树查询（支持层级结构，如：`销售管理 > 查看销售 > 编辑销售`）
  - **权限分配**：通过角色管理 API（`PUT /api/roles/{role_id}`）更新 `DimRole.permissions` 字段实现

**文件变更**：

- 更新：`backend/schemas/auth.py`
- 更新：`backend/routers/permissions.py`
- 更新：`modules/core/db/schema.py`（如需要）

---

## Impact

### 正面影响

1. **系统管理功能完整**

   - 前端系统管理模块可以完整实现
   - 管理员可以通过界面管理所有系统配置

2. **安全性提升**

   - 密码策略、登录限制、会话管理等安全配置可管理
   - 审计日志增强，便于安全审计

3. **可运维性提升**

   - 数据备份与恢复可通过 API 管理
   - 系统维护操作可通过 API 执行
   - 系统配置可通过 API 管理

4. **符合 Contract-First 原则**
   - 所有 API 先定义契约，再实现逻辑
   - 前后端可以并行开发
   - API 变更可追溯

### 风险与缓解

1. **数据备份恢复 API 误用风险（P0）**

   - **缓解**：多重安全防护（禁止生产环境、管理员权限、交互确认、文件完整性验证、恢复前自动备份、超时控制）
   - **缓解**：恢复操作记录到审计日志（包含恢复前后状态对比）
   - **缓解**：恢复超时自动回滚到紧急备份

2. **数据库配置 API 安全风险（P0）**

   - **缓解**：配置更新前必须测试连接
   - **缓解**：保存旧配置用于回滚
   - **缓解**：敏感数据加密存储
   - **缓解**：配置状态管理（pending 状态，需要重启生效）

3. **系统维护 API 误操作风险（P1）**

   - **缓解**：所有维护操作需要管理员权限
   - **缓解**：重要操作（如数据清理）需要二次确认
   - **缓解**：所有操作记录到审计日志
   - **缓解**：添加限流配置防止滥用

4. **系统升级 API 安全风险（P0 - 已标记为 P3 不推荐）**

   - **缓解**：标记为 P3，不推荐实现
   - **缓解**：如果必须实现，需要多重安全措施（版本验证、多重确认、自动备份、沙箱测试、回滚机制）

5. **API 实现复杂度**
   - **缓解**：分 Phase 实施，每个 Phase 完成后验证
   - **缓解**：遵循 Contract-First 原则，先定义契约再实现

---

## Implementation Plan（高层级）

1. **Phase 1：系统日志与审计日志增强 API（优先）**

   - 实现系统日志 API
   - 增强审计日志 API（筛选、导出、详情）

2. **Phase 2：安全设置 API**

   - 实现密码策略 API
   - 实现登录限制 API
   - 实现会话管理 API
   - 实现 2FA 配置 API（可选）

3. **Phase 3：数据备份与恢复 API**

   - 实现数据备份 API（调用脚本层）
   - 实现数据恢复 API（多重安全防护）
   - 实现自动备份配置 API

4. **Phase 4：系统维护 API**

   - 实现缓存清理 API
   - 实现数据清理 API
   - 实现系统升级 API（可选）

5. **Phase 5：通知配置 API**

   - 实现 SMTP 配置 API
   - 实现通知模板 API
   - 实现告警规则 API

6. **Phase 6：系统配置增强 API**

   - 实现系统基础配置 API
   - 实现数据库配置 API

7. **Phase 7：权限管理增强 API**
   - 实现权限树 API
   - 实现权限 CRUD API

---

## 开发规范要求

### Contract-First 开发检查清单（每个 Phase 必须）

- [ ] 数据模型是否在 `modules/core/db/schema.py` 中定义？
- [ ] 是否创建了 Alembic 迁移？
- [ ] Pydantic 模型是否在 `backend/schemas/` 中定义（禁止在 routers/定义）？
- [ ] 路由是否定义了 `response_model` 参数？
- [ ] 是否遵循异步架构规范（使用 `get_async_db()`、`await db.execute()`）？
- [ ] 是否使用现有的 `require_admin` 依赖（从 `backend.routers.users` 导入）？
- [ ] 是否添加了限流配置（使用 `@role_based_rate_limit`）？
- [ ] 是否添加了输入验证（Pydantic validators）？
- [ ] 敏感数据是否加密存储（使用 `EncryptionService`）？
- [ ] 路由命名是否统一使用连字符（kebab-case）？

### 验证命令（每个 Phase 完成后）

```bash
# SSOT验证（ORM模型）
python scripts/verify_architecture_ssot.py  # 期望: 100%

# Contract-First验证（Pydantic模型）
python scripts/verify_contract_first.py

# Emoji检查（Windows编码兼容性）
python scripts/verify_no_emoji.py
```

---

**最后更新**: 2026-01-06  
**维护**: AI Agent Team  
**状态**: 📝 提案阶段
