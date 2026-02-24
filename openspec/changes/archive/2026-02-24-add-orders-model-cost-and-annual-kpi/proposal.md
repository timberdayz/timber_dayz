# Change: Orders 模型成本列扩展与年度成本 KPI 落地

## Why

1. **成本口径已梳理完成**：变更 `clarify-cost-data-sources` 已产出权威文档 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`，明确 A/B 类成本、总成本公式、GMV 与各比率口径；字段映射辞典与 `ORDER_COST_FIELDS` 已同步，但**尚未在 Orders 模型与年度模块中实现**。
2. **Orders 模型缺成本列**：当前 `sql/metabase_models/orders_model.sql` 仅输出 sales_amount、paid_amount、profit 等，未输出采购金额、仓库操作费、平台费用分项及双总费用列，导致下游 KPI、趋势图、按店铺下钻无法基于订单粒度汇总成本。
3. **年度数据总结成本区块待落地**：年度数据总结已要求展示「成本与产出」区块（总成本、GMV、成本产出比、ROI、毛利率、净利率），但实现依赖：(1) Orders 模型提供 B 类成本列；(2) 后端/看板按成本文档公式聚合 A 类 + B 类并计算比率；按店铺下钻需 A 类 operating_costs.店铺ID 与订单侧 platform_code/shop_id 的 JOIN 一致方案。

因此，本变更在**不改变成本口径**的前提下，完成「Orders Model 成本列扩展」与「年度模块成本落地」两项后续工作，使成本数据从文档变为可用的模型输出与 KPI 展示。

## What Changes

### 依赖与单一事实来源

- **依赖**：变更 `clarify-cost-data-sources` 已收尾；成本口径、列名、公式以 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` 及 `backend/services/field_mapping/standard_fields.py` 中 `ORDER_COST_FIELDS` 为准。
- **GMV**：paid_amount（实付金额）汇总；**比率分母为 0**：展示 N/A 或「-」。

### 1. Orders Model 成本列扩展

- **范围**：`sql/metabase_models/orders_model.sql`。
- **新增输出列**（与成本文档、ORDER_COST_FIELDS 一致）：
  - 核心：`purchase_amount`、`order_original_amount`、`warehouse_operation_fee`（profit、paid_amount 已有）。
  - 平台费用 6 项：`shipping_fee`、`promotion_fee`、`platform_commission`、`platform_deduction_fee`、`platform_voucher`、`platform_service_fee`。
  - 双总费用列：`platform_total_cost_derived`（= 订单原始金额 − 采购金额 − 利润 − 仓库操作费）、`platform_total_cost_itemized`（= 六项之和）。
- **实现要点**：
  - 在 field_mapping CTE 中，为各平台（Shopee、TikTok、Miaoshou 等）从 `raw_data` 用 COALESCE 抽取成本相关键名（中文/英文导出列名），得到 *_raw 列；键名与 `field_mapping_dictionary`/成本文档一致，某平台暂无成本列时返回 NULL 并在注释中标明「暂无」或「待补充」。
  - 在 cleaned CTE 中将上述 *_raw 转为 NUMERIC 并参与双总费用列计算（derived 与 itemized）。
  - 在最终 SELECT 中输出上述列，使用 COALESCE(..., 0) 等默认值。
- **fact_expenses_month**：按成本文档结论**不纳入**总成本；A 类运营成本仅来自 operating_costs。本变更不修改 fact_expenses_month 的聚合逻辑。

### 2. 年度模块成本落地

- **范围**：年度数据总结相关的后端 API、前端展示及（若存在）Metabase 问题/看板；按店铺下钻时的数据聚合。
- **总成本公式**（与成本文档一致）：总成本 = A 类运营成本（仅来自 `a_class.operating_costs`，按周期/按店铺汇总**所有成本列之和**，当前为四列，扩展后含新增列）+ B 类订单成本（采购金额 + 仓库操作费 + 平台费用，按周期/按店铺汇总）。B 类来自 Orders 模型（或订单事实表）的上述成本列汇总。
- **KPI 与比率**：成本产出比 = 总成本/GMV；ROI = (GMV−总成本)/总成本；毛利率 = (GMV−COGS)/GMV；净利率 = (GMV−总成本)/GMV；COGS 取 B 类采购金额（purchase_amount）；分母为 0 时展示 N/A 或「-」。
- **按店铺下钻**：按成本文档第 5 节约定，实现「operating_costs.店铺ID」与订单侧「platform_code、shop_id」的对应与 JOIN，保证按店铺汇总总成本与比率时口径一致；若当前无统一店铺主数据，可在实现中约定映射表或规则并文档化。
- **数据源**：年度数据总结仅使用 **granularity = 'monthly'** 的数据；成本 KPI 的 B 类部分来自 Orders 模型（月度）或等价聚合。

### 3. 不修改

- 成本口径、列名、公式不再变更，仅按文档实现。
- `fact_expenses_month` 不纳入总成本，A 类仅来自 operating_costs（与成本文档一致）。
- 字段映射辞典与 ORDER_COST_FIELDS 已由 clarify-cost-data-sources 维护，本变更仅引用。

## Impact

### 受影响的规格

- **dashboard**：MODIFIED 年度数据总结的「成本与产出」区块：总成本、各比率的数据来源改为 Orders 模型成本列 + A 类 operating_costs，公式与 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` 一致；按店铺下钻时 A 类与订单侧店铺口径一致。

### 受影响的代码与资源

| 类型     | 位置/模块                               | 修改内容 |
|----------|------------------------------------------|----------|
| SQL 模型 | `sql/metabase_models/orders_model.sql`  | field_mapping/cleaned/最终 SELECT 增加成本列及双总费用列计算 |
| 后端     | 年度数据总结相关 API / 聚合服务         | 总成本 = A 类汇总 + B 类（Orders 成本列）汇总；比率公式；按店铺 JOIN |
| 前端     | 年度数据总结页面                        | 成本与产出区块展示总成本、GMV、成本产出比、ROI、毛利率、净利率；分母为 0 时 N/A 或「-」 |
| 可选     | Metabase 问题/看板                      | 若成本指标由 Metabase 直接查 Orders 模型，则更新问题以使用新列 |

### 依赖关系

- **依赖**：`clarify-cost-data-sources`（成本梳理文档与辞典已定稿）。
- **被依赖**：无；本变更为成本落地的首轮实现。

## Non-Goals

- 不在此变更中变更 cost 口径或新增 A/B 类成本项。
- 不将 fact_expenses_month 纳入总成本（成本文档已明确不纳入）。
- 不实现库存/产品 unit_cost 作为 COGS 的自动回填（可选逻辑可后续单独变更）。

## 实现说明（4.3）

- **成本口径与公式**：以 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` 为准。
- **Orders 模型成本列**：与 `ORDER_COST_FIELDS`（如 `backend/services/field_mapping/standard_fields.py`）一致；年度 KPI 的 B 类聚合由 `backend/services/annual_cost_aggregate.py` 从订单事实表 monthly 的 raw_data 抽取并汇总。
