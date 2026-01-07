# 设计文档：用户注册和审批流程

**创建日期**: 2026-01-04  
**最后更新**: 2026-01-05  
**状态**: 📋 设计阶段  
**版本**: 1.1

## 设计概述

本设计文档详细说明用户注册和审批流程的技术实现细节，采用管理员审批机制，适合中小团队快速实施。

## 核心设计决策

### 1. 审批机制选择

**决策**：使用管理员审批，而非邮箱验证

**原因**：

- ✅ 中小团队无需配置邮件服务
- ✅ 审批流程简单，易于管理
- ✅ 管理员可控制用户质量
- ✅ 实施成本低，快速上线

**替代方案**：

- 邮箱验证：需要邮件服务配置，实施复杂
- 自动审批：安全性不足，不适合生产环境
- 邀请注册：适合 B2B 场景，但不适合内部系统

### 2. 用户状态设计

**决策**：使用 `status` 字段 + `is_active` 字段

**原因**：

- ✅ `status` 字段语义清晰（pending/active/rejected/suspended）
- ✅ `is_active` 字段与现有代码兼容
- ✅ 两个字段保持一致，确保数据完整性

**状态映射规则**：

```python
# status 和 is_active 必须保持一致
if status == "active":
    is_active = True
else:
    is_active = False
```

> ⚠️ **重要**：当 `is_active=False` 时，必须同步设置 `status="suspended"`（或其他非 active 状态）。违反此规则会导致数据不一致。

### 3. 密码强度要求

**决策**：至少 8 位，包含字母和数字

**原因**：

- ✅ 平衡安全性和用户体验
- ✅ 符合大多数系统的标准
- ✅ 不需要过复杂的规则（如特殊字符）

**未来扩展**：

- 可配置密码强度规则
- 密码复杂度评分
- 密码历史记录（防止重复使用）

### 4. 角色分配策略

**决策**：审批时分配角色，默认 operator 角色

**原因**：

- ✅ 管理员可控制用户权限
- ✅ 默认角色保证新用户有基本权限
- ✅ 支持后续修改角色

**分配规则**：

- 如果指定 `role_ids`，使用指定角色
- 如果未指定，默认分配 `operator` 角色
- 支持多角色分配（用户可拥有多个角色）

## 数据模型设计

### DimUser 表扩展

```python
# modules/core/db/schema.py

class DimUser(Base):
    __tablename__ = "dim_users"

    # 现有字段...
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)

    # ⭐ 新增字段
    status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="用户状态: pending/active/rejected/suspended/deleted"
    )
    approved_at = Column(
        DateTime,
        nullable=True,
        comment="审批时间"
    )
    approved_by = Column(
        BigInteger,
        ForeignKey('dim_users.user_id'),
        nullable=True,
        comment="审批人ID"
    )
    rejection_reason = Column(
        Text,
        nullable=True,
        comment="拒绝原因"
    )
```

### UserApprovalLog 表（必需）⚠️

```python
class UserApprovalLog(Base):
    """用户审批记录表（用于审计）"""
    __tablename__ = "user_approval_logs"

    log_id = Column(BigInteger, primary_key=True, index=True)

    # 用户信息
    user_id = Column(
        BigInteger,
        ForeignKey('dim_users.user_id'),
        nullable=False,
        index=True
    )

    # 审批信息
    action = Column(
        String(20),
        nullable=False,
        index=True,
        comment="操作类型: approve/reject/suspend"
    )
    approved_by = Column(
        BigInteger,
        ForeignKey('dim_users.user_id'),
        nullable=False,
        comment="操作人ID"
    )
    reason = Column(
        Text,
        nullable=True,
        comment="操作原因/备注"
    )

    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True
    )

    __table_args__ = (
        Index("idx_approval_user_time", "user_id", "created_at"),
        Index("idx_approval_action_time", "action", "created_at"),
    )
```

## API 设计详细说明

### 1. 用户注册 API

**端点**: `POST /api/auth/register`

**速率限制**: `5次/分钟`（IP 限流）⚠️（P0 安全漏洞）

**请求体**:

```python
class RegisterRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        regex="^[a-zA-Z0-9_]+$",
        description="用户名（3-50字符，字母数字下划线）"
    )
    email: EmailStr = Field(..., description="邮箱地址")
    password: str = Field(
        ...,
        min_length=8,
        description="密码（至少8位，包含字母和数字）"
    )
    full_name: Optional[str] = Field(None, max_length=200, description="姓名")
    phone: Optional[str] = Field(None, max_length=50, description="手机号")
    department: Optional[str] = Field(None, max_length=100, description="部门")

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('密码长度至少8位')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('密码必须包含字母')
        if not re.search(r'[0-9]', v):
            raise ValueError('密码必须包含数字')
        return v
```

**响应**:

```python
class RegisterResponse(BaseModel):
    user_id: int
    username: str
    email: str
    status: str  # "pending"
    message: str
```

**业务逻辑**:

1. 验证请求数据（Pydantic 自动验证）
2. **合并检查用户名和邮箱唯一性（统一错误消息）** ⚠️（P0 安全漏洞）
3. 密码哈希（bcrypt）
4. 创建用户记录（status="pending", is_active=False）
5. 记录审计日志（user_registered）
6. 返回成功响应

