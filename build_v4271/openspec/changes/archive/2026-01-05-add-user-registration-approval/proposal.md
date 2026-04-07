# Change: 添加用户注册和审批流程

> **状态**: 📋 待审批  
> **创建日期**: 2026-01-04  
> **最后更新**: 2026-01-05  
> **优先级**: P1 - 核心功能  
> **类型**: 新增功能  
> **已知漏洞**: 68（P0: 13, P1: 34, P2: 21）

## Why

当前系统缺少用户注册功能，所有用户需要由管理员手动创建，存在以下问题：

### 1. 用户体验不佳（高严重性）

- **问题**：新用户无法自助注册，必须等待管理员创建账户
- **影响**：增加管理员工作负担，新用户入职流程繁琐
- **场景**：新员工入职时，需要联系管理员创建账户，等待时间不确定

### 2. 安全性控制不足（中严重性）

- **问题**：无法对新注册用户进行审批和审核
- **影响**：可能被恶意用户注册，无法控制用户质量
- **场景**：外部人员可能尝试注册系统账户

### 3. 缺少用户状态管理（中严重性）

- **问题**：用户状态字段（`status`）未充分利用
- **影响**：无法区分待审批、已激活、已拒绝等状态
- **场景**：需要暂停用户账户时，只能删除或禁用，无法记录原因

### 4. 符合中小团队实际需求

- **优势**：管理员审批机制，无需邮件服务配置
- **优势**：审批流程简单，易于管理和审计
- **优势**：适合中小团队快速实施

## What Changes

> **📋 实施状态说明**：本文档中的任务清单使用 `[ ]` 标记，表示功能设计。详细的实施状态和完成情况请参考 `tasks.md`。  
> **✅ 当前完成状态**：Phase 1-4, 6-7 核心功能已完成，部分 P0/P1 安全要求待修复（详见 `tasks.md`）。

### Phase 1: 数据模型扩展 - P0

#### 1.1 用户状态字段完善

- [ ] 添加 `status` 字段到 `DimUser` 表（如果不存在）
- [ ] 添加 `approved_at`、`approved_by`、`rejection_reason` 字段
- [ ] 创建 Alembic 迁移脚本
- [ ] 更新现有用户数据：`status="active"`, `is_active=True`

#### 1.2 用户审批记录表（必需）⚠️

- [ ] 创建 `UserApprovalLog` 表（用于审计）
- [ ] 记录审批操作（批准/拒绝/暂停）
- [ ] 记录审批人、时间、原因

> **决策**：审批日志表设为**必需**，确保审计追踪完整

### Phase 2: 后端 API 实现 - P0

#### 2.1 用户注册 API

- [ ] 实现 `POST /api/auth/register` 端点
- [ ] **添加速率限制：`@limiter.limit("5/minute")`** ⚠️（P0 安全漏洞）
- [ ] 密码强度验证（至少 8 位，包含字母和数字）
- [ ] **用户名/邮箱唯一性检查（合并检查，统一错误消息）** ⚠️（P0 安全漏洞）
- [ ] 创建用户状态为 `pending`
- [ ] 返回注册成功提示（等待审批）

#### 2.2 用户审批 API

- [ ] 实现 `POST /api/users/{user_id}/approve` 端点（管理员）
  - [ ] **添加速率限制：`@limiter.limit("20/minute")`** ⚠️（P1 安全要求）
    - [ ] ⚠️ **实施状态检查**：确认是否已添加速率限制装饰器
  - [ ] **输入验证** ⚠️（P1 安全要求）
    - [ ] 验证 `role_ids` 是否存在（最多 10 个角色）
      - [ ] ⚠️ **实施状态检查**：确认 Pydantic schema 中已添加 `max_items=10`
      - [ ] ⚠️ **修复**：在审批 API 中验证所有 `role_ids` 是否都存在（不能静默忽略不存在的角色 ID）
    - [ ] 限制 `notes` 长度（最多 500 字符）
      - [ ] ⚠️ **实施状态检查**：确认 Pydantic schema 中已添加 `max_length=500`
  - [ ] 支持角色分配（审批时指定角色）
  - [ ] 记录审批日志
- [ ] 实现 `POST /api/users/{user_id}/reject` 端点（管理员）
  - [ ] **添加速率限制：`@limiter.limit("20/minute")`** ⚠️（P1 安全要求）
    - [ ] ⚠️ **实施状态检查**：确认是否已添加速率限制装饰器
  - [ ] **输入验证** ⚠️（P1 安全要求）
    - [ ] 限制 `reason` 长度（1-500 字符）
      - [ ] ⚠️ **实施状态检查**：确认 Pydantic schema 中已添加 `min_length=1, max_length=500`（注意：当前实现为 `min_length=5`，需要修改）
  - [ ] 记录审批日志

#### 2.3 待审批用户列表 API

