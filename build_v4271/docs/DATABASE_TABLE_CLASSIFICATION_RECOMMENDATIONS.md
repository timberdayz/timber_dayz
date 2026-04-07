# 数据库表分类建议

**创建时间**: 2025-12-31  
**状态**: 📋 分类建议（待确认）  
**目的**: 为 94 张"孤立表"提供分类建议，便于后续整理

---

## 📊 分类规则

### 数据流转规则

- **a_class**: 用户前端输入的数据（销售战役、目标管理、绩效配置等）
- **b_class**: 数据采集自动同步的数据（订单、产品、流量等）
- **c_class**: 计算输出的数据（员工绩效、佣金、评分等）
- **core**: 核心 ERP 表（系统必需的管理表和维度表）
- **finance**: 财务域表（采购、库存、发票等）
- **public**: 其他表（视图、物化视图、报告等）

---

## 📋 分类建议

### 1. b_class Schema（数据采集）- 应保留在 b_class

#### 按平台分表的数据（已存在，应保留）

- `fact_miaoshou_inventory_snapshot` - 秒售平台库存快照
- `fact_shopee_analytics_daily/weekly/monthly` - Shopee 分析数据（3 张）
- `fact_shopee_products_daily/weekly/monthly` - Shopee 产品数据（3 张）
- `fact_shopee_services_agent_daily/weekly/monthly` - Shopee 服务数据（Agent，3 张）
- `fact_shopee_services_ai_assistant_daily/weekly/monthly` - Shopee 服务数据（AI 助手，3 张）
- `fact_tiktok_analytics_daily/weekly/monthly` - TikTok 分析数据（3 张）
- `fact_tiktok_products_daily/weekly/monthly` - TikTok 产品数据（3 张）
- `fact_tiktok_services_daily/monthly` - TikTok 服务数据（2 张）

**建议**: ✅ 保留在 b_class（这些是按平台分表的数据，符合新架构）

#### 测试/临时表（需要确认）

- `fact_test_platform_orders_daily` - 测试平台订单

**建议**: ⚠️ 如果不再使用，可以删除；如果需要保留，放在 b_class

---

### 2. core Schema（核心 ERP 表）- 应迁移到 core

#### 维度表（应迁移到 core）

- `dim_platforms` (public) - 平台维度表
- `dim_shops` (public) - 店铺维度表
- `dim_products` (public) - 产品维度表
- `dim_product_master` (public) - 产品主数据表
- `bridge_product_keys` (public) - 产品键桥接表
- `dim_currency_rates` (public) - 汇率维度表
- `dim_exchange_rates` (public) - 汇率维度表（可能与 dim_currency_rates 重复）
- `dim_currencies` (public) - 货币维度表
- `dim_fiscal_calendar` (public) - 财务日历维度表
- `dim_date` (public) - 日期维度表
- `dim_vendors` (public) - 供应商维度表
- `dim_roles` (public) - 角色维度表
- `dim_users` (public) - 用户维度表

**建议**: ✅ 迁移到 core schema

#### 管理表（应迁移到 core）

- `accounts` (public) - 账号表（core 已有，可能是重复）
- `account_aliases` (public) - 账号别名表
- `platform_accounts` (public) - 平台账号表
- `collection_configs` (public) - 采集配置表
- `collection_sync_points` (public) - 采集同步点表
- `collection_task_logs` (public) - 采集任务日志表
- `collection_tasks_backup` (public) - 采集任务备份表（可能删除）
- `component_test_history` (public) - 组件测试历史表
- `component_versions` (public) - 组件版本表
- `field_mapping_templates` (public) - 字段映射模板表
- `field_mapping_template_items` (public) - 字段映射模板明细表
- `field_mapping_dictionary` (public) - 字段映射辞典表（core 已有，可能是重复）
- `field_mapping_audit` (public) - 字段映射审计表
- `field_mappings` (public) - 字段映射表（旧表，可能废弃）
- `field_usage_tracking` (public) - 字段使用追踪表
- `mapping_sessions` (public) - 映射会话表（core 已有，可能是重复）
- `catalog_files` (public) - 文件目录表（core 已有，可能是重复）
- `data_files` (public) - 数据文件表（core 已有，可能是重复）
- `data_records` (public) - 数据记录表（core 已有，可能是重复）
- `data_quarantine` (public) - 数据隔离表（core 已有，可能是重复）
- `staging_orders` (public) - 订单暂存表（core 已有，可能是重复）
- `staging_product_metrics` (public) - 产品指标暂存表（core 已有，可能是重复）
- `staging_inventory` (public) - 库存暂存表
- `staging_raw_data` (public) - 原始数据暂存表（b_class 已有，可能是重复）
- `sync_progress_tasks` (public) - 同步进度任务表
- `entity_aliases` (public) - 实体别名表（b_class 已有，可能是重复）

