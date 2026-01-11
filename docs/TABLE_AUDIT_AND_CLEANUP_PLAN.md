# 数据库表审计和清理计划

**日期**: 2026-01-11  
**目标**: 审计所有表，清理历史遗留表，确保所有表都有对应的迁移记录

---

## 一、审计结果总结

### 1.1 表数量统计

- **schema.py 中定义的表**: 105 张
- **迁移文件中创建的表**: 39 张（检测可能不完整）
- **数据库中实际存在的表**: 164 张（所有 schema）
- **系统表**: 2 张（`alembic_version`, `apscheduler_jobs`）

### 1.2 分类统计

| 分类 | 数量 | 说明 |
|------|------|------|
| schema.py 定义的表 | 105 | 预期表 |
| 未迁移的表 | 66 | schema.py 中定义但迁移文件中未创建 |
| 动态创建的表 | 26 | b_class schema 中的 fact_* 表（通过 PlatformTableManager 动态创建） |
| 历史遗留表 | 12 | 不在 schema.py 中，也不在迁移文件中 |

---

## 二、动态创建的表（需要保留）

### 2.1 b_class schema 中的 fact_* 表（26 张）

这些表通过 `PlatformTableManager` 动态创建，不在 schema.py 中定义（v4.17.0+ 架构调整）。

**操作**: **保留，不需要清理，不需要迁移**

**表列表**:
- `fact_shopee_analytics_daily`, `fact_shopee_analytics_monthly`, `fact_shopee_analytics_weekly`
- `fact_shopee_orders_monthly`, `fact_shopee_orders_weekly`
- `fact_shopee_products_daily`, `fact_shopee_products_monthly`, `fact_shopee_products_weekly`
- `fact_shopee_services_agent_daily`, `fact_shopee_services_agent_monthly`, `fact_shopee_services_agent_weekly`
- `fact_shopee_services_ai_assistant_daily`, `fact_shopee_services_ai_assistant_monthly`, `fact_shopee_services_ai_assistant_weekly`
- `fact_tiktok_analytics_daily`, `fact_tiktok_analytics_monthly`, `fact_tiktok_analytics_weekly`
- `fact_tiktok_orders_monthly`, `fact_tiktok_orders_weekly`
- `fact_tiktok_products_daily`, `fact_tiktok_products_monthly`, `fact_tiktok_products_weekly`
- `fact_tiktok_services_agent_daily`, `fact_tiktok_services_agent_monthly`
- `fact_miaoshou_inventory_snapshot`
- `fact_test_platform_orders_daily`

---

## 三、历史遗留表（可以清理）

### 3.1 真正的历史遗留表（12 张）

这些表不在 schema.py 中定义，也不在迁移文件中创建，可能是旧系统的遗留表。

**操作**: **需要检查后清理**

#### a_class schema (1 张)

- `campaign_targets` - 可能在旧版本中使用，需要确认是否仍有数据或引用

#### core schema (2 张)

- `dim_date` - 在迁移 `20251027_0009_create_dim_date.py` 中创建，但不在 schema.py 中定义
  - **建议**: 如果代码中使用，应该在 schema.py 中定义；如果未使用，可以清理
- `fact_sales_orders` - 在迁移 `20251023_0005_add_erp_core_tables.py` 中创建，但不在 schema.py 中定义
  - **建议**: 检查是否与 `fact_orders` 重复，如果重复且 `fact_orders` 已使用，可以清理

#### public schema (9 张)

- `collection_tasks_backup` - 备份表，可能可以清理
- `key_value`, `keyvalue` - 键值对表，需要检查是否仍在使用
- `raw_ingestions` - 原始数据表，可能需要保留或迁移
- `report_execution_log`, `report_recipient`, `report_schedule`, `report_schedule_user` - 报告相关表，可能是旧系统遗留
- `user_roles` - 在 schema.py 中定义为 `Table`（关联表），但在迁移中也创建了，可能重复

### 3.2 清理步骤

1. **检查表是否有数据**
   ```sql
   SELECT table_schema, table_name, 
          (SELECT COUNT(*) FROM information_schema.tables t WHERE t.table_schema = t.table_schema AND t.table_name = t.table_name) as row_count
   FROM information_schema.tables
   WHERE table_name IN ('campaign_targets', 'dim_date', 'fact_sales_orders', ...)
   ```

2. **检查代码引用**
   ```bash
   grep -r "campaign_targets\|dim_date\|fact_sales_orders\|user_roles" --include="*.py" .
   ```

3. **执行清理（谨慎操作）**
   ```sql
   -- a_class schema
   DROP TABLE IF EXISTS a_class.campaign_targets CASCADE;
   
   -- core schema
   DROP TABLE IF EXISTS core.dim_date CASCADE;
   DROP TABLE IF EXISTS core.fact_sales_orders CASCADE;
   
   -- public schema
   DROP TABLE IF EXISTS collection_tasks_backup CASCADE;
   DROP TABLE IF EXISTS key_value CASCADE;
   DROP TABLE IF EXISTS keyvalue CASCADE;
   DROP TABLE IF EXISTS raw_ingestions CASCADE;
   DROP TABLE IF EXISTS report_execution_log CASCADE;
   DROP TABLE IF EXISTS report_recipient CASCADE;
   DROP TABLE IF EXISTS report_schedule CASCADE;
   DROP TABLE IF EXISTS report_schedule_user CASCADE;
   DROP TABLE IF EXISTS user_roles CASCADE;  -- 注意：如果 schema.py 中定义为 Table，可能需要保留
   ```

---

## 四、未迁移的表（需要补充迁移）