- [ ] 实现 `GET /api/users/pending` 端点（管理员）
  - [ ] **添加速率限制：`@limiter.limit("30/minute")`** ⚠️（P1 安全要求）
    - [ ] ⚠️ **实施状态检查**：确认是否已添加速率限制装饰器
  - [ ] 支持分页查询
  - [ ] **返回字段控制** ⚠️（P2 隐私要求）
    - [ ] 必需字段：`user_id`, `username`, `created_at`, `status`
      - [ ] ⚠️ **修复**：确认 `PendingUserResponse` schema 包含 `status` 字段
    - [ ] 可选字段：`email`（仅管理员可见）
    - [ ] 禁止字段：`password_hash`, `phone`（敏感信息）
    - [ ] ⚠️ **实施状态检查**：确认 `PendingUserResponse` schema 不包含敏感字段
  - [ ] 返回用户基本信息（用户名、邮箱、注册时间等）

#### 2.4 登录 API 修改

- [ ] 修改 `POST /api/auth/login` 端点
- [ ] 检查用户状态（`pending`/`rejected`/`suspended`）
- [ ] 只有 `status="active"` 的用户才能登录
- [ ] 返回友好的错误提示

### Phase 3: 错误码和响应 - P1

#### 3.1 错误码定义

- [ ] 添加用户状态相关错误码（**注意：避免与现有错误码冲突**）⚠️
  - `AUTH_ACCOUNT_PENDING = 4005` - 账号待审批
  - `AUTH_ACCOUNT_REJECTED = 4006` - 账号已拒绝
  - `AUTH_ACCOUNT_SUSPENDED = 4007` - 账号已暂停
  - `AUTH_ACCOUNT_INACTIVE = 4008` - 账号未激活

> **决策**：采用统一错误消息方案（防枚举攻击），不再需要 `REGISTER_USERNAME_EXISTS` 和 `REGISTER_EMAIL_EXISTS` 错误码

#### 3.2 响应格式统一

- [ ] 统一错误响应格式
- [ ] 添加友好的错误提示消息
- [ ] 支持错误恢复建议

### Phase 4: 前端实现 - P0

#### 4.1 登录页面（必需）

- [ ] 创建登录页面 (`/login`)
- [ ] 用户名/密码登录表单
- [ ] 表单验证
- [ ] 登录成功后的重定向处理
- [ ] 显示登录错误提示
- [ ] 添加注册链接（如果有注册功能）
- [ ] 显示用户状态错误提示（pending/rejected/suspended）
- [ ] 友好的错误消息展示

#### 4.2 前端路由守卫（必需）

- [ ] **确定 Store 使用策略**（必须先完成）⚠️
  - [ ] 评估 `useUserStore` 和 `useAuthStore` 的使用情况
  - [ ] 确定统一使用的 Store（推荐 `useAuthStore`）
- [ ] 在 `router.beforeEach` 中添加登录状态检查
- [ ] **添加已登录用户访问公开路由的重定向逻辑** ⚠️
- [ ] 未登录用户重定向到登录页面
- [ ] 公开路由配置（登录、注册等）
- [ ] 登录后的重定向处理（redirect 参数）
- [ ] 保持现有的权限和角色检查逻辑

#### 4.3 注册页面

- [ ] 创建用户注册页面 (`/register`)
- [ ] 表单验证（用户名、邮箱、密码强度）
- [ ] 提交注册请求
- [ ] 显示注册成功提示（等待审批）
- [ ] 注册成功后跳转到登录页面

#### 4.4 管理员审批页面

- [ ] 创建用户审批页面 (`/admin/users/pending`)
- [ ] 显示待审批用户列表
- [ ] 批准/拒绝操作
- [ ] 角色分配功能（可选）

### Phase 5: 通知机制（可选） - P2

#### 5.1 系统通知

- [ ] 新用户注册通知管理员
- [ ] 审批结果通知用户
- [ ] 使用系统通知或站内消息

### Phase 6: 密码管理 - P1（建议实施）

#### 6.1 密码重置功能

- [ ] 管理员重置密码功能（通过用户管理页面）
- [ ] 生成临时密码或通知用户
- [ ] ⚠️ **强制撤销所有活跃会话**（P0 安全要求）
  - [ ] 密码重置后，必须撤销用户所有活跃会话
  - [ ] 用户下次登录时会看到密码重置通知
- [ ] ⚠️ **发送密码重置通知**（P1）
  - [ ] 创建 `notify_password_reset` 函数
  - [ ] 在 `reset_user_password` API 中调用
  - [ ] 通知内容："您的密码已被管理员重置，请使用新密码登录"

#### 6.2 账户锁定机制

- [ ] 添加账户锁定字段（`failed_login_attempts`, `locked_until`）
- [ ] 登录失败计数
- [ ] 达到阈值后锁定账户（5 次失败，锁定 30 分钟）
- [ ] ⚠️ **账户锁定后强制撤销所有活跃会话**（P0 安全要求）
  - [ ] 账户锁定后，必须撤销用户所有活跃会话
  - [ ] 用户下次尝试登录时会看到锁定通知
- [ ] ⚠️ **发送账户锁定通知**（P1）
  - [ ] 创建 `notify_account_locked` 函数
  - [ ] 在登录 API 中，账户锁定后调用
  - [ ] 通知内容："您的账户因多次登录失败已被锁定 X 分钟"
