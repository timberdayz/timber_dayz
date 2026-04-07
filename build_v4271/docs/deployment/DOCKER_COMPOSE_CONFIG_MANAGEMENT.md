# Docker Compose 配置管理方案

## 📋 概述

本文档定义了西虹ERP系统的Docker Compose配置管理规范和最佳实践，旨在解决配置不一致、重复定义和维护困难等问题。

## 🎯 核心原则

### 1. **单源真实（SSOT - Single Source of Truth）**

**问题**：多个Docker Compose文件重复定义相同配置，导致不一致。

**解决方案**：
- **基础配置**：`docker-compose.yml` 是所有服务的基础定义（SSOT）
- **环境覆盖**：`docker-compose.*.yml` 只覆盖环境差异，不重复定义
- **共享数据卷**：所有环境使用相同的数据卷名称，确保数据一致性

### 2. **配置继承和覆盖**

**Docker Compose 文件层次结构**：

```
docker-compose.yml              # 基础配置（SSOT）
├── docker-compose.dev.yml      # 开发环境覆盖（端口映射、调试配置）
├── docker-compose.prod.yml     # 生产环境覆盖（资源限制、安全配置）
├── docker-compose.cloud.yml    # 云端环境覆盖（资源优化）
└── docker-compose.collection.yml # 采集服务独立配置
```

**使用方式**：

```bash
# 开发环境（基础 + 开发覆盖）
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 生产环境（基础 + 生产覆盖）
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 云端环境（基础 + 生产 + 云端覆盖）
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d
```

### 3. **关键配置统一管理**

以下配置必须在所有环境中保持一致：

| 配置项 | 位置 | 说明 | 示例 |
|--------|------|------|------|
| `PGDATA` | postgres environment | PostgreSQL数据目录路径 | `/var/lib/postgresql/data/pgdata` |
| 数据卷名称 | volumes | 数据持久化卷名 | `postgres_data`, `redis_data` |
| 网络名称 | networks | 容器网络名称 | `erp_network` |
| 服务名称 | services | 容器服务名 | `postgres`, `redis`, `backend` |
| 容器名称 | container_name | Docker容器名称 | `xihong_erp_postgres` |

## 🔧 配置规范

### PostgreSQL 配置

**基础配置（docker-compose.yml）**：

```yaml
services:
  postgres:
    image: postgres:15-alpine
    container_name: xihong_erp_postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-erp_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-erp_pass_2025}
      POSTGRES_DB: ${POSTGRES_DB:-xihong_erp}
      PGDATA: /var/lib/postgresql/data/pgdata  # ⭐ 必须在所有环境中保持一致
    volumes:
      - postgres_data:/var/lib/postgresql/data  # ⭐ 数据卷名称必须一致
    networks:
      - erp_network
```

**环境覆盖示例（docker-compose.dev.yml）**：

```yaml
services:
  postgres:
    # 只覆盖开发环境特有的配置（如端口映射）
    ports:
      - "15432:5432"
    # ⚠️ 不要重复定义 environment、volumes、networks 等基础配置
```

### Redis 配置

**基础配置（docker-compose.yml）**：

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: xihong_erp_redis
    volumes:
      - redis_data:/data  # ⭐ 数据卷名称必须一致
    networks:
      - erp_network
```

### 后端服务配置

**基础配置（docker-compose.yml）**：

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: xihong_erp_backend
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-erp_user}:${POSTGRES_PASSWORD:-erp_pass_2025}@postgres:5432/${POSTGRES_DB:-xihong_erp}
      # ... 其他环境变量
    networks:
      - erp_network
    depends_on:
      postgres:
        condition: service_healthy
```

## ⚠️ 常见问题和解决方案

### 问题1：PGDATA 配置不一致

**症状**：
```
initdb: error: directory "/var/lib/postgresql/data" exists but is not empty
```

**原因**：
- `docker-compose.yml` 中定义了 `PGDATA: /var/lib/postgresql/data/pgdata`
- `docker-compose.prod.yml` 中缺少 `PGDATA` 配置
- 数据卷中的数据在 `pgdata` 子目录，但PostgreSQL期望在根目录

**解决方案**：
在所有包含 PostgreSQL 服务定义的配置文件中，确保 `PGDATA` 配置一致：

```yaml
environment:
  PGDATA: /var/lib/postgresql/data/pgdata  # ⭐ 必须添加
```

**检查清单**：
- [ ] `docker-compose.yml` 中有 `PGDATA` 配置
- [ ] `docker-compose.prod.yml` 中有 `PGDATA` 配置
- [ ] 所有独立的 Docker Compose 文件（如果有）都有 `PGDATA` 配置

### 问题2：数据卷名称不一致

**症状**：
- 不同环境使用不同的数据卷名称
- 切换环境时数据丢失

