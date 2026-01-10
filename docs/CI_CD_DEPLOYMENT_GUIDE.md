# CI/CD 自动部署指南（v4.20.0）

## 📋 概述

本文档说明西虹ERP系统的CI/CD自动部署流程。完成改造后，实现：
- ✅ **本地开发/测试** → `git push` → 仅构建镜像（不自动部署）
- ✅ **正式上线** → `git tag vX.Y.Z && git push origin vX.Y.Z` → 自动构建 + 自动部署生产

---

## 🚀 用户操作流程

### 日常开发/测试

```bash
# 1. 本地开发和测试
# ... 编写代码 ...

# 2. 提交并推送到 GitHub（不触发生产部署）
git add .
git commit -m "feat: 添加新功能"
git push origin main
```

**结果**：
- ✅ GitHub Actions 自动触发 `Docker Build and Push` workflow
- ✅ 构建并推送镜像到 `ghcr.io`（标签：`main-<sha>`, `latest` 等）
- ❌ **不触发**生产部署（安全）

### 正式上线

```bash
# 1. 确保代码已合并到 main 分支并测试通过
git checkout main
git pull origin main

# 2. 打版本标签并推送（触发自动部署）
git tag v4.20.0
git push origin v4.20.0
```

**结果**：
- ✅ GitHub Actions 自动触发 `Docker Build and Push` workflow（构建 `v4.20.0` 标签的镜像）
- ✅ 构建成功后，自动触发 `Deploy to Production` workflow
- ✅ 服务器自动拉取镜像并部署到生产环境

---

## 🔄 自动部署流程

### 1. 构建阶段（`Docker Build and Push`）

**触发条件**：
- `push` 到 `main`/`develop` 分支
- `push` `v*` 标签
- 手动触发（`workflow_dispatch`）

**执行步骤**：
1. 检出代码
2. 构建 Backend 镜像（`Dockerfile.backend`）
3. 构建 Frontend 镜像（`Dockerfile.frontend`）
4. 推送到 `ghcr.io`（标签：`vX.Y.Z`, `main-<sha>`, `latest` 等）

### 2. 部署阶段（`Deploy to Production`）

**触发条件**：
- `workflow_run`：`Docker Build and Push` 成功完成（**自动触发**）
- `push` `v*` 标签（**备用触发**）
- 手动触发（`workflow_dispatch`，需要输入 `image_tag` 和 `confirm=DEPLOY`）

**执行步骤**：

#### 2.1 检查配置
- 验证必要的 GitHub Secrets 已配置
- 验证部署确认（手动触发时）

#### 2.2 同步 Compose 文件到服务器
- **优先**：通过 `git pull` 同步（如果服务器有 git 仓库）
- **降级**：通过 `scp` 上传 compose 文件

#### 2.3 备份当前部署
- 备份 `docker-compose.config.yaml`
- 备份当前运行的容器列表

#### 2.4 分阶段部署服务

**阶段1：基础设施层**
```bash
# 启动 PostgreSQL 和 Redis
docker-compose ... up -d postgres redis
# 等待健康检查通过
```

**阶段2：Metabase（生产必需组件）**
```bash
# 启动 Metabase（必须在 Nginx 之前启动）
docker-compose -f docker-compose.metabase.yml --profile production up -d metabase
# 等待健康检查通过（最多60秒）
```

**阶段3：应用层**
```bash
# 启动 Backend、Celery Worker、Celery Beat、Celery Exporter
docker-compose ... up -d backend celery-worker celery-beat celery-exporter
# 等待 Backend 健康检查通过
```

**阶段4：前端层**
```bash
# 启动 Frontend
docker-compose ... up -d frontend
# 等待健康检查通过
```

**阶段5：网关层（最后启动）**
```bash
# 启动 Nginx（依赖所有上游服务）
docker-compose ... up -d nginx
# 等待健康检查通过
```

#### 2.5 健康检查验证
- Backend 健康检查（容器内部）
- Frontend 健康检查（容器内部）
- Nginx 健康检查（端口 80）
- 外部健康检查（`PRODUCTION_URL`，支持 HTTP/HTTPS 降级）

---

## 🔧 关键配置

### GitHub Secrets（必需）

| Secret | 说明 | 示例 |
|--------|------|------|
| `PRODUCTION_SSH_PRIVATE_KEY` | 生产服务器 SSH 私钥 | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `PRODUCTION_HOST` | 生产服务器地址 | `134.175.222.171` |
| `PRODUCTION_USER` | SSH 用户 | `deploy` |
| `PRODUCTION_PATH` | 部署路径 | `/opt/xihong_erp` |
| `PRODUCTION_URL` | 生产环境 URL（用于健康检查） | `https://www.xihong.site` |
| `GITHUB_TOKEN` | GitHub Token（自动提供） | - |

### 服务器环境要求

- ✅ Docker 和 Docker Compose 已安装
- ✅ 部署用户（`deploy`）在 `docker` 组中
- ✅ `.env` 文件权限允许部署用户读取
- ✅ 网络连接正常（可以访问 `ghcr.io` 拉取镜像）