- [ ] 管理员解锁功能
- [ ] ⚠️ **发送账户解锁通知**（P1）
  - [ ] 创建 `notify_account_unlocked` 函数
  - [ ] 在 `unlock_user_account` API 中调用
  - [ ] 在登录 API 中，自动解锁后调用
  - [ ] 通知内容："您的账户已解锁，可以重新登录"

### Phase 7: 会话管理 - P1（可选）

- [ ] 查看活跃会话列表
- [ ] 强制登出其他设备
- [ ] 会话过期管理
- [ ] ⚠️ **用户暂停后强制撤销所有活跃会话**（P0 安全要求）
  - [ ] 在 `update_user` API 中，设置 `is_active=False` 时
  - [ ] 必须同步设置 `status="suspended"`（数据一致性）
  - [ ] 必须撤销用户所有活跃会话
  - [ ] 必须发送用户暂停通知

## Impact

### 受影响的代码位置

| 类型         | 文件数 | 修改点数 | 优先级 |
| ------------ | ------ | -------- | ------ |
| 数据库模型   | 1-2    | 10+      | P0     |
| 认证路由     | 1      | 30+      | P0     |
| 用户管理路由 | 1      | 50+      | P0     |
| 错误码定义   | 1      | 5+       | P1     |
| 前端页面     | 3-4    | 300+     | P0     |
| 前端路由守卫 | 1      | 50+      | P0     |

### 预期效果

- ✅ 用户可自助注册，提升用户体验
- ✅ 管理员可审批用户，控制账户质量
- ✅ 完整的用户状态管理（pending/active/rejected/suspended）
- ✅ 审计日志记录审批操作
- ✅ 符合中小团队实际需求（无需邮件服务）

## 用户状态设计

### 状态枚举

| 状态        | 说明                 | is_active | 可登录 |
| ----------- | -------------------- | --------- | ------ |
| `pending`   | 待审批（新注册）     | `false`   | ❌     |
| `active`    | 已启用               | `true`    | ✅     |
| `rejected`  | 已拒绝               | `false`   | ❌     |
| `suspended` | 已暂停（管理员手动） | `false`   | ❌     |
| `deleted`   | 已删除（软删除）     | `false`   | ❌     |

### 状态流转

```
注册 → pending → (管理员审批) → active (可登录)
                      ↓
                   rejected (被拒绝)

active → (管理员操作) → suspended (暂停)
          ↓                    ↓
        deleted (软删除)    (管理员恢复) → active
```

> ⚠️ **注意**：`suspended` 状态可以通过管理员操作恢复为 `active` 状态（通过 `update_user` API 设置 `is_active=True`，系统会自动同步设置 `status="active"`）。

## 数据库设计

### DimUser 表字段

```python
status = Column(String(20), default="pending", nullable=False, index=True)
approved_at = Column(DateTime, nullable=True)
approved_by = Column(BigInteger, ForeignKey('dim_users.user_id'), nullable=True)
rejection_reason = Column(Text, nullable=True)
```

### UserApprovalLog 表（必需）⚠️

> **决策**：审批日志表设为**必需**，确保审计追踪完整

```python
class UserApprovalLog(Base):
    log_id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('dim_users.user_id'), nullable=False)
    action = Column(String(20), nullable=False)  # approve/reject/suspend
    approved_by = Column(BigInteger, ForeignKey('dim_users.user_id'), nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
```

## API 设计概要

### 用户注册

```http
POST /api/auth/register
Content-Type: application/json

{
  "username": "newuser",
  "email": "user@example.com",
  "password": "SecurePass123",
  "full_name": "New User",
  "phone": "13800138000",
  "department": "运营部"
}

Response 200:
{
  "success": true,
  "data": {
    "user_id": 123,
    "username": "newuser",
    "email": "user@example.com",
    "status": "pending"
  },
  "message": "注册成功，请等待管理员审批。审批通过后您将收到通知。"
}
```

### 用户审批

```http
POST /api/users/{user_id}/approve
Content-Type: application/json

{
  "role_ids": [2, 3],  // 可选，分配的角色ID
  "notes": "审批通过"    // 可选，审批备注
}

Response 200:
{
  "success": true,
  "data": {
    "user_id": 123,
    "status": "active"
  },
  "message": "用户已批准，账号已启用"
}
```

### 用户拒绝

```http
POST /api/users/{user_id}/reject
Content-Type: application/json

{
  "reason": "资料不完整"  // 必填，拒绝原因
}

Response 200:
{
  "success": true,
  "data": {
    "user_id": 123,
    "status": "rejected"
  },
  "message": "用户已拒绝"
}
```

## 风险评估

| 风险               | 严重程度 | 缓解措施                                                   |
| ------------------ | -------- | ---------------------------------------------------------- |
| 恶意注册           | 中       | 管理员审批机制，可拒绝 + **注册 API 限流（5 次/分钟）** ⚠️ |
| 审批不及时         | 低       | 可添加系统通知提醒管理员                                   |
| 状态不一致         | 中       | 确保 `status` 和 `is_active` 同步（数据库触发器）          |
| 密码安全           | 高       | 密码强度验证，bcrypt 哈希存储                              |
| 代码兼容性         | 中       | 修复现有代码中的字段名不一致问题                           |
| **用户名枚举攻击** | **高**   | **统一错误消息，避免信息泄露** ⚠️                          |
| **权限绕过**       | **高**   | **修复 require_admin 函数，检查 is_superuser** ⚠️          |
| **Open Redirect**  | **高**   | **验证 redirect 参数是否为合法内部路径** ⚠️                |

