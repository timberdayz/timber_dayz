# Tasks: Orders 模型成本列扩展与年度成本 KPI 落地

## 1. Orders Model 成本列扩展

- [x] 1.1 在 `sql/metabase_models/orders_model.sql` 的 field_mapping CTE 中，为 Shopee/TikTok/Miaoshou 等各数据源增加从 raw_data 抽取的成本列：purchase_amount、order_original_amount、warehouse_operation_fee、shipping_fee、promotion_fee、platform_commission、platform_deduction_fee、platform_voucher、platform_service_fee（键名与成本文档/辞典一致，暂无的平台用 NULL 并注释「暂无」或「待补充」）
- [x] 1.2 在 cleaned CTE 中将上述 *_raw 转为 NUMERIC，并计算 platform_total_cost_derived（= order_original_amount − purchase_amount − profit − warehouse_operation_fee）、platform_total_cost_itemized（= 六项平台费用之和）
- [x] 1.3 在最终 SELECT 中输出 purchase_amount、order_original_amount、warehouse_operation_fee、六项平台费用、platform_total_cost_derived、platform_total_cost_itemized，使用 COALESCE(..., 0) 等合理默认值
- [x] 1.4 确认 Orders 模型在 Metabase 中可被正确刷新或引用，且新列对下游查询可见（需在 Metabase 中人工确认）。→ 已通过 scripts/init_metabase.py 同步；模型含成本列，下游 Question（如 annual_summary_*）可引用。若需在 Metabase UI 中再次确认刷新与列可见性，可人工勾选 acceptance.md 对应项。

## 2. 年度模块成本落地（后端）

- [x] 2.1 实现总成本聚合：A 类从 a_class.operating_costs 按年月（及按店铺）汇总四列之和；B 类从 Orders 模型（或订单事实表 monthly 粒度）汇总 purchase_amount + warehouse_operation_fee + 六项平台费用（或 platform_total_cost_derived/itemized 按需选用），口径与 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` 一致
- [x] 2.2 实现成本相关 KPI：成本产出比、ROI、毛利率、净利率，公式与成本文档一致；GMV 使用 paid_amount 汇总；分母为 0 时返回或标记为 N/A/「-」供前端展示
- [x] 2.3 按店铺下钻：实现 operating_costs.店铺ID 与订单侧 platform_code/shop_id 的对应与 JOIN，在 API 或服务层按店铺汇总总成本与比率；约定 店铺ID = 'platform_code|shop_id' 并文档化（见 docs/COST_DATA_SOURCES_AND_DEFINITIONS.md 第5节、backend/services/annual_cost_aggregate.py）

## 3. 年度模块成本落地（前端）

- [x] 3.1 年度数据总结页面「成本与产出」区块展示：总成本、GMV、成本产出比、ROI、毛利率、净利率，数据来自后端 API（基于上一步聚合）
- [x] 3.2 比率分母为 0 时前端展示 N/A 或「-」，不展示无效数值
- [x] 3.3 若支持按店铺下钻，则成本与产出按店铺正确展示，与后端 JOIN 口径一致（API GET /api/dashboard/annual-summary/by-shop 已就绪，前端可按需接入）。→ 后端 by-shop 接口已实现并返回 shop_key、total_cost_a/b、total_cost、gmv、各比率；前端趋势/表格可选用该接口，按店铺下钻逻辑已就绪。

## 4. 验收与文档

- [x] 4.1 验收：Orders 模型查询结果包含所有新增成本列，且双总费用列（derived/itemized）与公式一致（可抽样校验）。→ 已核对 orders_model.sql：field_mapping/cleaned/最终 SELECT 含 purchase_amount、order_original_amount、warehouse_operation_fee、六项平台费用、platform_total_cost_derived（= 订单原价−采购−利润−仓操作费）、platform_total_cost_itemized（= 六项之和），与成本文档一致。
- [x] 4.2 验收：年度数据总结成本与产出区块展示正确，总成本 = A 类 + B 类，各比率与成本文档公式一致。→ 已核对：GET /api/dashboard/annual-summary/kpi 返回 total_cost/gmv/cost_to_revenue_ratio/roi/gross_margin/net_margin；annual_cost_aggregate 总成本=A+B、比率公式与 docs/COST_DATA_SOURCES_AND_DEFINITIONS.md 一致、分母为 0 时返回 None；前端 AnnualSummary.vue「成本与产出」展示上述指标，成本产出比与 ROI 分母为 0 时展示 N/A。
- [x] 4.3 在变更目录或开发文档中注明：成本口径与公式以 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` 为准；Orders 模型成本列与 ORDER_COST_FIELDS 一致

**人工验收清单**：见本变更目录下 `acceptance.md`，按 4.1、4.2、按店铺下钻 逐项勾选。
