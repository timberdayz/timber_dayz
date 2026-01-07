# GitHub CI/CD 配置清单

版本: v4.19.7  
更新时间: 2026-01-05

## 快速配置清单

使用此清单确保所有 CI/CD 配置已完成。

---

## 步骤 1: GitHub Secrets 配置

### 访问路径
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

### 测试环境 Secrets（必需）

- [ ] `STAGING_SSH_PRIVATE_KEY`
  - **说明**: 测试服务器 SSH 私钥
  - **格式**: 完整的私钥内容（包含 `-----BEGIN` 和 `-----END`）
  - **生成命令**: `ssh-keygen -t ed25519 -C "github-actions-staging" -f ~/.ssh/github_staging`
  - **验证**: `cat ~/.ssh/github_staging`

- [ ] `STAGING_HOST`
  - **说明**: 测试服务器地址
  - **示例**: `staging.example.com` 或 `192.168.1.100`
  - **验证**: `ping staging.example.com`

- [ ] `STAGING_USER`（可选，默认：root）
  - **说明**: SSH 用户名
  - **示例**: `root` 或 `deploy`

- [ ] `STAGING_PATH`（可选，默认：/opt/xihong_erp）
  - **说明**: 项目路径
  - **示例**: `/opt/xihong_erp`

- [ ] `STAGING_URL`（可选）
  - **说明**: 测试环境 URL（用于健康检查）
  - **示例**: `http://staging.example.com`

### 生产环境 Secrets（必需）

- [ ] `PRODUCTION_SSH_PRIVATE_KEY`
  - **说明**: 生产服务器 SSH 私钥
  - **格式**: 完整的私钥内容（包含 `-----BEGIN` 和 `-----END`）
  - **生成命令**: `ssh-keygen -t ed25519 -C "github-actions-production" -f ~/.ssh/github_production`
  - **验证**: `cat ~/.ssh/github_production`

- [ ] `PRODUCTION_HOST`
  - **说明**: 生产服务器地址
  - **示例**: `production.example.com`
  - **验证**: `ping production.example.com`

- [ ] `PRODUCTION_USER`（可选，默认：root）
  - **说明**: SSH 用户名
  - **示例**: `root` 或 `deploy`

- [ ] `PRODUCTION_PATH`（可选，默认：/opt/xihong_erp）
  - **说明**: 项目路径
  - **示例**: `/opt/xihong_erp`

- [ ] `PRODUCTION_URL`（可选）
  - **说明**: 生产环境 URL（用于健康检查）
  - **示例**: `https://production.example.com`

### 可选 Secrets

- [ ] `SLACK_WEBHOOK_URL`（可选）
  - **说明**: Slack Webhook URL（用于部署通知）
  - **获取**: Slack App → Incoming Webhooks
  - **示例**: `https://hooks.slack.com/services/...`

---

## 步骤 2: GitHub Environments 配置

### 访问路径
**Settings** → **Environments** → **New environment**

### 测试环境（staging）

- [ ] 创建环境
  - **名称**: `staging`
  - **URL**: `http://staging.example.com`（可选）

- [ ] 配置部署分支（可选）
  - **Deployment branches**: 选择 `main` 和 `develop`

### 生产环境（production）

- [ ] 创建环境
  - **名称**: `production`
  - **URL**: `https://production.example.com`（可选）

- [ ] 配置部署分支
  - **Deployment branches**: 选择 `main`（推荐）

- [ ] 配置审批人（必需）
  - **Required reviewers**: 添加至少 1 个审批人
  - **说明**: 生产环境部署需要审批人批准

- [ ] 配置等待时间（可选）
  - **Wait timer**: 0 分钟（或根据需要设置）

---

## 步骤 3: 服务器准备

### SSH 密钥配置

- [ ] 生成 SSH 密钥对
  ```bash
  ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy
  ```

