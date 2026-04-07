# Docker 镜像清理指南

## 概述

在生产部署过程中，Docker 镜像会不断累积，占用大量服务器磁盘空间。本指南说明自动镜像清理功能的配置和使用。

## 功能说明

### 自动清理机制

部署脚本 `scripts/deploy_remote_production.sh` 在每次部署成功后会自动清理旧镜像：

1. **保留最近 N 个版本**（默认 5 个）
2. **只清理版本号格式的镜像**（如 `v4.20.5`），保护 `latest`、`sha-*` 等特殊标签
3. **清理 dangling 镜像**（未标记的中间层）
4. **安全删除**：如果镜像正在使用，会跳过删除并记录警告

### 资源占用估算

- **单个镜像大小**：Backend ~500MB-1GB，Frontend ~200MB-500MB
- **10 个版本占用**：约 7GB-15GB
- **20 个版本占用**：约 14GB-30GB

## 配置方法

### 方法 1：通过 GitHub Secrets（推荐）

在 GitHub 仓库的 Settings > Secrets and variables > Actions 中添加：

- **Secret 名称**：`KEEP_IMAGES_COUNT`
- **值**：保留的镜像版本数量（例如：`5`、`10`）
- **默认值**：如果不设置，默认保留 5 个版本

### 方法 2：在服务器上设置环境变量

在服务器上执行部署前设置：

```bash
export KEEP_IMAGES_COUNT=10  # 保留 10 个版本
bash ./deploy_remote_production.sh
```

## 清理逻辑

### 清理规则

1. **只清理版本号格式的镜像**
   - ✅ 清理：`v4.20.5`、`v4.20.4`、`v4.20.3`
   - ❌ 保留：`latest`、`sha-abc123`、`4.20.5`（不带 v 前缀）

2. **按版本号排序**
   - 使用 `sort -V`（版本号排序）
   - 保留最新的 N 个版本
   - 删除更旧的版本

3. **独立清理 Backend 和 Frontend**
   - Backend 和 Frontend 镜像分别计算和清理
   - 互不影响

### 清理示例

假设服务器上有以下 Backend 镜像：

```
ghcr.io/user/repo/backend:v4.20.5  (最新)
ghcr.io/user/repo/backend:v4.20.4
ghcr.io/user/repo/backend:v4.20.3
ghcr.io/user/repo/backend:v4.20.2
ghcr.io/user/repo/backend:v4.20.1
ghcr.io/user/repo/backend:v4.20.0  (最旧)
ghcr.io/user/repo/backend:latest   (特殊标签，保留)
```

如果 `KEEP_IMAGES_COUNT=5`，则：
- ✅ 保留：`v4.20.5`、`v4.20.4`、`v4.20.3`、`v4.20.2`、`v4.20.1`、`latest`
- ❌ 删除：`v4.20.0`

## 手动清理

### 查看当前镜像

```bash
# 查看所有镜像
docker images | grep "ghcr.io/user/repo"

# 查看镜像占用空间
docker system df
```

### 手动删除旧镜像

```bash
# 删除特定版本的镜像
docker rmi ghcr.io/user/repo/backend:v4.20.0

# 删除所有未使用的镜像（谨慎使用）
docker image prune -a
```

### 查看清理日志

部署脚本会输出详细的清理日志：

```
[INFO] Cleaning up old images (keeping latest 5 versions)...
[INFO] Found 6 backend version(s)
[INFO] Removing 1 old backend image(s)...
  [INFO] Removing: ghcr.io/user/repo/backend:v4.20.0
[INFO] Found 5 frontend version(s)
[INFO] Frontend images count (5) <= keep count (5), skipping cleanup
[INFO] Cleaning up dangling images...
[OK] Dangling images cleaned (freed: 1.2 GB)
[OK] Image cleanup completed
```

## 监控和告警

### 查看磁盘使用情况

```bash
# 查看 Docker 总体使用情况
docker system df

# 查看各镜像大小（按大小排序）
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | \
  sort -k3 -h -r | head -20
```

### 设置磁盘告警

建议设置监控告警：
- **告警阈值**：磁盘使用率 > 80%
- **清理阈值**：磁盘使用率 > 90%

## 最佳实践

### 1. 保留版本数建议

- **生产环境**：保留 5-10 个版本（便于回滚）
- **测试环境**：保留 3-5 个版本（节省空间）

### 2. 定期检查

- 每周检查一次磁盘使用情况
- 每月检查一次镜像占用情况

### 3. 紧急清理

如果磁盘空间不足，可以临时降低保留数量：

```bash
# 临时保留 3 个版本
export KEEP_IMAGES_COUNT=3
bash ./deploy_remote_production.sh
```

## 故障排查

### 镜像删除失败

如果出现 `[WARN] Failed to remove ${img} (may be in use)`：

1. **检查是否有容器使用该镜像**
   ```bash
   docker ps -a | grep "v4.20.0"
   ```

2. **强制删除（谨慎使用）**
   ```bash
   docker rmi -f ghcr.io/user/repo/backend:v4.20.0
   ```

### 清理功能未执行

1. **检查部署日志**：确认部署是否成功
2. **检查环境变量**：确认 `KEEP_IMAGES_COUNT` 是否设置
3. **手动执行清理**：在服务器上手动运行 `cleanup_old_images` 函数

## 相关文档

- [CI/CD 部署指南](docs/CI_CD_DEPLOYMENT_GUIDE.md)
- [Docker 部署文档](docs/deployment/DOCKER_DEPLOYMENT.md)