**错误处理**:

- **用户名或邮箱已被使用：400 + `DATA_UNIQUE_CONSTRAINT_VIOLATION`（统一错误消息）** ⚠️
- 密码强度不足：422 + 验证错误

**安全要求**:

- **必须添加速率限制：`@limiter.limit("5/minute")`** ⚠️（P0 安全漏洞）

### 2. 用户审批 API

**端点**: `POST /api/users/{user_id}/approve`

**权限要求**: 管理员（`require_admin`）

**请求体**:

```python
class ApproveUserRequest(BaseModel):
    role_ids: List[int] = Field(
        default_factory=list,
        description="角色ID列表（可选，默认operator）"
    )
    notes: Optional[str] = Field(None, description="审批备注")
```

**业务逻辑**:

1. 权限检查（必须是管理员）
2. 查找用户（user_id）
3. 检查用户状态（必须是 pending）
4. 更新用户状态（status="active", is_active=True）
5. 记录审批时间（approved_at=now）
6. 记录审批人（approved_by=current_user.user_id）
7. 分配角色：
   - 如果指定了 role_ids，分配指定角色
     - ⚠️ **验证所有 role_ids 是否存在**（Vulnerability 50）
     - 如果存在不存在的角色 ID，返回错误（不能静默忽略）
   - 如果未指定，分配默认 operator 角色（**必须确保 operator 角色存在**）⚠️（P1 建议）
8. 记录审批日志（UserApprovalLog）
9. 记录审计日志（user_approved）
   - ⚠️ **获取真实 IP 和 User-Agent**（Vulnerability 52）
   - 不能硬编码 `"127.0.0.1"` 和 `"Unknown"`
10. 通知用户审批通过
    - ⚠️ **添加错误处理**（Vulnerability 51）
    - 通知失败不应影响审批操作，但应记录警告日志
11. 返回成功响应

**错误处理**:

- 用户不存在：404
- 用户状态不是 pending：400（只能审批 pending 状态的用户）
- 非管理员：403
- 默认角色不存在：500（如果未指定 role_ids 且 operator 角色不存在）

### 3. 用户拒绝 API

**端点**: `POST /api/users/{user_id}/reject`

**权限要求**: 管理员

**请求体**:

```python
class RejectUserRequest(BaseModel):
    reason: str = Field(
        ...,
        min_length=5,
        description="拒绝原因（必填，至少5字符）"
    )
```

**业务逻辑**:

1. 权限检查
2. 查找用户
3. 检查用户状态（必须是 pending）
4. 更新用户状态（status="rejected", is_active=False）
5. 记录拒绝原因（rejection_reason）
6. 记录审批人（approved_by）
7. 记录审批日志（UserApprovalLog）
8. 记录审计日志（user_rejected）
9. 返回成功响应

### 4. 待审批用户列表 API

**端点**: `GET /api/users/pending`

**权限要求**: 管理员

**查询参数**:

- `page`: int = 1（页码）
- `page_size`: int = 20（每页数量）

**响应**:

```python
{
  "success": true,
  "data": [
    {
      "user_id": 123,
      "username": "newuser",
      "email": "user@example.com",
      "status": "pending",  # ⚠️ 必需字段（Vulnerability 49）
      "full_name": "New User",
      "department": "运营部",
      "created_at": "2026-01-04T10:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 5,
    "total_pages": 1
  }
}
```

**响应 Schema**:

```python
class PendingUserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    status: str  # ⚠️ 必需字段（Vulnerability 49）
    full_name: Optional[str]
    department: Optional[str]
    created_at: datetime
```

**业务逻辑**:

1. 权限检查
2. 查询 status="pending" 的用户
3. 按 created_at 倒序排序
4. 分页查询
5. 返回用户列表和分页信息

### 5. 登录 API 修改

**修改点**: `POST /api/auth/login`

**新增逻辑**:

```python
# 查找用户（预加载 roles 关系）
result = await db.execute(
    select(DimUser)
    .where(DimUser.username == credentials.username)
    .options(selectinload(DimUser.roles))
)
user = result.scalar_one_or_none()

# 1. 先检查用户是否存在（不泄露信息，统一错误消息）
if not user:
    return error_response(
        code=ErrorCode.AUTH_CREDENTIALS_INVALID,
        message="Invalid credentials",
        error_type=get_error_type(ErrorCode.AUTH_CREDENTIALS_INVALID),
        recovery_suggestion="用户名或密码错误",
        status_code=401
    )

# 2. 检查用户状态（在密码验证之前）
if user.status == "pending":
    return error_response(
        code=ErrorCode.AUTH_ACCOUNT_PENDING,
        message="账号待审批，请联系管理员",
        error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_PENDING),
        recovery_suggestion="请等待管理员审批",
        status_code=403
    )

if user.status == "rejected":
    return error_response(
        code=ErrorCode.AUTH_ACCOUNT_REJECTED,
        message="账号已被拒绝，请联系管理员",
        error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_REJECTED),
        recovery_suggestion="请联系管理员了解拒绝原因",
        status_code=403
    )

if user.status == "suspended":
    return error_response(
        code=ErrorCode.AUTH_ACCOUNT_SUSPENDED,
        message="账号已被暂停，请联系管理员",
        error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_SUSPENDED),
        recovery_suggestion="请联系管理员了解暂停原因",
        status_code=403
    )

# 3. 检查status和is_active（只有active状态且is_active=True才能继续）
if user.status != "active" or not user.is_active:
    return error_response(
        code=ErrorCode.AUTH_ACCOUNT_INACTIVE,
        message="账号未激活",
        error_type=get_error_type(ErrorCode.AUTH_ACCOUNT_INACTIVE),
        recovery_suggestion="请联系管理员激活账号",
        status_code=403
    )

# 4. 验证密码（只有到这里才会验证密码）
if not auth_service.verify_password(credentials.password, user.password_hash):
    # ... 密码验证失败处理（记录审计日志等）
    ...
```