---

## 🎯 关键改进点（v4.20.0）

### 1. 解决并行竞态问题
- ✅ **之前**：`docker-build` 和 `deploy-production` 并行运行，可能导致部署时镜像不存在
- ✅ **现在**：使用 `workflow_run` 触发器，确保 Deploy 等待 Build 成功后再执行

### 2. 整合 Metabase 到生产部署
- ✅ **之前**：Metabase 未启动，导致 Nginx 启动失败（无法解析 `metabase:3000`）
- ✅ **现在**：分阶段启动，确保 Metabase 在 Nginx 之前启动并健康

### 3. 提升可追溯性
- ✅ **之前**：使用 `latest` 标签，无法确定生产环境运行的具体版本
- ✅ **现在**：直接使用 `vX.Y.Z` 标签，可以明确知道生产环境运行的版本

### 4. 服务启动顺序优化
- ✅ **之前**：所有服务同时启动，可能导致依赖服务未就绪
- ✅ **现在**：按依赖关系分阶段启动，确保每个阶段的服务健康后再启动下一阶段

---

## ⚠️ 注意事项

### 1. 发布策略
- ⭐ **推荐**：使用 `push tag (v*)` 自动部署（最安全，可控）
- ⚠️ **不推荐**：`push main` 自动部署（风险高，除非有强门禁）

### 2. Metabase 必需性
- ⭐ **Metabase 是生产必需组件**，必须在 Nginx 之前启动
- ⚠️ 如果 Metabase 未启动，Nginx 会因无法解析 `metabase:3000` 而启动失败

### 3. 镜像标签
- ⭐ 生产部署使用不可变标签（`vX.Y.Z`），不使用 `latest`
- ✅ 便于回滚：只需重新部署上一个稳定标签

### 4. 回滚流程
- 如果部署失败，查看 `backups/pre_deploy_<timestamp>/` 目录
- 手动回滚：`git tag v4.19.7 && git push origin v4.19.7`（部署上一个稳定版本）

---

## 📊 部署时间线

```
T=0s      [Docker Build and Push 触发]
          └─ 构建 Backend 镜像（~5-10分钟）
          └─ 构建 Frontend 镜像（~3-5分钟）
          └─ 推送到 ghcr.io

T=10min   [Docker Build and Push 成功]
          └─ 触发 Deploy to Production

T=10min   [Deploy to Production 开始]
          ├─ 同步 Compose 文件（~30秒）
          ├─ 备份当前部署（~10秒）
          ├─ 拉取镜像（~2-5分钟，取决于网络）
          ├─ 阶段1：基础设施层（~30秒）
          ├─ 阶段2：Metabase（~60-120秒）
          ├─ 阶段3：应用层（~60-90秒）
          ├─ 阶段4：前端层（~30-60秒）
          └─ 阶段5：网关层（~30-60秒）

T=15-20min [部署完成，服务可用]
```

---

## 🐛 故障排查

### 问题1：部署失败 "Failed to pull image with tag vX.Y.Z"
**原因**：镜像可能还未构建完成或标签不存在
**解决**：
1. 检查 `Docker Build and Push` workflow 是否成功
2. 等待构建完成后再重试部署
3. 使用手动触发指定正确的标签

### 问题2：Nginx 启动失败 "host not found in upstream 'metabase:3000'"
**原因**：Metabase 服务未启动或未加入同一网络
**解决**：
1. 检查 Metabase 容器是否运行：`docker ps | grep metabase`
2. 检查网络连通性：`docker network inspect xihong_erp_erp_network`
3. 手动启动 Metabase：`docker-compose -f docker-compose.metabase.yml --profile production up -d metabase`

### 问题3：健康检查失败
**原因**：服务启动时间过长或配置错误
**解决**：
1. 查看容器日志：`docker logs xihong_erp_backend`（替换容器名）
2. 检查健康检查配置：`docker inspect <container_name> | grep -A 10 Healthcheck`
3. 手动验证健康端点：`docker exec xihong_erp_backend curl http://localhost:8000/health`

---

## 📚 相关文档

- [Agent开始指南](docs/AGENT_START_HERE.md) - Agent接手必读
- [部署和运维规范](docs/DEVELOPMENT_RULES/DEPLOYMENT.md) - 详细部署规范
- [架构指南](docs/architecture/V4_6_0_ARCHITECTURE_GUIDE.md) - 系统架构说明

---

## ✅ 总结

完成改造后，**用户操作变化**：

- **日常开发**：照常 `git push`（不自动部署，安全）
- **正式上线**：`git tag vX.Y.Z && git push origin vX.Y.Z`（自动部署，便捷）

**关键改进**：
1. ✅ 解决并行竞态（Deploy 等待 Build 成功）
2. ✅ 整合 Metabase（确保启动顺序）
3. ✅ 使用 tag 而非 latest（提升可追溯性）
4. ✅ 分阶段启动（确保服务健康）

**记住**：`push tag` 就是上线，确保代码已测试通过！
