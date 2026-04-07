# CI/CD 配置与测试指南

版本: v4.19.7  
更新时间: 2026-01-05

## 概述

本文档提供 CI/CD 流程的配置步骤和测试方法，帮助您快速设置和验证 GitHub Actions 工作流。

---

## 配置步骤

### 1. GitHub Secrets 配置

#### 1.1 访问 Secrets 设置

1. 打开 GitHub 仓库
2. 进入 **Settings** → **Secrets and variables** → **Actions**
3. 点击 **New repository secret**

#### 1.2 测试环境 Secrets

| Secret 名称               | 说明                | 示例值                                   | 必需                     |
| ------------------------- | ------------------- | ---------------------------------------- | ------------------------ |
| `STAGING_SSH_PRIVATE_KEY` | 测试服务器 SSH 私钥 | `-----BEGIN OPENSSH PRIVATE KEY-----...` | ✅                       |
| `STAGING_HOST`            | 测试服务器地址      | `staging.example.com` 或 `192.168.1.100` | ✅                       |
| `STAGING_USER`            | SSH 用户名          | `root` 或 `deploy`                       | ⚠️ 默认：root            |
| `STAGING_PATH`            | 项目路径            | `/opt/xihong_erp`                        | ⚠️ 默认：/opt/xihong_erp |
| `STAGING_URL`             | 测试环境 URL        | `http://staging.example.com`             | ⚠️ 用于健康检查          |
| `SLACK_WEBHOOK_URL`       | Slack Webhook       | `https://hooks.slack.com/...`            | ❌ 可选                  |

#### 1.3 生产环境 Secrets

| Secret 名称                  | 说明                | 示例值                                   | 必需                     |
| ---------------------------- | ------------------- | ---------------------------------------- | ------------------------ |
| `PRODUCTION_SSH_PRIVATE_KEY` | 生产服务器 SSH 私钥 | `-----BEGIN OPENSSH PRIVATE KEY-----...` | ✅                       |
| `PRODUCTION_HOST`            | 生产服务器地址      | `production.example.com`                 | ✅                       |
| `PRODUCTION_USER`            | SSH 用户名          | `root` 或 `deploy`                       | ⚠️ 默认：root            |
| `PRODUCTION_PATH`            | 项目路径            | `/opt/xihong_erp`                        | ⚠️ 默认：/opt/xihong_erp |
| `PRODUCTION_URL`             | 生产环境 URL        | `https://production.example.com`         | ⚠️ 用于健康检查          |
| `SLACK_WEBHOOK_URL`          | Slack Webhook       | `https://hooks.slack.com/...`            | ❌ 可选                  |

#### 1.4 生成 SSH 密钥对

```bash
# 在本地生成 SSH 密钥对（用于服务器访问）
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy

# 查看公钥（需要添加到服务器的 ~/.ssh/authorized_keys）
cat ~/.ssh/github_actions_deploy.pub

# 查看私钥（需要添加到 GitHub Secrets）
cat ~/.ssh/github_actions_deploy
```

**重要提示**：

- 私钥必须包含完整的 `-----BEGIN` 和 `-----END` 标记
- 不要添加换行符或空格
- 将整个私钥内容复制到 GitHub Secret

#### 1.5 配置服务器 SSH 访问

```bash
# 在服务器上执行
# 1. 添加公钥到 authorized_keys
echo "YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh

# 2. 测试 SSH 连接
ssh -i ~/.ssh/github_actions_deploy user@server
```

---

### 2. GitHub Environments 配置

#### 2.1 创建测试环境

1. 打开 GitHub 仓库
2. 进入 **Settings** → **Environments**
3. 点击 **New environment**
4. 输入名称：`staging`
5. 配置：
   - **Environment URL**: `http://staging.example.com`（可选）
   - **Deployment branches**: 选择 `main` 和 `develop`（可选）

#### 2.2 创建生产环境

1. 点击 **New environment**
2. 输入名称：`production`
3. 配置：
   - **Environment URL**: `https://production.example.com`（可选）
   - **Deployment branches**: 选择 `main`（推荐）
   - **Required reviewers**: 添加至少 1 个审批人
   - **Wait timer**: 0 分钟（或根据需要设置）

**重要提示**：

- 生产环境必须设置审批人
- 审批人会在部署前收到通知
- 只有审批人批准后才能继续部署

---

### 3. 服务器准备

#### 3.1 安装 Docker 和 Docker Compose

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version
```

#### 3.2 准备项目目录

```bash
# 创建项目目录
sudo mkdir -p /opt/xihong_erp
sudo chown $USER:$USER /opt/xihong_erp

# 克隆项目（或上传文件）
cd /opt/xihong_erp
git clone https://github.com/your-org/xihong_erp.git .

# 创建必要的目录
mkdir -p data logs temp uploads downloads backups

# 创建 .env 文件
cp env.production.example .env
# 编辑 .env 文件，配置环境变量
```

#### 3.3 配置 Docker Compose

```bash
# 确保 docker-compose.yml 和 docker-compose.prod.yml 存在
ls -la docker-compose*.yml

# 测试 Docker Compose 配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml config
```

---

## 测试步骤

### 1. 本地测试 Docker 镜像构建

```bash
# 测试后端镜像构建
docker build -f Dockerfile.backend -t xihong_erp_backend:test .