## 安全性考虑

### 1. 密码安全

- ✅ 使用 bcrypt 哈希存储（cost factor >= 12）
- ✅ 密码强度验证（至少 8 位，包含字母和数字）
- ✅ 不在日志中记录密码

### 2. 权限控制

- ✅ 审批 API 需要管理员权限
- ✅ 使用 `require_admin` 依赖检查
- ✅ 审计日志记录所有审批操作

### 3. 数据验证

- ✅ 用户名格式验证（防止 SQL 注入、XSS）
- ✅ 邮箱格式验证
- ✅ 密码强度验证
- ✅ 输入数据清理

### 4. 错误处理

- ✅ 统一错误响应格式
- ✅ 不泄露敏感信息（如用户是否存在）
- ✅ 友好的错误提示

## 性能考虑

### 1. 数据库索引

- ✅ `status` 字段添加索引（查询待审批用户）
- ✅ `approved_by` 字段添加索引（查询审批记录）
- ✅ `created_at` 字段已有索引（排序查询）

### 2. 查询优化

- ✅ 使用 `selectinload` 预加载角色关系
- ✅ 分页查询避免一次性加载大量数据
- ✅ 使用数据库索引优化查询

## 前端路由守卫设计

### 1. 登录状态检查

**目标**：确保用户必须登录才能访问系统

**实现位置**：`frontend/src/router/index.js`

**逻辑**：

```javascript
router.beforeEach((to, from, next) => {
  // ⚠️ 注意：需要确定使用 useAuthStore 还是 useUserStore
  // 建议统一使用 useAuthStore（功能更完整）
  const authStore = useAuthStore(); // 或 useUserStore()

  // 1. 定义公开路由（不需要登录）
  // ⚠️ 建议：使用路由meta标记 public: true，而不是硬编码列表
  const publicRoutes = [
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
  ];

  // 2. 如果已登录，访问公开路由应该重定向到默认页面
  if (
    authStore.isLoggedIn &&
    (publicRoutes.includes(to.path) || to.meta?.public)
  ) {
    next("/business-overview");
    return;
  }

  // 3. 检查是否已登录
  if (!authStore.isLoggedIn) {
    // 如果是公开路由，允许访问
    if (publicRoutes.includes(to.path) || to.meta?.public) {
      next();
      return;
    }
    // 否则重定向到登录页面，保存原始路径用于登录后重定向
    next(`/login?redirect=${encodeURIComponent(to.fullPath)}`);
    return;
  }

  // 4. 如果已登录，检查权限和角色（现有逻辑保持不变）
  const isAdmin = authStore.hasRole ? authStore.hasRole(["admin"]) : false;

  if (!isAdmin && to.meta.permission) {
    if (
      authStore.hasPermission &&
      !authStore.hasPermission(to.meta.permission)
    ) {
      next("/business-overview");
      return;
    }
  }

  if (to.meta.roles && to.meta.roles.length > 0) {
    if (authStore.hasRole && !authStore.hasRole(to.meta.roles)) {
      next("/business-overview");
      return;
    }
  }

  next();
});
```

### 2. 登录页面设计

**路由**：`/login`

**功能**：

- 用户名/密码登录表单
- 表单验证
- 登录错误提示（包括用户状态错误：pending/rejected/suspended）
- 注册链接
- 忘记密码链接（如果实现了密码重置）
- 登录成功后重定向到原始页面或默认页面

**登录成功后的重定向处理**：

```javascript
// 在登录页面组件中
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

// ⚠️ 验证redirect是否是合法的内部路径（防止Open Redirect漏洞）
const isValidRedirect = (url) => {
  if (!url) return false;
  // 禁止协议（http:, https:, javascript:, data: 等）
  if (/^[a-z]+:/i.test(url)) return false;
  // 禁止协议相对URL（//evil.com）
  if (url.startsWith("//")) return false;
  // 禁止反斜杠（某些浏览器会转换）
  if (url.includes("\\")) return false;
  // 只允许以 / 开头
  if (!url.startsWith("/")) return false;
  // 防止 /\/evil.com 这种绕过（第二个字符是 / 或 \）
  if (url.length > 1 && (url[1] === "/" || url[1] === "\\")) return false;
  return true;
};

// 登录成功后
const handleLoginSuccess = () => {
  const redirect = route.query.redirect;
  // ⚠️ 必须验证redirect参数，防止钓鱼攻击
  if (redirect && isValidRedirect(redirect)) {
    router.push(redirect);
  } else {
    router.push("/business-overview");
  }
};
```

