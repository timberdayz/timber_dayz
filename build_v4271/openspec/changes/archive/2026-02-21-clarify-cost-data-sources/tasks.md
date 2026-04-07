# Tasks: 成本数据来源与口径梳理

## 1. A 类成本调研与文档化

- [x] 1.1 列出 a_class.operating_costs 表结构、字段含义、录入入口（API/前端）、按店铺ID+年月的唯一约束与索引
- [x] 1.2 确认 fact_expenses_month 的 period_month 格式、base_amt 含义、与 operating_costs 的科目划分；在成本梳理文档中给出明确结论：fact_expenses_month 不纳入总成本，A 类仅来自 operating_costs
- [x] 1.3 在成本梳理文档中固定：A 类包含项、来源、汇总方式（按周期、按店铺）

## 2. B 类成本调研与文档化

- [x] 2.1 调研各平台（含 Shopee、TikTok、Miaoshou）订单导出/采集中与成本相关的列名（采购价/采购金额、利润、订单原始金额/产品折后价格、实付金额/买家实付金额、仓库操作费；运费、推广费、平台佣金、平台扣费、代金券、服务费）
- [x] 2.2 确认字段映射中上述列对应的标准名（英文 field_code）与 raw_data 键名（含 b_class.fact_*_orders_* 的 raw_data 样本）
- [x] 2.3 在成本梳理文档中固定：Orders Model 扩展英文列名清单（purchase_amount、order_original_amount、warehouse_operation_fee、shipping_fee、promotion_fee、platform_commission、platform_deduction_fee、platform_voucher、platform_service_fee、platform_total_cost_derived、platform_total_cost_itemized）及双总费用列公式与校验用途
- [x] 2.4 明确 COGS 取数顺序：订单成本字段（采购金额）优先 vs GMV−利润；库存 unit_cost 的适用场景
- [x] 2.5 在成本梳理文档中固定：B 类五个核心字段、平台费用分项、恒等式、平台总费用_倒推须减仓库操作费的理由（第二方平台 vs 第三方仓库）

## 3. 口径与使用场景

- [x] 3.1 文档化总成本公式：A 类（仅 operating_costs）+ B 类（采购金额 + 仓库操作费 + 平台费用）；GMV 口径（paid_amount）；fact_expenses_month 不纳入总成本
- [x] 3.2 文档化各比率公式（成本产出比、ROI、毛利率、净利率）及分母为 0 的展示规则
- [x] 3.3 文档化按店铺下钻时 A 类 operating_costs.店铺ID 与订单侧（platform_code、shop_id）的对应规则，以及 JOIN 一致方案

## 4. 字段映射辞典与标准字段同步

- [x] 4.1 将成本梳理文档中约定的 B 类订单成本英文 field_code 同步至 `field_mapping_dictionary`：已在 `scripts/init_field_mapping_dictionary.py` 的 INITIAL_DICTIONARY 中为 orders 域增加上述成本相关条目（含 cn_name、description、synonyms 等）
- [x] 4.2 同步更新 `backend/services/field_mapping/standard_fields.py`：已新增 ORDER_COST_FIELDS 并纳入 ALL_STANDARD_FIELDS/FIELD_CATEGORIES；成本梳理文档定稿后须与之一致并注明

## 5. 评审与收尾

- [ ] 5.1 与业务/财务（可选）确认口径与科目边界
- [x] 5.2 将成本梳理文档定稿并放入 docs/ 或本 change 目录；在 openspec 中通过 validate
- [x] 5.3 标注后续实现归属（如「年度模块成本落地」或「Orders Model 成本列扩展」变更），便于年度模块收尾时按文档实现