⚠️ **安全漏洞详情请参考**：`VULNERABILITY_REVIEW.md`

## 已知问题和兼容性

### 1. 现有代码问题（需在实施时修复）⚠️ P0

**问题**：`backend/routers/users.py` 中使用了 `role.name`，但 `DimRole` 表实际字段是 `role_name`

**影响位置**：

- `require_admin()` 函数：`role.name == "admin"` 应改为 `role.role_name == "admin"`（**同时检查 is_superuser 标志**）
- `create_user()` 函数：`DimRole.name` 应改为 `DimRole.role_name`
- `update_user()` 函数：多处 `role.name` 应改为 `role.role_name`

**修复建议**：

- 在实施 Phase 2 时一并修复这些问题，确保代码一致性
- **require_admin 函数应该同时检查 is_superuser 标志**（安全关键）
- 修复代码示例：
  ```python
  async def require_admin(current_user: DimUser = Depends(get_current_user)):
      if current_user.is_superuser:
          return current_user
      is_admin = any(
          (hasattr(role, "role_code") and role.role_code == "admin") or
          (hasattr(role, "role_name") and role.role_name == "admin")
          for role in current_user.roles
      )
      if not is_admin:
          raise HTTPException(status_code=403, detail="Insufficient permissions")
      return current_user
  ```

### 2. 数据库字段兼容性

**现状**：

- `DimUser` 表目前没有 `status` 字段，需要新增
- `DimUser` 表已有 `is_active` 字段，需要与新 `status` 字段保持一致

**迁移策略**：

- 新增字段时，现有用户的 `status` 设置为 `"active"`
- 确保 `status="active"` 时，`is_active=True`
- **建议使用数据库触发器自动同步 status 和 is_active**（P1 建议）

### 3. 安全漏洞（必须修复）⚠️

**详情请参考**：`VULNERABILITY_REVIEW.md`

**P0 严重漏洞（必须修复）**：

1. 注册 API 缺少限流保护 → 添加 `@limiter.limit("5/minute")`
2. require_admin 权限检查不严格 → 检查 is_superuser 标志
3. 用户名/邮箱枚举攻击 → 统一错误消息
4. 错误码编号冲突 → 使用 4005-4008
5. **Open Redirect 漏洞** → 验证 redirect 参数是否为合法内部路径 ⚠️

**P1 中严重漏洞（建议修复）**：

6. 默认角色不存在处理 → 确保 operator 角色存在或要求指定角色
7. 状态同步机制缺失 → 使用数据库触发器
8. rejected 用户重新注册 → 允许重新注册或添加重新激活 API
9. 审批 API 状态检查 → 明确只允许 pending 状态
10. **Store 使用不一致** → 统一使用 `useAuthStore` ⚠️
11. **isLoggedIn 判断逻辑** → 确保与后端 Cookie 存储机制兼容 ⚠️

**P2 低严重性问题（可选修复）**：

12. 已登录用户访问登录页面 → 添加重定向逻辑 ⚠️
13. 登录后重定向 → 处理 redirect 参数 ⚠️
14. 公开路由配置 → 使用路由 meta 标记或集中配置 ⚠️

## 实际应用流程

### 用户注册流程

1. **用户操作**

   - 访问注册页面 (`/register`)
   - 填写注册信息（用户名、邮箱、密码等）
   - 提交注册请求

2. **系统处理**

   - 验证数据格式和唯一性
   - 创建用户账户（`status="pending"`, `is_active=False`）
   - 返回注册成功提示

3. **用户状态**
   - 状态：`pending`（待审批）
   - 无法登录（登录时提示"账号待审批"）

### 管理员审批流程

1. **查看待审批列表**

   - 访问 `/admin/users/pending`
   - 查看所有 `status="pending"` 的用户

2. **审批决策**

   - **批准**：分配角色，用户状态变为 `active`，可登录
   - **拒绝**：填写拒绝原因，用户状态变为 `rejected`，不可登录

3. **审批后处理**
   - 系统自动更新状态和字段
   - 记录审批日志和审计日志

### 用户登录流程

1. **状态检查**

   - `pending` → 返回"账号待审批，请联系管理员"（403）
   - `rejected` → 返回"账号已被拒绝，请联系管理员"（403）
   - `suspended` → 返回"账号已被暂停，请联系管理员"（403）
   - `active` → 继续登录流程

2. **登录成功**
   - 生成 JWT Token
   - 返回用户信息和权限
   - 记录登录日志

## Phase 8: 通知系统现代化改进 - P0/P1

### 背景

当前通知系统采用轮询机制（30 秒间隔），相比现代化 Web 设计存在以下差距：

1. **实时性不足**：轮询机制最多 30 秒延迟，无法即时推送
2. **用户体验**：缺少浏览器原生通知、快速操作、分组聚合等功能
3. **资源消耗**：频繁 HTTP 请求造成不必要的资源浪费