### 3. Store 使用策略

**问题**：

- 系统中有两个 Store：`useUserStore` 和 `useAuthStore`
- 需要统一使用一个 Store 以避免状态不一致
- **Token 存储键名不一致**：
  - `useUserStore`: `localStorage.getItem('token')`
  - `useAuthStore`: `localStorage.getItem('access_token')`

**决策：必须使用 `useAuthStore`** ⚠️

**原因**：

- ✅ `useAuthStore` 调用真实的登录 API
- ✅ 功能更完整（登录、登出、刷新 token）
- ✅ `isLoggedIn` 逻辑更可靠（同时检查 token 和 user）
- ❌ `useUserStore.login()` 是模拟登录（Mock），**不适合生产环境**

**Token 存储统一方案**：

```javascript
// 统一使用 useAuthStore 的存储键名
const token = ref(localStorage.getItem("access_token") || "");
const refreshToken = ref(localStorage.getItem("refresh_token") || "");
```

**hasPermission 实现差异**：

- `useAuthStore`: 简化版（admin 返回 true，其他也返回 true）
- `useUserStore`: 检查 `permissions` 数组

**建议**：完善 `useAuthStore.hasPermission()` 实现，或在路由守卫中使用 `useUserStore` 的权限检查逻辑

**实施步骤**：

1. 路由守卫从 `useUserStore` 切换到 `useAuthStore`
2. 登录页面使用 `useAuthStore.login()`
3. 删除或标记 `useUserStore.login()` 为废弃
4. 统一使用 `access_token` 作为存储键名

## 会话管理表设计（Phase 7 可选）

如果实现会话管理功能，需要创建以下表：

```python
class UserSession(Base):
    """用户会话表（用于会话管理）"""
    __tablename__ = "user_sessions"

    session_id = Column(String(64), primary_key=True, comment="会话ID（Token的哈希值）")
    user_id = Column(
        BigInteger,
        ForeignKey('dim_users.user_id'),
        nullable=False,
        index=True
    )

    # 会话信息
    device_info = Column(String(255), nullable=True, comment="设备信息（User-Agent）")
    ip_address = Column(String(45), nullable=True, comment="IP地址")
    location = Column(String(100), nullable=True, comment="登录位置（可选）")

    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间（登录时间）"
    )
    expires_at = Column(
        DateTime,
        nullable=False,
        comment="过期时间"
    )
    last_active_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后活跃时间"
    )

    # 状态
    is_active = Column(Boolean, default=True, nullable=False, comment="是否有效")
    revoked_at = Column(DateTime, nullable=True, comment="撤销时间")
    revoked_reason = Column(String(100), nullable=True, comment="撤销原因")

    __table_args__ = (
        Index("idx_session_user_active", "user_id", "is_active"),
        Index("idx_session_expires", "expires_at"),
    )
```

**会话管理 API 设计**：

```python
# 获取当前用户的活跃会话列表
@router.get("/users/me/sessions")
async def get_my_sessions(current_user: DimUser = Depends(get_current_user)):
    """获取当前用户的所有活跃会话"""
    pass

# 撤销指定会话
@router.delete("/users/me/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: DimUser = Depends(get_current_user)
):
    """撤销指定会话（强制登出其他设备）"""
    pass

# 撤销除当前会话外的所有会话
@router.delete("/users/me/sessions")
async def revoke_other_sessions(
    current_user: DimUser = Depends(get_current_user),
    current_session_id: str = Header(None, alias="X-Session-ID")
):
    """撤销除当前会话外的所有会话"""
    pass
```

## 强制撤销会话和通知设计（P0 安全要求）⚠️

### 1. 通用会话撤销函数

**设计**：创建通用函数 `revoke_all_user_sessions`，用于撤销用户所有活跃会话。

**实现位置**：`backend/routers/users.py` 或 `backend/services/session_service.py`

**代码示例**：

```python
async def revoke_all_user_sessions(
    db: AsyncSession,
    user_id: int,
    reason: str
) -> int:
    """
    撤销用户所有活跃会话
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        reason: 撤销原因
    
    Returns:
        撤销的会话数量
    """
    from modules.core.db import UserSession
    from datetime import datetime
    
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.is_active == True,
            UserSession.expires_at > datetime.utcnow()
        )
    )
    sessions = result.scalars().all()
    
    revoked_count = 0
    for session in sessions:
        session.is_active = False
        session.revoked_at = datetime.utcnow()
        session.revoked_reason = reason
        revoked_count += 1
    
    await db.commit()
    return revoked_count
```

### 2. 密码重置后强制撤销会话

**触发场景**：管理员重置用户密码

**实现位置**：`backend/routers/users.py` - `reset_user_password` API

**代码示例**：

```python
# 重置密码
user.password_hash = auth_service.hash_password(new_password)
user.failed_login_attempts = 0
user.locked_until = None

# ⚠️ 强制撤销所有活跃会话（P0 安全要求）
revoked_count = await revoke_all_user_sessions(
    db=db,
    user_id=user.user_id,
    reason="密码重置，强制登出"
)

# ⚠️ 发送密码重置通知（P1）
try:
    from backend.routers.notifications import notify_password_reset
    await notify_password_reset(
        db=db,
        user_id=user.user_id,
        reset_by=current_user.username
    )
except Exception as e:
    logger.warning(f"[WARN] Failed to send password reset notification: {e}")

await db.commit()
```

