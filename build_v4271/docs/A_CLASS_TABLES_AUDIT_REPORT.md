# A 类数据表结构审查报告

对比「库中实际列」与 `modules/core/db/schema.py` 中模型定义。

## public.sales_targets [OK]

- 期望列数: 15, 实际列数: 15
- 与 schema.py 一致。

## a_class.sales_targets [OK]

- 期望列数: 15, 实际列数: 20
- 多余列（库中有、模型无）: shop_id, target_order_count, target_sales_amount, updated_by, year_month

## a_class.target_breakdown [OK]

- 期望列数: 15, 实际列数: 15
- 与 schema.py 一致。

## a_class.sales_campaigns [OK]

- 期望列数: 15, 实际列数: 15
- 与 schema.py 一致。

## a_class.sales_campaign_shops [OK]

- 期望列数: 12, 实际列数: 12
- 与 schema.py 一致。

## a_class.performance_config [OK]

- 期望列数: 12, 实际列数: 12
- 与 schema.py 一致。

---

## 审查结论与建议

- **缺失列**：本次审查中，所有被检表在各自 schema 下均**无缺失列**（即无类似此前 `sales_targets.target_name does not exist` 的情况）。`public.sales_targets`、`a_class.target_breakdown`、`a_class.sales_campaigns`、`a_class.sales_campaign_shops`、`a_class.performance_config` 与当前 schema.py 定义一致。
- **a_class.sales_targets 多余列**：该表在 `a_class` 下多出 `shop_id, target_order_count, target_sales_amount, updated_by, year_month`，属于历史或另一套设计。若目标管理等 API 使用的是 `public.sales_targets`（默认 schema），可忽略；若将来有接口直接读写 `a_class.sales_targets`，需在代码或文档中明确该表与 `SalesTarget` 的差异，或通过迁移/脚本将 a_class 下表收敛为与模型一致。
- **复跑审查**：表结构或模型有变更后，可在项目根目录执行  
  `python scripts/check_a_class_tables_schema.py --report`  
  更新本报告（依赖与后端相同的 `DATABASE_URL`）。
