# 数据库连接问题已解决

**解决时间**：2025-12-08  
**问题根源**：Python 后端连接到了本地 PostgreSQL 18，而不是 Docker PostgreSQL 15

---

## ✅ 问题已解决

### 问题描述

- **Metabase** 和 **pgAdmin** 显示 `b_class` schema 中只有 2 个表
- **Python 脚本** 显示 `b_class` schema 中有 26 个表
- 两者看到的数据库状态不一致

### 问题根源

**系统中运行了两个 PostgreSQL 实例**：

| 工具 | PostgreSQL 版本 | 数据库位置 |
|------|----------------|-----------|
| **Python 后端** | PostgreSQL 18.0 on x86_64-windows | 本地 Windows 安装 |
| **Docker 容器** | PostgreSQL 15-alpine | Docker 容器 |
| **pgAdmin** | 连接 Docker 容器 | Docker 容器 |
| **Metabase** | 连接 Docker 容器 | Docker 容器 |

Python 后端连接到了本地 Windows 安装的 PostgreSQL 18，而 pgAdmin 和 Metabase 连接到了 Docker 容器内的 PostgreSQL 15。

### 解决方案

**停止本地 PostgreSQL 服务**：

```powershell
# 需要管理员权限
net stop postgresql-x64-18
```

或者通过 Windows 服务管理器停止。

---

## ✅ 验证结果

停止本地 PostgreSQL 后，Python 后端现在连接到 Docker PostgreSQL：

```
[1] 数据库 URL: postgresql://erp_user:***@localhost:5432/xihong_erp

[4] 当前数据库信息:
    数据库: xihong_erp
    用户: erp_user
    版本: PostgreSQL 15.14 on x86_64-pc-linux-musl...

[5] 数据库中的 schema:
    schema 列表: ['a_class', 'b_class', 'c_class', 'core', 'finance', 'public']
```

### 数据库表统计

| Schema | 表数量 |
|--------|--------|
| a_class | 7 |
| b_class | 2 |
| c_class | 4 |
| core | 18 |
| public | 14 |
| **总计** | **45** |

---

## 📋 最终解决方案

### ✅ Docker PostgreSQL 使用独立端口 5433（2025-12-08）

为了彻底避免端口冲突，已将 Docker PostgreSQL 端口从 5432 改为 5433：

| 服务 | 端口 | 用途 |
|------|------|------|
| 本地 PostgreSQL 18 | 5432 | 可正常使用（不影响 ERP 系统） |
| Docker PostgreSQL 15 | 5433 | ERP 系统专用 |

**修改的文件**：
1. `env.example` - 默认 POSTGRES_PORT 改为 5433
2. `.env` - 添加 POSTGRES_PORT=5433 和 DATABASE_URL
3. `backend/utils/config.py` - 默认端口改为 5433

**优点**：
- ✅ 两个 PostgreSQL 可以同时运行，互不干扰
- ✅ 在任何环境都不会发生端口冲突
- ✅ 本地 PostgreSQL 可以用于其他项目

### 备选方案（已不使用）：禁用本地 PostgreSQL

在 `docker-compose.yml` 中修改 PostgreSQL 端口映射：

```yaml
postgres:
  ports:
    - "5433:5432"  # 使用 5433 避免冲突
```

然后修改 `.env`：

```env
DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:5433/xihong_erp
```

---

## 🔍 诊断脚本

如果将来遇到类似问题，运行以下脚本诊断：

```bash
python scripts/debug_db_connection.py
```

这会显示：
- 数据库 URL
- 直接 SQL 查询结果
- SQLAlchemy Inspector 查询结果
- PostgreSQL 版本（关键信息！）
- 数据库中的 schema 列表

如果看到 "PostgreSQL 18.0 on x86_64-windows"，说明连接到了本地 PostgreSQL。
如果看到 "PostgreSQL 15.x on x86_64-pc-linux-musl"，说明连接到了 Docker PostgreSQL。

---

**创建时间**：2025-12-08  
**状态**：✅ 问题已解决