**站内通知的价值**：
- 用户下次登录时会看到通知："您的密码已被管理员重置，请使用新密码登录"
- 作为历史记录，用户可以查看账户状态变更历史

### 4. Token刷新API账户状态检查（P0 安全要求）⚠️

**触发场景**：用户刷新 access token

**实现位置**：`backend/routers/auth.py` - `refresh_token` API

**代码示例**：

```python
# backend/routers/auth.py:refresh_token
try:
    new_tokens = await auth_service.refresh_token_pair(refresh_token_value)
    
    # ⚠️ 新增：检查用户账户状态
    payload = auth_service.verify_token(refresh_token_value)
    user_id = payload.get("user_id")
    
    if user_id:
        async with AsyncSessionLocal() as temp_db:
            # 获取用户信息
            user_result = await temp_db.execute(
                select(DimUser).where(DimUser.user_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                return error_response(
                    code=ErrorCode.AUTH_TOKEN_INVALID,
                    message="User not found",
                    status_code=401
                )
            
            # 检查账户状态
            if user.status != "active" or not user.is_active:
                return error_response(
                    code=ErrorCode.AUTH_ACCOUNT_INACTIVE,
                    message="账号未激活",
                    status_code=403
                )
            
            # 检查账户是否被锁定
            if user.locked_until and user.locked_until > datetime.utcnow():
                return error_response(
                    code=ErrorCode.AUTH_ACCOUNT_LOCKED,
                    message="账户已被锁定",
                    status_code=403
                )
            
            # 检查会话是否已被撤销
            session_result = await temp_db.execute(
                select(UserSession)
                .where(
                    UserSession.user_id == user_id,
                    UserSession.is_active == True
                )
                .order_by(UserSession.last_active_at.desc())
                .limit(1)
            )
            session = session_result.scalar_one_or_none()
            
            if not session or session.is_active == False:
                return error_response(
                    code=ErrorCode.AUTH_TOKEN_INVALID,
                    message="Session has been revoked",
                    status_code=401
                )
            
            # 继续更新会话...
```

### 5. get_current_user 状态检查增强（P1 安全要求）⚠️

**触发场景**：所有需要认证的 API 端点

**实现位置**：`backend/routers/auth.py` - `get_current_user` 函数

**代码示例**：

```python
# backend/routers/auth.py:get_current_user
user = result.scalar_one_or_none()
# ⚠️ 修改：添加 status 检查
if not user or not user.is_active or user.status != "active":
    raise HTTPException(
        status_code=401,
        detail="User not found or inactive"
    )
```

### 6. 会话更新时状态检查（P1 安全要求）⚠️

**触发场景**：Token 刷新时更新会话

**实现位置**：`backend/routers/auth.py` - `refresh_token` API

**代码示例**：

```python
# backend/routers/auth.py:refresh_token
session = session_result.scalar_one_or_none()

if session:
    # ⚠️ 新增：检查会话和账户状态
    if session.is_active == False:
        return error_response(
            code=ErrorCode.AUTH_TOKEN_INVALID,
            message="Session has been revoked",
            status_code=401
        )
    
    # 获取用户信息并检查状态
    user_result = await temp_db.execute(
        select(DimUser).where(DimUser.user_id == user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user or user.status != "active" or not user.is_active:
        return error_response(
            code=ErrorCode.AUTH_ACCOUNT_INACTIVE,
            message="Account is not active",
            status_code=403
        )
    
    # 更新会话信息
    session.session_id = new_session_id
    session.last_active_at = datetime.utcnow()
    session.expires_at = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    session.is_active = True
    await temp_db.commit()
```

### 3. 账户锁定后强制撤销会话

**触发场景**：登录失败 5 次后账户自动锁定

**实现位置**：`backend/routers/auth.py` - `login` API

**代码示例**：

```python
if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
    user.locked_until = datetime.utcnow() + timedelta(minutes=30)
    
    # ⚠️ 强制撤销所有活跃会话（P0 安全要求）
    revoked_count = await revoke_all_user_sessions(
        db=db,
        user_id=user.user_id,
        reason="账户被锁定，强制登出"
    )
    
    # ⚠️ 发送账户锁定通知（P1）
    try:
        from backend.routers.notifications import notify_account_locked
        await notify_account_locked(
            db=db,
            user_id=user.user_id,
            locked_until=user.locked_until,
            reason="多次登录失败"
        )
    except Exception as e:
        logger.warning(f"[WARN] Failed to send account locked notification: {e}")
    
    await db.commit()
```

**站内通知的价值**：
- 用户下次尝试登录时会看到通知："您的账户因多次登录失败已被锁定 X 分钟"
- 作为历史记录，用户可以查看账户状态变更历史

### 4. 账户解锁通知

**触发场景**：
- 管理员手动解锁账户
- 账户锁定时间过期后自动解锁

**实现位置**：
- `backend/routers/users.py` - `unlock_user_account` API
- `backend/routers/auth.py` - `login` API（自动解锁）

