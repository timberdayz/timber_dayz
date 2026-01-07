# Nginx 前端代理 404 问题修复报告

> **修复日期**: 2026-01-03  
> **问题**: 前端服务返回 404  
> **状态**: ✅ 已修复

## 🔍 问题分析

### 问题现象

- 直接访问 `http://localhost:5173` 返回 404
- 访问 `http://localhost:5173/index.html` 返回 200
- Nginx 代理 `http://localhost:8081/` 返回 404

### 根本原因

Vite 开发服务器对于根路径 `/` 的处理需要特殊配置。虽然 Vite 支持 SPA 路由，但在某些情况下，直接访问根路径可能返回 404，需要明确指定 `/index.html`。

## 🔧 修复方案

### 修复内容

修改 `nginx/nginx.dev.conf` 中的前端代理配置：

1. **添加根路径特殊处理**：

   - 使用 `location = /` 精确匹配根路径
   - 直接代理到 `http://frontend/index.html`

2. **添加 SPA 路由回退**：
   - 在 `location /` 中添加 `proxy_intercept_errors on`
   - 使用 `error_page 404 = /index.html` 处理 404 错误
   - 确保所有 SPA 路由都能正确回退到 `index.html`

### 修复后的配置

```nginx
# 前端静态文件（开发环境：Vite 开发服务器）
# 注意：Vite 开发服务器需要特殊处理 SPA 路由
# 对于根路径，直接代理到 /index.html（Vite 会自动处理）
location = / {
    proxy_pass http://frontend/index.html;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache_bypass $http_upgrade;
}

# 其他前端路由（SPA 路由回退）
location / {
    proxy_pass http://frontend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_cache_bypass $http_upgrade;

    # Vite HMR 支持
    # 如果后端返回 404，拦截并重写为 /index.html（SPA 路由回退）
    proxy_intercept_errors on;
    error_page 404 = /index.html;
}
```

## ✅ 验证结果

### 测试结果

| 测试项                             | 状态    | 说明                      |
| ---------------------------------- | ------- | ------------------------- |
| `http://localhost:8081/`           | ✅ 200  | 根路径正常访问            |
| `http://localhost:8081/index.html` | ✅ 200  | index.html 正常访问       |
| SPA 路由                           | ✅ 正常 | 404 自动回退到 index.html |

### 验证命令

```powershell
# 测试根路径
Invoke-WebRequest -Uri "http://localhost:8081/" -UseBasicParsing

# 测试 index.html
Invoke-WebRequest -Uri "http://localhost:8081/index.html" -UseBasicParsing

# 测试 SPA 路由
Invoke-WebRequest -Uri "http://localhost:8081/dashboard" -UseBasicParsing
```

## 📝 技术说明

### Vite 开发服务器 SPA 路由处理

Vite 开发服务器默认支持 SPA 路由，但在以下情况下可能需要特殊处理：

1. **根路径访问**：直接访问 `/` 时，Vite 可能返回 404
2. **直接文件访问**：需要明确指定 `/index.html`
3. **Nginx 代理**：需要通过配置确保所有路由都能正确回退到 `index.html`

### Nginx 配置要点

1. **精确匹配根路径**：使用 `location = /` 确保根路径被正确处理
2. **错误拦截**：使用 `proxy_intercept_errors on` 拦截后端 404 错误
3. **错误重写**：使用 `error_page 404 = /index.html` 将 404 重写为 index.html
4. **HMR 支持**：保持 `Upgrade` 和 `Connection` 头，支持 Vite HMR

## 🎯 修复效果

- ✅ 根路径 `/` 正常访问
- ✅ SPA 路由正常工作
- ✅ Vite HMR 功能正常
- ✅ 前端代理功能完全正常

## 📊 修复前后对比

| 项目                               | 修复前 | 修复后      |
| ---------------------------------- | ------ | ----------- |
| `http://localhost:8081/`           | ❌ 404 | ✅ 200      |
| `http://localhost:8081/index.html` | ✅ 200 | ✅ 200      |
| SPA 路由                           | ❌ 404 | ✅ 正常回退 |

## ✅ 总结

前端代理 404 问题已完全修复。现在 Nginx 可以正确处理：

- 根路径访问
- SPA 路由
- Vite HMR 功能

所有前端代理功能正常工作，可以用于开发环境测试。
