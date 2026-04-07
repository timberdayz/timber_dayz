# 密码配置和镜像仓库检查报告

**生成时间**: 2025-01-XX  
**检查工具**: `scripts/check_passwords_and_registry.py`

---

## 📋 密码配置状态

### ✅ 已配置的密钥

| 配置项 | 状态 | 说明 |
|--------|------|------|
| `SECRET_KEY` | ✅ 已配置 | 应用密钥（已掩码显示） |
| `JWT_SECRET_KEY` | ✅ 已配置 | JWT签名密钥（已掩码显示） |
| `ACCOUNT_ENCRYPTION_KEY` | ✅ 已配置 | 账号加密密钥（Fernet格式） |

### ⚠️ 需要检查的配置

| 配置项 | 状态 | 说明 |
|--------|------|------|
| `POSTGRES_PASSWORD` | ⚠️ 需确认 | 可能在`.env`中使用`DATABASE_URL`包含密码 |
| `REDIS_PASSWORD` | ⚠️ 需确认 | 可能在`.env`中使用`REDIS_URL`包含密码 |

### 📝 可选配置

| 配置项 | 状态 | 说明 |
|--------|------|------|
| `PGADMIN_PASSWORD` | ⚠️ 未配置 | 可选，pgAdmin管理界面密码 |
| `METABASE_ENCRYPTION_SECRET_KEY` | ⚠️ 未配置 | 可选，Metabase加密密钥 |
| `METABASE_EMBEDDING_SECRET_KEY` | ⚠️ 未配置 | 可选，Metabase嵌入密钥 |

---

## 🐳 镜像仓库信息

### GitHub仓库
- **仓库名称**: `timberdayz/timber_dayz`
- **仓库URL**: `https://github.com/timberdayz/timber_dayz.git`

### 镜像仓库地址
- **Registry**: `ghcr.io` (GitHub Container Registry)
- **后端镜像**: `ghcr.io/timberdayz/timber_dayz/backend`
- **前端镜像**: `ghcr.io/timberdayz/timber_dayz/frontend`

### 镜像标签策略
根据`.github/workflows/docker-build.yml`配置：
- `latest` - main分支的最新构建
- `main-{sha}` - main分支的特定提交
- `develop-{sha}` - develop分支的特定提交
- `v{version}` - 版本标签（如 `v4.19.7`）
- `{major}.{minor}` - 主次版本（如 `4.19`）

---

## ✅ 镜像仓库可用性检查

### Docker环境
- ✅ Docker已安装: `Docker version 28.5.1`
- ✅ Docker守护进程运行正常

### 镜像访问
- ⚠️ **注意**: 需要GitHub认证才能访问私有镜像
- 如果镜像未公开，需要先登录: `docker login ghcr.io`

### 测试镜像拉取
```bash
# 测试后端镜像
docker pull ghcr.io/timberdayz/timber_dayz/backend:latest

# 测试前端镜像
docker pull ghcr.io/timberdayz/timber_dayz/frontend:latest
```

---

## 🔧 部署前检查清单

### 1. 密码配置
- [ ] 确认`POSTGRES_PASSWORD`已配置（或在`DATABASE_URL`中）
- [ ] 确认`REDIS_PASSWORD`已配置（或在`REDIS_URL`中）
- [x] `SECRET_KEY`已配置
- [x] `JWT_SECRET_KEY`已配置
- [x] `ACCOUNT_ENCRYPTION_KEY`已配置

### 2. GitHub配置
- [x] GitHub仓库已确定: `timberdayz/timber_dayz`
- [ ] 确认GitHub Packages权限已启用
- [ ] 确认GitHub Actions有`packages: write`权限

### 3. 服务器配置
- [ ] 在服务器上安装Docker和Docker Compose
- [ ] 在服务器上登录镜像仓库: `docker login ghcr.io`
- [ ] 配置GitHub Secrets（PRODUCTION_SSH_PRIVATE_KEY等）

---

## 🚀 生成新密码

如果需要生成新的密码和密钥，运行：

```bash
python scripts/check_passwords_and_registry.py --generate
```

这将生成：
- `POSTGRES_PASSWORD` - 24位随机密码
- `REDIS_PASSWORD` - 24位随机密码
- `SECRET_KEY` - 32位随机字符串
- `JWT_SECRET_KEY` - 32位随机字符串
- `ACCOUNT_ENCRYPTION_KEY` - Fernet密钥

---

## 📚 相关文档

- [CI/CD流程指南](../CI_CD_GUIDE.md)
- [生产环境部署指南](./PRODUCTION_DEPLOYMENT_GUIDE.md)
- [Docker部署指南](./DOCKER_DEPLOYMENT.md)

---

## ⚠️ 重要提示

1. **密码安全**: 所有密码必须使用强随机字符串，不要使用默认值
2. **镜像访问**: 如果镜像仓库是私有的，需要在服务器上登录GitHub
3. **权限配置**: 确保GitHub Actions有权限推送镜像到ghcr.io
4. **环境变量**: 生产环境必须使用`.env`文件，不要硬编码密码

---

**最后更新**: 2025-01-XX
