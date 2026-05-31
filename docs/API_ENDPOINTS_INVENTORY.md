# API 端点清单

**更新时间**: 2026-05-31  
**状态**: Active  
**说明**: 本文档只维护当前运行时仍注册、且建议前后端继续使用的主接口。历史兼容端点不再作为主契约记录。

---

## 认证管理

| 方法 | 路径 | 说明 | 认证模式 |
|---|---|---|---|
| POST | `/api/auth/login` | 用户登录 | Public |
| POST | `/api/auth/logout` | 用户登出 | Authenticated |
| POST | `/api/auth/refresh` | 刷新会话 | Public with refresh token |
| GET | `/api/auth/me` | 获取当前用户及后端驱动权限 payload | Authenticated |
| PUT | `/api/auth/me` | 更新当前用户资料 | Authenticated |

## 平台管理域

### 用户管理

| 方法 | 路径 | 说明 | 认证模式 |
|---|---|---|---|
| GET | `/api/users/` | 获取活跃用户分页列表 | Admin |
| GET | `/api/users/deleted` | 获取已删除用户分页列表 | Admin |
| GET | `/api/users/unlinked` | 获取未关联员工的用户 | Admin |
| GET | `/api/users/{user_id}` | 获取用户详情 | Admin |
| POST | `/api/users/` | 创建用户 | Admin |
| PUT | `/api/users/{user_id}` | 更新用户 | Admin |
| DELETE | `/api/users/{user_id}` | 软删除用户 | Admin |
| POST | `/api/users/delete-batch` | 批量软删除用户 | Admin |
| POST | `/api/users/{user_id}/restore` | 恢复已删除用户 | Admin |
| POST | `/api/users/{user_id}/reset-password` | 重置用户密码 | Admin |
| GET | `/api/users/pending` | 获取待审批用户列表 | Admin |
| GET | `/api/users/pending-count` | 获取待审批用户数 | Admin |
| POST | `/api/users/{user_id}/approve` | 审批通过用户 | Admin |
| POST | `/api/users/{user_id}/reject` | 拒绝用户 | Admin |
| POST | `/api/users/reject-batch` | 批量拒绝用户 | Admin |

### RBAC 管理

| 方法 | 路径 | 说明 | 认证模式 |
|---|---|---|---|
| GET | `/api/admin/roles` | 获取角色列表 | Admin |
| GET | `/api/admin/roles/{role_id}` | 获取角色详情 | Admin |
| POST | `/api/admin/roles` | 创建角色 | Admin |
| PUT | `/api/admin/roles/{role_id}` | 更新角色 | Admin |
| DELETE | `/api/admin/roles/{role_id}` | 删除角色 | Admin |
| GET | `/api/admin/rbac/assignable-roles` | 获取可分配角色选项 | Admin |
| GET | `/api/admin/permissions` | 获取权限目录 | Admin |
| GET | `/api/admin/permissions/tree` | 获取权限树 | Admin |
| GET | `/api/admin/rbac/permission-usage` | 获取指定权限的角色引用情况 | Admin |
| POST | `/api/admin/rbac/check-permission` | 校验指定用户是否具备指定权限 | Admin |

### 个人会话与通知偏好

| 方法 | 路径 | 说明 | 认证模式 |
|---|---|---|---|
| GET | `/api/users/me/sessions` | 获取当前用户会话列表 | Self-scoped |
| DELETE | `/api/users/me/sessions/{session_id}` | 撤销指定会话 | Self-scoped |
| DELETE | `/api/users/me/sessions` | 撤销除当前外的其他会话 | Self-scoped |
| GET | `/api/users/me/notification-preferences` | 获取通知偏好 | Self-scoped |
| PUT | `/api/users/me/notification-preferences` | 批量更新通知偏好 | Self-scoped |
| GET | `/api/users/me/notification-preferences/{notification_type}` | 获取单类通知偏好 | Self-scoped |
| PUT | `/api/users/me/notification-preferences/{notification_type}` | 更新单类通知偏好 | Self-scoped |

## 系统管理

| 方法 | 路径 | 说明 | 认证模式 |
|---|---|---|---|
| GET | `/api/system/config` | 获取系统配置 | Admin |
| GET | `/api/system/database/config` | 获取数据库配置 | Admin |
| GET | `/api/system/logs` | 获取系统日志 | Admin |
| GET | `/api/system/backup/backups` | 获取备份列表 | Admin |
| POST | `/api/system/backup/backups` | 创建备份 | Admin |
| GET | `/api/system/maintenance/cache/status` | 获取缓存状态 | Admin |
| POST | `/api/system/maintenance/cache/clear` | 清理缓存 | Admin |
| GET | `/api/system/maintenance/data/status` | 获取数据清理状态 | Admin |
| POST | `/api/system/maintenance/data/clean` | 执行数据清理 | Admin |
| GET | `/api/system/maintenance/upgrade/check` | 检查升级 | Admin |
| GET | `/api/system/security/password-policy` | 获取密码策略 | Admin |
| GET | `/api/system/security/login-restrictions` | 获取登录限制 | Admin |
| GET | `/api/system/security/ip-whitelist` | 获取 IP 白名单 | Admin |
| GET | `/api/system/security/session-config` | 获取会话配置 | Admin |
| GET | `/api/system/security/2fa-config` | 获取 2FA 配置 | Admin |

## 说明

- 旧 `/api/roles/*`、`/api/system/permissions*`、`/api/permissions/tree` 已退出主运行时契约，不再建议前端或脚本继续调用。
- 当前 RBAC 的唯一事实源为后端认证与 `/api/admin/*` 管理接口；前端不应再自行推导生产权限。
