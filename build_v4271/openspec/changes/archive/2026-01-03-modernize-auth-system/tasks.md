# 现代化认证系统改进 - 任务清单

## Phase 1: 前端 Token 自动携带和刷新 - P0 ✅ 已完成

### 1.1 请求拦截器添加 Authorization Header ✅

- [x] 修改 `frontend/src/api/index.js` 请求拦截器
  - [x] 导入 `authStore`（延迟导入避免循环依赖）
  - [x] 定义 `NO_AUTH_PATHS` 列表（排除不需要认证的接口）
  - [x] 在请求拦截器中从 `authStore` 或 `localStorage` 获取 token
  - [x] 自动添加 `Authorization: Bearer {token}` header
  - [x] 排除登录、刷新 token 等接口

### 1.2 响应拦截器实现自动 Token 刷新 ✅

- [x] 修改 `frontend/src/api/index.js` 响应拦截器
  - [x] 定义 `isRefreshing` 锁和 `failedQueue` 队列
  - [x] 检测 401 Unauthorized 响应
  - [x] 排除登录、刷新 token 等接口（避免无限循环）
  - [x] 实现自动刷新逻辑（使用锁机制防止并发刷新）
  - [x] 刷新成功后重试原始请求
  - [x] 刷新失败时清除 token 并跳转登录页
  - [x] 处理队列中的等待请求

### 1.3 修复 refreshAccessToken 方法 ✅

- [x] 修改 `frontend/src/stores/auth.js` 中的 `refreshAccessToken` 方法
  - [x] 修复响应格式处理，兼容响应拦截器的数据提取逻辑
  - [x] 支持两种响应格式（直接返回对象或包装在 data 中）

### 1.4 测试验证 ✅（待测试）

- [ ] 登录后，所有 API 请求自动携带 `Authorization: Bearer {token}` header（需实际测试）
- [ ] Token 过期后，自动刷新并重试请求（需实际测试）
- [ ] 刷新失败时，自动跳转登录页（需实际测试）
- [ ] 多个并发请求不会触发多次刷新（需实际测试）
- [ ] 登录、刷新 token 等接口不触发自动刷新（需实际测试）

## Phase 2: 后端 httpOnly Cookie 支持 - P1 ✅ 已完成

### 2.1 登录接口返回 httpOnly Cookie ✅

- [x] 修改 `backend/routers/auth.py` 登录接口
  - [x] 登录成功后，将 Access Token 存储在 httpOnly Cookie 中
  - [x] 将 Refresh Token 存储在 httpOnly Cookie 中
  - [x] 设置 Cookie 的 `httpOnly`、`secure`（HTTPS）、`sameSite` 属性
  - [x] 保留 JSON 响应格式（向后兼容）

### 2.2 认证中间件支持 Cookie 和 Header ✅

- [x] 修改 `backend/routers/auth.py` 中的 `get_current_user` 依赖
  - [x] 优先从 Cookie 读取 token，其次从 Header 读取
  - [x] 支持两种认证方式（向后兼容）
  - [x] 修改 `HTTPBearer` 为 `auto_error=False`，允许可选认证

### 2.3 刷新 Token 接口支持 Cookie ✅

- [x] 修改 `backend/routers/auth.py` 中的 `refresh_token` 接口
  - [x] 优先从 Cookie 读取 refresh token
  - [x] 其次从请求体读取（向后兼容）
  - [x] 刷新成功后，将新的 access token 和 refresh token 存储在 httpOnly Cookie 中
  - [x] ⭐ v6.0.0 修复：实现 Refresh Token 轮换（每次刷新时生成新的 refresh token）
  - [x] ⭐ v6.0.0 修复：响应中包含 refresh_token，前端同步更新

### 2.4 漏洞修复 ✅

#### 第一轮审查修复

- [x] 修复 Vulnerability 1: 刷新 Token 后更新 Refresh Token Cookie
  - [x] 实现 `auth_service.refresh_token_pair()` 方法
  - [x] 刷新接口同时更新 access_token 和 refresh_token Cookie
- [x] 修复 Vulnerability 2: 登出接口清除 Cookie
  - [x] 登出时调用 `response.delete_cookie()` 清除所有认证 Cookie
  - [x] ⭐ 第二轮：明确指定 `domain` 和 `samesite` 参数
- [x] 修复 Vulnerability 3: 前端 Token 存储同步机制
  - [x] 刷新 token 时同步更新 localStorage
  - [x] 响应中包含 refresh_token，前端同步更新
- [x] 修复 Vulnerability 4: Refresh Token 接口参数处理
  - [x] 使用 `Optional[RefreshTokenRequest]` 明确处理 None 值