### 改进目标

将通知系统升级为现代化 Web 标准，提升用户体验和系统效率。

### Phase 8.1: WebSocket 实时推送 - P0

#### 8.1.1 后端实现

- [ ] 创建通知 WebSocket 路由（`backend/routers/notification_websocket.py`）
  - [ ] 独立的连接管理器（基于 `user_id`，不影响采集任务 WebSocket）
  - [ ] WebSocket 端点：`/api/notifications/ws`
  - [ ] **JWT 认证支持** ⚠️（P0 安全要求）
    - [ ] Token 验证（验证签名、过期时间）
    - [ ] 用户权限验证（确保用户只能接收自己的通知）
    - [ ] **Token 过期处理** ⚠️（P0 安全要求）
      - [ ] 使用 WebSocket close code 4005（**注意：与 HTTP 错误码不同**）
      - [ ] **明确区分**：
        - WebSocket close code：用于关闭连接（4005/4006）
        - WebSocket 错误码：用于消息中的错误（如 `WS_ERROR_TOKEN_EXPIRED = 4002`，仅用于消息格式）
      - [ ] 前端根据 close code 判断连接失败原因
  - [ ] **Origin 验证** ⚠️（P0 安全要求）
    - [ ] 验证 WebSocket 连接的 Origin 头
    - [ ] 仅允许来自受信任域名的连接
    - [ ] 防止跨站 WebSocket 劫持（CSWSH）攻击
  - [ ] **WSS 强制要求** ⚠️（P0 安全要求）
    - [ ] 生产环境强制使用 WSS（WebSocket Secure）
    - [ ] 拒绝非 WSS 连接（生产环境）
    - [ ] 确保数据传输加密
  - [ ] **连接速率限制** ⚠️（P0 安全要求）
    - [ ] 每个 IP 每分钟最多建立 10 个 WebSocket 连接
    - [ ] 防止快速建立/断开连接导致资源耗尽
    - [ ] **存储策略** ⚠️（P1 设计要求）
      - [ ] 优先使用 Redis（持久化、分布式）
      - [ ] Redis 不可用时降级到内存缓存（单机）
      - [ ] 内存缓存使用 LRU 策略，限制大小（最多 10000 条记录）
      - [ ] 定期清理过期的连接频率记录（如 1 小时）
  - [ ] **连接数限制** ⚠️（P0 安全要求）
    - [ ] 每个用户最多 3 个连接（防止资源滥用）
    - [ ] 系统最多 1000 个总连接（防止 DoS）
    - [ ] **超出限制处理** ⚠️（P0 安全要求）
      - [ ] 使用 WebSocket close code 4006（**注意：与 HTTP 错误码不同**）
      - [ ] 在关闭连接前发送错误消息（可选，使用 WebSocket 错误码）
      - [ ] 记录连接限制日志
  - [ ] **消息格式验证** ⚠️（P0 安全要求）
    - [ ] 使用 Pydantic 验证消息格式
    - [ ] 防止消息注入攻击
    - [ ] 验证通知内容（recipient_id 匹配）
    - [ ] 通知内容长度限制（标题最多 200 字符，内容最多 1000 字符）
  - [ ] **心跳机制** ⚠️（P0 安全要求）
    - [ ] 30 秒心跳间隔
    - [ ] 120 秒无响应则断开连接
    - [ ] 自动清理死连接
  - [ ] **连接超时处理** ⚠️（P1 安全要求）
    - [ ] 1 小时连接超时
    - [ ] 定期清理超时连接
  - [ ] 连接生命周期管理（连接/断开/重连）
- [ ] 通知推送服务集成
  - [ ] 在创建通知时通过 WebSocket 实时推送
  - [ ] **推送前验证** ⚠️（P0 安全要求）
    - [ ] 验证 recipient_id 与连接用户 ID 匹配
    - [ ] 防止跨用户通知泄露
  - [ ] 修改 `notify_user_registered`、`notify_user_approved`、`notify_user_rejected` 函数
  - [ ] **批量推送优化** ⚠️（P1 性能要求）
    - [ ] 支持批量推送（管理员通知）
    - [ ] 使用异步批量创建（避免阻塞）
    - [ ] **批量数量限制策略** ⚠️（P1 性能要求）
      - [ ] 如果管理员数量 ≤ 50：直接批量推送
      - [ ] 如果管理员数量 > 50：
        - [ ] 方案 1（推荐）：分批推送（每批 50 个，异步处理）
        - [ ] 方案 2：仅推送前 50 个管理员，其余通过轮询获取
        - [ ] 方案 3：使用消息队列（Redis/RabbitMQ）异步处理
    - [ ] **失败处理机制** ⚠️（P2 可靠性要求）
      - [ ] 记录失败的管理员 ID
      - [ ] 返回部分成功的结果（成功数量、失败数量、失败列表）
      - [ ] 可选：自动重试失败的推送（最多 3 次）
      - [ ] 记录失败日志，便于排查
    - [ ] **通知偏好检查** ⚠️（P2 用户体验要求）
      - [ ] 推送前检查用户的通知偏好（`UserNotificationPreference.enabled`）
      - [ ] 跳过已禁用通知的用户
      - [ ] 记录跳过的用户数量
    - [ ] 记录批量推送日志（成功/失败数量）
  - [ ] **连接状态监控** ⚠️（P1 运维要求）
    - [ ] 添加连接统计 API：`GET /api/notifications/ws/stats`
    - [ ] **权限要求**：仅管理员可访问（使用 `require_admin`）
    - [ ] **添加速率限制：`@limiter.limit("10/minute")`** ⚠️（P1 安全要求）
    - [ ] **响应格式**：
      ```python
      class WebSocketStatsResponse(BaseModel):
          total_connections: int  # 总连接数
          active_users: int  # 活跃用户数
          connections_per_user: Dict[int, int]  # user_id -> connection_count（最多100个用户）
          error_stats: Dict[str, int]  # error_type -> count
          timestamp: datetime  # 统计时间
      ```
    - [ ] **分页或限制** ⚠️（P2 性能要求）
      - [ ] 限制返回的连接数（如最多 100 个用户）
      - [ ] 或添加分页参数（`page`, `page_size`）
      - [ ] 或仅返回连接数最多的前 N 个用户
    - [ ] 返回：活跃连接数、每个用户的连接数、连接错误统计
