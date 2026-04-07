# 现代化认证系统改进 - 实施总结

## 实施日期
2026-01-03

## 已完成阶段

### Phase 1: 前端 Token 自动携带和刷新 ✅

#### 1.1 请求拦截器添加 Authorization Header

**文件**: `frontend/src/api/index.js`

**修改内容**：
- 添加延迟导入 `authStore` 机制，避免循环依赖
- 定义 `NO_AUTH_PATHS` 列表，排除不需要认证的接口
- 在请求拦截器中自动从 `authStore` 或 `localStorage` 获取 token
- 自动添加 `Authorization: Bearer {token}` header

**关键代码**：
```javascript
// 延迟导入避免循环依赖
let authStore = null;
const getAuthStore = () => {
  if (!authStore) {
    const { useAuthStore } = require("@/stores/auth");
    authStore = useAuthStore();
  }
  return authStore;
};

// 不需要认证的接口列表
const NO_AUTH_PATHS = [
  "/auth/login",
  "/auth/refresh",
  "/health",
];

// 请求拦截器中自动添加 token
const needsAuth = !NO_AUTH_PATHS.some(path => config.url.includes(path));
if (needsAuth) {
  const token = store.token || localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
}
```

#### 1.2 响应拦截器实现自动 Token 刷新

**文件**: `frontend/src/api/index.js`

**修改内容**：
- 实现 `isRefreshing` 锁机制，防止多个请求同时触发刷新
- 实现 `failedQueue` 队列，存储等待刷新的请求
- 检测 401 Unauthorized 响应，自动触发刷新
- 刷新成功后，更新所有队列中的请求的 token 并重试
- 刷新失败时，清除 token 并跳转登录页

**关键代码**：
```javascript
// Token 刷新锁和队列
let isRefreshing = false;
let failedQueue = [];

// 响应拦截器中检测 401
if (error.response && error.response.status === 401) {
  // 排除登录、刷新 token 等接口
  if (NO_AUTH_PATHS.some(path => originalRequest.url.includes(path))) {
    return Promise.reject(error);
  }
  
  // 如果正在刷新，将请求加入队列
  if (isRefreshing) {
    return new Promise((resolve, reject) => {
      failedQueue.push({ resolve, reject });
    }).then(token => {
      originalRequest.headers.Authorization = `Bearer ${token}`;
      return api(originalRequest);
    });
  }
  
  // 开始刷新 token
  isRefreshing = true;
  const refreshed = await store.refreshAccessToken();
  
  if (refreshed) {
    const newToken = store.token || localStorage.getItem('access_token');
    // 处理队列中的请求
    failedQueue.forEach(({ resolve }) => resolve(newToken));
    failedQueue = [];
    // 重试原始请求
    originalRequest.headers.Authorization = `Bearer ${newToken}`;
    return api(originalRequest);
  }
}
```

#### 1.3 修复 refreshAccessToken 方法

**文件**: `frontend/src/stores/auth.js`

**修改内容**：
- 修复响应格式处理，兼容响应拦截器的数据提取逻辑
- 支持两种响应格式（直接返回对象或包装在 data 中）

### Phase 2: 后端 httpOnly Cookie 支持 ✅

#### 2.1 登录接口返回 httpOnly Cookie

**文件**: `backend/routers/auth.py`

**修改内容**：
- 使用 `JSONResponse` 创建响应对象
- 将 Access Token 和 Refresh Token 存储在 httpOnly Cookie 中
- 根据环境变量设置 `secure` 属性（生产环境使用 HTTPS）
- 设置 `samesite="lax"` 防止 CSRF 攻击

**关键代码**：
```python
from fastapi.responses import JSONResponse

# 创建响应对象
response = JSONResponse(content=response_data)

# 设置 Access Token Cookie
response.set_cookie(
    key="access_token",
    value=tokens["access_token"],
    max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    httponly=True,  # 防止 XSS 攻击
    secure=is_production,  # 生产环境使用 HTTPS
    samesite="lax",  # 防止 CSRF 攻击
    path="/"
)

# 设置 Refresh Token Cookie
response.set_cookie(
    key="refresh_token",
    value=tokens["refresh_token"],
    max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    httponly=True,
    secure=is_production,
    samesite="lax",
    path="/"
)
```

#### 2.2 认证中间件支持 Cookie 和 Header

**文件**: `backend/routers/auth.py`

**修改内容**：
- 修改 `HTTPBearer` 为 `auto_error=False`，允许可选认证
- `get_current_user` 依赖优先从 Cookie 读取 token，其次从 Header 读取
- 支持两种认证方式（向后兼容）

**关键代码**：
```python
security = HTTPBearer(auto_error=False)  # 允许可选认证

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_async_db)
):
    token = None
    
    # 优先从 Cookie 读取
    if "access_token" in request.cookies:
        token = request.cookies.get("access_token")
    # 其次从 Header 读取（向后兼容）
    elif credentials and credentials.credentials:
        token = credentials.credentials
    
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    
    # 验证 token...
```

#### 2.3 刷新 Token 接口支持 Cookie

**文件**: `backend/routers/auth.py`

**修改内容**：
- 刷新 token 接口优先从 Cookie 读取 refresh token
- 其次从请求体读取（向后兼容）
- 刷新成功后，将新的 access token 存储在 httpOnly Cookie 中

## 待实施阶段

### Phase 3: CSRF Token 保护 - P1

- 创建 CSRF 中间件
- 登录时生成 CSRF Token
- 所有 POST/PUT/DELETE 请求验证 CSRF Token
- 前端自动添加 CSRF Token header

### Phase 4: 优化 Token 过期时间 - P2

- 缩短 Access Token 过期时间到 15 分钟
- 实现 Token 刷新预检查（提前 5 分钟刷新）

## 测试建议

### Phase 1 测试

1. **Token 自动携带测试**：
   - 登录后，检查所有 API 请求是否自动携带 `Authorization: Bearer {token}` header
   - 验证登录、刷新 token 等接口不携带 token

2. **Token 自动刷新测试**：
   - 等待 token 过期（30 分钟）或手动修改 token 使其无效
   - 发送 API 请求，验证是否自动刷新 token 并重试
   - 验证多个并发请求不会触发多次刷新

3. **刷新失败测试**：
   - 修改 refresh token 使其无效
   - 发送 API 请求，验证是否自动跳转登录页

### Phase 2 测试

1. **Cookie 存储测试**：
   - 登录后，检查浏览器 Cookie 中是否存储了 `access_token` 和 `refresh_token`
   - 验证 Cookie 的 `httpOnly`、`secure`、`sameSite` 属性

2. **Cookie 认证测试**：
   - 清除 `Authorization` header，验证是否仍能正常认证（从 Cookie 读取）
   - 清除 Cookie，验证是否仍能正常认证（从 Header 读取）

3. **向后兼容测试**：
   - 使用旧的前端代码（仅使用 Header 认证），验证是否仍能正常工作

## 已知问题

1. **前端 Cookie 读取**：
   - 当前前端代码仍从 `localStorage` 读取 token
   - 需要更新前端代码，优先从 Cookie 读取 token（但 httpOnly Cookie 无法通过 JavaScript 读取）
   - 建议：前端继续使用 Header 方式，后端同时支持 Cookie 和 Header（已实现）

2. **CSRF Token**：
   - 当前未实现 CSRF Token 保护
   - 建议尽快实施 Phase 3

## 后续工作

1. 实施 Phase 3（CSRF Token 保护）
2. 实施 Phase 4（优化 Token 过期时间）
3. 全面测试所有功能
4. 更新用户文档

