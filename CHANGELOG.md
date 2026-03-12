# Changelog - 西虹 ERP 系统

## [Unreleased] - 组件版本管理模块重构 (optimize-component-version-management)

### 组件版本管理

- 组件版本测试执行一致性：测试时执行 `version.file_path` 对应实现，adapter 支持 override 注入
- 生产执行器按 file_path 加载：`_load_component_with_version` 使用 `load_python_component_from_path`，`_execute_python_component` 当 component dict 含 `_python_component_class` 时直接使用该类
- 删除规则放宽：可删除条件调整为 `!is_testing && !is_active`，稳定版禁用后也可删除
- 验证码步骤 unconditional 暂停：图形验证码步骤到达即等待 1s → 截图 → raise VerificationRequiredError
- 实际执行文件展示：版本列表增加 file_path 列
- 录制保存创建新版本：component_name 由 platform+component_type+data_domain+sub_domain 推导；版本号应用层语义解析递增；新版本默认非稳定
- 前端 export 保存传 data_domain/sub_domain

### 新增

- `backend/services/component_name_utils.py`：component_name 标准化、版本号解析
- `ComponentLoader.load_python_component_from_path`：按 file_path 加载，模块名唯一避免 sys.modules 污染

---

## [v4.20.0] - 2026-01-08 - 系统管理模块 API 完整实现

### 核心功能

#### 1. 系统日志与审计日志增强

- ✅ 系统日志 API（`GET /api/system/logs`）
  - 支持按级别、模块、用户、时间范围筛选
  - 分页查询（最大 100 条/页）
  - 日志详情查看（`GET /api/system/logs/{log_id}`）
  - 日志导出（Excel/CSV 格式）
  - 清空日志功能（管理员权限）
- ✅ 审计日志增强
  - 增强筛选功能（操作类型、资源类型、用户、IP 地址、时间范围）
  - 审计日志详情查看（包含变更前后对比）
  - 审计日志导出功能

#### 2. 安全设置 API

- ✅ 密码策略管理（`GET/PUT /api/security/password-policy`）
  - 最小长度、复杂度要求、过期时间、历史密码检查
  - 动态配置，实时生效
- ✅ 登录限制配置（`GET/PUT /api/security/login-restrictions`）
  - 最大失败尝试次数、账户锁定时长
  - IP 白名单管理（`GET/POST/DELETE /api/security/ip-whitelist`）
  - 动态配置，替换硬编码常量
- ✅ 会话管理配置（`GET/PUT /api/security/session-config`）
  - 会话超时时间、并发会话限制
  - 支持动态配置会话超时（集成到 auth_service）
- ✅ 2FA 配置（`GET/PUT /api/security/2fa-config`）
  - 启用/禁用 2FA、强制要求 2FA

#### 3. 数据备份与恢复 API

- ✅ 数据备份功能（`POST /api/backup/create`）
  - 支持数据库备份、文件备份、完整备份
  - Docker 环境适配（使用 pg_dump、tar、zip）
  - 备份记录管理（`GET /api/backup/list`）
  - 备份下载（`GET /api/backup/{backup_id}/download`）
- ✅ 数据恢复功能（`POST /api/backup/{backup_id}/restore`）
  - 多重安全防护（维护窗口检查、多管理员确认、强制确认）
  - 备份验证、恢复前自动备份
  - 恢复状态跟踪
- ✅ 自动备份配置（`GET/PUT /api/backup/auto-config`）
  - 备份频率、保留策略、备份时间窗口

#### 4. 系统维护 API

- ✅ 缓存清理（`GET/POST /api/maintenance/cache/*`）
  - Redis 缓存状态查询
  - 按类型清理缓存（全部、用户会话、数据缓存）
  - Docker 环境适配（redis:6379）
- ✅ 数据清理（`GET/POST /api/maintenance/data/*`）
  - 系统日志清理、临时文件清理
  - 数据状态查询
  - 安全措施（管理员权限、确认机制）
- ✅ 系统升级（`GET/POST /api/maintenance/upgrade/*`）
  - 升级检查、升级执行
  - 多重确认、自动备份
  - P3 功能，不推荐使用（建议通过 CI/CD 完成）

#### 5. 通知配置 API

- ✅ SMTP 配置（`GET/PUT /api/notification-config/smtp`）
  - SMTP 服务器配置（服务器、端口、TLS、用户名、密码）
  - 密码加密存储
  - 连接测试、测试邮件发送
- ✅ 通知模板管理（`CRUD /api/notification-config/templates`）
  - 模板类型（系统通知、告警通知、审批通知）
  - 模板变量支持
  - 模板激活/停用
- ✅ 告警规则管理（`CRUD /api/notification-config/alert-rules`）
  - 告警级别（critical、warning、info）
  - 告警条件（JSON 格式）
  - 通知方式（email、sms、in_app）
  - 通知对象配置

#### 6. 系统配置增强 API

- ✅ 系统基础配置（`GET/PUT /api/system/config`）
  - 系统名称、版本、时区、语言、货币
  - 配置持久化存储（SystemConfig 表）