- [ ] 注册 WebSocket 路由到 `backend/main.py`
  - [ ] 独立路径，不影响现有采集任务 WebSocket

#### 8.1.2 前端实现

- [ ] 创建 WebSocket 客户端服务（`frontend/src/services/notificationWebSocket.js`）
  - [ ] WebSocket 连接管理
  - [ ] **自动重连机制**（指数退避）⚠️（P1 可用性要求）
    - [ ] 连接失败时自动重连
    - [ ] 重连间隔递增（1s, 2s, 4s, 8s...）
    - [ ] 最大重连次数限制（最多 10 次）
    - [ ] 最大重连间隔限制（最多 30 秒）
    - [ ] 达到最大次数后降级到轮询
  - [ ] **降级方案** ⚠️（P1 可用性要求）
    - [ ] WebSocket 失败时降级到轮询
    - [ ] 检测 WebSocket 可用性
    - [ ] 自动切换轮询/WebSocket
  - [ ] 消息处理（通知推送、未读数量更新）
  - [ ] **消息验证** ⚠️（P0 安全要求）
    - [ ] 验证消息格式
    - [ ] 防止恶意消息导致前端错误
  - [ ] 连接状态管理
- [ ] 更新通知组件
  - [ ] 修改 `NotificationBell.vue`：移除轮询，改用 WebSocket
  - [ ] 实时更新未读数量和通知列表
  - [ ] WebSocket 连接状态显示

#### 8.1.3 架构隔离

- ✅ **独立路由**：`/api/notifications/ws`（不影响 `/api/collection/ws/collection/{task_id}`）
- ✅ **独立连接管理器**：基于 `user_id`（不影响基于 `task_id` 的采集任务管理器）
- ✅ **独立业务逻辑**：通知推送（不影响任务进度推送）

### Phase 8.2: 浏览器原生通知 - P0

#### 8.2.1 权限管理

- [ ] 通知权限请求
  - [ ] 用户首次访问时请求通知权限
  - [ ] 在通知设置页面提供权限管理
  - [ ] 权限状态显示和引导

#### 8.2.2 桌面通知实现

- [ ] 集成 Notification API
  - [ ] 在 `NotificationBell.vue` 中集成浏览器原生通知
  - [ ] 收到 WebSocket 通知时显示桌面通知
  - [ ] **通知内容验证** ⚠️（P1 安全要求）
    - [ ] 移除 HTML 标签（防止 XSS）
    - [ ] 转义特殊字符
    - [ ] 限制通知内容长度（标题最多 200 字符，内容最多 1000 字符）
  - [ ] 通知点击跳转到相关页面
  - [ ] 通知图标和徽章配置

#### 8.2.3 通知设置

- [ ] **数据库设计** ⚠️（P1 设计要求）

  - [ ] 创建 `UserNotificationPreference` 表（`modules/core/db/schema.py`）
  - [ ] 表结构：

    ```python
    class UserNotificationPreference(Base):
        __tablename__ = "user_notification_preferences"

        preference_id = Column(BigInteger, primary_key=True)
        user_id = Column(BigInteger, ForeignKey('dim_users.user_id'), nullable=False, index=True)
        notification_type = Column(String(50), nullable=False, index=True)
        enabled = Column(Boolean, default=True, nullable=False)
        desktop_enabled = Column(Boolean, default=False, nullable=False)
        created_at = Column(DateTime, server_default=func.now(), nullable=False)
        updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

        __table_args__ = (
            UniqueConstraint('user_id', 'notification_type', name='uq_user_notification_type'),
            Index('idx_user_notification_user', 'user_id'),
        )
    ```

  - [ ] 创建 Alembic 迁移脚本
  - [ ] 更新 `modules/core/db/__init__.py` 导出