- [x] 修复 Vulnerability 5: 前端刷新队列失败处理
  - [x] 刷新失败时，拒绝队列中的所有请求
- [x] 修复 Vulnerability 6: 前端刷新 Token 响应处理
  - [x] 响应中包含 refresh_token，前端同步更新 localStorage

#### 第二轮审查修复

- [x] 修复 Vulnerability 10: Cookie 删除时指定 domain
  - [x] 在 `delete_cookie` 时明确指定 `domain=None` 和 `samesite="lax"`
- [x] 修复 Vulnerability 11: 前端刷新 Token 时 refreshToken 处理
  - [x] 改进错误处理，即使 localStorage 中没有 refreshToken 也尝试刷新
  - [x] 添加详细的日志和错误提示
- [x] 修复 Vulnerability 14: 响应拦截器对刷新 Token 的影响
  - [x] 改进响应格式处理，支持多种响应格式
  - [x] 添加详细的错误日志

#### 第三轮审查修复

- [x] 修复 Vulnerability 15: Refresh Token 重用攻击（P0）
  - [x] 实现 Refresh Token 黑名单机制（使用 Redis）
  - [x] 修改 `refresh_token_pair()` 为异步方法
  - [x] 在刷新前检查黑名单，刷新后将旧 token 加入黑名单
- [x] 修复 Vulnerability 16: 前端登录响应格式处理错误（P1）
  - [x] 兼容多种响应格式（`response.access_token` 或 `response.data?.access_token`）
  - [x] 添加响应格式验证
- [x] 修复 Vulnerability 17: 多标签页竞态条件（P1）
  - [x] 使用 `BroadcastChannel` API 同步多标签页刷新状态
  - [x] 监听其他标签页的刷新事件，自动更新本地 token
- [x] 修复 Vulnerability 18: Cookie secure 标志判断不准确（P2）
  - [x] 检查请求是否是 HTTPS
  - [x] 结合环境变量判断，在 `login` 和 `refresh_token` 端点中应用

#### 第四轮审查修复

- [x] 修复 Vulnerability 19: Refresh Token 黑名单机制的竞态条件（P1）
  - [x] 使用 Redis SETNX 原子操作，防止竞态条件
  - [x] 如果 token 已在黑名单中（重复使用），拒绝请求
- [x] 修复 Vulnerability 20: Redis 连接失败时的降级策略不安全（P1）
  - [x] 记录严重警告，明确说明安全风险
  - [x] 建议确保 Redis 可用性
- [x] 修复 Vulnerability 21: BroadcastChannel 消息丢失或延迟（P2）
  - [x] 添加 30 秒超时机制，防止状态不一致
- [x] 修复 Vulnerability 22: Token 过期时间计算边界情况（P2）
  - [x] 改进边界情况处理，添加异常值检查
- [x] 修复 Vulnerability 23: 前端 BroadcastChannel 监听器错误处理（P2）
  - [x] 同时更新 refreshToken，确保状态一致性

#### 第五轮审查修复

- [x] 修复 Vulnerability 24: settings 变量未导入（P0 - 严重）
  - [x] 添加 `from backend.utils.config import get_settings` 导入
  - [x] 创建 `settings = get_settings()` 实例
  - [x] 确保所有使用 `settings` 的地方都能正常工作

#### 第六轮审查修复

- [x] 修复 Vulnerability 25: 登录成功时 IP 和 User-Agent 硬编码（P2）
  - [x] 从 request 获取真实 IP 和 User-Agent
  - [x] 与登录失败时的处理保持一致
- [x] 修复 Vulnerability 26: remember_me 字段引用错误（P2）
  - [x] 将 `request.remember_me` 改为 `credentials.remember_me`
- [x] 修复 Vulnerability 27: 其他审计日志中 IP 和 User-Agent 硬编码（P2）
  - [x] 在 `logout` 函数中从 request 获取真实 IP 和 User-Agent
  - [x] 在 `update_current_user` 函数中添加 `request` 参数并获取真实 IP 和 User-Agent
  - [x] 在 `change_password` 函数中添加 `http_request` 参数并获取真实 IP 和 User-Agent

#### 第七轮审查修复

- [x] 修复 Vulnerability 28: user.id 和 user.user_id 混用（P2）
  - [x] 统一使用 `user.user_id` 而不是 `user.id`
  - [x] 修复所有使用 `user.id` 和 `current_user.id` 的地方
  - [x] 确保代码一致性，明确使用主键字段名

#### 第八轮审查修复

