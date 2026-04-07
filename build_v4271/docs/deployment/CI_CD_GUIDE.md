# CI/CD 流程指南

版本: v4.19.7  
更新时间: 2026-01-05

## 概述

本文档描述西虹ERP系统的 CI/CD 流程，包括：
- CI 工作流（测试、构建、镜像推送）
- 测试环境自动部署
- 生产环境部署与审批
- 回滚操作与故障排查

---

## CI 工作流

### 工作流文件

- `.github/workflows/ci.yml` - 代码测试和验证
- `.github/workflows/docker-build.yml` - Docker 镜像构建和推送

### CI 流程

1. **代码检查**
   - 代码格式化检查（Black）
   - 代码质量检查（Ruff）
   - 类型检查（mypy）

2. **安全扫描**
   - Bandit 安全扫描
   - 依赖漏洞检查（Safety）
   - 密钥泄露检查

3. **测试**
   - 单元测试（pytest）
   - 集成测试
   - 契约测试

4. **Docker 镜像构建**
   - 后端镜像构建（`Dockerfile.backend`）
   - 前端镜像构建（`Dockerfile.frontend`）
   - 使用 docker buildx + 缓存优化

### 镜像标签策略

镜像标签遵循以下策略：

- `latest` - main 分支的最新构建
- `main-{sha}` - main 分支的特定提交
- `develop-{sha}` - develop 分支的特定提交
- `v{version}` - 版本标签（如 `v4.19.7`）
- `{major}.{minor}` - 主次版本（如 `4.19`）
- `pr-{number}` - Pull Request 构建

**示例**:
```
ghcr.io/owner/xihong_erp/backend:latest
ghcr.io/owner/xihong_erp/backend:v4.19.7
ghcr.io/owner/xihong_erp/backend:main-abc123
ghcr.io/owner/xihong_erp/backend:4.19
```

---

## 测试环境部署

### 工作流文件

- `.github/workflows/deploy-staging.yml`

### 触发条件

1. **自动触发**:
   - CI Pipeline 成功完成后
   - Docker Build 成功完成后
   - 仅限 `main` 和 `develop` 分支

2. **手动触发**:
   - 通过 GitHub Actions UI 手动触发
   - 可指定镜像标签

### 部署流程

1. **SSH 连接到测试服务器**
   - 使用 `STAGING_SSH_PRIVATE_KEY` Secret

2. **拉取镜像**
   ```bash
   docker pull ghcr.io/owner/xihong_erp/backend:{tag}
   docker pull ghcr.io/owner/xihong_erp/frontend:{tag}
   ```

3. **部署服务**
   ```bash
   export APP_ENV=staging
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d
   ```

4. **健康检查**
   - 等待后端服务启动（最多 60 秒）
   - 调用 `/health` 接口验证
   - 验证前端服务（如果部署）

5. **发送通知**
   - Slack/邮件通知部署结果

### 配置要求

**GitHub Secrets**:
- `STAGING_SSH_PRIVATE_KEY` - 测试服务器 SSH 私钥
- `STAGING_HOST` - 测试服务器地址
- `STAGING_USER` - SSH 用户名（默认：root）
- `STAGING_PATH` - 项目路径（默认：/opt/xihong_erp）
- `STAGING_URL` - 测试环境 URL（用于健康检查）
- `SLACK_WEBHOOK_URL` - Slack Webhook（可选）

**GitHub Environment**:
- `staging` - 测试环境配置

---

## 生产环境部署

### 工作流文件

- `.github/workflows/deploy-production.yml`

### 触发条件

1. **手动触发**（推荐）:
   - 通过 GitHub Actions UI 手动触发
   - 必须输入镜像标签
   - 必须输入 "DEPLOY" 确认

2. **Tag 触发**:
   - 推送版本标签（如 `v4.19.7`）
   - 自动触发部署

### 部署流程

1. **审批确认**
   - 检查 GitHub Environment `production` 审批
   - 验证手动确认输入

2. **部署前备份**
   - 备份当前 docker-compose 配置
   - 记录当前运行的容器
   - 保存到 `backups/pre_deploy_YYYYMMDD_HHMMSS/`

3. **SSH 连接到生产服务器**
   - 使用 `PRODUCTION_SSH_PRIVATE_KEY` Secret