- ✅ 数据库配置（`GET/PUT /api/system/database/config`）
  - 数据库连接信息查看（敏感字段加密）
  - 数据库配置更新（保存为 pending 状态）
  - 数据库连接测试（`POST /api/system/database/test-connection`）
  - Docker 环境适配（从容器环境变量读取）

#### 7. 权限管理增强 API

- ✅ 权限树 API（`GET /api/permissions/tree`）
  - 按模块分组的权限树结构
  - 支持层级展示
- ✅ 权限列表 API（`GET /api/system/permissions`）
  - 系统预定义权限列表（60+权限）
  - 支持按分类筛选
  - 权限树结构（`GET /api/system/permissions/tree`）

### 技术改进

#### 架构合规性

- ✅ 100% SSOT 合规（所有 ORM 模型在`modules/core/db/schema.py`定义）
- ✅ Contract-First 开发（所有 API 先定义 Pydantic 模型，后实现业务逻辑）
- ✅ 异步架构统一（所有服务类仅支持 AsyncSession）
- ✅ 路由前缀统一（`/api/system/*`、`/api/security/*`等）

#### 数据模型

- ✅ 新增表：`system_logs`、`security_config`、`backup_records`、`smtp_config`、`notification_templates`、`alert_rules`、`system_config`
- ✅ 数据库迁移脚本（手动执行，避免 Alembic 编码问题）

#### 安全措施

- ✅ 所有管理 API 需要管理员权限（`require_admin`）
- ✅ 敏感数据加密存储（密码、SMTP 密码）
- ✅ 限流保护（`role_based_rate_limit`）
- ✅ 输入验证（Pydantic 模型验证）
- ✅ 审计日志记录（所有配置变更）

#### Docker 环境适配

- ✅ 数据库备份使用`pg_dump`连接`postgres:5432`
- ✅ 文件备份使用容器内部路径（`/app/data`、`/app/downloads`、`/app/logs`）
- ✅ Redis 连接使用`redis:6379`
- ✅ 数据库配置从容器环境变量读取

### 前端集成

- ✅ 创建`frontend/src/api/system.js`，包含所有系统管理 API 客户端函数
- ✅ 支持系统日志、安全设置、备份恢复、系统维护、通知配置、系统配置、权限管理等所有 API

### 文档更新

- ✅ 更新`CHANGELOG.md`
- ✅ API 文档自动生成（OpenAPI/Swagger）

### 已知限制

- ⚠️ 数据恢复实际逻辑需要 Celery 异步任务支持（基础框架已完成）
- ⚠️ 自动备份配置需要集成到 Celery 定时任务
- ⚠️ 系统升级功能标记为 P3（不推荐使用），建议通过 CI/CD 完成
- ⚠️ 通知模板变量替换需要在使用时实现
- ⚠️ 告警规则触发逻辑需要监控系统支持

---

## [v4.19.0] - 2026-01-05 - 用户注册审批与账户管理

### 核心功能

#### 1. 用户注册与审批流程

- ✅ 新增用户注册功能（`POST /api/auth/register`）
  - 支持用户名、邮箱、密码、姓名等信息注册
  - 密码强度验证（至少 8 位，包含字母和数字）
  - 统一错误消息（防止用户名/邮箱枚举攻击）
  - 注册频率限制（5 次/分钟）
- ✅ 用户状态管理
  - pending（待审批）：注册成功，等待管理员审批
  - active（已激活）：审批通过，可以正常使用
  - rejected（已拒绝）：审批被拒绝
  - suspended（已暂停）：账户被管理员暂停
- ✅ 数据库触发器自动同步`status`和`is_active`字段
- ✅ 用户审批记录表（`user_approval_logs`）记录所有审批操作

#### 2. 管理员审批功能

- ✅ 待审批用户列表（`GET /api/users/pending`）
- ✅ 批准用户（`POST /api/users/{user_id}/approve`）
  - 自动分配默认角色（operator）
  - 记录审批日志
- ✅ 拒绝用户（`POST /api/users/{user_id}/reject`）
  - 必须填写拒绝原因
  - 记录拒绝日志
- ✅ 用户审批页面（`/admin/users/pending`）

#### 3. 密码管理

- ✅ 密码重置功能（`POST /api/users/{user_id}/reset-password`）
  - 管理员可以重置用户密码
  - 支持指定新密码或生成临时密码
  - 重置后清除账户锁定状态
- ✅ 账户锁定机制
  - 5 次登录失败后锁定账户 30 分钟
  - 管理员可以手动解锁账户（`POST /api/users/{user_id}/unlock`）
  - 登录失败次数记录（`failed_login_attempts`）

#### 4. 会话管理

- ✅ 会话记录表（`user_sessions`）
  - 记录用户登录会话信息（设备、IP、登录时间、最后活跃时间）
  - 支持会话过期时间管理
- ✅ 会话管理 API
  - 获取活跃会话列表（`GET /api/users/me/sessions`）
  - 撤销指定会话（`DELETE /api/users/me/sessions/{session_id}`）
  - 撤销所有其他会话（`DELETE /api/users/me/sessions`）
