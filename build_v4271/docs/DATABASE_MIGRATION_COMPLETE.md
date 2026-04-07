# 数据库迁移完成报告

## 日期
2025-12-08

## 迁移概述

成功将所有数据从本地 PostgreSQL 18 迁移到 Docker PostgreSQL 15，实现了数据库的完全容器化。

## 迁移前状态

| 数据库 | 版本 | 端口 | b_class 表数量 | public 表数量 |
|--------|------|------|---------------|--------------|
| 本地 PostgreSQL | 18.0 | 5432 | **26** | 102 |
| Docker PostgreSQL | 15.14 | 15432 | 2 | 14 |

**问题**：Python 后端连接到本地 PostgreSQL，而 Metabase/pgAdmin 连接到 Docker PostgreSQL，导致数据不一致。

## 迁移后状态

| 数据库 | 版本 | 端口 | b_class 表数量 | public 表数量 |
|--------|------|------|---------------|--------------|
| Docker PostgreSQL | 15.14 | 15432 | **28** | 106 |
| 本地 PostgreSQL | 18.0 (已禁用) | 5432 | - | - |

**解决**：所有组件统一连接到 Docker PostgreSQL 15。

## 执行步骤

1. ✅ 从本地 PostgreSQL 导出数据（SQL 格式，72.63MB）
2. ✅ 将数据导入到 Docker PostgreSQL
3. ✅ 验证数据迁移完整性（核心表数据已迁移）
4. ✅ 更新项目配置（端口改为 15432）
5. ✅ 永久禁用本地 PostgreSQL 服务
6. ✅ 更新文档

## 端口配置

### 为什么使用端口 15432？

Windows 系统保留了端口范围 5433-5832，无法使用这些端口。选择 15432 作为 Docker PostgreSQL 的外部端口。

### 当前端口配置

| 组件 | 连接方式 |
|------|---------|
| **Python 后端** | `localhost:15432` |
| **Docker 容器内部** | `postgres:5432` |
| **Metabase (Docker内)** | `host.docker.internal:15432` 或 `postgres:5432` |
| **pgAdmin (Docker内)** | `postgres:5432` 或 `host.docker.internal:15432` |

## 修改的文件

1. `.env` - POSTGRES_PORT=15432, DATABASE_URL 更新
2. `env.example` - 端口配置示例更新
3. `backend/utils/config.py` - 默认端口改为 15432
4. `docker/postgres/init-tables.py` - 默认连接 URL 更新

## Metabase/pgAdmin 连接配置

### Metabase

| 字段 | 值 |
|------|-----|
| 主机 | `host.docker.internal` |
| 端口 | `15432` |
| 数据库 | `xihong_erp` |
| 用户名 | `erp_user` |
| 密码 | `erp_pass_2025` |

### pgAdmin（推荐方式）

| 字段 | 值 |
|------|-----|
| 主机 | `postgres` |
| 端口 | `5432` |
| 用户名 | `erp_user` |
| 密码 | `erp_pass_2025` |

## 本地 PostgreSQL 状态

- **服务名**：postgresql-x64-18
- **状态**：Stopped（已停止）
- **启动类型**：Disabled（已禁用）

如果将来需要使用本地 PostgreSQL，可以通过以下命令启用：

```powershell
# 启用服务（需要管理员权限）
Set-Service -Name "postgresql-x64-18" -StartupType Manual
Start-Service -Name "postgresql-x64-18"
```

## 云端部署说明

本次迁移确保了系统完全容器化，适合云端部署：

1. **无本地依赖**：所有数据库操作通过 Docker 容器
2. **端口可配置**：通过环境变量 `POSTGRES_PORT` 配置
3. **Docker Compose 支持**：一键部署所有服务
4. **数据持久化**：使用 Docker Volume 存储数据

## 验证命令

```bash
# 检查 Docker PostgreSQL 状态
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr postgres

# 验证表数量
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT table_schema, COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema') GROUP BY table_schema;"

# 测试 Python 后端连接
python -c "from sqlalchemy import create_engine, text; e = create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp'); print(e.connect().execute(text('SELECT version()')).fetchone()[0])"
```

