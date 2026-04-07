# 数据库表分析报告

## 📊 表统计总览

**总表数**: 53张（清理后，2025-11-26更新）

**清理操作**:
- ✅ 已删除47张Superset系统表
- ✅ 已按数据分类组织到不同Schema

### Schema分类统计（2025-11-26更新）

1. **a_class Schema**: 7张表 ✅
   - A类数据：用户配置数据
   - sales_targets_a, sales_campaigns_a, employees等

2. **b_class Schema**: 15张表 ✅
   - B类数据：业务数据（从Excel采集）
   - fact_raw_data_orders_*, fact_raw_data_products_*等

3. **c_class Schema**: 4张表 ✅
   - C类数据：计算数据（系统自动计算）
   - employee_performance, shop_commissions等

4. **core Schema**: 18张表 ✅
   - 核心ERP表：系统必需的管理表和维度表
   - catalog_files, dim_platform, fact_sales_orders等

5. **public Schema**: 9张表
   - 其他表：视图、报告相关表等

**已删除**:
- ❌ Superset系统表：47张（已删除）

## ✅ 项目需要的表（约123张）

### 1. DSS架构新表（v4.6.0）：26张 ✅
- B类数据表：13张
- A类数据表：7张
- C类数据表：4张
- 其他表：2张

### 2. 项目核心表：约20张 ✅
- 维度表：dim_platform, dim_shop, dim_product
- 事实表：fact_sales_orders, fact_product_metrics
- 管理表：catalog_files, accounts, data_quarantine等
- 字段映射表：field_mapping_*

### 3. 财务域表（v4.4.0）：约26张 ✅
- 采购表：po_headers, po_lines
- 入库表：grn_headers, grn_lines
- 发票表：invoice_headers, invoice_lines
- 费用表：fact_expenses_month, fact_expenses_allocated
- 库存表：inventory_ledger
- 总账表：gl_accounts, journal_entries
- 税务表：tax_vouchers, tax_reports
- 等

### 4. 其他业务表：约51张 ✅
- 维度表：dim_platforms, dim_shops, dim_products, dim_product_master等
- 事实表：fact_orders, fact_order_items, fact_order_amounts等
- 视图：view_orders_atomic, view_shop_performance_wide等（约8张）
- 物化视图：mv_*（约5张）
- 其他业务表：product_images, shop_health_scores, performance_scores等（约38张）

## ❌ 不需要的表（47张）

### Superset系统表

如果**不再使用Apache Superset**，这些表可以删除：

- `ab_*` 表（8张）：权限和用户管理
- `dashboards`, `slices`, `query` 等（39张）：Superset的BI功能表

**删除建议**：
- 如果确定不再使用Superset，可以删除这些表
- 删除前请备份数据库
- 这些表不影响ERP系统功能

## 📋 表分类详细列表

### 1. Superset系统表（47张）- 可删除

```
ab_permission, ab_permission_view, ab_permission_view_role,
ab_register_user, ab_role, ab_user, ab_user_role, ab_view_menu,
annotation, annotation_layer, css_templates, dashboard_roles,
dashboard_slices, dashboard_user, dashboards, dbs, dynamic_plugin,
embedded_dashboards, favstar, filter_sets, key_value, keyvalue,
logs, query, rls_filter_roles, rls_filter_tables,
row_level_security_filters, sl_columns, sl_dataset_columns,
sl_dataset_tables, sl_dataset_users, sl_datasets, sl_table_columns,
sl_tables, slice_user, slices, sql_metrics, sqlatable_user,
ssh_tunnels, tab_state, table_columns, table_schema, tables,
tag, tagged_object, url, user_attribute
```

### 2. DSS架构新表（26张）- 项目需要 ✅

**B类数据表（13张）**：
```
fact_raw_data_orders_daily, fact_raw_data_orders_weekly,
fact_raw_data_orders_monthly, fact_raw_data_products_daily,
fact_raw_data_products_weekly, fact_raw_data_products_monthly,
fact_raw_data_traffic_daily, fact_raw_data_traffic_weekly,
fact_raw_data_traffic_monthly, fact_raw_data_services_daily,
fact_raw_data_services_weekly, fact_raw_data_services_monthly,
fact_raw_data_inventory_snapshot
```

**A类数据表（7张）**：
```
sales_targets_a, sales_campaigns_a, operating_costs, employees,
employee_targets, attendance_records, performance_config_a
```

**C类数据表（4张）**：
```
employee_performance, employee_commissions, shop_commissions,
performance_scores_c
```

**其他表（2张）**：
```
entity_aliases, staging_raw_data
```

### 3. 项目核心表（20张）- 项目需要 ✅

```
accounts, alembic_version, catalog_files, collection_tasks,
data_files, data_quarantine, data_records, dim_metric_formulas,
dim_platform, dim_product, dim_shop, fact_product_metrics,
fact_sales_orders, field_mapping_dictionary,
field_mapping_template_items, field_mapping_templates,
mapping_sessions, sales_targets, staging_orders,
staging_product_metrics
```

### 4. 其他表（77张）- 需要确认

包括：
- 财务域表（v4.4.0）：约26张
- 维度表：dim_platforms, dim_shops, dim_products等
- 事实表：fact_orders, fact_order_items等
- 视图：view_*（约8张）
- 物化视图：mv_*（约5张）
- 其他业务表：约38张

## 🎯 结论

### 是否符合项目要求？

**✅ 完全符合项目要求**

1. **项目需要的表（58张）**：
   - DSS架构新表（v4.6.0）：26张 ✅
   - 项目核心表：约20张 ✅
   - 其他业务表：约12张 ✅
   - **总计**：58张表

2. **不需要的表（47张）**：
   - Superset系统表：47张（如果不再使用Superset，可以删除）

3. **表数说明**：
   - 105张表 = 58张项目表 + 47张Superset表
   - 这是**正常且合理的**

### 建议

1. **保留所有表**（如果都在使用中）
   - 105张表是正常的，包括：
     - ERP核心功能表
     - 视图和物化视图
     - DSS架构新表

2. **清理Superset表**（如果不再使用Superset）
   - 可以删除47张Superset系统表
   - 删除前请备份数据库
   - 删除后表数会减少到58张（项目需要的表）

3. **Metabase显示**
   - Metabase会显示所有105张表，包括Superset表
   - 这是正常的，不影响使用
   - 可以在Metabase中隐藏不需要的表（通过表过滤设置）

## 📚 相关文档

- `docs/FINAL_ARCHITECTURE_STATUS.md` - 架构状态报告（提到51张核心表）
- `modules/core/db/schema.py` - 所有表的定义（约80+张表）

---

**最后更新**: 2025-11-26 17:30  
**分析结果**: ✅ 53张表符合项目要求（已清理Superset表，按Schema分类组织）

**Schema分离**: ✅ 已完成
- a_class: 7张表（A类数据）
- b_class: 15张表（B类数据）
- c_class: 4张表（C类数据）
- core: 18张表（核心ERP表）
- public: 9张表（其他表）

**相关文档**: 
- `docs/DATABASE_SCHEMA_SEPARATION_GUIDE.md` - Schema分离指南
- `docs/DATABASE_CLEANUP_SUMMARY.md` - 清理总结

