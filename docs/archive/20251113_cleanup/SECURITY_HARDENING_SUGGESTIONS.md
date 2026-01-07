# 安全加固建议文档

**创建日期**: 2025-11-05  
**适用版本**: v4.6.2+  
**安全标准**: OWASP Top 10 + 企业级ERP安全标准

---

## 1. 认证和授权加固

### 1.1 JWT密钥管理（P0 - 已在本次改进中完成）

**状态**: ✅ 已添加警告日志

**后续建议**:
```python
# 生产环境强制检查（可选）
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("生产环境必须设置JWT_SECRET_KEY环境变量！")
```

### 1.2 Token过期时间优化（P1 - 重要）

**当前配置**: 24小时过期

**建议配置**:
```python
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # 15分钟
REFRESH_TOKEN_EXPIRE_DAYS = 7     # 7天刷新Token
```

### 1.3 Token黑名单（P1 - 重要）

**实施方案**:
```python
# 使用Redis存储已撤销的Token
async def revoke_token(token: str, redis: Redis):
    await redis.setex(f"revoked:{token}", 86400, "1")

async def is_token_revoked(token: str, redis: Redis):
    return await redis.exists(f"revoked:{token}")
```

---

## 2. API安全

### 2.1 API速率限制（P0 - 紧急）

**使用slowapi**:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/auth/login")
@limiter.limit("5/minute")  # 每分钟5次
async def login(request: Request):
    pass
```

### 2.2 CSRF保护（P1 - 重要）

**关键操作添加CSRF Token**:
- 数据入库
- 用户信息修改
- 权限变更

---

## 3. 密码加密升级（P2 - 建议）

**当前**: pbkdf2_sha256

**建议升级为Argon2**:
```python
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4
)
```

---

## 4. 输入验证和输出编码

### 4.1 SQL注入防护

**状态**: ✅ 已使用SQLAlchemy ORM（自动参数化）

**注意**: 如有原始SQL，必须使用参数化查询

### 4.2 XSS防护

**前端输出编码**:
```javascript
// 使用Vue的v-text而非v-html
<div v-text="userInput"></div>  // 安全
<div v-html="userInput"></div>  // 危险
```

---

## 5. 敏感数据保护

### 5.1 审计所有硬编码密钥（P0 - 紧急）

**当前发现**: 137处密码/密钥相关代码

**建议**:
1. 审计所有密码/密钥引用
2. 确认无硬编码泄露
3. 使用密钥管理服务

### 5.2 敏感字段加密存储（P1 - 重要）

**需要加密的字段**:
- 用户密码（已加密）
- API密钥
- 数据库连接字符串

---

## 6. 日志和审计

### 6.1 审计日志增强（P2 - 建议，部分在TODO中）

**记录内容**:
- 用户登录/登出
- 数据修改操作
- 权限变更
- API调用（关键接口）

---

## 7. 依赖安全

### 7.1 定期扫描依赖漏洞（P1 - 重要）

```bash
# 安装safety
pip install safety

# 扫描Python依赖
safety check --json

# 扫描npm依赖
cd frontend && npm audit
```

---

## 8. HTTPS和传输加密

### 8.1 生产环境强制HTTPS（P0 - 紧急）

**Nginx配置**:
```nginx
server {
    listen 443 ssl;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
}
```

---

## 实施优先级

**P0 - 紧急（生产前必须）**:
- [ ] API速率限制
- [ ] HTTPS配置
- [ ] 审计硬编码密钥

**P1 - 重要（1个月内）**:
- [ ] Token过期优化
- [ ] Token黑名单
- [ ] CSRF保护
- [ ] 依赖安全扫描

**P2 - 建议（持续优化）**:
- [ ] 密码加密升级
- [ ] 审计日志增强

---

**最后更新**: 2025-11-05