**解决方案**：
在所有环境中使用相同的数据卷名称：

```yaml
volumes:
  postgres_data:  # ⭐ 名称必须一致
  redis_data:     # ⭐ 名称必须一致
```

### 问题3：环境变量重复定义

**症状**：
- 环境变量在多个文件中重复定义
- 修改时容易遗漏某些环境

**解决方案**：
- 使用 `.env` 文件统一管理环境变量
- Docker Compose 文件中使用 `${VAR_NAME:-default_value}` 语法
- 只在环境覆盖文件中覆盖特定变量，不重复定义所有变量

## 📝 配置检查清单

### 新增服务时的检查清单

- [ ] 在 `docker-compose.yml` 中定义完整的基础配置
- [ ] 确保数据卷名称唯一且有意义
- [ ] 确保网络名称一致（`erp_network`）
- [ ] 确保容器名称唯一且有意义
- [ ] 在环境覆盖文件中只覆盖环境差异
- [ ] 测试所有环境的配置一致性

### 修改配置时的检查清单

- [ ] 检查是否影响其他环境
- [ ] 检查数据卷配置是否一致
- [ ] 检查网络配置是否一致
- [ ] 检查关键环境变量是否一致
- [ ] 更新相关文档

### 部署前的检查清单

- [ ] 运行配置验证脚本（如果存在）
- [ ] 检查所有 Docker Compose 文件语法正确
- [ ] 检查环境变量是否完整
- [ ] 检查数据卷名称是否一致
- [ ] 检查网络配置是否一致

## 🛠️ 配置验证工具

### 手动验证命令

```bash
# 验证 Docker Compose 文件语法
docker-compose -f docker-compose.yml config

# 验证生产环境配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml config

# 检查数据卷名称
docker-compose -f docker-compose.yml config | grep -A 5 "volumes:"

# 检查网络名称
docker-compose -f docker-compose.yml config | grep -A 3 "networks:"
```

### 自动化验证脚本（建议）

创建 `scripts/verify_docker_compose_config.py`：

```python
"""
验证 Docker Compose 配置一致性

检查项：
1. PGDATA 配置在所有文件中一致
2. 数据卷名称一致
3. 网络名称一致
4. 容器名称唯一
"""
import yaml
from pathlib import Path

def verify_pgdata_consistency():
    """验证 PGDATA 配置一致性"""
    # 实现逻辑
    pass

def verify_volume_consistency():
    """验证数据卷名称一致性"""
    # 实现逻辑
    pass

# ... 其他验证函数
```

## 📚 最佳实践

### 1. **环境变量管理**

- 使用 `.env` 文件管理环境变量
- 在 Docker Compose 文件中使用 `${VAR:-default}` 语法
- 敏感信息使用 Docker Secrets（生产环境）

### 2. **配置文档化**

- 所有关键配置必须有注释说明
- 环境差异必须有明确说明
- 数据迁移和升级步骤必须有文档

### 3. **版本控制**

- 所有 Docker Compose 文件必须版本控制
- 配置变更必须有明确的提交信息
- 重大配置变更需要更新文档

### 4. **测试和验证**

- 每次配置变更后测试所有环境
- 使用配置验证脚本自动化检查
- 在 CI/CD 中添加配置验证步骤

## 🔄 配置迁移指南

### 从旧配置迁移到新配置

如果遇到配置不一致问题（如 PGDATA），按以下步骤迁移：

1. **备份数据**：
   ```bash
   docker-compose -f docker-compose.yml down
   docker volume ls | grep postgres_data
   docker run --rm -v xihong_erp_postgres_data:/data -v $(pwd)/backups:/backup alpine tar czf /backup/postgres_data_backup.tar.gz /data
   ```

2. **修复配置**：
   - 在所有相关文件中添加缺失的配置项
   - 确保配置值一致

3. **验证配置**：
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml config
   ```

4. **重新启动**：
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

5. **验证数据**：
   ```bash
   docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT COUNT(*) FROM dim_users;"
   ```

## 📖 相关文档

- [环境变量管理指南](ENVIRONMENT_VARIABLES_REFERENCE.md)
- [Docker部署指南](DEPLOYMENT_GUIDE.md)
- [数据库迁移指南](../guides/DATABASE_MIGRATION.md)

## ✅ 总结

统一配置管理的核心是：

1. **SSOT原则**：`docker-compose.yml` 作为单源真实
2. **继承覆盖**：环境文件只覆盖差异，不重复定义
3. **一致性检查**：关键配置（PGDATA、数据卷、网络）必须一致
4. **文档和工具**：配置变更需要文档化和自动化验证

遵循这些原则，可以避免配置不一致导致的问题，提高系统的可维护性和可靠性。
