# CI/CD 快速开始指南

版本: v4.19.7  
更新时间: 2026-01-05

## 5 分钟快速配置

### 步骤 1: 运行配置检查（1 分钟）

```bash
python scripts/test_cicd_setup.py
```

**预期结果**: 所有本地检查通过 ✅

---

### 步骤 2: 测试 Docker 镜像构建（2 分钟）

```bash
# Windows
powershell -ExecutionPolicy Bypass -File scripts/test_docker_build.ps1

# Linux/Mac
bash scripts/test_docker_build.sh
```

**预期结果**: 后端和前端镜像构建成功 ✅

---

### 步骤 3: 配置 GitHub Secrets（2 分钟）

1. 打开 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions**

2. 添加必需 Secrets：

   **测试环境**:
   - `STAGING_SSH_PRIVATE_KEY` - SSH 私钥
   - `STAGING_HOST` - 服务器地址

   **生产环境**:
   - `PRODUCTION_SSH_PRIVATE_KEY` - SSH 私钥
   - `PRODUCTION_HOST` - 服务器地址

3. 生成 SSH 密钥（如果还没有）:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions" -f ~/.ssh/github_actions
   ```

---

### 步骤 4: 配置 GitHub Environments（1 分钟）

1. 打开 **Settings** → **Environments**

2. 创建 `staging` 环境（可选 URL）

3. 创建 `production` 环境：
   - 添加至少 1 个审批人
   - 设置部署分支为 `main`

---

### 步骤 5: 测试工作流

1. **测试镜像构建**:
   - 推送代码到 `main` 分支
   - 查看 **Actions** → `Docker Build and Push`
   - 验证构建成功 ✅

2. **测试测试环境部署**:
   - 等待构建成功后自动触发
   - 或手动触发：**Actions** → **Deploy to Staging** → **Run workflow**
   - 验证部署成功 ✅

3. **测试生产环境部署**:
   - **Actions** → **Deploy to Production** → **Run workflow**
   - 输入镜像标签（如 `v4.19.7`）
   - 输入确认（`DEPLOY`）
   - 等待审批（如果设置了审批人）
   - 验证部署成功 ✅

---

## 详细配置

- [完整配置指南](./CI_CD_SETUP_GUIDE.md)
- [配置清单](./GITHUB_CONFIG_CHECKLIST.md)
- [CI/CD 流程指南](./CI_CD_GUIDE.md)

---

## 故障排查

### 问题: 配置检查失败

**解决**: 查看详细错误信息，修复后重试

### 问题: Docker 镜像构建失败

**解决**: 
1. 检查 Dockerfile 语法
2. 验证依赖文件存在
3. 查看构建日志

### 问题: GitHub Actions 工作流失败

**解决**:
1. 查看工作流日志
2. 验证 GitHub Secrets 配置
3. 检查服务器连接

---

## 下一步

配置完成后，您可以：
- 自动构建和推送 Docker 镜像
- 自动部署到测试环境
- 手动部署到生产环境（需要审批）

---

**更新历史**:
- **v4.19.7** (2026-01-05): 创建快速开始指南