- ✅ 会话管理页面（`/settings/sessions`）
  - 显示活跃会话列表
  - 当前设备标识
  - 登出此设备/登出所有其他设备

#### 5. 系统通知机制

- ✅ 通知数据模型（`Notification`表）
  - 通知类型：user_registered, user_approved, user_rejected, password_reset, account_locked, account_unlocked, user_suspended, system_alert
  - 支持未读/已读状态管理
  - 支持关联用户信息
  - **新增优先级字段**（high/medium/low）
- ✅ 通知 API
  - 获取通知列表（`GET /api/notifications`）- 支持分页、过滤和优先级排序
  - 获取分组通知列表（`GET /api/notifications/grouped`）- 按类型分组统计
  - 获取未读数量（`GET /api/notifications/unread-count`）
  - 标记已读（`PUT /api/notifications/{id}/read`）
  - 标记全部已读（`PUT /api/notifications/read-all`）
  - 删除通知（`DELETE /api/notifications/{id}`）
  - **新增快速操作 API**（`POST /api/notifications/{id}/action`）
- ✅ 自动通知触发
  - 新用户注册时通知所有管理员（高优先级）
  - 用户审批通过时通知用户
  - 用户审批拒绝时通知用户
  - 密码重置时通知用户
  - 账户锁定/解锁时通知用户
  - 账户被暂停时通知用户
- ✅ **WebSocket 实时通知**
  - JWT 认证的 WebSocket 连接（`/api/ws`）
  - 实时推送通知到用户
  - 心跳机制和自动重连
  - 连接数限制和速率限制
  - 降级到 HTTP 轮询
- ✅ **浏览器原生通知**
  - 通知权限管理
  - 桌面通知显示（可配置）
  - 通知偏好设置（`/settings/notifications`）
  - 内容验证和 XSS 防护
- ✅ **通知快速操作**
  - 从通知面板直接批准/拒绝用户
  - 完整权限验证和审计日志
- ✅ **通知分组和优先级**
  - 按类型分组显示通知
  - 高优先级通知特殊样式
  - 优先级筛选功能
- ✅ 前端通知组件
  - 顶部栏通知图标（带未读数量徽章）
  - 通知下拉面板（最近 10 条通知，带快速操作按钮）
  - WebSocket 实时更新未读数量
  - 通知列表页面（支持过滤、分页、批量操作、分组视图）

#### 6. 前端实现

- ✅ 登录页面（`/login`）
  - 支持用户名/密码登录
  - 账户状态检查（pending/rejected/suspended/inactive）
  - 账户锁定提示
  - Open Redirect 防护
- ✅ 注册页面（`/register`）
  - 用户注册表单
  - 密码强度提示
  - 注册成功提示
- ✅ 路由守卫
  - 登录状态检查
  - 权限验证
  - 公开路由处理

### 数据库变更

#### 新增字段（`dim_users`表）

- `status` (VARCHAR): 用户状态（pending/active/rejected/suspended/deleted）
- `approved_at` (TIMESTAMP): 审批时间
- `approved_by` (BIGINT): 审批人 ID（外键）
- `rejection_reason` (TEXT): 拒绝原因
- `failed_login_attempts` (INTEGER): 登录失败次数
- `locked_until` (TIMESTAMP): 账户锁定截止时间

#### 新增表

- `user_approval_logs`: 用户审批记录表
- `user_sessions`: 用户会话表
- `notifications`: 系统通知表

#### 数据库触发器

- 自动同步`status`和`is_active`字段

### API 变更

#### 新增端点

- `POST /api/auth/register` - 用户注册
- `GET /api/users/pending` - 获取待审批用户列表
- `POST /api/users/{user_id}/approve` - 批准用户
- `POST /api/users/{user_id}/reject` - 拒绝用户
- `POST /api/users/{user_id}/reset-password` - 重置用户密码
- `POST /api/users/{user_id}/unlock` - 解锁用户账户
- `GET /api/users/me/sessions` - 获取活跃会话列表
- `DELETE /api/users/me/sessions/{session_id}` - 撤销指定会话
- `DELETE /api/users/me/sessions` - 撤销所有其他会话
- `GET /api/notifications` - 获取通知列表
- `GET /api/notifications/unread-count` - 获取未读通知数量
- `GET /api/notifications/{id}` - 获取单个通知详情
- `PUT /api/notifications/{id}/read` - 标记单个通知为已读
- `PUT /api/notifications/read-all` - 标记全部通知为已读
- `DELETE /api/notifications/{id}` - 删除单个通知
- `DELETE /api/notifications` - 删除所有已读通知

#### 修改端点

- `POST /api/auth/login` - 增强用户状态检查、账户锁定检查、会话创建
- `POST /api/auth/refresh` - 更新会话`last_active_at`

### 错误代码

新增错误代码（4005-4010）：

- `4005`: AUTH_ACCOUNT_PENDING - 账号待审批
- `4006`: AUTH_ACCOUNT_REJECTED - 账号已拒绝
- `4007`: AUTH_ACCOUNT_SUSPENDED - 账号已暂停
- `4008`: AUTH_ACCOUNT_INACTIVE - 账号未激活
- `4009`: AUTH_ACCOUNT_LOCKED - 账号已锁定
- `4010`: AUTH_ACCOUNT_NOT_LOCKED - 账号未锁定

