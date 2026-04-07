# 数据库表审计总结报告

**日期**: 2026-01-11  
**状态**: ✅ 审计完成，清理建议已生成

---

## 一、审计结果总结

### 1.1 表数量统计

| 分类 | 数量 | 说明 |
|------|------|------|
| **schema.py 定义的表** | 105 张 | 预期表（应该存在的表） |
| **迁移文件中创建的表** | 39 张 | 已在迁移中管理的表（检测可能不完整） |
| **数据库中实际存在的表** | 164 张 | 所有 schema 的表总数 |
| **系统表** | 2 张 | `alembic_version`, `apscheduler_jobs` |
| **未迁移的表** | 66 张 | schema.py 中定义但迁移文件中未创建 |
| **动态创建的表（b_class）** | 26 张 | 通过 PlatformTableManager 动态创建（正常） |
| **历史遗留表** | 12 张 | 不在 schema.py 中，也不在迁移文件中 |

---

## 二、历史遗留表检查结果

### 2.1 检查脚本

**脚本**: `scripts/check_legacy_tables_usage.py`  
**详细报告**: `temp/legacy_tables_usage_check.txt`  
**总结文档**: `docs/LEGACY_TABLES_USAGE_CHECK_SUMMARY.md`

### 2.2 清理建议

#### ❌ 不能删除（2张）

1. **`user_roles`** (public)
   - ✅ 在 schema.py 中定义为 `Table`（关联表）
   - ✅ 有业务代码引用（40处）
   - ✅ 有数据（2行）
   - **结论**: 必须保留

2. **`dim_date`** (core)
   - ⚠️ 有数据（4,018行）
   - ⚠️ 有迁移文件创建（`20251027_0009_create_dim_date.py`）
   - ⚠️ 不在 schema.py 中定义
   - **结论**: 不能删除，需要确认是否应该在 schema.py 中定义

#### ⚠️ 需要确认（2张）

1. **`campaign_targets`** (a_class)
   - 表为空（0行）
   - 有业务代码引用（`backend/routers/config_management.py`）
   - **建议**: 确认是否应该在 schema.py 中定义

2. **`fact_sales_orders`** (core)
   - 表为空（0行）
   - 引用主要在脚本文件（不是业务代码）
   - **建议**: 确认后可以清理

#### ✅ 可以安全清理（8张）

**public schema**:
- `collection_tasks_backup` - 备份表（0行）
- `key_value` - 键值对表（0行）
- `keyvalue` - 键值对表（0行）
- `raw_ingestions` - 原始数据表（0行）
- `report_execution_log` - 报告执行日志（0行）
- `report_recipient` - 报告接收者（0行）
- `report_schedule` - 报告调度（0行）
- `report_schedule_user` - 报告调度用户（0行）

**清理SQL**（需要用户确认后执行）:
```sql
-- public schema（需要确认后执行）
DROP TABLE IF EXISTS collection_tasks_backup CASCADE;
DROP TABLE IF EXISTS key_value CASCADE;
DROP TABLE IF EXISTS keyvalue CASCADE;
DROP TABLE IF EXISTS raw_ingestions CASCADE;
DROP TABLE IF EXISTS report_execution_log CASCADE;
DROP TABLE IF EXISTS report_recipient CASCADE;
DROP TABLE IF EXISTS report_schedule CASCADE;
DROP TABLE IF EXISTS report_schedule_user CASCADE;
```

---

## 三、未迁移的表（需要补充迁移）

### 3.1 未迁移的表统计

**数量**: 66 张表

这些表在 schema.py 中定义，但迁移文件中未创建。需要补充迁移。

### 3.2 分类列表

#### 核心维度表（7张）
- `dim_platforms`, `dim_shops`, `dim_products`, `dim_product_master`
- `bridge_product_keys`, `dim_currency_rates`, `dim_exchange_rates`

#### 核心事实表（6张）
- `fact_orders`, `fact_order_items`, `fact_order_amounts`
- `fact_product_metrics`, `fact_traffic`, `fact_service`, `fact_analytics`

#### 管理表（20张）
- `account_aliases`, `accounts`, `catalog_files`, `data_files`, `data_records`
- `data_quarantine`, `collection_configs`, `collection_tasks`, `collection_task_logs`
- `collection_sync_points`, `component_versions`, `component_test_history`
- `platform_accounts`, `field_mappings`, `mapping_sessions`
- `field_mapping_dictionary`, `field_mapping_templates`, `field_mapping_template_items`
- `field_mapping_audit`, `field_usage_tracking`

#### 用户权限表（4张）
- `dim_users`, `dim_roles`, `user_sessions`, `user_approval_logs`

#### 暂存表（4张）
- `staging_orders`, `staging_product_metrics`, `staging_inventory`, `staging_raw_data`

#### 其他表（25张）
- `product_images`, `entity_aliases`
- `sales_campaigns`, `sales_campaign_shops`, `sales_targets`, `target_breakdown`
- `performance_config`, `performance_scores`, `shop_health_scores`, `shop_alerts`
- `clearance_rankings`, `notifications`, `user_notification_preferences`
- `dim_rate_limit_config`, `fact_rate_limit_config_audit`
- `system_logs`, `security_config`, `backup_records`, `smtp_config`
- `notification_templates`, `alert_rules`, `system_config`
- `sync_progress_tasks`

**注意**: 详细列表请查看 `temp/table_audit_report.txt`

---

## 四、下一步行动

### 4.1 遗留表清理（用户确认后）

1. ✅ 检查脚本已创建并运行完成
2. ⏳ 等待用户确认可以清理的表列表
3. ⏳ 执行清理SQL（用户确认后）

### 4.2 补充迁移（待执行）

1. ⏳ 创建整合迁移文件（包含所有未迁移的表）
2. ⏳ 使用 IF NOT EXISTS 模式（避免覆盖已存在的表）
3. ⏳ 测试迁移文件（本地环境）
4. ⏳ 执行迁移（生产环境）

---

## 五、相关文档

- [表审计和清理计划](TABLE_AUDIT_AND_CLEANUP_PLAN.md) - 完整计划文档
- [遗留表使用情况检查总结](LEGACY_TABLES_USAGE_CHECK_SUMMARY.md) - 详细检查结果
- [表审计脚本](scripts/audit_all_tables.py) - 审计脚本
- [遗留表检查脚本](scripts/check_legacy_tables_usage.py) - 检查脚本
- [详细审计报告](temp/table_audit_report.txt) - 详细报告
- [遗留表使用情况报告](temp/legacy_tables_usage_check.txt) - 详细检查报告