- [ ] **后端 API** ⚠️（P1 设计要求）

  - [ ] `GET /api/users/me/notification-preferences` - 获取用户所有通知偏好
    - [ ] **添加速率限制：`@limiter.limit("30/minute")`** ⚠️（P1 安全要求）
  - [ ] `PUT /api/users/me/notification-preferences` - 批量更新通知偏好
    - [ ] **添加速率限制：`@limiter.limit("10/minute")`** ⚠️（P1 安全要求）
    - [ ] **权限验证** ⚠️（P1 安全要求）
      - [ ] 验证所有偏好记录的 `user_id` 必须等于 `current_user.user_id`
      - [ ] 禁止从请求中获取 `user_id`，必须使用 `current_user.user_id`
  - [ ] `GET /api/users/me/notification-preferences/{notification_type}` - 获取特定类型偏好
    - [ ] **添加速率限制：`@limiter.limit("30/minute")`** ⚠️（P1 安全要求）
  - [ ] `PUT /api/users/me/notification-preferences/{notification_type}` - 更新特定类型偏好
    - [ ] **添加速率限制：`@limiter.limit("10/minute")`** ⚠️（P1 安全要求）
    - [ ] **权限验证** ⚠️（P1 安全要求）
      - [ ] 查询偏好时验证 `user_id == current_user.user_id`
      - [ ] 创建新偏好时使用 `current_user.user_id`，不能从请求中获取
  - [ ] 创建 Pydantic schemas（`NotificationPreferenceResponse`, `NotificationPreferenceUpdate`）

- [ ] **前端实现**
  - [ ] 在用户设置页面添加通知偏好管理
  - [ ] 允许用户开启/关闭桌面通知
  - [ ] 按通知类型设置开关
  - [ ] 支持跨设备同步（从数据库读取）

### Phase 8.3: 通知快速操作 - P1

#### 8.3.1 后端 API

- [ ] 通知操作配置
  - [ ] 在通知响应中添加操作按钮配置（`actions` 字段）
  - [ ] 支持快速操作（如批准/拒绝用户）
  - [ ] **操作权限验证** ⚠️（P0 安全要求）
    - [ ] 从通知的 `actions` 字段解析操作类型（如 `approve_user`、`reject_user`）
    - [ ] 验证用户是否有权限执行操作（使用 `require_admin` 或自定义权限检查）
    - [ ] 验证操作目标资源权限（如批准用户需要管理员权限）
    - [ ] 验证操作目标资源存在且状态正确（如只能批准 `pending` 状态的用户）
    - [ ] 防止权限绕过攻击
  - [ ] **CSRF 防护** ⚠️（P0 安全要求）
    - [ ] 验证 CSRF Token（如果使用 Cookie 认证）
    - [ ] 或验证 Origin/Referer 头
  - [ ] **操作日志记录** ⚠️（P1 审计要求）
    - [ ] 记录所有快速操作到审计日志
    - [ ] 记录操作人、时间、操作类型、目标资源
  - [ ] 操作结果通知

#### 8.3.2 前端实现

- [ ] 通知操作按钮
  - [ ] 在通知卡片中显示操作按钮
  - [ ] 点击按钮直接执行操作（无需跳转）
  - [ ] 操作结果反馈

### Phase 8.4: 通知分组和聚合 - P1

#### 8.4.1 后端逻辑

- [ ] 通知分组 API
  - [ ] 在通知列表 API 中添加分组逻辑
  - [ ] 按通知类型分组
  - [ ] 相同类型通知合并显示（如"3 个新用户注册"）

#### 8.4.2 前端展示

- [ ] 通知分组 UI
  - [ ] 在通知列表中按类型分组
  - [ ] 支持展开/折叠分组
  - [ ] 分组统计显示

### Phase 8.5: 通知优先级 - P1

#### 8.5.1 数据库扩展

- [ ] 添加优先级字段
  - [ ] 在 `notifications` 表添加 `priority` 字段（VARCHAR，high/medium/low）
  - [ ] **优先级验证** ⚠️（P1 数据完整性要求）
    - [ ] 使用枚举验证优先级值
    - [ ] 无效优先级值使用默认值（medium）
    - [ ] 防止恶意优先级值注入
  - [ ] 创建 Alembic 迁移脚本

#### 8.5.2 后端逻辑

- [ ] 优先级管理
  - [ ] 在创建通知时设置优先级
  - [ ] 在通知列表 API 中按优先级排序
  - [ ] 高优先级通知特殊处理

#### 8.5.3 前端展示

- [ ] 优先级标识
  - [ ] 在通知卡片中显示优先级标识
  - [ ] 高优先级通知特殊样式
  - [ ] 优先级筛选功能

### 实施优先级和时间估算

| 优先级 | 功能               | 工作量 | 影响范围   |
| ------ | ------------------ | ------ | ---------- |
| P0     | WebSocket 实时推送 | 2-3 天 | 仅通知模块 |
| P0     | 浏览器原生通知     | 1-2 天 | 仅通知模块 |
| P1     | 通知快速操作       | 1-2 天 | 仅通知模块 |
| P1     | 通知分组聚合       | 1-2 天 | 仅通知模块 |
| P1     | 通知优先级         | 1 天   | 仅通知模块 |

**总计**：约 6-10 天（按优先级分阶段实施）

### 架构隔离保证