- [ ] 将公钥添加到服务器
  ```bash
  # 在服务器上执行
  echo "YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys
  chmod 600 ~/.ssh/authorized_keys
  chmod 700 ~/.ssh
  ```

- [ ] 测试 SSH 连接
  ```bash
  ssh -i ~/.ssh/github_actions_deploy user@server
  ```

### Docker 安装

- [ ] 安装 Docker
  ```bash
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  sudo usermod -aG docker $USER
  ```

- [ ] 安装 Docker Compose
  ```bash
  sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
  ```

- [ ] 验证安装
  ```bash
  docker --version
  docker-compose --version
  ```

### 项目目录准备

- [ ] 创建项目目录
  ```bash
  sudo mkdir -p /opt/xihong_erp
  sudo chown $USER:$USER /opt/xihong_erp
  ```

- [ ] 克隆或上传项目文件
  ```bash
  cd /opt/xihong_erp
  git clone https://github.com/your-org/xihong_erp.git .
  ```

- [ ] 创建必要目录
  ```bash
  mkdir -p data logs temp uploads downloads backups
  ```

- [ ] 配置环境变量
  ```bash
  cp env.production.example .env
  # 编辑 .env 文件
  ```

---

## 步骤 4: 测试工作流

### 测试镜像构建

- [ ] 推送代码到 `main` 或 `develop` 分支
- [ ] 查看 GitHub Actions → `Docker Build and Push` 工作流
- [ ] 验证构建成功
- [ ] 验证镜像已推送到 GitHub Container Registry

### 测试测试环境部署

- [ ] 等待 CI Pipeline 和 Docker Build 成功
- [ ] 查看 `Deploy to Staging` 工作流是否自动触发
- [ ] 或手动触发：**Actions** → **Deploy to Staging** → **Run workflow**
- [ ] 验证部署成功
- [ ] 验证服务健康检查通过

### 测试生产环境部署

- [ ] 进入 **Actions** → **Deploy to Production**
- [ ] 点击 **Run workflow**
- [ ] 输入镜像标签（如 `v4.19.7`）
- [ ] 输入确认（`DEPLOY`）
- [ ] 等待审批（如果设置了审批人）
- [ ] 验证部署成功
- [ ] 验证服务健康检查通过

---

## 验证命令

### 本地验证

```bash
# 运行配置检查脚本
python scripts/test_cicd_setup.py

# 测试 Docker 镜像构建
bash scripts/test_docker_build.sh
```

### 服务器验证

```bash
# 测试 SSH 连接
ssh -i ~/.ssh/github_actions_deploy user@server

# 测试 Docker
ssh user@server "docker --version"
ssh user@server "docker-compose --version"

# 测试项目目录
ssh user@server "ls -la /opt/xihong_erp"
```

---

## 常见问题

### Q1: SSH 连接失败

**检查**:
- SSH 密钥格式是否正确（包含 BEGIN/END 标记）
- 服务器防火墙是否允许 SSH
- SSH 服务是否运行

**解决**:
```bash
# 测试 SSH 连接
ssh -v -i ~/.ssh/github_actions_deploy user@server
```

### Q2: 镜像构建失败

**检查**:
- Dockerfile 语法是否正确
- 依赖文件是否存在
- 构建上下文是否正确

**解决**:
```bash
# 本地测试构建
docker build -f Dockerfile.backend -t test-backend .
```

### Q3: 部署失败

**检查**:
- GitHub Secrets 是否配置正确
- 服务器 SSH 连接是否正常
- Docker 和 Docker Compose 是否安装

**解决**:
- 查看 GitHub Actions 日志
- 在服务器上手动测试部署命令

---

## 相关文档

- [CI/CD 配置与测试指南](./CI_CD_SETUP_GUIDE.md)
- [CI/CD 流程指南](./CI_CD_GUIDE.md)
- [快速参考](./INFRA_OPS_QUICK_REFERENCE.md)

---

## 更新历史

- **v4.19.7** (2026-01-05): 创建配置清单