**建议**: ✅ 迁移到 core schema（注意检查是否有重复表）

#### 系统表（应保留在 core）

- `apscheduler_jobs` (core) - 调度器任务表
- `dim_metric_formulas` (core) - 指标公式维度表
- `fact_sales_orders` (core) - 销售订单事实表（旧表，可能废弃）
- `sales_targets` (core) - 销售目标表（旧表，可能废弃）

**建议**: ⚠️ 检查是否仍在使用，如果废弃则删除

---

### 3. a_class Schema（用户输入）- 应迁移到 a_class

#### 用户配置表（应迁移到 a_class）

- `sales_campaigns` (public) - 销售战役表（旧表，a_class 已有 sales_campaigns_a）
- `sales_campaign_shops` (public) - 销售战役店铺关联表
- `campaign_targets` (public) - 战役目标表
- `target_breakdown` (public) - 目标分解表
- `sales_targets` (public) - 销售目标表（旧表，a_class 已有 sales_targets_a）
- `employee_targets` (public) - 员工目标表（a_class 已有，可能是重复）
- `employees` (public) - 员工信息表（a_class 已有，可能是重复）
- `attendance_records` (public) - 考勤记录表（a_class 已有，可能是重复）
- `operating_costs` (public) - 运营成本表（a_class 已有，可能是重复）
- `performance_config` (public) - 绩效配置表（旧表，a_class 已有 performance_config_a）
- `performance_config_a` (public) - 绩效配置表（a_class 已有，可能是重复）

**建议**: ✅ 迁移到 a_class schema（注意检查是否有重复表）

---

### 4. c_class Schema（计算输出）- 应迁移到 c_class

#### 计算输出表（应迁移到 c_class）

- `employee_performance` (public) - 员工绩效表（c_class 已有，可能是重复）
- `employee_commissions` (public) - 员工佣金表（c_class 已有，可能是重复）
- `shop_commissions` (public) - 店铺佣金表（c_class 已有，可能是重复）
- `performance_scores` (public) - 绩效评分表（旧表，c_class 已有 performance_scores_c）
- `performance_scores_c` (public) - 绩效评分表（c_class 已有，可能是重复）
- `shop_health_scores` (public) - 店铺健康度评分表
- `clearance_rankings` (public) - 清理排名表

**建议**: ✅ 迁移到 c_class schema（注意检查是否有重复表）

---

### 5. finance Schema（财务域）- 应迁移到 finance

#### 财务域表（应迁移到 finance）

- `po_headers` (public) - 采购订单头表
- `po_lines` (public) - 采购订单明细表
- `grn_headers` (public) - 入库单头表
- `grn_lines` (public) - 入库单明细表
- `invoice_headers` (public) - 发票头表
- `invoice_lines` (public) - 发票明细表
- `invoice_attachments` (public) - 发票附件表
- `fact_expenses_month` (public) - 月度费用事实表
- `fact_expenses_allocated_day_shop_sku` (public) - 费用分配事实表
- `allocation_rules` (public) - 分配规则表
- `logistics_costs` (public) - 物流成本表
- `logistics_allocation_rules` (public) - 物流分配规则表
- `inventory_ledger` (public) - 库存分类账表
- `opening_balances` (public) - 期初余额表
- `gl_accounts` (public) - 总账科目表
- `journal_entries` (public) - 日记账分录表
- `journal_entry_lines` (public) - 日记账分录明细表
- `fx_rates` (public) - 汇率表
- `tax_vouchers` (public) - 税务凭证表
- `tax_reports` (public) - 税务报告表
- `three_way_match_log` (public) - 三方匹配日志表
- `approval_logs` (public) - 审批日志表
- `return_orders` (public) - 退货订单表

