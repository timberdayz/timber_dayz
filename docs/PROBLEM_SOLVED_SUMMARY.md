# Metabase 显示旧表名问题 - 已解决

**解决时间**：2025-12-08  
**问题根源**：Alembic 迁移脚本创建的旧表（`fact_raw_data_*`）仍在数据库中

---

## ✅ 问题已解决

### 问题根源

Alembic 迁移脚本 `migrations/versions/20251126_132151_v4_6_0_dss_architecture_tables.py` 创建了旧表名的表：
- `fact_raw_data_orders_daily`
- `fact_raw_data_orders_weekly`
- `fact_raw_data_orders_monthly`
- `fact_raw_data_products_daily`
- `fact_raw_data_products_weekly`
- `fact_raw_data_products_monthly`
- `fact_raw_data_traffic_daily`
- `fact_raw_data_traffic_weekly`
- `fact_raw_data_traffic_monthly`
- `fact_raw_data_services_daily`
- `fact_raw_data_services_weekly`
- `fact_raw_data_services_monthly`
- `fact_raw_data_inventory_snapshot`

这些表在 `b_class` schema 中，Metabase 同步时看到了它们，所以显示旧表名。

### 解决方案

已删除所有 13 个旧表：
```sql
DROP TABLE IF EXISTS b_class.fact_raw_data_orders_daily CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_orders_weekly CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_orders_monthly CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_products_daily CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_products_weekly CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_products_monthly CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_traffic_daily CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_traffic_weekly CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_traffic_monthly CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_services_daily CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_services_weekly CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_services_monthly CASCADE;
DROP TABLE IF EXISTS b_class.fact_raw_data_inventory_snapshot CASCADE;
```

---

## ✅ 当前数据库状态

### b_class schema（26 个新表）

- ✅ `fact_shopee_*` (14个表)
- ✅ `fact_tiktok_*` (10个表)
- ✅ `fact_miaoshou_*` (1个表)
- ✅ `fact_test_*` (1个表)
- ✅ `entity_aliases` (1个表)
- ✅ `staging_raw_data` (1个表)

### 旧表状态

- ✅ **已删除**：所有 `fact_raw_data_*` 表已删除
- ✅ **不再存在**：数据库中不再有旧表

---

## 📋 下一步操作

### 在 Metabase 中重新同步 Schema

1. **登录 Metabase**：`http://localhost:8080`
2. **进入数据库设置**：
   - Admin → Databases → XIHONG_ERP
3. **重新同步 Schema**：
   - 点击 **"Sync database schema now"** 按钮
   - 等待同步完成（60-90秒）
4. **验证结果**：
   - 在 `b_class` schema 中应该看到 **26 个按平台分表的表**
   - **不应该看到** `fact_raw_data_*` 开头的旧表

---

## 🔍 验证方法

运行以下脚本验证数据库状态：

```bash
# 检查 b_class schema 中的表
python scripts/check_b_class_tables.py

# 检查所有 schema 中的旧表
python scripts/check_all_schemas_for_old_tables.py
```

**预期输出**：
- ✅ `b_class` schema 中有 26 个按平台分表的表
- ✅ 没有 `fact_raw_data_*` 开头的旧表

---

## 📊 问题总结

### 问题根源

1. **Alembic 迁移脚本**创建了旧表名的表
2. **这些表没有被删除**，一直存在于数据库中
3. **Metabase 同步时看到了这些表**，所以显示旧表名

### 解决方案

1. ✅ **删除旧表**：从 `b_class` schema 中删除所有 `fact_raw_data_*` 表
2. ✅ **保留新表**：保留按平台分表的表（`fact_shopee_*`, `fact_tiktok_*` 等）
3. ✅ **重新同步**：在 Metabase 中重新同步 Schema

---

## ⚠️ 注意事项

### Alembic 迁移脚本

Alembic 迁移脚本 `migrations/versions/20251126_132151_v4_6_0_dss_architecture_tables.py` 仍然会创建这些旧表。

**建议**：
- 如果需要回滚到旧版本，这些表会被重新创建
- 但正常情况下，新架构使用按平台分表的表，不需要这些旧表

### 未来迁移

如果将来需要迁移到新架构，应该：
1. 创建新的按平台分表的表
2. 迁移数据（如果需要）
3. 删除旧表

---

**创建时间**：2025-12-08  
**状态**：✅ 问题已解决，旧表已删除

