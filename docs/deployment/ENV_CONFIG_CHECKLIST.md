# 生产环境配置检查清单

**域名**: `www.xihong.site`  
**服务器IP**: `134.175.222.171`  
**检查时间**: 2025-01-XX

---

## ✅ 当前配置检查

### 你的配置

```bash
ALLOWED_ORIGINS=http://www.xihong.site
ALLOWED_HOSTS=134.175.222.171
```

### ⚠️ 建议改进

#### 1. ALLOWED_ORIGINS（CORS允许的来源）

**当前配置**：
```bash
ALLOWED_ORIGINS=http://www.xihong.site
```

**建议配置**（同时支持域名和IP访问）：
```bash
ALLOWED_ORIGINS=http://www.xihong.site,http://xihong.site,http://134.175.222.171,https://www.xihong.site,https://xihong.site
```

**说明**：
- ✅ 包含 `www.xihong.site`（带www）
- ✅ 包含 `xihong.site`（不带www）
- ✅ 包含IP地址（如果需要通过IP直接访问）
- ✅ 包含HTTPS（如果已配置SSL证书）

#### 2. ALLOWED_HOSTS（允许的主机）

**当前配置**：
```bash
ALLOWED_HOSTS=134.175.222.171
```

**建议配置**（同时支持域名和IP）：
```bash
ALLOWED_HOSTS=www.xihong.site,xihong.site,134.175.222.171,localhost
```

**说明**：
- ✅ 包含域名（带www和不带www）
- ✅ 包含IP地址
- ✅ 包含localhost（用于健康检查）

#### 3. VITE_API_URL（前端API地址）

**建议配置**：
```bash
# 如果使用域名（推荐）
VITE_API_URL=http://www.xihong.site/api

# 或使用IP地址（如果域名未配置）
VITE_API_URL=http://134.175.222.171:8000
```

**说明**：
- ✅ 如果域名已配置DNS解析，使用域名
- ✅ 如果域名未配置，使用IP地址
- ⚠️ 注意端口号（8000是后端API端口）

---

## 📋 完整配置建议

### 推荐配置（域名已配置DNS）

```bash
# 服务器配置
HOST=0.0.0.0
PORT=8000
FRONTEND_PORT=80

# CORS允许的来源（同时支持域名和IP）
ALLOWED_ORIGINS=http://www.xihong.site,http://xihong.site,http://134.175.222.171,https://www.xihong.site,https://xihong.site

# 允许的主机（同时支持域名和IP）
ALLOWED_HOSTS=www.xihong.site,xihong.site,134.175.222.171,localhost

# 前端API地址（使用域名）
VITE_API_URL=http://www.xihong.site/api
# 或
VITE_API_URL=http://www.xihong.site:8000
```

### 备选配置（域名未配置DNS）

```bash
# 服务器配置
HOST=0.0.0.0
PORT=8000
FRONTEND_PORT=80

# CORS允许的来源（仅IP）
ALLOWED_ORIGINS=http://134.175.222.171

# 允许的主机（仅IP）
ALLOWED_HOSTS=134.175.222.171,localhost

# 前端API地址（使用IP）
VITE_API_URL=http://134.175.222.171:8000
```

---

## ✅ 配置检查清单

### 域名配置

- [ ] 域名 `www.xihong.site` 已配置DNS解析指向 `134.175.222.171`
- [ ] 域名 `xihong.site` 已配置DNS解析指向 `134.175.222.171`（可选）
- [ ] 域名解析已生效（可以使用 `ping www.xihong.site` 测试）

### 服务器配置

- [ ] `ALLOWED_ORIGINS` 包含域名和IP
- [ ] `ALLOWED_HOSTS` 包含域名和IP
- [ ] `VITE_API_URL` 使用正确的地址（域名或IP）

### 安全配置

- [ ] 如果使用HTTPS，`ALLOWED_ORIGINS` 包含 `https://` 地址
- [ ] 如果使用HTTPS，`VITE_API_URL` 使用 `https://` 地址

---

## 🔍 DNS配置检查

### 检查域名解析

```bash
# 检查域名解析
ping www.xihong.site
nslookup www.xihong.site

# 应该返回: 134.175.222.171
```

### DNS记录配置（在DNSPod中）

**A记录**：
- 主机记录: `www`
- 记录类型: `A`
- 记录值: `134.175.222.171`
- TTL: `600`（或默认）

**A记录**（可选，不带www）：
- 主机记录: `@`
- 记录类型: `A`
- 记录值: `134.175.222.171`
- TTL: `600`（或默认）

---

## ⚠️ 常见问题

### 问题1：只配置了域名，无法通过IP访问

**解决方案**：在 `ALLOWED_ORIGINS` 和 `ALLOWED_HOSTS` 中同时添加IP地址

### 问题2：只配置了IP，无法通过域名访问

**解决方案**：
1. 配置DNS解析（在DNSPod中）
2. 在 `ALLOWED_ORIGINS` 和 `ALLOWED_HOSTS` 中添加域名

### 问题3：HTTPS配置

**如果使用HTTPS**：
- 修改 `ALLOWED_ORIGINS` 为 `https://www.xihong.site`
- 修改 `VITE_API_URL` 为 `https://www.xihong.site/api`
- 配置SSL证书（在Nginx或服务器上）

---

## 📝 最终推荐配置

```bash
# ==================== 服务器配置 ====================
HOST=0.0.0.0
PORT=8000
FRONTEND_PORT=80

# ==================== CORS和主机配置 ====================
# 同时支持域名和IP访问
ALLOWED_ORIGINS=http://www.xihong.site,http://xihong.site,http://134.175.222.171,https://www.xihong.site,https://xihong.site
ALLOWED_HOSTS=www.xihong.site,xihong.site,134.175.222.171,localhost

# ==================== 前端配置 ====================
# 使用域名（推荐）或IP地址
VITE_API_URL=http://www.xihong.site:8000
# 或
# VITE_API_URL=http://134.175.222.171:8000
```

---

**最后更新**: 2025-01-XX