**建议**: ✅ 迁移到 finance schema（需要先创建 finance schema）

---

### 6. public Schema（其他表）- 保留在 public 或删除

#### 运营数据表（应迁移到 b_class 或删除）

- `fact_analytics` (public) - 分析数据表（旧表，已被按平台分表替代）
- `fact_traffic` (public) - 流量数据表（旧表，已被按平台分表替代）
- `fact_service` (public) - 服务数据表（旧表，已被按平台分表替代）
- `fact_order_amounts` (public) - 订单金额表（旧表，可能废弃）

**建议**: ⚠️ 检查是否仍在使用，如果废弃则删除

#### 物化视图管理表（保留在 public）

- `mv_refresh_log` (public) - 物化视图刷新日志表

**建议**: ✅ 保留在 public（物化视图相关）

#### 报告相关表（保留在 public 或删除）

- `report_execution_log` (public) - 报告执行日志表
- `report_recipient` (public) - 报告接收者表
- `report_schedule` (public) - 报告调度表
- `report_schedule_user` (public) - 报告调度用户关联表

**建议**: ⚠️ 如果不再使用报告功能，可以删除；如果需要保留，放在 public

#### 其他表（需要确认）

- `fact_audit_logs` (public) - 审计日志表
- `product_images` (public) - 产品图片表
- `raw_ingestions` (public) - 原始数据入库表
- `key_value` (public) - 键值对表（可能废弃）
- `keyvalue` (public) - 键值对表（可能废弃，与 key_value 重复）
- `user_roles` (public) - 用户角色关联表
- `shop_alerts` (public) - 店铺告警表

**建议**: ⚠️ 需要人工确认用途，决定保留或删除

---

## 📊 分类统计

| Schema             | 表数量 | 说明                       |
| ------------------ | ------ | -------------------------- |
| **b_class**        | 17 张  | 按平台分表的数据（应保留） |
| **core**           | 35 张  | 维度表和管理表（应迁移）   |
| **a_class**        | 11 张  | 用户配置表（应迁移）       |
| **c_class**        | 7 张   | 计算输出表（应迁移）       |
| **finance**        | 23 张  | 财务域表（应迁移）         |
| **public（保留）** | 1 张   | 物化视图管理表             |
| **public（删除）** | 0 张   | 需要确认后删除             |

**总计**: 94 张表

---

## 🎯 执行建议

### 阶段 1：创建 finance schema（如果不存在）

```sql
CREATE SCHEMA IF NOT EXISTS finance;
COMMENT ON SCHEMA finance IS '财务域表：采购、库存、发票、费用、税务、总账等';
```

### 阶段 2：迁移表到对应 schema

按照上述分类建议，使用 SQL 迁移表：

```sql
-- 示例：迁移财务域表
ALTER TABLE po_headers SET SCHEMA finance;
ALTER TABLE po_lines SET SCHEMA finance;
-- ... 其他表
```

### 阶段 3：检查并删除重复表

在迁移前，先检查是否有重复表（如 public 和 core 中都有 accounts 表），删除重复的旧表。

### 阶段 4：删除废弃表

删除不再使用的旧表（如 fact_analytics、fact_traffic 等）。

---

## ⚠️ 注意事项

1. **重复表检查**: 迁移前先检查是否有重复表（如 public 和 core 中都有相同表名）
2. **数据备份**: 迁移前建议备份数据库
3. **依赖关系**: 迁移时注意外键依赖关系
4. **测试环境**: 建议先在测试环境执行，确认无误后再在生产环境执行

---

**创建时间**: 2025-12-31  
**状态**: 📋 待确认和执行