**代码示例**：

```python
# 解锁账户
user.locked_until = None
user.failed_login_attempts = 0

# ⚠️ 发送账户解锁通知（P1）
try:
    from backend.routers.notifications import notify_account_unlocked
    await notify_account_unlocked(
        db=db,
        user_id=user.user_id,
        unlocked_by=current_user.username if current_user else "system",
        reason=request_body.reason if hasattr(request_body, 'reason') else "锁定时间已过期，自动解锁"
    )
except Exception as e:
    logger.warning(f"[WARN] Failed to send account unlocked notification: {e}")

await db.commit()
```

**站内通知的价值**：
- 用户下次登录时会看到通知："您的账户已解锁，可以重新登录"
- 作为历史记录，用户可以查看账户状态变更历史

### 5. 用户暂停后强制撤销会话

**触发场景**：管理员通过 `update_user` API 设置 `is_active=False`

**实现位置**：`backend/routers/users.py` - `update_user` API

**代码示例**：

```python
if user_update.is_active is not None:
    old_is_active = user.is_active
    user.is_active = user_update.is_active
    
    # ⚠️ 同步更新 status 字段（数据一致性）
    if user_update.is_active == False and old_is_active == True:
        # 从 active 变为 inactive，设置为 suspended
        if user.status == "active":
            user.status = "suspended"
            
            # ⚠️ 强制撤销所有活跃会话（P0 安全要求）
            revoked_count = await revoke_all_user_sessions(
                db=db,
                user_id=user.user_id,
                reason="账户被暂停，强制登出"
            )
            
            # ⚠️ 发送用户暂停通知（P1）
            try:
                from backend.routers.notifications import notify_user_suspended
                await notify_user_suspended(
                    db=db,
                    user_id=user.user_id,
                    suspended_by=current_user.username,
                    reason="管理员手动暂停"
                )
            except Exception as e:
                logger.warning(f"[WARN] Failed to send suspension notification: {e}")
    elif user_update.is_active == True and old_is_active == False:
        # 从 inactive 变为 active，设置为 active
        if user.status == "suspended":
            user.status = "active"
```

**站内通知的价值**：
- 用户下次尝试登录时会看到通知："您的账户已被暂停，请联系管理员"
- 作为历史记录，用户可以查看账户状态变更历史

### 6. 通知类型扩展

**需要添加的通知类型**：

```python
# backend/schemas/notification.py
class NotificationType(str, Enum):
    USER_REGISTERED = "user_registered"
    USER_APPROVED = "user_approved"
    USER_REJECTED = "user_rejected"
    USER_SUSPENDED = "user_suspended"  # ✅ 已存在
    PASSWORD_RESET = "password_reset"  # ✅ 已存在
    ACCOUNT_LOCKED = "account_locked"  # ⚠️ 需要添加
    ACCOUNT_UNLOCKED = "account_unlocked"  # ⚠️ 需要添加
    SYSTEM_ALERT = "system_alert"
```

### 7. 通知函数实现和调用位置

**需要创建的通知函数**：

1. `notify_password_reset(db, user_id, reset_by)` - 密码重置通知
   - ✅ **已存在**（`backend/routers/notifications.py` 第515行）
   - ⚠️ **调用位置**：`backend/routers/users.py` - `reset_user_password` API
   - ⚠️ **当前状态**：函数存在但未被调用

2. `notify_account_locked(db, user_id, locked_until, reason)` - 账户锁定通知
   - ❌ **不存在**，需要创建
   - ⚠️ **调用位置**：`backend/routers/auth.py` - `login` API（账户锁定后）

3. `notify_account_unlocked(db, user_id, unlocked_by, reason)` - 账户解锁通知
   - ❌ **不存在**，需要创建
   - ⚠️ **调用位置**：
     - `backend/routers/users.py` - `unlock_user_account` API
     - `backend/routers/auth.py` - `login` API（自动解锁后）

4. `notify_user_suspended(db, user_id, suspended_by, reason)` - 用户暂停通知
   - ❌ **不存在**，需要创建
   - ⚠️ **调用位置**：`backend/routers/users.py` - `update_user` API（用户暂停后）

**实现位置**：`backend/routers/notifications.py`

**函数签名和实现示例**：参见 `VULNERABILITY_REVIEW.md` 漏洞 61 的修复建议。

## 扩展性考虑

### 1. 未来可扩展功能

- 密码重置功能（P1 建议）- 已实现，需要添加强制撤销会话和通知
- 账户锁定机制（P1 建议）- 已实现，需要添加强制撤销会话和通知
- 会话管理（P1 可选）- 已实现
- 自动审批规则（特定域名自动审批）
- 多级审批流程
- 审批提醒通知（系统通知）
- 用户信息完善流程（注册后补充信息）

### 2. 配置化

- 密码强度规则可配置
- 默认角色可配置
- 审批流程可配置
- 账户锁定策略可配置（失败次数、锁定时间）

## 测试策略

### 1. 单元测试

- 用户注册 API 测试
- 用户审批 API 测试
- 用户拒绝 API 测试
- 登录状态检查测试

### 2. 集成测试

- 完整的注册-审批-登录流程
- 管理员审批工作流
- 错误场景测试

