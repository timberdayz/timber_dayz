# 数据库架构提案 - 避免双数据库问题

## 文档版本
- **版本**: 1.0
- **日期**: 2025-12-08
- **状态**: 已实施

## 背景

### 问题描述

2025-12-08 发现系统存在严重的数据分散问题：
- **本地 PostgreSQL 18**：包含 26 个业务表和 102 个公共表
- **Docker PostgreSQL 15**：只有 2 个基础表

导致 Metabase、pgAdmin 和 Python 后端看到的数据不一致。

### 根本原因

1. **端口冲突**：本地 PostgreSQL 占用 5432 端口，Docker PostgreSQL 无法映射到该端口
2. **连接配置不一致**：Python 后端连接到本地 PostgreSQL，而 Metabase/pgAdmin 连接到 Docker PostgreSQL
3. **Windows 端口保留**：5433-5832 端口范围被 Windows 系统保留，无法使用

## 解决方案

### 1. 统一使用 Docker PostgreSQL

所有组件必须连接到同一个 Docker PostgreSQL 实例：

```
┌─────────────────────────────────────────────────────────────┐
│                     所有组件统一连接                          │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Python 后端 │  │  Metabase   │  │   pgAdmin   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         ▼                ▼                ▼                 │
│  localhost:15432   host.docker.internal:15432   postgres:5432
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          ▼                                  │
│              ┌─────────────────────┐                        │
│              │  Docker PostgreSQL  │                        │
│              │     (端口 15432)     │                        │
│              └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### 2. 使用非保留端口

选择 **15432** 作为 Docker PostgreSQL 的外部端口，避开 Windows 保留端口范围。

```yaml
# docker-compose.yml
postgres:
  ports:
    - "${POSTGRES_PORT:-15432}:5432"
```

### 3. 禁用本地 PostgreSQL

永久禁用本地 PostgreSQL 服务，防止端口冲突：

```powershell
# 以管理员身份运行
Set-Service -Name "postgresql-x64-18" -StartupType Disabled
Stop-Service -Name "postgresql-x64-18" -Force
```

## 配置规范

### 环境变量配置 (.env)

```env
# Docker PostgreSQL 配置
POSTGRES_PORT=15432
DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp

# Docker 内部配置（容器间通信）
POSTGRES_HOST=postgres
# 注意：容器内部仍使用 5432 端口
```

### 连接配置对照表

| 组件 | 主机 | 端口 | 说明 |
|------|------|------|------|
| **Python 后端** | `localhost` | `15432` | 从 Windows 访问 Docker |
| **Metabase** | `host.docker.internal` | `15432` | 从 Docker 容器访问 Windows 主机 |
| **pgAdmin** | `postgres` | `5432` | Docker 容器内部通信 |
| **Docker 内部服务** | `postgres` | `5432` | 容器内部端口不变 |

### 代码配置 (backend/utils/config.py)

```python
# 默认端口必须是 15432
POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "15432"))

# 默认 DATABASE_URL 必须使用 15432
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
)
```

## 预防措施

### 1. 启动前检查清单

每次启动系统前，执行以下检查：

```powershell
# 1. 检查本地 PostgreSQL 是否已禁用
Get-Service -Name "postgresql*" | Select-Object Name, Status, StartType
# 期望：Status=Stopped, StartType=Disabled

# 2. 检查 Docker PostgreSQL 端口
docker ps --format "table {{.Names}}\t{{.Ports}}" | findstr postgres
# 期望：0.0.0.0:15432->5432/tcp

# 3. 测试连接
python -c "from sqlalchemy import create_engine, text; e = create_engine('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp'); print(e.connect().execute(text('SELECT version()')).fetchone()[0])"
# 期望：PostgreSQL 15.x
```

### 2. CI/CD 检查

在 CI/CD 流水线中添加以下检查：

```yaml
# .github/workflows/check-database.yml
- name: Verify database configuration
  run: |
    # 检查端口配置
    grep -q "POSTGRES_PORT=15432" .env || exit 1
    grep -q "localhost:15432" backend/utils/config.py || exit 1
```

### 3. 文档维护

- 所有数据库连接配置变更必须更新此文档
- 新开发人员必须阅读此文档

## Schema 架构说明

项目使用数据分类架构，**不是多余的 schema**：

| Schema | 用途 | 说明 |
|--------|------|------|
| `a_class` | A类配置数据 | 用户配置、系统参数 |
| `b_class` | B类业务数据 | 订单、产品、库存等事实表 |
| `c_class` | C类计算数据 | 统计指标、计算结果 |
| `core` | 核心系统表 | 用户、权限、审计等 |
| `public` | 公共表 | 字段映射、文件目录等 |

## 故障排查指南

### 问题1：Metabase 显示的表与数据库不一致

**原因**：连接到了不同的数据库实例

**解决**：
1. 检查 Metabase 数据库连接配置
2. 确保使用 `host.docker.internal:15432`
3. 点击 "Sync database schema now" 重新同步

### 问题2：Python 后端连接失败

**原因**：端口配置错误或本地 PostgreSQL 占用端口

**解决**：
1. 检查 `.env` 中的 `DATABASE_URL`
2. 确保本地 PostgreSQL 已禁用
3. 确保 Docker PostgreSQL 正在运行

### 问题3：.env 文件编码错误

**错误**：`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xbf`

**解决**：
```powershell
# 重新编码为 UTF-8
$content = Get-Content .env -Raw -Encoding Default
Set-Content .env -Value $content -Encoding UTF8
```

## 云端部署说明

部署到云端服务器时：

1. **使用 Docker Compose**：所有服务容器化，无需本地 PostgreSQL
2. **端口配置**：可以根据云服务器情况调整 `POSTGRES_PORT`
3. **环境变量**：通过云平台的环境变量管理配置
4. **数据持久化**：使用云存储卷或托管数据库服务

```yaml
# 云端 docker-compose.yml 示例
services:
  postgres:
    image: postgres:15-alpine
    ports:
      - "${POSTGRES_PORT:-5432}:5432"  # 云端可以使用标准端口
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

## 变更历史

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2025-12-08 | 1.0 | 初始版本，解决双数据库问题 |