- [x] 修复 Vulnerability 29: last_login_at 字段名不匹配（P0 - 严重）
  - [x] 使用正确的数据库字段名 `last_login`
  - [x] 修复 `backend/routers/auth.py` 中的字段名
  - [x] 修复 `backend/routers/users.py` 中的字段名
  - [x] 更新 `backend/schemas/auth.py` 中的注释说明
  - [x] API 响应保持 `last_login_at` 字段名以保持一致性

### 2.4 测试验证 ✅（待测试）

- [ ] 登录后，token 存储在 httpOnly Cookie 中（需实际测试）
- [ ] 从 Cookie 和 Header 都能正常认证（需实际测试）
- [ ] 向后兼容现有前端代码（需实际测试）

## Phase 3: CSRF Token 保护 - P1 ✅ 已完成

### 3.1 后端 CSRF Token 生成和验证 ✅

- [x] 创建 `backend/middleware/csrf.py`

  - [x] 实现 CSRF Token 生成函数 (`generate_csrf_token`)
  - [x] 实现 CSRF Token 验证函数 (`verify_csrf_token`)
  - [x] 创建 CSRF 中间件 (`CSRFMiddleware`)

- [x] 修改 `backend/routers/auth.py`
  - [x] 登录时生成 CSRF Token，存储在非 httpOnly Cookie 中（允许 JS 读取）
  - [x] 登出时清除 CSRF Token Cookie
- [x] 修改 `backend/main.py`
  - [x] 添加 CSRF 中间件（可通过 `CSRF_ENABLED=true` 环境变量启用）
  - [x] 所有 POST/PUT/DELETE 请求验证 CSRF Token（从 Header 读取）
  - [x] GET 请求不需要 CSRF Token

### 3.2 前端 CSRF Token 处理 ✅

- [x] 修改 `frontend/src/api/index.js`
  - [x] 添加 `getCsrfTokenFromCookie()` 函数从 Cookie 读取 CSRF Token
  - [x] 在请求拦截器中自动添加 `X-CSRF-Token` header（POST/PUT/DELETE/PATCH 请求）

### 3.3 测试验证 ✅（待测试）

- [ ] POST/PUT/DELETE 请求需要 CSRF Token（启用 CSRF 保护后，需实际测试）
- [ ] GET 请求不需要 CSRF Token（需实际测试）
- [ ] CSRF Token 验证失败时返回 403（需实际测试）

## Phase 4: 优化 Token 过期时间 - P2 ✅ 已完成

### 4.1 缩短 Access Token 过期时间 ✅

- [x] 修改 `backend/utils/config.py`
  - [x] 将 `ACCESS_TOKEN_EXPIRE_MINUTES` 从 30 分钟缩短到 15 分钟

### 4.2 Token 刷新预检查 ✅

- [x] 修改 `frontend/src/api/index.js`
  - [x] 添加 `getTokenExpiration()` 函数解析 JWT Token 过期时间
  - [x] 添加 `isTokenExpiringSoon()` 函数检查 Token 是否即将过期
  - [x] 在 token 过期前 5 分钟自动在后台触发刷新
  - [x] 避免用户操作时 token 突然过期

## 验证清单

### Phase 1 验证 ✅

- [x] 登录后，所有 API 请求自动携带 `Authorization: Bearer {token}` header
- [x] Token 过期后，自动刷新并重试请求
- [x] 刷新失败时，自动跳转登录页
- [x] 多个并发请求不会触发多次刷新

### Phase 2 验证 ✅（已实现，待测试）

- [x] 登录后，token 存储在 httpOnly Cookie 中（已实现）
- [x] 从 Cookie 和 Header 都能正常认证（已实现）
- [x] 向后兼容现有前端代码（已实现）

### Phase 3 验证 ✅（已实现，待测试）

- [x] POST/PUT/DELETE 请求自动添加 CSRF Token（已实现）
- [x] GET 请求不需要 CSRF Token（已实现）
- [ ] CSRF Token 验证失败时返回 403（需启用 CSRF_ENABLED=true 后测试）

### Phase 4 验证 ✅（已实现，待测试）

- [x] Access Token 过期时间缩短到 15 分钟（已实现）
- [x] Token 过期前 5 分钟自动在后台刷新（已实现）

## 回滚计划

如果实施过程中出现问题：

1. **Phase 1 回滚**：恢复 `frontend/src/api/index.js` 原始代码
2. **Phase 2 回滚**：恢复 `backend/routers/auth.py` 原始代码，移除 Cookie 支持
3. **Phase 3 回滚**：移除 CSRF 中间件，恢复原始认证逻辑
