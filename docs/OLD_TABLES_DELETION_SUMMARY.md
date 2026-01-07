# 旧表删除总结

**执行时间**：2025-12-08  
**操作**：删除 `b_class` schema 中的 13 个旧表（`fact_raw_data_*`）

---

## ✅ 已删除的表

以下 13 个旧表已从 `b_class` schema 中删除：

1. `fact_raw_data_orders_daily`
2. `fact_raw_data_orders_weekly`
3. `fact_raw_data_orders_monthly`
4. `fact_raw_data_products_daily`
5. `fact_raw_data_products_weekly`
6. `fact_raw_data_products_monthly`
7. `fact_raw_data_traffic_daily`
8. `fact_raw_data_traffic_weekly`
9. `fact_raw_data_traffic_monthly`
10. `fact_raw_data_services_daily`
11. `fact_raw_data_services_weekly`
12. `fact_raw_data_services_monthly`
13. `fact_raw_data_inventory_snapshot`

---

## 🔍 问题根源

这些表是由 Alembic 迁移脚本 `migrations/versions/20251126_132151_v4_6_0_dss_architecture_tables.py` 创建的。

**问题**：
- Alembic 迁移脚本创建了旧表名的表（`fact_raw_data_*`）
- 但新的架构使用按平台分表的表（`fact_shopee_*`, `fact_tiktok_*` 等）
- 这些旧表没有被删除，导致 Metabase 显示旧表名

---

## ✅ 删除结果

- ✅ 所有 13 个旧表已成功删除
- ✅ `b_class` schema 中不再有 `fact_raw_data_*` 表
- ✅ Metabase 应该不再显示这些旧表

---

## 📋 下一步操作

1. **在 Metabase 中重新同步 Schema**：
   - 登录 Metabase：`http://localhost:8080`
   - Admin → Databases → XIHONG_ERP
   - 点击 "Sync database schema now"
   - 等待同步完成（60-90秒）

2. **验证结果**：
   - 在 `b_class` schema 中应该只看到新表（`fact_shopee_*`, `fact_tiktok_*` 等）
   - 不应该看到 `fact_raw_data_*` 开头的旧表

---

## ⚠️ 注意事项

如果新表（`fact_shopee_*` 等）不存在，需要：
1. 运行数据同步任务，让 `PlatformTableManager` 自动创建新表
2. 或手动创建新表（不推荐）

---

**创建时间**：2025-12-08  
**状态**：✅ 旧表已删除

