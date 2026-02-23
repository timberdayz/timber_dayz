# 人工验收清单：add-orders-model-cost-and-annual-kpi

成本口径与公式以 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` 为准；Orders 模型成本列与 `ORDER_COST_FIELDS` 一致。

---

## 4.1 Orders 模型成本列与双总费用

- [ ] **数据源**：在 Metabase 中打开或引用 Orders 模型（`sql/metabase_models/orders_model.sql` 对应数据源），确认可正确刷新/执行。
- [ ] **成本列存在**：查询结果包含以下列（可抽样 1～2 个平台/粒度）：
  - `purchase_amount`、`order_original_amount`、`warehouse_operation_fee`
  - 六项平台费用：`shipping_fee`、`promotion_fee`、`platform_commission`、`platform_deduction_fee`、`platform_voucher`、`platform_service_fee`
  - `platform_total_cost_derived`、`platform_total_cost_itemized`
- [ ] **双总费用公式校验**（任选几条记录）：
  - `platform_total_cost_derived` ≈ 订单原始金额 − 采购金额 − 利润 − 仓库操作费（允许四舍五入差异）
  - `platform_total_cost_itemized` = 六项平台费用之和
- [ ] **1.4**：新列对下游 Metabase 问题/看板可见（若有引用 Orders 模型的下游，确认其可选用新列）。

---

## 4.2 年度数据总结 - 成本与产出区块

- [ ] **接口**：`GET /api/dashboard/annual-summary/kpi?granularity=monthly&period=YYYY-MM`（及 `yearly` + `YYYY`）返回体中包含：
  - `total_cost`、`gmv`、`cost_to_revenue_ratio`、`roi`、`gross_margin`、`net_margin`
- [ ] **总成本口径**：总成本 = A 类（operating_costs 四列之和）+ B 类（订单事实表 monthly：采购金额 + 仓库操作费 + 六项平台费用）；可与数据库/成本文档手工核对同一周期是否一致。
- [ ] **比率公式**（与成本文档一致）：
  - 成本产出比 = 总成本 / GMV
  - ROI = (GMV − 总成本) / 总成本
  - 毛利率 = (GMV − 采购金额) / GMV
  - 净利率 = (GMV − 总成本) / GMV
- [ ] **分母为 0**：当 GMV 或总成本为 0 时，对应比率为 `null`，前端展示为 N/A 或「-」。
- [ ] **前端**：年度数据总结页「成本与产出」区块展示上述指标，数值与接口一致。

---

## 按店铺下钻（2.3 / 3.3）可选验收

- [ ] **接口**：`GET /api/dashboard/annual-summary/by-shop?granularity=monthly&period=YYYY-MM` 返回 `data` 为数组，每项含 `shop_key`、`total_cost_a`、`total_cost_b`、`total_cost`、`gmv`、各比率。
- [ ] **店铺键约定**：费用管理中 operating_costs.店铺ID 填写为 `platform_code|shop_id` 时，该店铺的 A 类与订单侧 B 类能合并到同一 `shop_key`。
- [ ] **前端**：若年度总结页有按店铺下钻表格/列表，数据与 by-shop 接口一致。

---

验收完成后可在 `tasks.md` 中勾选 4.1、4.2（及 1.4、2.3、3.3 若已验）。