- ✅ **独立 WebSocket 路由**：不影响现有采集任务 WebSocket
- ✅ **独立连接管理器**：基于 `user_id`，与 `task_id` 完全隔离
- ✅ **独立业务逻辑**：通知推送与任务进度推送互不干扰
- ✅ **向后兼容**：现有功能完全不受影响

### 安全要求（必须实施）⚠️

#### P0 安全要求（必须修复）

1. **密码重置/账户锁定/用户暂停后强制撤销活跃会话** ⚠️

   - 密码重置后，必须撤销用户所有活跃会话（防止使用旧密码的 token 继续操作）
   - 账户锁定后，必须撤销用户所有活跃会话（防止使用活跃会话继续操作）
   - 用户暂停后，必须撤销用户所有活跃会话（防止使用活跃会话继续操作）
   - 实现通用函数 `revoke_all_user_sessions(user_id, reason)`

2. **Token 刷新 API 必须检查账户状态** ⚠️

   - `refresh_token` API 必须检查用户账户状态（`status == "active"` 且 `is_active == True`）
   - 必须检查账户是否被锁定（`locked_until`）
   - 必须检查会话是否已被撤销（`is_active=False`）
   - 账户状态不满足时，拒绝刷新并返回相应错误

3. **WebSocket 认证和权限验证**

   - JWT Token 验证（签名、过期）
   - 用户权限验证（确保用户只能接收自己的通知）
   - Token 过期处理（使用 WebSocket close code 4005，避免与现有错误码冲突）

4. **WebSocket Origin 验证**

   - 验证 WebSocket 连接的 Origin 头
   - 仅允许来自受信任域名的连接
   - 防止跨站 WebSocket 劫持（CSWSH）攻击

5. **WebSocket 安全传输（WSS）**

   - 生产环境强制使用 WSS（WebSocket Secure）
   - 拒绝非 WSS 连接（生产环境）
   - 确保数据传输加密

6. **WebSocket 连接速率限制**

   - 每个 IP 每分钟最多建立 10 个 WebSocket 连接
   - 防止快速建立/断开连接导致资源耗尽

7. **连接数限制**

   - 每个用户最多 3 个连接
   - 系统最多 1000 个总连接
   - 超出限制时拒绝连接（使用 WebSocket close code 4006）

8. **消息格式验证**

   - 使用 Pydantic 验证消息格式
   - 验证通知内容（recipient_id 匹配）
   - 防止消息注入攻击
   - 通知内容长度限制（标题最多 200 字符，内容最多 1000 字符）

9. **心跳机制**

   - 30 秒心跳间隔
   - 120 秒无响应则断开
   - 自动清理死连接

10. **快速操作 CSRF 防护**

    - CSRF Token 验证
    - 或验证 Origin/Referer 头

11. **快速操作权限验证**
    - 从通知的 `actions` 字段解析操作类型
    - 验证用户权限（使用 `require_admin` 或自定义权限检查）
    - 验证操作目标资源权限和状态

#### P1 安全要求（建议修复）

1. **get_current_user 必须检查 status 字段** ⚠️

   - `get_current_user` 函数必须检查 `status == "active"`，而不仅仅是 `is_active`
   - 防止被暂停的用户使用现有 token 访问系统

2. **会话更新时必须检查账户状态和会话撤销状态** ⚠️

   - Token 刷新时更新会话前，必须检查：
     - 会话是否已被撤销（`is_active=False`）
     - 用户账户状态（`status == "active"` 且 `is_active == True`）
     - 账户是否被锁定
   - 检查失败时，不更新会话，返回错误

3. **WebSocket 降级方案**

   - WebSocket 失败时降级到轮询
   - 自动检测和切换
   - 最大重连次数限制（10 次）后降级

4. **浏览器通知内容验证**

   - 移除 HTML 标签
   - 转义特殊字符
   - 限制内容长度（标题最多 200 字符，内容最多 1000 字符）

5. **操作日志记录**

   - 记录所有快速操作
   - 审计追踪

6. **优先级验证**

   - 枚举验证优先级值
   - 默认值处理

7. **连接超时处理**

   - 1 小时连接超时
   - 定期清理超时连接

8. **批量推送性能优化**

   - 使用异步批量创建
   - 限制批量通知数量（最多 50 个管理员）
   - 考虑使用消息队列处理大量通知（可选）

9. **WebSocket 连接状态监控**

   - 添加连接统计 API
   - 返回活跃连接数、每个用户的连接数、连接错误统计

10. **通知设置持久化**
    - 使用数据库存储（`user_notification_preferences` 表）
    - 支持跨设备同步

## 后续优化（可选功能）

1. **自动审批规则**：特定域名邮箱自动审批
2. **审批工作流**：多级审批流程
3. **用户信息完善**：注册后补充更多信息
4. **双因素认证（2FA）**：两步验证
5. **标准密码重置流程**：邮箱验证 + 重置 Token（如果需要）
6. **通知统计和分析**：阅读率、响应时间等（Phase 8.6 - P2）
7. **通知模板系统**：可配置的通知模板（Phase 8.7 - P2）
8. **通知偏好设置**：免打扰时间、通知频率等（Phase 8.8 - P2）