### 4.1 未迁移的表列表（66 张）

这些表在 schema.py 中定义，但迁移文件中未创建。需要补充迁移。

**分类**:

#### 核心维度表 (7 张)
- `dim_platforms`, `dim_shops`, `dim_products`, `dim_product_master`
- `bridge_product_keys`, `dim_currency_rates`, `dim_exchange_rates`

#### 核心事实表 (6 张)
- `fact_orders`, `fact_order_items`, `fact_order_amounts`
- `fact_product_metrics`, `fact_traffic`, `fact_service`, `fact_analytics`

#### 管理表 (20 张)
- `account_aliases`, `accounts`, `catalog_files`, `data_files`, `data_records`
- `data_quarantine`, `collection_configs`, `collection_tasks`, `collection_task_logs`
- `collection_sync_points`, `component_versions`, `component_test_history`
- `platform_accounts`, `field_mappings`, `mapping_sessions`
- `field_mapping_dictionary`, `field_mapping_templates`, `field_mapping_template_items`
- `field_mapping_audit`, `field_usage_tracking`

#### 用户权限表 (4 张)
- `dim_users`, `dim_roles`, `user_sessions`, `user_approval_logs`

#### 暂存表 (4 张)
- `staging_orders`, `staging_product_metrics`, `staging_inventory`, `staging_raw_data`

#### 其他表 (25 张)
- `product_images`, `entity_aliases`
- `sales_campaigns`, `sales_campaign_shops`, `sales_targets`, `target_breakdown`
- `performance_config`, `performance_scores`, `shop_health_scores`, `shop_alerts`
- `clearance_rankings`, `notifications`, `user_notification_preferences`
- `dim_rate_limit_config`, `fact_rate_limit_config_audit`
- `system_logs`, `security_config`, `backup_records`, `smtp_config`
- `notification_templates`, `alert_rules`, `system_config`
- `sync_progress_tasks`

### 4.2 迁移整合建议

**目标**: 整合迁移文件，避免表的创建文件太多太复杂

**建议方案**:

1. **基础迁移文件** (`20250925_0001_init_unified_star_schema.py`)
   - 包含核心维度表：`dim_platforms`, `dim_shops`, `dim_products`, `dim_currency_rates`
   - 包含核心事实表：`fact_orders`, `fact_order_items`, `fact_product_metrics`

2. **ERP核心表迁移文件** (`20251023_0005_add_erp_core_tables.py`)
   - 包含用户权限表：`dim_users`, `dim_roles`
   - 包含审计日志表：`fact_audit_logs`
   - （已存在，需要检查是否包含所有相关表）

3. **完整schema基础迁移文件** (`20260110_0001_complete_schema_base_tables.py`)
   - 包含所有缺失的基础表（使用 IF NOT EXISTS 模式）
   - （已存在，但可能不完整）

4. **按功能域分组的迁移文件**
   - 财务域：所有 finance schema 的表
   - 运营域：a_class 和 c_class schema 的表
   - 系统表：系统配置、日志、通知等表

**具体操作**:

1. 检查现有的迁移文件，识别哪些表已经在迁移中创建
2. 创建一个新的整合迁移文件，包含所有未迁移的表（使用 IF NOT EXISTS 模式）
3. 按照功能域分组，创建多个迁移文件（如果表太多）
4. 确保迁移文件之间没有冲突（down_revision 正确）

---

## 五、实施计划

### 5.1 第一阶段：审计和确认（已完成）

- [x] 创建表审计脚本
- [x] 分析所有表的来源
- [x] 识别历史遗留表
- [x] 识别未迁移的表

### 5.2 第二阶段：清理历史遗留表

- [ ] 检查遗留表是否有数据
- [ ] 检查代码引用（grep 搜索）
- [ ] 确认可以安全清理的表
- [ ] 备份数据库
- [ ] 执行清理 SQL
- [ ] 验证清理结果

### 5.3 第三阶段：补充迁移

- [ ] 分析现有迁移文件结构
- [ ] 识别可整合的迁移
- [ ] 创建整合迁移文件（或更新现有迁移文件）
- [ ] 测试迁移文件（本地环境）
- [ ] 执行迁移（生产环境）

### 5.4 第四阶段：验证和文档

- [ ] 验证所有表都有迁移记录
- [ ] 更新文档
- [ ] 更新审计脚本

---

## 六、风险评估

### 6.1 清理历史遗留表的风险

- **数据丢失**: 如果表中有重要数据，清理会导致数据丢失
- **代码依赖**: 如果代码中仍在使用这些表，清理会导致运行时错误

**缓解措施**:
- 执行清理前必须备份数据库
- 使用 grep 搜索确认没有代码引用
- 先在生产环境之外测试清理脚本

### 6.2 补充迁移的风险

- **迁移冲突**: 如果表已存在，迁移可能失败
- **数据不一致**: 如果迁移文件与实际表结构不一致，可能导致数据问题

**缓解措施**:
- 使用 IF NOT EXISTS 模式创建表
- 迁移前验证表结构
- 在测试环境先执行迁移

---

## 七、后续工作

1. **定期审计**: 建议每季度执行一次表审计，确保没有新的遗留表
2. **迁移规范**: 建立迁移规范，确保所有新表都有对应的迁移文件
3. **文档更新**: 更新开发规范，明确表的创建和管理流程

---

## 八、参考文档

- [数据库设计规范](docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md)
- [迁移测试结果](SCHEMA_MIGRATION_TEST_RESULTS.md)
- [表审计脚本](scripts/audit_all_tables.py)
- [清理计划脚本](scripts/analyze_table_cleanup_plan.py)