### 安全增强

- ✅ 统一错误消息（防止用户名/邮箱枚举攻击）
- ✅ 注册 API 限流（5 次/分钟）
- ✅ 账户锁定机制（5 次失败锁定 30 分钟）
- ✅ Open Redirect 防护（前端验证 redirect 参数）
- ✅ 会话管理（支持查看和撤销活跃会话）

### 测试

- ✅ 安全测试（限流、枚举攻击、权限绕过、Open Redirect、CSRF）
- ✅ 单元测试（注册 API、审批 API、登录 API）
- ✅ 集成测试（完整注册-审批-登录流程）

### 文档

- ✅ 用户注册指南（`docs/guides/USER_REGISTRATION_GUIDE.md`）
- ✅ 管理员审批指南（`docs/guides/ADMIN_APPROVAL_GUIDE.md`）
- ✅ 测试总结（`backend/tests/TEST_SUMMARY.md`）
- ✅ 测试指南（`backend/tests/README_TESTING.md`）

### 迁移说明

1. **数据库迁移**

   - 运行迁移脚本添加新字段和表
   - 确保`operator`角色存在
   - 创建数据库触发器

2. **现有用户处理**

   - 现有用户状态自动设置为"active"
   - `is_active`字段自动同步

3. **管理员账号创建**
   - 使用`scripts/create_admin_user.py`创建管理员账号
   - 默认管理员：用户名`xihong`，密码`~!Qq1`1`

### 已知问题

无

### 后续计划

- Phase 5: 通知机制（可选）
  - 新用户注册时通知管理员
  - 审批结果通知用户

---

## [v4.8.0] - 2025-12-29 - 数据采集模块异步化改造与 Python 组件集成

### 核心改造

#### 1. Python 组件异步化

- 将 38 个平台组件从同步转为异步 (`def run` -> `async def run`)
- Shopee 平台: 17 个组件 (login, navigation, orders_export, products_export 等)
- TikTok 平台: 12 个组件 (login, navigation, date_picker, shop_selector 等)
- Miaoshou 平台: 9 个组件 (login, navigation, export, overlay_guard 等)

#### 2. Python 组件适配层

- 新增 `modules/apps/collection_center/python_component_adapter.py`
- `PythonComponentAdapter` 类提供统一的组件调用接口
- 支持 `login()`, `navigate()`, `export()`, `call_component()` 方法
- 自动密码解密 (`EncryptionService.decrypt_password()`)

#### 3. Executor V2 重构

- 添加 `use_python_components = True` 配置开关
- 新增 `_execute_python_component()` 方法
- 新增 `_execute_with_python_components()` 完整执行流程
- 支持直接调用 Python 组件，跳过 YAML 解析

#### 4. 组件加载器增强

- 新增 `load_python_component()` 方法
- 新增 `validate_python_component()` 方法
- 新增 `list_python_components()` 方法
- 支持通过 inspect 模块读取组件元数据

#### 5. 录制工具优化

- 移除 Codegen 模式支持
- 统一使用 Inspector 模式 (`page.pause()` + Trace)
- 移除 `_launch_playwright_codegen_subprocess()` 函数

#### 6. TraceParser 增强

- 新增 `generate_python_skeleton()` 方法
- 支持从 Trace 文件生成 Python 组件骨架代码
- 新增 `generate_component_from_trace()` 便捷函数

### 数据同步对齐（v4.8.0 新增）

#### 7. 文件命名标准化

- 使用 `StandardFileName.generate()` 生成标准文件名
- 格式: `{platform}_{data_domain}[_{sub_domain}]_{granularity}_{timestamp}.xlsx`
- 与数据同步模块完全对齐

#### 8. 文件存储路径标准化

- 采集完成后移动文件到 `data/raw/YYYY/` 目录
- 数据同步模块仅扫描此目录
- 自动删除临时文件

#### 9. 伴生文件格式标准化

- 使用 `MetadataManager.create_meta_file()` 生成 `.meta.json` 文件
- 伴生文件与数据文件在同一目录
- 包含 `business_metadata` 和 `collection_info` 完整元数据

#### 10. 文件注册自动化

- 采集完成后自动调用 `register_single_file()` 注册到 `catalog_files` 表
- 添加注册失败的错误处理和日志

#### 11. Python 组件测试工具更新

- 更新 `tools/test_component.py` 支持 Python 组件加载和测试
- 更新 `tools/run_component_test.py` 支持 `.py` 文件路径
- 更新 `backend/routers/component_versions.py` 支持 Python 组件测试
- 新增 `test_python_component()` 和 `_test_python_component_with_browser()` 方法

### 组件管理功能完善（v4.8.0 第二阶段）

#### 12. YAML 组件清理

- 新增 `scripts/cleanup_yaml_components.py` 清理脚本
- 支持将 YAML 文件移动到 `backups/yaml_components_YYYYMMDD/`
- 支持禁用 ComponentVersion 表中的 YAML 记录
- 支持 `--dry-run` 预览模式

#### 13. Python 组件批量注册

- 新增 `scripts/register_python_components.py` 批量注册脚本
- 扫描 `modules/platforms/` 下所有 Python 组件
- 自动读取组件元数据并注册到 ComponentVersion 表
- 支持 `--platform` 和 `--dry-run` 参数

#### 14. 批量注册 API

- 新增 `POST /component-versions/batch-register-python` API 端点
- 返回注册统计和详细结果
- 支持指定平台过滤

#### 15. 组件录制工具保存逻辑更新

- `RecorderSaveRequest` 模型支持 `python_code` 和 `data_domain`
- 保存 Python 组件到 `modules/platforms/{platform}/components/`
- Python 代码语法验证（`ast.parse`）
- 更新覆盖逻辑：文件路径相同时更新现有版本

#### 16. 前端组件管理功能

- 添加"批量注册 Python 组件"按钮
- 版本列表显示组件类型（Python/YAML）
- 新增 `batchRegisterPythonComponents` API 方法

#### 17. 稳定版本唯一性保证

- 增强 `promote_to_stable()` 方法
- 自动取消相同 component_name 的其他稳定版本
- 自动取消相同 file_path 的其他稳定版本

### Windows 兼容性

#### 日志 Emoji 替换

- 创建 `scripts/verify_no_emoji.py` 验证脚本
- 替换 `modules/platforms/` 下所有 emoji 为 ASCII 符号
- 标准替换: [OK], [FAIL], [WARN], [SCAN]

### 新增文件

- `modules/apps/collection_center/python_component_adapter.py` - Python 组件适配层
- `scripts/async_component_transformer.py` - 异步改造辅助脚本
- `scripts/verify_no_emoji.py` - Emoji 验证脚本
- `scripts/cleanup_yaml_components.py` - YAML 组件清理脚本
- `scripts/register_python_components.py` - Python 组件批量注册脚本
- `docs/guides/PYTHON_COMPONENT_TEMPLATE.md` - Python 组件编写模板

### 修改文件

- `modules/apps/collection_center/executor_v2.py` - 添加 Python 组件支持 + 文件处理对齐
- `modules/apps/collection_center/component_loader.py` - 添加 Python 组件加载
- `backend/routers/component_recorder.py` - 移除 Codegen 模式 + Python 组件保存
- `backend/routers/component_versions.py` - 支持 Python 组件测试 + 批量注册 API
- `backend/services/component_version_service.py` - 增强稳定版本唯一性保证
- `backend/utils/trace_parser.py` - 添加 Python 骨架生成
- `tools/test_component.py` - 支持 Python 组件测试
- `tools/run_component_test.py` - 支持 Python 组件路径
- `frontend/src/views/ComponentVersions.vue` - 批量注册按钮 + 组件类型显示
- `frontend/src/api/index.js` - 批量注册 API 方法
- `modules/platforms/*/components/*.py` - 异步化 + emoji 替换

### 验收标准 (已完成)

1. [OK] 所有 38 个 Python 组件成功转为异步版本
2. [OK] executor_v2 支持 Python 组件执行
3. [OK] 登录组件使用统一的密码解密逻辑
4. [OK] Windows 控制台无 UnicodeEncodeError (核心组件)
5. [OK] 组件加载器支持 Python 组件加载
6. [OK] 录制工具仅支持 Inspector 模式
7. [OK] Python 组件支持调用子组件
8. [OK] Trace 解析器生成 Python 代码骨架
9. [OK] 文件命名使用 StandardFileName.generate()
10. [OK] 采集文件保存到 data/raw/YYYY/ 目录
11. [OK] 伴生文件使用 .meta.json 格式
12. [OK] 文件自动注册到 catalog_files 表
13. [OK] Python 组件测试工具可正常使用
14. [OK] 架构验证脚本通过

---

## [v4.16.0] - 2025-12-08 - 数据库架构统一和端口配置优化

### 🚨 重大修复

#### 1. 解决双数据库数据分散问题

- ⭐⭐⭐ **问题根因**：本地 PostgreSQL 18 和 Docker PostgreSQL 15 同时运行，数据分散在两个数据库
- ⭐⭐⭐ **数据迁移**：将本地 PostgreSQL 的所有数据（72.63MB）迁移到 Docker PostgreSQL
- ⭐⭐⭐ **端口统一**：使用 15432 端口（避开 Windows 保留端口 5433-5832）
- ⭐⭐⭐ **服务禁用**：永久禁用本地 PostgreSQL 服务，防止端口冲突

#### 2. 配置文件更新

- ✅ `.env` - POSTGRES_PORT=15432, DATABASE_URL 更新
- ✅ `env.example` - 端口配置示例更新为 15432
- ✅ `backend/utils/config.py` - 默认端口改为 15432
- ✅ `docker/postgres/init-tables.py` - 默认连接 URL 更新

#### 3. .env 文件编码修复

- ✅ 修复 UnicodeDecodeError 编码问题
- ✅ 确保 .env 文件使用 UTF-8 编码

### 📊 数据库状态（迁移后）

| Schema  | 表数量 | 说明                                |
| ------- | ------ | ----------------------------------- |
| a_class | 7      | A 类配置数据                        |
| b_class | 28     | B 类业务数据（含 26 个 fact\_\*表） |
| c_class | 4      | C 类计算数据                        |
| core    | 18     | 核心系统表                          |
| public  | 106    | 公共表                              |

### 🔧 连接配置

| 组件        | 主机                 | 端口  |
| ----------- | -------------------- | ----- |
| Python 后端 | localhost            | 15432 |
| Metabase    | host.docker.internal | 15432 |
| pgAdmin     | postgres             | 5432  |

### 📄 新增文档

- `docs/DATABASE_MIGRATION_COMPLETE.md` - 迁移完成报告
- `docs/DATABASE_ARCHITECTURE_PROPOSAL.md` - 架构提案和预防措施

### ⚠️ 注意事项

- 本地 PostgreSQL 服务已永久禁用（StartupType=Disabled）
- 云端部署时可根据需要调整 POSTGRES_PORT
- 所有组件必须连接到同一个 Docker PostgreSQL 实例

---

## [v4.15.0] - 2025-12-05 - 优化数据同步以适应实际工作场景 ⭐

### 🎯 核心优化

#### 1. 货币代码变体识别

### 🎯 核心优化

#### 1. 货币代码变体识别

- ⭐ **智能表头变化检测**：识别货币代码变体（如 BRL、COP、SGD），将其视为同一字段的不同变体
- ⭐ **字段名归一化**：在表头变化检测前，将货币变体字段归一化为基础字段名（移除货币代码）
- ⭐ **货币代码提取**：从字段名中提取货币代码，存储到`currency_code`系统字段（String(3)）
- ⭐ **数据存储优化**：
  - `raw_data` JSONB 中字段名归一化（不含货币代码）
  - `currency_code`字段存储货币代码
  - `header_columns`保留原始字段名（含货币代码）
- ⭐ **智能匹配策略**：
  - 如果只有货币代码差异，视为匹配（不触发变化检测）
  - 如果还有其他字段变化，正常触发变化检测

#### 2. 库存数据 UPSERT 策略

- ⭐ **UPSERT 策略**：对于库存数据域，使用 UPSERT（INSERT ... ON CONFLICT ... UPDATE）而非 INSERT ... ON CONFLICT DO NOTHING
- ⭐ **更新字段配置**：定义哪些字段在冲突时应该更新
  - 更新字段：`raw_data`, `ingest_timestamp`, `file_id`, `header_columns`, `currency_code`
  - 保留字段：`metric_date`, `platform_code`, `shop_id`, `data_domain`, `granularity`, `data_hash`
- ⭐ **数据域特定策略**：
  - `inventory`域：使用 UPSERT（更新而非插入）
  - 其他域（orders/products/traffic/services/analytics）：使用 INSERT（跳过重复）

### 📊 数据库变更

- ✅ 所有 `fact_raw_data_*` 表新增 `currency_code` 字段（VARCHAR(3), nullable=True, index=True）

### 🔧 技术实现

#### 新增文件

- `backend/services/currency_extractor.py` - 货币代码提取和字段名归一化服务

#### 修改文件

- `backend/services/template_matcher.py` - 表头变化检测（货币变体识别）
- `backend/services/data_ingestion_service.py` - 数据入库时提取和存储货币代码
- `backend/services/raw_data_importer.py` - UPSERT 实现和 currency_code 字段存储
- `backend/services/deduplication_fields_config.py` - 策略和更新字段配置

### ✅ 测试

- ✅ 货币变体识别测试（16 个测试用例全部通过）
- ✅ 表头变化检测测试（2 个测试用例全部通过）
- ✅ 去重策略配置测试（7 个测试用例全部通过）
- ✅ 性能测试（字段名归一化和货币代码提取性能影响<0.5%）

### 📈 性能影响

- **写入性能影响**：<0.5%（几乎可忽略）
- **查询性能提升**：10-100 倍（按货币筛选可以使用索引）

### 📝 文档

- ✅ 新增文档：`docs/V4_15_0_DATA_SYNC_OPTIMIZATION.md` - 完整的功能说明和使用指南
- ✅ 新增文档：`docs/V4_15_0_EMPTY_FILE_HANDLING.md` - 空文件处理策略说明

### 🐛 Bug 修复

#### 空文件处理优化

- ⭐ **提前检测空文件**：在读取文件后立即检测（第 239 行），避免后续不必要的处理
- ⭐ **成功标记**：空文件返回`success=True`，避免用户混淆（之前返回`success=False`导致前端显示"失败"）
- ⭐ **重复处理防护**：检查`[空文件标识]`，避免重复处理空文件
- ⭐ **状态管理优化**：区分空文件和重复数据，提供更准确的状态信息
- ⭐ **性能提升**：减少不必要的计算和数据库操作（规范化、数据清洗等）

### 🎯 成功标准

1. ✅ 货币代码变体不再触发表头变化检测（如果只有货币差异）
2. ✅ 货币代码正确提取并存储到`currency_code`字段
3. ✅ 字段名归一化正确（`raw_data`中字段名不含货币代码）
4. ✅ 库存数据更新而非重复插入（同一商品+仓库只有一条记录）
5. ✅ 其他数据域保持现有行为（orders/products 使用 INSERT 策略）
6. ✅ 向后兼容现有模板和数据
7. ✅ 性能不受影响（写入性能影响<0.5%，查询性能提升 10-100 倍）

---

## [v4.14.2] - 2025-11-27 - 重构 DSS 架构下的必填字段验证设计 ⭐

### 🔄 架构重构

#### 核心变更

- ⭐ **移除所有必填字段验证**：不再要求 product_id、platform_sku 等标准字段名
- ⭐ **只验证数据格式**：日期、数字等格式验证（如果字段存在且不为空）
- ⭐ **支持中英文字段名**：验证器同时支持中英文字段名（如"产品 ID"、"商品编号"等）
- ⭐ **允许空值**：PostgreSQL 支持 NULL 值，允许字段为空

#### 设计原则

1. 表头字段完全参考源文件的实际表头行
2. PostgreSQL 只做数据存储（JSONB 格式，保留原始中文表头）
3. 目标：把正确不重复的数据入库到 PostgreSQL 即可
4. 去重通过 data_hash 实现，不依赖业务字段名

#### 修改的文件

- `backend/services/enhanced_data_validator.py` - 重构`validate_inventory`函数
- `backend/services/data_validator.py` - 重构所有验证函数（orders、products、traffic、services、analytics）

#### 影响

- ✅ 数据不再因为缺少标准字段名而被隔离
- ✅ 支持任意格式的表头字段名（中文、英文、混合）
- ✅ 数据入库更加灵活，符合 DSS 架构设计原则
- ✅ 去重机制通过 data_hash 实现，不依赖业务字段名

### 📝 相关文件

- `backend/services/enhanced_data_validator.py` - 库存数据验证器（已重构）
- `backend/services/data_validator.py` - 其他数据域验证器（已重构）

---

## [v4.14.1] - 2025-11-27 - 删除字段映射审核模块，完全迁移到数据同步 ⭐

### 🗑️ 清理工作

#### 1. 删除字段映射审核模块

- ✅ **删除菜单项**: `frontend/src/config/menuGroups.js` - 移除 `/field-mapping` 菜单项
- ✅ **删除路由**: `frontend/src/router/index.js` - 移除 `/field-mapping` 路由定义
- ✅ **归档组件**: `FieldMappingEnhanced.vue` → `backups/20250131_field_mapping_audit/FieldMappingEnhanced.vue`
- ✅ **清理引用**:
  - `frontend/src/App.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/Header.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/SimpleHeader.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/SimpleSidebar.vue` - 删除字段映射审核菜单项
- ✅ **修复跳转**: `frontend/src/views/DataBrowser.vue` - 将"跳转到字段映射审核"改为"跳转到数据同步-模板管理"
- ✅ **清理权限**: `frontend/src/stores/user.js` - 移除 `field-mapping` 权限
- ✅ **更新注释**: `frontend/src/api/index.js` - 更新废弃 API 注释

#### 2. 迁移说明

- ✅ **替代方案**: 所有字段映射审核功能已完全迁移到"数据同步-模板管理"模块
- ✅ **数据浏览器**: 字段映射跳转现在指向 `/data-sync/templates`
- ✅ **保留功能**: 字段映射辞典 API 和模板管理 API 仍然保留，供数据同步功能使用

### 📝 相关文件

- `backups/20250131_field_mapping_audit/FieldMappingEnhanced.vue` - 归档的字段映射审核组件
- `frontend/src/config/menuGroups.js` - 已删除字段映射审核菜单项
- `frontend/src/router/index.js` - 已删除字段映射审核路由
- `frontend/src/views/DataBrowser.vue` - 已更新跳转逻辑

---

## [v4.14.0] - 2025-02-01 - 清理 Superset 相关文件，迁移到 Metabase ⭐

### 🗑️ 清理工作

#### 1. 归档 Superset 相关文件

- ✅ **归档**: 35 个 Superset 相关文件已移动到`backups/20250201_superset_cleanup/`
  - Docker 配置: `docker-compose.superset.yml`, `superset_config.py`
  - 文档: 14 个 Superset 相关文档
  - 脚本: 13 个 Superset 相关脚本
  - SQL 文件: `create_superset_views.sql`, `refresh_superset_materialized_views.sql`
  - 代码文件: `backend/routers/superset_proxy.py`, `frontend/src/components/SupersetChart.vue`
- ✅ **更新**: `backend/main.py`移除 superset_proxy 路由引用
- ✅ **原因**: 项目从 Superset 迁移到 Metabase 作为唯一 BI 工具

#### 2. 移除 Streamlit 依赖

- ✅ **更新**: `requirements.txt`移除 Streamlit 相关依赖
  - 移除: `streamlit>=1.28.0`
  - 移除: `streamlit-aggrid>=0.3.0`
  - 移除: `streamlit-antd-components>=0.3.0`
  - 移除: `streamlit-option-menu>=0.3.6`
- ✅ **原因**: 项目已完全迁移到 Vue.js 3 前端，不再使用 Streamlit

### 📝 相关文件

- `backups/20250201_superset_cleanup/README.md` - 归档说明
- `requirements.txt` - 已移除 Streamlit 依赖
- `backend/main.py` - 已移除 superset_proxy 引用

---

## [v4.13.3] - 2025-11-22 - 修复数据流转显示问题：source_catalog_id 未设置 ⭐

### 🐛 Bug 修复

#### 1. 修复数据流转显示 Fact 层数据为 0 的问题

- ✅ **问题**: 数据已入库到 Fact 层，但数据流转显示 Fact 层数据为 0
- ✅ **原因**: `upsert_product_metrics`函数中`source_catalog_id`字段未正确设置，导致无法通过`source_catalog_id`查询 Fact 层数据
- ✅ **修复**:
  - `backend/services/data_ingestion_service.py`：在调用`upsert_product_metrics`前为每行数据设置`source_catalog_id = file_record.id`
  - `backend/services/data_importer.py`：在`upsert_product_metrics`函数中添加 fallback 逻辑，如果行数据中没有`source_catalog_id`，则使用`file_record.id`
- ✅ **数据修复**: 使用`scripts/fix_source_catalog_id_final.py`修复了 1092 条已存在数据的`source_catalog_id`字段
- ✅ **验证**: 数据流转 API 现在正确显示 Fact 层数据数量（1092 条）

### 📝 相关文件

- `backend/services/data_ingestion_service.py`：修复数据入库时的 source_catalog_id 设置
- `backend/services/data_importer.py`：修复 upsert_product_metrics 函数的 fallback 逻辑
- `scripts/fix_source_catalog_id_final.py`：数据修复脚本（修复已存在数据）

---

## [v4.13.2] - 2025-11-22 - 修复任务日志查询 API 的数据库字段错误 ⭐

### 🐛 Bug 修复

#### 1. 修复数据流转显示 Fact 层数据为 0 的问题

- ✅ **问题**: 数据已入库到 Fact 层，但数据流转显示 Fact 层数据为 0
- ✅ **原因**: `upsert_product_metrics`函数中`source_catalog_id`字段未正确设置，导致无法通过`source_catalog_id`查询 Fact 层数据
- ✅ **修复**:
  - `backend/services/data_ingestion_service.py`：在调用`upsert_product_metrics`前为每行数据设置`source_catalog_id = file_record.id`
  - `backend/services/data_importer.py`：在`upsert_product_metrics`函数中添加 fallback 逻辑，如果行数据中没有`source_catalog_id`，则使用`file_record.id`
- ✅ **影响**: 数据流转查询现在可以正确显示 Fact 层数据数量

---

## [v4.13.2] - 2025-11-22 - 修复任务日志查询 API 的数据库字段错误 ⭐

### 🐛 Bug 修复

#### 1. 修复 FactProductMetric.file_id 字段错误

- ✅ **问题**: 任务日志查询 API 返回 500 错误，提示`fact_product_metrics`表不存在`file_id`字段
- ✅ **原因**: `FactProductMetric`表使用`source_catalog_id`字段关联文件，而非`file_id`
- ✅ **修复**:
  - `backend/routers/auto_ingest.py`第 527 行：修复`get_task_logs`函数
  - `backend/routers/auto_ingest.py`第 627 行：修复`get_file_logs`函数
- ✅ **影响**: 任务日志查询和文件日志查询功能恢复正常

### 📝 相关文件

- `backend/routers/auto_ingest.py`：修复数据库查询字段
- `openspec/changes/improve-data-sync-reliability/BUGFIX_FactProductMetric_file_id.md`：Bug 修复文档

---

## [v4.13.1] - 2025-01-31 - 完成可选功能：数据流转可视化和丢失数据导出 ⭐

### ✅ 新增功能

#### 1. 数据流转可视化（100%完成）

- ✅ **ECharts 饼图可视化**: 在 FieldMappingEnhanced.vue 中添加数据流转可视化图表
  - 显示 Fact 层、丢失数据、隔离区的数据分布
  - 自动更新图表数据
  - 响应式布局支持
  - 窗口大小变化时自动调整

#### 2. 丢失数据导出功能（100%完成）

- ✅ **后端 API**: 添加`/api/raw-layer/export-lost-data/{file_id}`端点
  - 支持 orders/products/traffic/analytics/inventory 域
  - 导出为 Excel 格式（使用 pandas 和 openpyxl）
  - 包含丢失数据的详细信息
- ✅ **前端导出按钮**: 在对比报告中添加导出按钮
  - 当有丢失数据时显示导出按钮
  - 支持一键导出丢失数据到 Excel

### 📝 相关文件

- `backend/routers/raw_layer_export.py`：丢失数据导出 API 端点
- `frontend/src/views/FieldMappingEnhanced.vue`：数据流转可视化图表和导出按钮
- `frontend/src/api/index.js`：导出丢失数据 API 方法

---

## [v4.13.0] - 2025-01-31 - 提升数据同步可靠性 ⭐
