# Metabase数据库连接问题排查指南

## 问题诊断结果

### ✅ PostgreSQL状态检查

**Docker中的PostgreSQL**：
- 当前Alembic版本：`20251126_132151` ✅（已是最新版本）
- 数据库连接：`postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp`
- 总表数：79张表

**问题发现**：
- ❌ **DSS架构新表在Docker PostgreSQL中不存在**
- ❌ 查询`fact_raw_data%`表：0张
- ❌ 查询`sales_targets_a`表：不存在（只有旧表`sales_targets`）
- ❌ 查询`entity_aliases`表：不存在

### ❌ Metabase状态检查

**Metabase显示的表**：
- 显示的是**旧架构表**（如`Fact Sales Orders`、`Dim Shop`等）
- 这些表在PostgreSQL中确实存在（旧表）
- **新DSS架构表未显示**（因为PostgreSQL中也不存在）

## 问题根本原因

**Alembic迁移版本已更新，但表未创建**。可能的原因：

1. **迁移脚本执行失败**：迁移版本更新了，但表创建失败
2. **迁移链分支问题**：存在5个head版本，迁移链混乱
3. **数据库连接问题**：Python脚本连接的数据库和Docker中的不是同一个

## 解决方案

### 方案1：手动执行迁移脚本（推荐）

由于迁移链存在多个head，需要手动指定目标版本：

```bash
# 1. 连接到Docker PostgreSQL
docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp

# 2. 检查当前版本
SELECT version_num FROM alembic_version;

# 3. 手动执行迁移脚本（如果表不存在）
# 需要运行 migrations/versions/20251126_132151_v4_6_0_dss_architecture_tables.py
```

### 方案2：修复迁移链后重新运行

1. **合并迁移链**：需要创建一个合并迁移，将所有head合并
2. **重新运行迁移**：`alembic upgrade 20251126_132151`

### 方案3：直接创建表（临时方案）

如果迁移脚本有问题，可以直接在PostgreSQL中执行SQL创建表：

```sql
-- 参考 migrations/versions/20251126_132151_v4_6_0_dss_architecture_tables.py
-- 手动执行CREATE TABLE语句
```

## 验证步骤

### 1. 检查表是否存在

```bash
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND (
    table_name LIKE 'fact_raw_data%' 
    OR table_name LIKE 'sales_targets_a%'
    OR table_name = 'entity_aliases'
)
ORDER BY table_name;
"
```

**期望结果**：应该看到26张新表

### 2. 检查Alembic版本

```bash
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "
SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1;
"
```

**期望结果**：`20251126_132151`

### 3. 如果表存在，同步Metabase Schema

1. 登录Metabase：http://localhost:3000
2. Admin → Databases → XIHONG_ERP
3. 点击 "Sync database schema now"
4. 等待同步完成

## 下一步行动

1. ✅ **已确认**：PostgreSQL中DSS架构新表不存在
2. ⏳ **待执行**：运行迁移脚本创建表
3. ⏳ **待验证**：确认表创建成功
4. ⏳ **待同步**：在Metabase中同步Schema

## 相关文档

- `docs/METABASE_SCHEMA_SYNC_TROUBLESHOOTING.md` - Schema同步问题排查
- `docs/METABASE_DSS_TABLES_SYNC_GUIDE.md` - 表同步指南
- `migrations/versions/20251126_132151_v4_6_0_dss_architecture_tables.py` - DSS架构迁移脚本

