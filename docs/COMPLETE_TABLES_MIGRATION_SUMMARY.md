# 数据库表完整迁移总结

## 迁移时间
2025-12-31

## 迁移目标
根据分类建议，将所有剩余表从 `public` schema 迁移到对应的 schema（`core`、`a_class`、`c_class`、`finance`），实现清晰的架构分离。

## 迁移结果

### ✅ 成功迁移的表（57张）

#### core Schema（20张）- 维度表和管理表

**维度表（13张）**:
- `dim_platforms` - 平台维度表
- `dim_shops` - 店铺维度表
- `dim_products` - 产品维度表
- `dim_product_master` - 产品主数据表
- `bridge_product_keys` - 产品键桥接表
- `dim_currency_rates` - 汇率维度表
- `dim_exchange_rates` - 汇率维度表
- `dim_currencies` - 货币维度表
- `dim_fiscal_calendar` - 财务日历维度表
- `dim_date` - 日期维度表
- `dim_vendors` - 供应商维度表
- `dim_roles` - 角色维度表
- `dim_users` - 用户维度表

**管理表（7张）**:
- `account_aliases` - 账号别名表
- `field_mapping_templates` - 字段映射模板表
- `field_mapping_template_items` - 字段映射模板明细表
- `field_mapping_audit` - 字段映射审计表
- `field_mappings` - 字段映射表（旧表）
- `field_usage_tracking` - 字段使用追踪表
- `staging_inventory` - 库存暂存表

#### a_class Schema（9张）- 用户输入数据表

- `sales_campaigns` - 销售战役表（旧表）
- `sales_campaign_shops` - 销售战役店铺关联表
- `campaign_targets` - 战役目标表
- `target_breakdown` - 目标分解表
- `sales_targets` - 销售目标表（从core迁移）
- `performance_config` - 绩效配置表（旧表）
- `employee_targets` - 员工目标表（从public迁移，替换空表）
- `employees` - 员工信息表（从public迁移，替换空表）
- `attendance_records` - 考勤记录表（从public迁移，替换空表）

#### c_class Schema（5张）- 计算输出表

- `performance_scores` - 绩效评分表（旧表）
- `shop_health_scores` - 店铺健康度评分表
- `clearance_rankings` - 清理排名表
- `employee_performance` - 员工绩效表（从public迁移，替换空表）
- `employee_commissions` - 员工佣金表（从public迁移，替换空表）

#### finance Schema（23张）- 财务域表

**采购和入库（4张）**:
- `po_headers` - 采购订单头表
- `po_lines` - 采购订单明细表
- `grn_headers` - 入库单头表
- `grn_lines` - 入库单明细表

**发票管理（3张）**:
- `invoice_headers` - 发票头表
- `invoice_lines` - 发票明细表
- `invoice_attachments` - 发票附件表

**费用管理（3张）**:
- `fact_expenses_month` - 月度费用事实表
- `fact_expenses_allocated_day_shop_sku` - 费用分配事实表
- `allocation_rules` - 分配规则表

**物流成本（2张）**:
- `logistics_costs` - 物流成本表
- `logistics_allocation_rules` - 物流分配规则表

**库存和总账（4张）**:
- `inventory_ledger` - 库存分类账表
- `opening_balances` - 期初余额表
- `gl_accounts` - 总账科目表
- `journal_entries` - 日记账分录表
- `journal_entry_lines` - 日记账分录明细表

**汇率和税务（3张）**:
- `fx_rates` - 汇率表
- `tax_vouchers` - 税务凭证表
- `tax_reports` - 税务报告表

**其他（4张）**:
- `three_way_match_log` - 三方匹配日志表
- `approval_logs` - 审批日志表
- `return_orders` - 退货订单表

### ✅ 删除的空表（5张）

在迁移过程中，自动删除目标schema中的空表（旧版本）：

- `a_class.employee_targets` - 空表，已替换
- `a_class.employees` - 空表，已替换
- `a_class.attendance_records` - 空表，已替换
- `c_class.employee_performance` - 空表，已替换
- `c_class.employee_commissions` - 空表，已替换

## 迁移统计