4. **拉取指定版本镜像**
   ```bash
   docker pull ghcr.io/owner/xihong_erp/backend:{tag}
   docker pull ghcr.io/owner/xihong_erp/frontend:{tag}
   ```

5. **部署服务**
   ```bash
   export APP_ENV=production
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d
   ```

6. **健康检查**
   - 等待后端服务启动（最多 2 分钟）
   - 调用 `/health` 接口验证
   - 验证前端服务（如果部署）

7. **失败回滚**
   - 如果部署失败，自动触发回滚流程
   - 使用部署前备份恢复

8. **发送通知**
   - Slack/邮件/企业微信通知部署结果

### 配置要求

**GitHub Secrets**:
- `PRODUCTION_SSH_PRIVATE_KEY` - 生产服务器 SSH 私钥
- `PRODUCTION_HOST` - 生产服务器地址
- `PRODUCTION_USER` - SSH 用户名（默认：root）
- `PRODUCTION_PATH` - 项目路径（默认：/opt/xihong_erp）
- `PRODUCTION_URL` - 生产环境 URL（用于健康检查）
- `SLACK_WEBHOOK_URL` - Slack Webhook（可选）

**GitHub Environment**:
- `production` - 生产环境配置
  - 审批人设置
  - 保护规则
  - Secret 绑定

---

## 回滚操作

### 自动回滚

如果部署失败，工作流会自动：
1. 检测部署失败
2. 查找部署前备份
3. 提示手动回滚步骤

### 手动回滚

#### 方法 1: 使用上一个镜像标签

```bash
# 1. SSH 登录生产服务器
ssh user@production-host

# 2. 进入项目目录
cd /opt/xihong_erp

# 3. 查看可用镜像标签
docker images | grep xihong_erp

# 4. 拉取上一个版本的镜像
docker pull ghcr.io/owner/xihong_erp/backend:v4.19.6
docker pull ghcr.io/owner/xihong_erp/frontend:v4.19.6

# 5. 标记为 latest
docker tag ghcr.io/owner/xihong_erp/backend:v4.19.6 xihong_erp_backend:latest
docker tag ghcr.io/owner/xihong_erp/frontend:v4.19.6 xihong_erp_frontend:latest

# 6. 重新部署
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d

# 7. 验证
curl http://localhost:8001/health
```

#### 方法 2: 使用部署前备份

```bash
# 1. SSH 登录生产服务器
ssh user@production-host

# 2. 进入项目目录
cd /opt/xihong_erp

# 3. 查找部署前备份
ls -lth backups/pre_deploy_* | head -5

# 4. 查看备份内容
cat backups/pre_deploy_YYYYMMDD_HHMMSS/docker-compose.config.yaml
cat backups/pre_deploy_YYYYMMDD_HHMMSS/running_containers.txt

# 5. 根据备份信息手动回滚
# （恢复配置、拉取对应镜像等）
```

#### 方法 3: 通过 GitHub Actions 回滚

1. 打开 GitHub Actions
2. 找到上一次成功的部署
3. 查看使用的镜像标签
4. 手动触发新的部署，使用上一次的镜像标签

---

## 故障排查

### 问题 1: 镜像构建失败

**症状**: `docker-build.yml` 工作流失败

**检查**:
```bash
# 查看构建日志
# GitHub Actions → docker-build.yml → 查看失败步骤

# 本地测试构建
docker build -f Dockerfile.backend -t test-backend .
docker build -f Dockerfile.frontend -t test-frontend .
```

**常见原因**:
- Dockerfile 语法错误
- 依赖安装失败
- 构建上下文问题

**解决**:
- 检查 Dockerfile 语法
- 验证依赖文件存在
- 检查 `.dockerignore` 配置

---

### 问题 2: 镜像推送失败

**症状**: 构建成功但推送失败

**检查**:
```bash
# 验证 GitHub Token 权限
# Settings → Actions → General → Workflow permissions
# 确保 "Read and write permissions" 已启用
```

**常见原因**:
- GitHub Token 权限不足
- 容器仓库访问权限问题
- 网络问题

**解决**:
- 检查 GitHub Token 权限
- 验证仓库访问权限
- 重试推送

---

### 问题 3: 部署失败 - SSH 连接失败

**症状**: 无法连接到服务器

**检查**:
```bash
# 测试 SSH 连接
ssh -i /path/to/private_key user@host

# 验证 SSH 密钥格式
# GitHub Secrets 中的密钥应该是完整的私钥（包括 -----BEGIN 和 -----END）
```