### 3. 安全性测试

- 权限检查测试
- SQL 注入测试
- XSS 测试
- 密码强度验证测试

## 迁移策略

### 1. 数据迁移

```python
# Alembic迁移脚本示例
def upgrade():
    # 添加字段
    op.add_column('dim_users', sa.Column('status', sa.String(20), nullable=False, server_default='active'))
    op.add_column('dim_users', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.add_column('dim_users', sa.Column('approved_by', sa.BigInteger(), nullable=True))
    op.add_column('dim_users', sa.Column('rejection_reason', sa.Text(), nullable=True))

    # 添加外键约束（自引用）
    op.create_foreign_key(
        'fk_users_approved_by',
        'dim_users', 'dim_users',
        ['approved_by'], ['user_id'],
        ondelete='SET NULL'  # 删除审批人时，设置为NULL
    )

    # 更新现有用户数据
    op.execute("""
        UPDATE dim_users
        SET status = 'active', is_active = true
        WHERE status IS NULL
    """)

    # 创建索引
    op.create_index('idx_users_status', 'dim_users', ['status'])

def downgrade():
    op.drop_index('idx_users_status', 'dim_users')
    op.drop_constraint('fk_users_approved_by', 'dim_users', type_='foreignkey')
    op.drop_column('dim_users', 'rejection_reason')
    op.drop_column('dim_users', 'approved_by')
    op.drop_column('dim_users', 'approved_at')
    op.drop_column('dim_users', 'status')
```

### 2. 向后兼容

- ✅ 现有用户自动设置为 `status="active"`
- ✅ 现有代码继续工作（`is_active` 字段保留）
- ✅ API 响应格式兼容

## 已知问题和兼容性

### 1. 现有代码兼容性问题

**问题**：`backend/routers/users.py` 中存在字段名不一致的问题

**详细说明**：

- `DimRole` 表的字段名是 `role_name`，不是 `name`
- 但 `users.py` 中多处使用了 `role.name` 或 `DimRole.name`
- 这会导致代码运行时出错（字段不存在）

**影响位置**：

```python
# ❌ 错误的代码（users.py 第22行）
if not any(role.name == "admin" for role in current_user.roles):

# ✅ 正确的代码
if not any(role.role_name == "admin" for role in current_user.roles):
```

**修复策略**：

- 在实施 Phase 2 之前，必须先修复这些字段名问题
- 使用全局搜索替换：`role.name` → `role.role_name`
- 使用全局搜索替换：`DimRole.name` → `DimRole.role_name`

### 2. 数据库迁移策略

**现状**：

- `DimUser` 表目前没有 `status` 字段
- 需要新增字段并迁移现有数据

**迁移脚本要点**：

```python
def upgrade():
    # 添加新字段
    op.add_column('dim_users', sa.Column('status', sa.String(20),
                  nullable=False, server_default='active'))
    op.add_column('dim_users', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.add_column('dim_users', sa.Column('approved_by', sa.BigInteger(), nullable=True))
    op.add_column('dim_users', sa.Column('rejection_reason', sa.Text(), nullable=True))

    # 更新现有用户数据（确保状态一致）
    op.execute("""
        UPDATE dim_users
        SET status = 'active'
        WHERE status IS NULL OR status = ''
    """)

    # 确保 is_active 与 status 一致
    op.execute("""
        UPDATE dim_users
        SET is_active = (status = 'active')
    """)

    # 创建索引
    op.create_index('idx_users_status', 'dim_users', ['status'])
```

## 总结

本设计采用管理员审批机制，适合中小团队快速实施。核心特点：

1. **简单高效**：无需邮件服务，审批流程简单
2. **安全可控**：管理员审批，控制用户质量
3. **易于扩展**：未来可添加邮箱验证、自动审批等功能
4. **完整审计**：审批记录和审计日志完整

**实施注意事项**：

- ⚠️ **必须先修复现有代码中的字段名问题（`role.name` → `role.role_name`）**
- ⚠️ **require_admin 函数必须同时检查 is_superuser 标志**（P0 安全漏洞）
- ⚠️ **注册 API 必须添加速率限制**（P0 安全漏洞）
- ⚠️ **用户名/邮箱检查必须统一错误消息**（P0 安全漏洞）
- ⚠️ **错误码编号避免冲突（使用 4005-4008）**（P0 安全漏洞）
- ⚠️ 数据库迁移时需更新现有用户数据
- ⚠️ **建议使用数据库触发器确保 `status` 和 `is_active` 字段同步**（P1 建议）
- ⚠️ **确保 operator 角色存在，或要求审批时必须指定角色**（P1 建议）

**安全漏洞详情请参考**：`VULNERABILITY_REVIEW.md`

---

## Phase 8: 通知系统现代化改进设计

### 8.2.3 用户通知偏好设置表设计

#### 数据库表结构

