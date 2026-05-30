# HR / 绩效相关 Schema 漂移清单（2026-05-29）

## 1. 目的

记录本轮“薪资、绩效、提成、我的收入、月结快照”排查过程中，真实 PostgreSQL 表结构与当前 ORM / 代码假设之间的差异，作为后续迁移治理输入。

## 2. 结论摘要

本轮排查确认：

- `a_class.salary_structures`
- `a_class.target_breakdown`
- `a_class.sales_targets`
- `a_class.payroll_records`
- `c_class.employee_performance`
- `c_class.employee_commissions`

与当前核心改造后的代码预期基本一致。

仍存在若干“代码或临时排查假设先于真实库”的漂移点，主要集中在查询假设层，而不是核心业务字段缺失层。

## 3. 2026-05-30 补充

以下已确认漂移项，已在 `20260530_hr_schema_alignment_cleanup` 迁移中补齐：

- `a_class.salary_structures.remark`
- `c_class.performance_scores.calculated_at`
- `core.dim_shops.is_active`

因此本清单中这三项保留为历史排查结论，但不再属于当前上线阻塞。

## 4. 已确认表结构

### 4.1 `a_class.salary_structures`

已存在关键字段：

- `base_salary`
- `position_salary`
- `housing_allowance`
- `transport_allowance`
- `meal_allowance`
- `communication_allowance`
- `other_allowance`
- `performance_ratio`
- `commission_ratio`
- `social_insurance_base`
- `housing_fund_base`
- `effective_date`
- `status`
- `performance_package_amount`
- `remark`

说明：

- 本轮重构引入的 `performance_package_amount` 已落库。
- `remark` 已通过迁移补齐。

### 4.2 `a_class.target_breakdown`

已存在关键字段：

- `target_id`
- `breakdown_type`
- `platform_code`
- `shop_id`
- `period_start`
- `period_end`
- `period_label`
- `target_amount`
- `target_quantity`
- `achieved_amount`
- `achieved_quantity`
- `achievement_rate`
- `target_profit_amount`
- `achieved_profit_amount`
- `product_id`
- `platform_sku`
- `company_sku`
- `target_value`
- `achieved_value`
- `manual_score_value`

说明：

- `target_profit_amount` 在真实库存在，但 2026-03 的多组店铺目标分解数据中大量为 `0`，这不是 schema 问题，而是数据治理问题。

### 4.3 `a_class.sales_targets`

已存在关键字段：

- `target_name`
- `target_type`
- `period_start`
- `period_end`
- `target_amount`
- `target_quantity`
- `target_profit_amount`
- `achieved_profit_amount`
- `product_id`
- `platform_sku`
- `company_sku`
- `metric_code`
- `metric_name`
- `metric_direction`
- `target_value`
- `achieved_value`
- `max_score`
- `penalty_enabled`
- `penalty_threshold`
- `penalty_per_unit`
- `penalty_max`
- `manual_score_enabled`
- `manual_score_value`
- `scope_type`

说明：

- `scope_type` 已落库。

### 4.4 `c_class.performance_scores`

已存在关键字段：

- `platform_code`
- `shop_id`
- `period`
- `total_score`
- `sales_score`
- `profit_score`
- `key_product_score`
- `operation_score`
- `score_details`
- `rank`
- `performance_coefficient`
- `calculated_at`
- `created_at`
- `updated_at`

说明：

- `calculated_at` 已通过迁移补齐。
- 当前正式查询、审计和对账仍建议统一以 `updated_at` 代表最新落库时间，避免双口径混淆。

### 4.5 `c_class.employee_performance`

已存在关键字段：

- `employee_code`
- `year_month`
- `actual_sales`
- `achievement_rate`
- `performance_score`
- `calculated_at`

### 4.6 `c_class.employee_commissions`

已存在关键字段：

- `employee_code`
- `year_month`
- `sales_amount`
- `commission_amount`
- `commission_rate`
- `calculated_at`

### 4.7 `a_class.payroll_records`

已存在关键字段：

- `base_salary`
- `position_salary`
- `performance_salary`
- `overtime_pay`
- `commission`
- `allowances`
- `bonus`
- `gross_salary`
- `social_insurance_personal`
- `housing_fund_personal`
- `income_tax`
- `other_deductions`
- `total_deductions`
- `net_salary`
- `social_insurance_company`
- `housing_fund_company`
- `total_cost`
- `status`
- `pay_date`
- `remark`
- `created_at`
- `updated_at`

## 5. 本轮确认的非 schema 类问题

### 5.1 店铺绩效事务边界问题

`PerformanceScore` 在提交前被后续收入/工资单链路的 rollback 冲掉，导致真实库里看起来“重算成功但绩效仍是旧值”。

状态：

- 已修复。

### 5.2 店铺目标单月有效版本治理不足

`target_breakdown` 在 2026-03 存在重复和重叠数据，尤其利润目标分解值大量为 `0`。

状态：

- 已通过“父级店铺目标利润按销售目标占比分摊”做临时兜底。
- 已通过“同月只读取最新 active 店铺目标版本”做运行规则收口。
- 仍建议后续继续做历史数据清理。

### 5.3 `employee_tasks` 幂等问题

`performance-confirmation:{period}:{employee}` 以前每次重算都重复创建，导致唯一键冲突 warning。

状态：

- 已修复为“存在即复用”。

### 5.4 Redis / 缓存删除 warning

缓存失效在 Redis 不可用时会反复 warning，污染重算日志。

状态：

- 已收敛为 debug 级别。

## 6. 后续治理建议

### P1

- 将 `c_class.performance_scores` 的“最后计算时间”统一抽象成 `updated_at`，不要在新代码里继续引入双口径。
- 对所有 HR / 绩效排查脚本统一使用真实库字段，不引入未迁移字段假设。

### P2

- 为 HR / 绩效关键表建立一份契约测试：
  - ORM 关键字段存在性
  - 真实库字段存在性
  - 查询层不再引用不存在字段

## 7. 当前建议

当前不建议再优先做新的大重构。  
更合理的是：

1. 保持现有主链路稳定
2. 在后续需求推进时，持续把“临时假设字段”收敛进真实 migration
3. 对 `target_breakdown` 做版本治理与历史数据清理
