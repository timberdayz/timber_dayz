# Metabase迁移状态报告

## 🔍 问题诊断

### 发现的问题

**存在两个PostgreSQL实例**：
1. **本地PostgreSQL**（Windows主机）
   - 版本：`20251126_132151` ✅（已迁移）
   - 表：26张DSS架构表已创建 ✅
   - Python脚本连接：`localhost:5432` → 连接到本地PostgreSQL

2. **Docker PostgreSQL**（容器内）
   - 版本：`ec54aca4c8a2` ❌（未迁移）
   - 表：0张DSS架构表 ❌
   - Metabase连接：通过Docker网络 → 连接到Docker PostgreSQL

### 根本原因

- Python迁移脚本通过`localhost:5432`连接到了**本地PostgreSQL**，而非Docker PostgreSQL
- Metabase通过Docker网络连接到**Docker PostgreSQL**，所以看不到新表
- 两个PostgreSQL实例独立运行，需要分别迁移

## ✅ 已完成的迁移

### 本地PostgreSQL
- ✅ 版本已升级到 `20251126_132151`
- ✅ 所有26张DSS架构表已创建
- ✅ 验证通过

### Docker PostgreSQL
- ❌ 版本仍为 `ec54aca4c8a2`（旧版本）
- ❌ 表未创建
- ⏳ **需要迁移**

## 🔧 解决方案

### 方案1：在Docker容器内执行迁移（推荐）

由于Docker容器内没有Python环境，需要：

1. **安装Python到Docker容器**（临时方案）
   ```bash
   docker exec -it xihong_erp_postgres sh
   apk add python3 py3-pip
   pip3 install alembic sqlalchemy psycopg2-binary
   ```

2. **复制迁移脚本到容器**
   ```bash
   docker cp migrations/versions/20251126_132151_v4_6_0_dss_architecture_tables.py xihong_erp_postgres:/tmp/
   ```

3. **在容器内执行迁移**
   ```bash
   docker exec -it xihong_erp_postgres python3 /tmp/migration.py
   ```

### 方案2：使用docker exec执行psql（需要SQL脚本）

将Python迁移脚本转换为SQL，然后：
```bash
docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp < migration.sql
```

### 方案3：停止本地PostgreSQL（最简单）

1. **停止本地PostgreSQL服务**
   ```powershell
   # Windows
   Stop-Service postgresql-x64-15  # 根据实际服务名调整
   ```

2. **重新运行迁移脚本**
   ```bash
   python temp/development/run_migration_docker_postgres.py
   ```

3. **验证迁移**
   ```bash
   docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT version_num FROM alembic_version;"
   ```

## 📋 推荐操作步骤

### 步骤1：停止本地PostgreSQL（如果不需要）

```powershell
# 检查PostgreSQL服务
Get-Service | Where-Object {$_.Name -like "*postgres*"}

# 停止服务（根据实际服务名）
Stop-Service postgresql-x64-15
```

### 步骤2：重新运行迁移

```bash
python temp/development/run_migration_docker_postgres.py
```

### 步骤3：验证Docker PostgreSQL迁移

```bash
# 检查版本
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT version_num FROM alembic_version;"

# 检查表数量
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_name LIKE 'fact_raw_data%';"
```

### 步骤4：在Metabase中同步Schema

1. 登录Metabase：http://localhost:3000
2. Admin → Databases → XIHONG_ERP
3. 点击 "Sync database schema now"
4. 验证新表出现

## 📊 当前状态

| 项目 | 本地PostgreSQL | Docker PostgreSQL | Metabase |
|------|---------------|-------------------|----------|
| Alembic版本 | ✅ 20251126_132151 | ❌ ec54aca4c8a2 | - |
| B类表数量 | ✅ 13张 | ❌ 0张 | ❌ 未同步 |
| A类表数量 | ✅ 7张 | ❌ 0张 | ❌ 未同步 |
| C类表数量 | ✅ 4张 | ❌ 0张 | ❌ 未同步 |
| 其他表 | ✅ 2张 | ❌ 0张 | ❌ 未同步 |
| **总计** | ✅ **26张** | ❌ **0张** | ❌ **未同步** |

## ⚠️ 注意事项

1. **本地PostgreSQL**: 如果正在使用，不要停止服务
2. **Docker PostgreSQL**: 这是Metabase连接的数据库，必须迁移
3. **端口冲突**: 两个PostgreSQL都在5432端口，但通过不同方式访问
4. **迁移顺序**: 先迁移Docker PostgreSQL，再在Metabase中同步Schema

## 📚 相关文档

- `docs/METABASE_SCHEMA_SYNC_TROUBLESHOOTING.md` - Schema同步问题排查
- `docs/METABASE_DSS_TABLES_SYNC_GUIDE.md` - 表同步指南
- `temp/development/run_migration_docker_postgres.py` - 迁移脚本

---

**最后更新**: 2025-11-26 16:54  
**状态**: ⏳ Docker PostgreSQL待迁移