```python
# modules/core/db/schema.py

class UserNotificationPreference(Base):
    """用户通知偏好设置表
    
    用于存储用户对不同类型通知的偏好设置，支持跨设备同步。
    """
    __tablename__ = "user_notification_preferences"
    
    preference_id = Column(BigInteger, primary_key=True, comment="偏好设置ID")
    
    # 用户关联
    user_id = Column(
        BigInteger,
        ForeignKey('dim_users.user_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment="用户ID"
    )
    
    # 通知类型
    notification_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="通知类型：user_registered, user_approved, user_rejected, password_reset, system_alert"
    )
    
    # 偏好设置
    enabled = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用此类型通知（默认启用）"
    )
    
    desktop_enabled = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否启用桌面通知（默认关闭）"
    )
    
    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间"
    )
    
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间"
    )
    
    __table_args__ = (
        # 唯一约束：每个用户每种通知类型只能有一条记录
        UniqueConstraint('user_id', 'notification_type', name='uq_user_notification_type'),
        # 索引：按用户查询
        Index('idx_user_notification_user', 'user_id'),
        # 索引：按通知类型查询
        Index('idx_user_notification_type', 'notification_type'),
    )
```

#### API 设计

##### 1. 获取用户所有通知偏好

```http
GET /api/users/me/notification-preferences
Authorization: Bearer {token}

Response 200:
{
  "success": true,
  "data": {
    "preferences": [
      {
        "preference_id": 1,
        "notification_type": "user_registered",
        "enabled": true,
        "desktop_enabled": false,
        "created_at": "2026-01-05T10:00:00Z",
        "updated_at": "2026-01-05T10:00:00Z"
      }
    ]
  },
  "message": "获取通知偏好成功"
}
```

##### 2. 批量更新通知偏好

```http
PUT /api/users/me/notification-preferences
Authorization: Bearer {token}
Content-Type: application/json

{
  "preferences": [
    {
      "notification_type": "user_registered",
      "enabled": true,
      "desktop_enabled": true
    }
  ]
}

Response 200:
{
  "success": true,
  "data": {
    "updated_count": 1
  },
  "message": "更新通知偏好成功"
}
```

##### 3. WebSocket 连接统计 API

```http
GET /api/notifications/ws/stats
Authorization: Bearer {token}
# 权限要求：管理员

Response 200:
{
  "success": true,
  "data": {
    "total_connections": 45,
    "active_users": 12,
    "connections_per_user": {
      "1": 2,
      "2": 1
    },
    "error_stats": {
      "token_expired": 5,
      "connection_limit_exceeded": 2
    },
    "timestamp": "2026-01-05T10:00:00Z"
  },
  "message": "获取连接统计成功"
}
```

#### Phase 8 实施状态说明

**当前状态**：Phase 8（通知系统现代化改进）尚未实施

**实施前准备**：
- ✅ Redis 基础设施已配置（`backend/utils/config.py`）
- ✅ Redis 客户端已实现（`backend/utils/redis_client.py`）
- ✅ 降级逻辑示例已存在（`backend/services/rate_limit_stats.py`）

**实施建议**：
- 复用现有的 Redis 客户端和降级逻辑
- 参考 `backend/services/rate_limit_stats.py` 的降级策略
- 确保 WebSocket 连接管理器能够正确处理 Redis 不可用的情况

#### WebSocket Close Code 与错误码区分

**概念区分**：

1. **WebSocket Close Code**（关闭代码）
   - 用途：用于关闭 WebSocket 连接
   - 获取方式：前端通过 `websocket.closeCode` 获取
   - 范围：1000-4999（标准范围）
   - 示例：4005（Token 过期）、4006（连接数限制）

2. **WebSocket 错误码**（消息错误码）
   - 用途：用于 WebSocket 消息中的错误信息
   - 获取方式：前端从消息 JSON 中解析
   - 范围：自定义（通常与 HTTP 错误码一致）
   - 示例：`WS_ERROR_TOKEN_EXPIRED = 4002`（用于消息格式）

**使用场景**：

```python
# 后端：关闭连接时使用 close code
await websocket.close(code=4005)  # Token 过期

# 后端：发送错误消息时使用错误码
await websocket.send_json({
    "type": "error",
    "code": 4002,  # WS_ERROR_TOKEN_EXPIRED
    "message": "Token expired"
})
```

```javascript
// 前端：处理连接关闭
websocket.onclose = (event) => {
    if (event.code === 4005) {
        // Token 过期，需要重新登录
        console.log("Token expired, redirecting to login");
    } else if (event.code === 4006) {
        // 连接数限制
        console.log("Connection limit exceeded");
    }
};
```

#### 批量推送性能优化策略

**处理策略**：

1. **如果管理员数量 ≤ 50**：直接批量推送
2. **如果管理员数量 > 50**：
   - **方案1（推荐）**：分批推送（每批 50 个，使用 `asyncio.create_task` 异步处理）
   - **方案2**：仅推送前 50 个管理员，其余通过轮询获取
   - **方案3**：使用消息队列（Redis/RabbitMQ）异步处理（可选）

**代码示例**：

```python
# 方案1：分批推送
async def batch_notify_admins(admin_users, notification_data):
    if len(admin_users) <= 50:
        # 直接批量推送
        await create_notifications_batch(admin_users, notification_data)
    else:
        # 分批推送
        batch_size = 50
        for i in range(0, len(admin_users), batch_size):
            batch = admin_users[i:i + batch_size]
            # 异步处理每批
            asyncio.create_task(
                create_notifications_batch(batch, notification_data)
            )
```
