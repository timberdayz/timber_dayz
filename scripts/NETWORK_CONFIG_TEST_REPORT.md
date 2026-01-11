# 网络配置测试报告

**日期**: 2026-01-11  
**目的**: 验证部署脚本中的 `docker-compose.deploy.yml` 网络配置  
**修复**: 在 `docker-compose.deploy.yml` 中显式添加 `networks` 配置

---

## 问题背景

在生产部署过程中，Alembic 迁移失败，错误信息：
```
psycopg2.OperationalError: could not translate host name "postgres" to address: Temporary failure in name resolution
```

**根本原因**：
- `docker-compose.deploy.yml` 中只定义了 `image`，没有定义 `networks`
- 使用 `docker-compose run --no-deps` 时，一次性容器无法连接到 Docker 网络
- 导致无法通过服务名 `postgres` 解析数据库主机

---

## 修复内容

### 1. 修复部署脚本

**文件**: `scripts/deploy_remote_production.sh`  
**位置**: 第 189-202 行

**修复前**：
```yaml
services:
  backend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_BACKEND}:${BACKEND_TAG}
  frontend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_FRONTEND}:${FRONTEND_TAG}
    ports: []
```

**修复后**：
```yaml
services:
  backend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_BACKEND}:${BACKEND_TAG}
    networks:
      - erp_network
  frontend:
    image: ${GHCR_REGISTRY}/${IMAGE_NAME_FRONTEND}:${FRONTEND_TAG}
    ports: []
    networks:
      - erp_network
```

### 2. 创建生产环境模拟测试脚本

**文件**: `scripts/test_production_deployment_network.sh`

**功能**：
- 模拟生产部署流程生成 `docker-compose.deploy.yml`
- 验证生成的 YAML 包含 `networks` 配置
- 验证 docker-compose 配置合并是否正确

**使用方式**：
```bash
bash scripts/test_production_deployment_network.sh
```

### 3. 增强现有测试脚本

#### 3.1 Bash 版本

**文件**: `scripts/test_deploy_script_locally.sh`

**新增验证**：
- 验证生成的 YAML 包含 `networks:` 配置
- 验证生成的 YAML 包含 `erp_network` 网络

#### 3.2 Python 版本

**文件**: `scripts/test_deploy_script_locally.py`

**新增验证**：
- 验证生成的 YAML 包含 `networks:` 配置
- 验证生成的 YAML 包含 `erp_network` 网络

---

## 测试结果

### 测试 1: Python 测试脚本

```bash
python scripts/test_deploy_script_locally.py
```

**结果**: ✅ **所有测试通过**

```
==================================================
[TEST 2] 验证 YAML 生成逻辑
--------------------------------------------------
[OK] Tag validation passed

Generated YAML content:
services:
  backend:
    image: ghcr.io/test/backend:v4.21.4
    networks:
      - erp_network
  frontend:
    image: ghcr.io/test/frontend:v4.21.4
    ports: []
    networks:
      - erp_network

[OK] YAML structure valid
[OK] YAML networks configuration valid
```

### 测试 2: 部署脚本网络配置验证

**验证点**：
- ✅ YAML 生成逻辑包含 `networks` 配置
- ✅ `docker-compose.deploy.yml` 生成正确的网络配置
- ✅ 所有测试脚本已更新，包含网络配置验证

---

## 为什么本地测试之前没有发现？

### 1. 测试脚本使用的 Compose 文件不同

**本地测试**：
```bash
# 使用开发环境的 compose 文件
docker-compose -f docker-compose.yml -f docker-compose.dev.yml \
  --profile dev-full run --rm --no-deps backend alembic current
```

**生产部署**：
```bash
# 使用生产环境的 compose 文件组合
docker-compose -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f docker-compose.deploy.yml \
  --profile production run --rm --no-deps backend alembic upgrade head
```

### 2. 开发环境配置已包含 networks

在 `docker-compose.dev.yml` 中，`backend` 服务已经显式定义了 `networks: - erp_network`，所以本地测试即使使用 `--no-deps`，网络配置也是正确的。

### 3. 测试脚本的覆盖范围不足

现有的 `test_deploy_script_locally.sh` 只测试了 YAML 生成逻辑，没有：
- 实际执行 `docker-compose run --no-deps`
- 验证容器能否连接到网络
- 验证服务名解析是否正常

---

## 改进建议

### ✅ 已完成的改进

1. ✅ **修复部署脚本**：在 `docker-compose.deploy.yml` 中显式添加 `networks` 配置
2. ✅ **创建生产环境模拟测试脚本**：`scripts/test_production_deployment_network.sh`
3. ✅ **增强现有测试脚本**：在 `test_deploy_script_locally.sh` 和 `test_deploy_script_locally.py` 中添加 networks 验证

### 📋 未来改进（可选）

1. **在 CI/CD 中添加部署前验证**：
   - 在 GitHub Actions 中添加一个验证步骤
   - 在实际部署前验证网络配置

2. **创建端到端测试**：
   - 在实际 Docker 环境中运行测试
   - 验证容器网络连接和服务名解析

3. **文档更新**：
   - 更新部署文档，说明网络配置的重要性
   - 添加故障排查指南

---

## 总结

✅ **修复完成**：部署脚本现在显式包含 `networks` 配置  
✅ **测试通过**：所有测试脚本已验证网络配置  
✅ **预防措施**：测试脚本现在会验证 networks 配置，防止未来回归

**下一步**：
1. 提交修复后的代码
2. 创建新的 tag（如 `v4.21.8`）触发自动部署
3. 验证部署是否成功，特别是 Alembic 迁移阶段

---

## 相关文件

- `scripts/deploy_remote_production.sh`：修复后的部署脚本
- `scripts/test_production_deployment_network.sh`：生产环境网络配置测试脚本（新增）
- `scripts/test_deploy_script_locally.sh`：增强后的部署脚本测试（Bash 版本）
- `scripts/test_deploy_script_locally.py`：增强后的部署脚本测试（Python 版本）
