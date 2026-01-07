# 数据同步Schema问题诊断和解决方案

**问题日期**: 2025-12-02  
**问题**: 数据已入库但Metabase中看不到

---

## 🔍 问题诊断

### 问题根源

**表位置不匹配**：
- ✅ **实际位置**: 表在 `public` schema 中（`public.fact_raw_data_inventory_snapshot`）
- ❌ **Metabase期望**: 表应该在 `b_class` schema 中（`b_class.fact_raw_data_inventory_snapshot`）

**验证结果**：
```sql
-- 实际表位置
SELECT table_schema, table_name 
FROM information_schema.tables 
WHERE table_name = 'fact_raw_data_inventory_snapshot';
-- 结果: schema=public, table=fact_raw_data_inventory_snapshot

-- 数据确实存在
SELECT COUNT(*) FROM public.fact_raw_data_inventory_snapshot;
-- 结果: 1218 行

-- Metabase期望的位置
SELECT COUNT(*) FROM b_class.fact_raw_data_inventory_snapshot;
-- 结果: 表不存在
```

---

## ✅ 解决方案

### 方案1：在Metabase中查看public schema的表（快速解决）

**步骤**：
1. 登录 Metabase：`http://localhost:8080`
2. 进入：`Admin → Databases → xihong_erp`
3. 点击数据库右侧的 **"Sync database schema now"**
4. 在表列表中查找 `public.fact_raw_data_inventory_snapshot`
5. 如果看不到，检查数据库连接的schema设置

**Metabase数据库连接配置**：
- 确保 `search_path` 包含 `public` schema
- 或者在Metabase中手动添加 `public` schema到可见列表

### 方案2：将表移动到b_class schema（长期方案）

**需要数据库迁移**：
1. 创建 `b_class` schema（如果不存在）
2. 将表从 `public` 移动到 `b_class`
3. 更新代码中的表引用

**迁移SQL**：
```sql
-- 1. 创建b_class schema（如果不存在）
CREATE SCHEMA IF NOT EXISTS b_class;

-- 2. 移动表到b_class schema
ALTER TABLE public.fact_raw_data_inventory_snapshot 
SET SCHEMA b_class;

-- 3. 移动所有fact_raw_data_*表
ALTER TABLE public.fact_raw_data_orders_daily SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_orders_weekly SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_orders_monthly SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_products_daily SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_products_weekly SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_products_monthly SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_traffic_daily SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_traffic_weekly SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_traffic_monthly SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_services_daily SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_services_weekly SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_services_monthly SET SCHEMA b_class;
ALTER TABLE public.fact_raw_data_inventory_snapshot SET SCHEMA b_class;
```

**注意**：移动表后需要：
- 更新代码中的表引用（如果硬编码了schema）
- 更新Metabase文档中的表引用
- 重新同步Metabase的数据库schema

---

## 🎯 推荐方案

**立即解决**：使用方案1，在Metabase中查看 `public` schema 的表

**长期方案**：如果架构设计要求表在 `b_class` schema，则执行方案2的数据库迁移

---

## 📝 验证步骤

### 验证1：检查表位置

```bash
python temp/development/check_table_schema.py
```

### 验证2：在Metabase中查询数据

1. 登录 Metabase：`http://localhost:8080`
2. 新建 Question → Simple question
3. 选择数据库：`xihong_erp`
4. 选择表：`public.fact_raw_data_inventory_snapshot`（或 `b_class.fact_raw_data_inventory_snapshot` 如果已迁移）
5. 查看数据：应该能看到1218行数据

---

## 📚 相关文档

- `docs/METABASE_DASHBOARD_SETUP.md` - Metabase配置指南（要求表在b_class schema）
- `docs/DATA_SYNC_TABLE_MAPPING.md` - 数据同步表映射关系