# 测试前端镜像构建
docker build -f Dockerfile.frontend -t xihong_erp_frontend:test .

# 验证镜像
docker images | grep xihong_erp
```

### 2. 测试 GitHub Actions 工作流

#### 2.1 测试镜像构建工作流

1. 推送代码到 `main` 或 `develop` 分支
2. 打开 GitHub Actions 页面
3. 查看 `Docker Build and Push` 工作流
4. 验证：
   - 构建成功
   - 镜像推送到 GitHub Container Registry
   - 镜像标签正确

#### 2.2 测试测试环境部署

1. 确保 CI Pipeline 和 Docker Build 成功
2. 查看 `Deploy to Staging` 工作流是否自动触发
3. 或手动触发：
   - 进入 **Actions** → **Deploy to Staging**
   - 点击 **Run workflow**
   - 选择分支和镜像标签
4. 验证：
   - SSH 连接成功
   - 镜像拉取成功
   - 服务部署成功
   - 健康检查通过

#### 2.3 测试生产环境部署

1. 进入 **Actions** → **Deploy to Production**
2. 点击 **Run workflow**
3. 输入：
   - **image_tag**: `v4.19.7` 或 `main-abc123`
   - **confirm**: `DEPLOY`
4. 等待审批（如果设置了审批人）
5. 验证：
   - 部署前备份创建
   - 镜像拉取成功
   - 服务部署成功
   - 健康检查通过

---

## 故障排查

### 问题 1: SSH 连接失败

**症状**: 部署工作流失败，提示 SSH 连接错误

**检查**:

```bash
# 在本地测试 SSH 连接
ssh -i ~/.ssh/github_actions_deploy user@server

# 检查服务器 SSH 配置
sudo tail -f /var/log/auth.log  # Ubuntu/Debian
sudo tail -f /var/log/secure    # CentOS/RHEL
```

**解决**:

- 验证 SSH 密钥格式正确
- 检查服务器防火墙设置
- 确认 SSH 服务正在运行
- 验证 authorized_keys 权限

---

### 问题 2: 镜像拉取失败

**症状**: 部署时无法拉取镜像

**检查**:

```bash
# 在服务器上手动测试
docker login ghcr.io -u YOUR_USERNAME -p YOUR_TOKEN
docker pull ghcr.io/owner/xihong_erp/backend:latest
```

**解决**:

- 验证 GitHub Token 权限
- 检查镜像仓库访问权限
- 确认镜像标签存在
- 检查网络连接

---

### 问题 3: Docker Compose 部署失败

**症状**: docker-compose up 失败

**检查**:

```bash
# 在服务器上查看日志
cd /opt/xihong_erp
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs

# 检查配置文件
docker-compose -f docker-compose.yml -f docker-compose.prod.yml config
```

**解决**:

- 验证 docker-compose 文件语法
- 检查环境变量配置
- 确认 Docker 服务正在运行
- 验证端口未被占用

---

### 问题 4: 健康检查失败

**症状**: 部署成功但健康检查超时

**检查**:

```bash
# 在服务器上手动测试
curl http://localhost:8001/health

# 查看容器日志
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs backend
```

**解决**:

- 检查服务是否正常启动
- 验证数据库连接
- 检查环境变量配置
- 增加健康检查超时时间

---

## 配置检查清单

### GitHub 配置

- [ ] 所有必需的 Secrets 已配置
- [ ] SSH 密钥格式正确（包含 BEGIN/END 标记）
- [ ] `staging` 环境已创建
- [ ] `production` 环境已创建并设置审批人
- [ ] GitHub Token 有足够权限（自动提供）

### 服务器配置

- [ ] Docker 已安装并运行
- [ ] Docker Compose 已安装
- [ ] SSH 密钥已添加到服务器
- [ ] 项目目录已创建
- [ ] `.env` 文件已配置
- [ ] docker-compose 文件存在

### 工作流测试

- [ ] 镜像构建工作流成功
- [ ] 镜像已推送到仓库
- [ ] 测试环境部署成功
- [ ] 生产环境部署流程正常
- [ ] 健康检查通过

---

## 快速测试脚本

### 配置检查

使用 `scripts/test_cicd_setup.py` 进行快速配置检查：

```bash
# Windows
python scripts/test_cicd_setup.py

# 检查服务器配置
python scripts/test_cicd_setup.py --check-server user@host
```

该脚本会检查：

- GitHub Secrets 配置（需要手动验证）
- 服务器 SSH 连接
- Docker 和 Docker Compose 安装
- 项目目录和文件
- 环境变量配置

### Docker 镜像构建测试

```bash
# Linux/Mac
bash scripts/test_docker_build.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File scripts/test_docker_build.ps1
```

该脚本会：

- 测试后端镜像构建
- 测试前端镜像构建
- 验证 Dockerfile 配置正确

---

## 相关文档

- [CI/CD 流程指南](./CI_CD_GUIDE.md)
- [快速参考](./INFRA_OPS_QUICK_REFERENCE.md)
- [Docker 部署指南](./DOCKER_DEPLOYMENT.md)

---

## 更新历史

- **v4.19.7** (2026-01-05): 创建配置与测试指南
