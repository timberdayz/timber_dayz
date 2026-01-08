# Nginx反向代理配置说明

**版本**: v4.19.7  
**适用**: 生产环境部署（使用Nginx反向代理）  
**更新时间**: 2025-01-XX

---

## 📋 配置概述

### 架构说明

```
用户请求
  ↓
Nginx (端口80/443)
  ↓
├─ /api/* → 后端服务 (backend:8000)
└─ /* → 前端服务 (frontend:80)
```

### 关键配置

1. **前端API配置**: 使用相对路径 `/api`
2. **Nginx配置**: `/api/` 路径代理到后端
3. **前端容器**: 使用Nginx提供静态文件服务

---

## 🔧 前端配置（VITE_API_BASE_URL）

### 推荐配置（Nginx反向代理）

```bash
# .env.production
VITE_API_BASE_URL=/api
VITE_MODE=production
```

**说明**:
- ✅ 使用相对路径 `/api`（推荐）
- ✅ 前端请求会自动使用当前域名
- ✅ 支持HTTP和HTTPS自动切换
- ✅ 无需修改配置即可切换域名

### 备选配置（直接访问后端）

```bash
# .env.production
VITE_API_BASE_URL=http://www.xihong.site:8000
VITE_MODE=production
```

**说明**:
- ⚠️ 使用完整URL（不推荐）
- ⚠️ 需要配置CORS
- ⚠️ 切换域名需要重新构建

---

## 📝 Nginx配置说明

### API代理配置

```nginx
# 后端API代理（通用限流）
location /api/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### 前端静态文件配置

```nginx
# 前端静态文件
location / {
    proxy_pass http://frontend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
}
```

---

## ✅ 配置验证

### 1. 检查前端配置

```bash
# 在 .env.production 中确认
grep VITE_API_BASE_URL .env.production
# 应该显示: VITE_API_BASE_URL=/api
```

### 2. 检查Nginx配置

```bash
# 检查Nginx配置文件
cat nginx/nginx.prod.conf | grep -A 5 "location /api/"
# 应该显示代理到 backend
```

### 3. 检查Docker Compose配置

```bash
# 检查前端服务配置
docker-compose -f docker-compose.prod.yml config | grep -A 10 frontend
```

---

## 🚀 部署流程

### 步骤1：配置环境变量

```bash
# 在 .env.production 中设置
VITE_API_BASE_URL=/api
```

### 步骤2：构建前端镜像

```bash
# GitHub Actions会自动构建
# 或手动构建
docker build -f frontend/Dockerfile.prod \
  --build-arg VITE_API_BASE_URL=/api \
  -t xihong_erp_frontend:latest \
  ./frontend
```

### 步骤3：启动服务

```bash
# 使用Docker Compose启动
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml --profile production up -d
```

### 步骤4：验证配置

```bash
# 检查前端容器
docker logs xihong_erp_frontend

# 检查Nginx容器
docker logs xihong_erp_nginx

# 测试API访问
curl http://localhost/api/health
```

---

## 🔍 工作原理

### 前端请求流程

1. **用户访问**: `http://www.xihong.site`
2. **前端加载**: Nginx返回前端静态文件
3. **API请求**: 前端发送请求到 `/api/xxx`
4. **Nginx代理**: Nginx将 `/api/xxx` 代理到 `backend:8000/api/xxx`
5. **后端处理**: 后端处理请求并返回响应

### 请求示例

```javascript
// 前端代码
const response = await fetch('/api/users')
// 实际请求: http://www.xihong.site/api/users
// Nginx代理: http://backend:8000/api/users
```

---

## ⚠️ 常见问题

### 问题1：前端API请求404

**原因**: `VITE_API_BASE_URL` 配置错误

**解决方案**:
```bash
# 检查配置
grep VITE_API_BASE_URL .env.production

# 应该显示: VITE_API_BASE_URL=/api
# 如果显示其他值，修改为 /api
```

### 问题2：CORS错误

**原因**: 后端CORS配置不正确

**解决方案**:
```bash
# 检查 ALLOWED_ORIGINS
grep ALLOWED_ORIGINS .env.production

# 应该包含域名和IP
ALLOWED_ORIGINS=http://www.xihong.site,http://xihong.site,http://134.175.222.171
```

### 问题3：前端无法访问后端

**原因**: Nginx配置错误或后端服务未启动

**解决方案**:
```bash
# 检查Nginx配置
docker exec xihong_erp_nginx nginx -t

# 检查后端服务
docker ps | grep backend

# 检查Nginx日志
docker logs xihong_erp_nginx
```

---

## 📚 相关文档

- [环境配置对比](./ENV_DEVELOPMENT_VS_PRODUCTION.md)
- [生产环境配置指南](./PRODUCTION_ENV_CONFIG.md)
- [快速部署指南](./QUICK_DEPLOYMENT_GUIDE.md)

---

**最后更新**: 2025-01-XX
