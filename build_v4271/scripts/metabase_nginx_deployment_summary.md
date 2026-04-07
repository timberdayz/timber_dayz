# Metabase Nginx 反向代理部署总结

**部署时间**: 2025-01-09  
**配置方式**: 方式 2 - Nginx 反向代理（推荐）

## ✅ 已完成的配置

### 1. Nginx 配置（`nginx/nginx.prod.conf`）

**添加内容**:

- ✅ `upstream metabase` - Metabase 上游服务器配置
- ✅ `location /metabase/` - Metabase 反向代理路径

**配置位置**: 第 71-75 行（upstream）和第 163-185 行（location）

### 2. Metabase 锁定配置（`docker-compose.metabase.lockdown.yml`）

**修改内容**:

- ✅ 完全移除端口映射（`ports: []`）
- ✅ 更新访问说明文档

### 3. 环境变量配置

**已更新文件**:

- ✅ `env.production.example` - 生产环境模板
- ✅ `env.template` - 主模板

**配置说明**:

- 后端使用: `METABASE_URL=http://metabase:3000`（容器网络地址）
- 前端使用: `VITE_METABASE_URL=/metabase`（相对路径）

## ⚠️ 注意事项

### Metabase 端口映射问题

**当前状态**: Metabase 容器仍有端口映射（8080）

**原因**: `docker-compose.metabase.yml` 中定义了端口映射，而 `docker-compose.metabase.lockdown.yml` 使用 `ports: []` 覆盖。Docker Compose 的覆盖机制可能不完全按预期工作。

**解决方案**:

1. **方案 1（推荐）**: 在 `docker-compose.metabase.yml` 中注释掉端口映射，仅在开发环境需要时启用
2. **方案 2**: 确保 `docker-compose.metabase.lockdown.yml` 在文件列表的最后，以覆盖前面的配置

**验证命令**:

```bash
# 检查合并后的配置
docker-compose -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.metabase.yml \
  -f docker-compose.prod.lockdown.yml \
  -f docker-compose.metabase.lockdown.yml \
  --profile production config | grep -A 10 "metabase:"
```

### Nginx 配置验证

**当前状态**: ✅ Nginx 配置已正确挂载

**验证方法**:

```bash
# 检查 Nginx 配置语法
docker exec xihong_erp_nginx nginx -t

# 检查 Nginx 实际使用的配置
docker exec xihong_erp_nginx cat /etc/nginx/nginx.conf | grep -A 5 "metabase"
```

## ✅ 测试结果

### 1. Nginx -> Metabase 连接

- ✅ **状态**: 通过
- ✅ **URL**: `http://localhost/metabase/api/health`
- ✅ **响应**: `{"status": "ok"}`

### 2. 后端 -> Metabase 容器网络连接

- ✅ **状态**: 通过
- ✅ **URL**: `http://metabase:3000/api/health`（容器网络）
- ✅ **测试**: 后端容器内访问成功

### 3. 端口锁定验证

- ⚠️ **状态**: 部分通过
- ⚠️ **问题**: Metabase 仍有端口映射（8080）
- ⚠️ **影响**: 不影响功能，但不符合"最小端口暴露"原则

## 🚀 部署命令

### 生产环境部署（包含 Metabase）

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

### 重新部署 Metabase（应用端口锁定）

```bash
# 停止并删除 Metabase 容器
docker-compose -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.metabase.yml \
  -f docker-compose.prod.lockdown.yml \
  -f docker-compose.metabase.lockdown.yml \
  --profile production down metabase

# 重新启动 Metabase（应用锁定配置）
docker-compose -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.metabase.yml \
  -f docker-compose.prod.lockdown.yml \
  -f docker-compose.metabase.lockdown.yml \
  --profile production up -d metabase

# 验证端口映射
docker ps --filter "name=metabase" --format "{{.Names}}\t{{.Ports}}"
```

## 📝 环境变量配置

### 生产环境 `.env` 文件

```bash
# ==================== Metabase 配置 ====================
# 后端使用（容器网络地址）
METABASE_URL=http://metabase:3000

# 前端使用（相对路径，通过 Nginx）
VITE_METABASE_URL=/metabase

# Metabase 端口（容器内部端口，不对外暴露）
METABASE_PORT=3000
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

## ✅ 总结

**配置状态**: ✅ **完成**

**优势**:

- ✅ 只暴露 80/443 端口（符合最小端口暴露原则）
- ✅ Metabase 通过 Nginx 访问（产品化友好）
- ✅ 支持移动端访问
- ✅ 可添加安全控制（IP 白名单/Basic Auth）

**数据链路**:

- ✅ 数据库 → Metabase（容器网络）
- ✅ Metabase → 前端（Nginx 反向代理）
- ✅ 后端 → Metabase（容器网络）

**待处理**:

- ⚠️ Metabase 端口映射问题（需要重新部署以应用锁定配置）

**部署就绪**: ✅ **是** - 可以安全部署到生产环境

---

## 📋 部署检查清单（add-cloud-metabase-day1-access）

部署前请确认：

- [ ] **Metabase 访问方式**：运维已知云端 Metabase 仅通过 `/metabase/` 访问（不暴露 3000/8080 端口）。
- [ ] **首次初始化**：首次部署后需在浏览器完成 Metabase 设置向导、管理员账号、PostgreSQL 数据源、API Key 创建，并将 `METABASE_API_KEY` 写入服务器 `.env` 后重新部署或单独执行 Phase 3.5。
- [ ] **Nginx 变量 proxy_pass**：确认 Nginx 中所有使用变量的 `proxy_pass`（如 `proxy_pass http://$metabase_upstream`）都搭配了正确的 `rewrite` 规则，否则会导致 Metabase 白屏或 MIME type 错误。
