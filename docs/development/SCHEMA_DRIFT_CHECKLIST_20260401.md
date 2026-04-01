# Schema Drift Checklist (2026-04-01)

## Summary

- 对比来源：
  - ORM 定义：`modules/core/db/schema.py`
  - 数据库真实落表：当前 PostgreSQL `information_schema.tables`
  - 现有 proof：`backend/utils/schema_cleanup_low_risk_proofs.py`、`backend/utils/schema_cleanup_wave2_proofs.py`
- 当前 `Base.metadata` 中存在 60 张“模型 schema 与数据库真实 schema 不一致”的表。
- 分组结果：
  - `public -> core`: 31
  - `public -> finance`: 23
  - `public -> a_class`: 3
  - `public -> b_class`: 2
  - `public -> c_class`: 1

## 已完成收敛

- `collection_configs`
- `collection_tasks`
- `collection_task_logs`
- Alembic 版本表已固定使用 `core.alembic_version`
- `public.alembic_version` 已归档为 `public.alembic_version__archive_retired`

## Group A: public -> a_class

这些表已有现成 proof，最适合下一批处理。

- `performance_config`
  - 模型：`public`
  - 实际：`a_class`
  - 现有 proof：`expected_target_schema = a_class`
  - 状态：可直接按“显式 schema 绑定 + 契约测试”推进
- `sales_campaigns`
  - 模型：`public`
  - 实际：`a_class`
  - 现有 proof：`expected_target_schema = a_class`
  - 状态：同上
- `sales_campaign_shops`
  - 模型：`public`
  - 实际：`a_class`
  - 现有 proof：`expected_target_schema = a_class`
  - 状态：同上

## Group B: public -> b_class

这些表已有目标 schema 证明，但 runtime proof 仍不足。

- `entity_aliases`
  - 模型：`public`
  - 实际：`b_class`
  - 现有 proof：`expected_target_schema = b_class`
  - 风险：中
  - 缺口：runtime proof 不足
- `staging_raw_data`
  - 模型：`public`
  - 实际：`b_class`
  - 现有 proof：`expected_target_schema = b_class`
  - 风险：中
  - 缺口：runtime proof 不足

## Group C: public -> c_class

- `clearance_rankings`
  - 模型：`public`
  - 实际：`c_class`
  - 当前仓库内没有同等级的 cleanup proof
  - 需要先补目标 schema 证明和 runtime 路径清单

## Group D: public -> core

这一组数量最多，且很多是高频基础表，风险最高。

### Core 基础维表 / 用户表

- `accounts`
- `dim_platforms`
- `dim_products`
- `dim_product_master`
- `dim_users`
- `dim_roles`
- `dim_vendors`
- `dim_currencies`
- `dim_currency_rates`
- `dim_exchange_rates`
- `dim_fiscal_calendar`
- `dim_metric_formulas`
- `bridge_product_keys`

### Core 元数据 / 采集 / 文件治理

- `collection_sync_points`
- `component_versions`
- `component_test_history`
- `data_files`
- `data_quarantine`
- `data_records`
- `field_mappings`
- `field_mapping_dictionary`
- `field_mapping_templates`
- `field_mapping_template_items`
- `field_mapping_audit`
- `field_usage_tracking`
- `mapping_sessions`
- `sync_progress_tasks`

### Core staging / 运行轨迹

- `staging_orders`
- `staging_product_metrics`
- `staging_inventory`
- `backup_records`

### 建议优先级

- P1:
  - `accounts`
  - `data_files`
  - `data_quarantine`
  - `data_records`
  - `field_mappings`
  - `mapping_sessions`
  - `sync_progress_tasks`
- P2:
  - `dim_platforms`
  - `dim_products`
  - `dim_product_master`
  - `dim_users`
  - `dim_roles`
  - `dim_vendors`
  - `component_versions`
  - `component_test_history`
- P3:
  - `bridge_product_keys`
  - `dim_currencies`
  - `dim_currency_rates`
  - `dim_exchange_rates`
  - `dim_fiscal_calendar`
  - `dim_metric_formulas`
  - `staging_orders`
  - `staging_product_metrics`
  - `staging_inventory`
  - `backup_records`
  - `collection_sync_points`

## Group E: public -> finance

财务域漂移数量第二多，但域边界清晰，适合按 finance 批次单独推进。

- `allocation_rules`
- `approval_logs`
- `fact_expenses_allocated_day_shop_sku`
- `fact_expenses_month`
- `fx_rates`
- `gl_accounts`
- `grn_headers`
- `grn_lines`
- `inventory_ledger`
- `invoice_attachments`
- `invoice_headers`
- `invoice_lines`
- `journal_entries`
- `journal_entry_lines`
- `logistics_allocation_rules`
- `logistics_costs`
- `opening_balances`
- `po_headers`
- `po_lines`
- `return_orders`
- `tax_reports`
- `tax_vouchers`
- `three_way_match_log`

### 建议优先级

- P1:
  - `gl_accounts`
  - `invoice_headers`
  - `invoice_lines`
  - `po_headers`
  - `po_lines`
  - `tax_reports`
- P2:
  - `fx_rates`
  - `journal_entries`
  - `journal_entry_lines`
  - `inventory_ledger`
  - `grn_headers`
  - `grn_lines`
- P3:
  - 其余 finance 表按业务接触面逐步收口

## Recommended Next Waves

1. Wave A: 先处理 `public -> a_class`
   - 范围小
   - 已有 proof
   - 用户面影响明确
2. Wave B: 再处理 `public -> core` 的文件治理与元数据表
   - `data_files` / `data_quarantine` / `data_records` / `field_mappings` / `mapping_sessions` / `sync_progress_tasks`
3. Wave C: 再处理 `public -> finance`
   - 单独按 finance 域推进
4. Wave D: 最后处理 `public -> b_class` / `public -> c_class`
   - 先补 runtime proof，再做 ORM 显式 schema 收口

## Verification Baseline

- 当前已验证：
  - `alembic current = 20260401_public_alembic_archive (head)`
  - `verify_schema_completeness().migration_status = up_to_date`
- 后续每一波都应复用当前做法：
  - 先加 schema 契约测试
  - 再改 ORM 显式 schema / 外键目标
  - 最后做运行态查询验证