| Schema | 迁移表数 | 说明 |
|--------|---------|------|
| **core** | 20张 | 维度表和管理表 |
| **a_class** | 9张 | 用户输入数据表 |
| **c_class** | 5张 | 计算输出表 |
| **finance** | 23张 | 财务域表 |
| **总计** | **57张** | 完整迁移 |

## 迁移安全性验证

### ✅ ORM查询兼容性
- 所有ORM查询不包含schema前缀（如 `db.query(DimPlatform)`）
- PostgreSQL `search_path` 已配置：`public,b_class,a_class,c_class,core,finance`
- 迁移后代码无需修改，自动找到对应schema中的表

### ✅ 外键依赖处理
- PostgreSQL的 `ALTER TABLE SET SCHEMA` 自动处理外键
- 所有外键引用自动更新到新的schema

### ✅ 数据完整性
- 所有数据已完整迁移
- 无数据丢失
- 表结构保持不变

## 迁移脚本

**脚本位置**: `scripts/migrate_all_tables.py`

**使用方法**:
```bash
# 预览模式（dry-run）
python scripts/migrate_all_tables.py

# 执行迁移（所有schema）
python scripts/migrate_all_tables.py --execute

# 执行迁移（指定schema）
python scripts/migrate_all_tables.py --execute --schema core
python scripts/migrate_all_tables.py --execute --schema a_class
python scripts/migrate_all_tables.py --execute --schema c_class
python scripts/migrate_all_tables.py --execute --schema finance
```

## 架构分离完成情况

### ✅ 已完成

1. **核心功能表迁移**（第一阶段）
   - 8张核心功能表已迁移到 `core` schema
   - 包括：账号密码、数据同步、采集任务等

2. **完整表迁移**（第二阶段）
   - 57张表已迁移到对应schema
   - 包括：维度表、管理表、用户输入表、计算输出表、财务域表

### 📊 最终架构

| Schema | 表数量 | 说明 |
|--------|--------|------|
| **core** | ~28张 | 核心ERP表（维度表、管理表、系统表） |
| **a_class** | ~18张 | 用户输入数据（销售战役、目标、绩效配置等） |
| **b_class** | ~17张 | 数据采集数据（订单、产品、流量等） |
| **c_class** | ~9张 | 计算输出数据（员工绩效、佣金、评分等） |
| **finance** | ~23张 | 财务域表（采购、库存、发票、费用等） |
| **public** | ~10张 | 其他表（视图、物化视图、报告等） |

**总计**: ~105张表

## 后续建议

### 1. 验证功能
迁移后请验证以下功能：
- ✅ 维度表查询（平台、店铺、产品等）
- ✅ 字段映射功能
- ✅ 用户配置功能（销售战役、目标等）
- ✅ 计算输出功能（员工绩效、佣金等）
- ✅ 财务域功能（采购、发票、费用等）

### 2. 清理public schema
迁移完成后，可以考虑清理 `public` schema 中不再使用的表：
- 废弃的旧表（如 `fact_analytics`、`fact_traffic` 等）
- 重复表（如果存在）

### 3. Metabase同步
- Metabase会自动识别新的schema结构
- 建议在Metabase中重新组织Collections，按schema分组

## 注意事项

1. **代码兼容性**：
   - 迁移不会导致路径变化
   - ORM模型和代码查询都不包含schema前缀
   - `search_path` 配置确保自动查找

2. **Metabase Question**：
   - 迁移不会影响Metabase Question
   - Metabase通过API查询，不直接依赖schema
   - 可以按计划清理和重新设计

3. **回滚方案**：
   - 如果需要回滚，可以使用 `ALTER TABLE {schema}.{table_name} SET SCHEMA public`
   - 建议在迁移前备份数据库

## 总结

✅ **迁移成功**：57张表已安全迁移到对应schema  
✅ **架构清晰**：表按数据分类清晰分离，便于维护  
✅ **代码兼容**：无需修改代码，ORM自动找到新位置的表  
✅ **数据完整**：所有数据已完整迁移，无数据丢失

**迁移完成时间**: 2025-12-31  
**迁移状态**: ✅ 完成

