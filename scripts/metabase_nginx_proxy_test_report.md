# Metabase Nginx 反向代理测试报告

**测试时间**: 2025-01-09  
**配置方式**: 方式2 - Nginx 反向代理（推荐）

## ✅ 配置修改

### 1. Nginx 配置（`nginx/nginx.prod.conf`）

**添加内容**:
- ✅ `upstream metabase` - Metabase 上游服务器配置
- ✅ `location /metabase/` - Metabase 反向代理路径

**配置说明**:
- Metabase 通过 `http://YOUR_SERVER_IP/metabase/` 访问
- 前端 iframe 使用相对路径 `/metabase/embed/dashboard/...`
- 后端使用容器网络地址 `http://metabase:3000`

### 2. Metabase 锁定配置（`docker-compose.metabase.lockdown.yml`）

**修改内容**:
- ✅ 完全移除端口映射（`ports: []`）
- ✅ Metabase 仅在容器网络内可访问

### 3. 环境变量配置

**后端配置**:
- `METABASE_URL=http://metabase:3000`（容器网络地址）

**前端配置**:
- `VITE_METABASE_URL=/metabase`（相对路径，通过 Nginx）

## 📊 架构对比

### 修改前（SSH 隧道方式）
```
用户浏览器
  ↓
SSH 隧道 (8080)
  ↓
Metabase (127.0.0.1:8080)
  ↓
PostgreSQL (容器网络)
```

**问题**:
- ❌ 每个用户需要 SSH 隧道
- ❌ 不适合产品化使用
- ❌ 移动端无法访问

### 修改后（Nginx 反向代理方式）✅
```
用户浏览器
  ↓
Nginx (80/443) - 唯一对外暴露
  ↓
├─ /api/* → backend:8000
├─ /metabase/* → metabase:3000  ⭐
└─ /* → frontend:80

Metabase ↔ PostgreSQL (容器网络)
```

**优势**:
- ✅ 统一入口（只暴露 80/443）
- ✅ 产品化友好（直接访问）
- ✅ 支持移动端
- ✅ 可添加 IP 白名单或 Basic Auth

## 🔍 数据链路验证

### 1. 数据库 → Metabase
- ✅ Metabase 通过容器网络 `postgres:5432` 访问数据库
- ✅ 不受端口锁定影响

### 2. Metabase → 前端
- ✅ 前端通过 Nginx `/metabase/` 路径访问 Metabase
- ✅ 使用相对路径，支持 HTTPS 自动切换
- ✅ 无跨域问题（同域名）

### 3. 后端代理 → Metabase
- ✅ 后端通过容器网络 `metabase:3000` 访问 Metabase
- ✅ 用于生成嵌入 Token 和 URL

## 🚀 部署命令

### 核心服务 + Metabase（推荐）

```bash
docker-compose --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.cloud.yml \
  -f docker-compose.metabase.yml \
  -f docker-compose.prod.lockdown.yml \
  -f docker-compose.metabase.lockdown.yml \
  --profile production up -d
```

## 🔐 安全性增强（可选）

### IP 白名单

在 `nginx/nginx.prod.conf` 的 `location /metabase/` 中添加：

```nginx
location /metabase/ {
    # IP 白名单
    allow 192.168.1.0/24;  # 内网
    allow YOUR_OFFICE_IP;   # 办公室IP
    deny all;
    
    proxy_pass http://metabase/;
    # ... 其他配置
}
```

### HTTP Basic Auth

```nginx
location /metabase/ {
    # HTTP Basic Auth
    auth_basic "Metabase Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    proxy_pass http://metabase/;
    # ... 其他配置
}
```

## ✅ 访问方式

### 管理员访问 Metabase UI
- **URL**: `http://YOUR_SERVER_IP/metabase/`
- **说明**: 通过 Nginx 反向代理，无需 SSH 隧道

### 前端 iframe 嵌入
- **URL**: `/metabase/embed/dashboard/{dashboard_id}?embedding_token={token}`
- **说明**: 使用相对路径，自动使用当前域名

### 后端 API 代理
- **URL**: `http://metabase:3000`（容器网络）
- **说明**: 后端服务使用容器网络地址

## 📝 环境变量配置

### 生产环境 `.env`

```bash
# Metabase 配置（后端使用）
METABASE_URL=http://metabase:3000

# Metabase 配置（前端使用）
VITE_METABASE_URL=/metabase
```

## ⚠️ 注意事项

1. **Metabase 首次启动**: 需要 1-2 分钟，请耐心等待
2. **路径配置**: 确保 Nginx 的 `proxy_pass` 使用 `http://metabase/`（带尾随斜杠）
3. **前端配置**: 确保 `VITE_METABASE_URL=/metabase`（相对路径）
4. **后端配置**: 确保 `METABASE_URL=http://metabase:3000`（容器网络地址）

## ✅ 总结

**配置状态**: ✅ **完成**

**优势**:
- ✅ 只暴露 80/443 端口
- ✅ Metabase 完全锁定（无宿主机端口）
- ✅ 产品化友好（直接访问）
- ✅ 支持移动端
- ✅ 可添加安全控制（IP 白名单/Basic Auth）

**数据链路**:
- ✅ 数据库 → Metabase（容器网络）
- ✅ Metabase → 前端（Nginx 反向代理）
- ✅ 后端 → Metabase（容器网络）

**部署就绪**: ✅ **是** - 可以安全部署到生产环境