**常见原因**:
- SSH 密钥格式错误
- 服务器地址错误
- 网络防火墙阻止

**解决**:
- 验证 SSH 密钥格式
- 检查服务器地址和端口
- 验证网络连接

---

### 问题 4: 部署失败 - 健康检查超时

**症状**: 部署成功但健康检查失败

**检查**:
```bash
# SSH 登录服务器
ssh user@host

# 查看容器日志
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs backend

# 检查容器状态
docker ps -a | grep backend

# 手动健康检查
curl http://localhost:8001/health
```

**常见原因**:
- 数据库连接失败
- 环境变量配置错误
- 服务启动时间过长

**解决**:
- 检查数据库连接
- 验证环境变量配置
- 增加健康检查超时时间

---

### 问题 5: 镜像标签不存在

**症状**: 拉取镜像失败，提示标签不存在

**检查**:
```bash
# 查看可用镜像标签
# GitHub Packages → 查看镜像标签列表

# 验证标签格式
# 应该使用完整的标签（如 v4.19.7 而不是 4.19.7）
```

**常见原因**:
- 标签拼写错误
- 镜像未构建
- 标签已被删除

**解决**:
- 验证标签存在
- 重新构建镜像
- 使用正确的标签格式

---

## 最佳实践

### 1. 版本管理

- **使用语义化版本**: `v4.19.7`
- **为重要发布打标签**: 每次生产部署前打标签
- **保留历史版本**: 不要删除旧版本镜像（用于回滚）

### 2. 部署前检查

- **验证镜像存在**: 确认要部署的镜像标签已构建
- **检查测试环境**: 确保测试环境部署成功
- **审查变更**: 查看本次部署的代码变更

### 3. 部署后验证

- **健康检查**: 验证所有服务正常
- **功能测试**: 测试关键功能
- **监控告警**: 关注监控指标和告警

### 4. 回滚准备

- **保留备份**: 部署前自动备份
- **记录版本**: 记录每次部署的镜像标签
- **测试回滚**: 定期演练回滚流程

---

## 工作流集成

### 集成到 CI Pipeline

可选：在 `ci.yml` 中集成镜像构建：

```yaml
# .github/workflows/ci.yml
jobs:
  # ... 现有测试任务 ...
  
  build-images:
    needs: [test]
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/develop'
    uses: ./.github/workflows/docker-build.yml
```

### 测试环境自动部署

测试环境部署会在以下情况自动触发：
- CI Pipeline 成功
- Docker Build 成功
- 仅限 `main` 和 `develop` 分支

### 生产环境部署

生产环境部署需要：
- 手动触发（推荐）
- 或推送版本标签（`v*`）
- GitHub Environment 审批

---

## 配置示例

### GitHub Secrets 配置清单

**Docker 构建**:
- `GITHUB_TOKEN` - 自动提供（无需配置）

**测试环境**:
- `STAGING_SSH_PRIVATE_KEY` - SSH 私钥
- `STAGING_HOST` - 服务器地址
- `STAGING_USER` - SSH 用户名
- `STAGING_PATH` - 项目路径
- `STAGING_URL` - 测试环境 URL
- `SLACK_WEBHOOK_URL` - Slack Webhook（可选）

**生产环境**:
- `PRODUCTION_SSH_PRIVATE_KEY` - SSH 私钥
- `PRODUCTION_HOST` - 服务器地址
- `PRODUCTION_USER` - SSH 用户名
- `PRODUCTION_PATH` - 项目路径
- `PRODUCTION_URL` - 生产环境 URL
- `SLACK_WEBHOOK_URL` - Slack Webhook（可选）

### GitHub Environment 配置

**staging**:
- URL: `http://staging.example.com`
- 无需审批（自动部署）

**production**:
- URL: `https://production.example.com`
- 审批人: 设置至少 1 个审批人
- 保护规则: 启用部署分支限制（可选）

---

## 相关文档

- [快速参考](./INFRA_OPS_QUICK_REFERENCE.md)
- [备份策略](./BACKUP_STRATEGY.md)
- [恢复指南](./RESTORE_GUIDE.md)
- [Docker 部署指南](./DOCKER_DEPLOYMENT.md)

---

## 更新历史

- **v4.19.7** (2026-01-05): 创建 CI/CD 流程指南

