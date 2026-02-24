## ADDED Requirements

### Requirement: 年度数据总结成本 KPI 实现
年度数据总结的「成本与产出」区块 SHALL 使用已实现的 Orders 模型成本列与 A 类运营成本汇总，总成本与各比率公式 SHALL 与 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` 一致。

#### Scenario: B 类成本来自 Orders 模型
- **WHEN** 系统计算年度数据总结的总成本或订单成本部分
- **THEN** B 类订单成本 SHALL 来自 Orders 模型（或等价月度聚合）的输出列：purchase_amount、warehouse_operation_fee、平台费用六项（或 platform_total_cost_derived/itemized），仅使用 granularity = 'monthly' 的数据
- **AND** 总成本 = A 类运营成本（仅来自 a_class.operating_costs，所有成本列之和，按周期/按店铺汇总）+ B 类订单成本（采购金额 + 仓库操作费 + 平台费用）

#### Scenario: 比率公式与分母为 0
- **WHEN** 系统展示成本产出比、ROI、毛利率、净利率
- **THEN** 公式 SHALL 与成本文档一致：成本产出比 = 总成本/GMV，ROI = (GMV−总成本)/总成本，毛利率 = (GMV−COGS)/GMV，净利率 = (GMV−总成本)/GMV；GMV 为 paid_amount 汇总，COGS 为 B 类采购金额
- **AND** 分母为 0 时 SHALL 展示 N/A 或「-」

#### Scenario: 按店铺下钻口径一致
- **WHEN** 用户按店铺查看成本与产出
- **THEN** 系统 SHALL 按成本文档第 5 节约定，将 a_class.operating_costs.店铺ID 与订单侧 platform_code、shop_id 对应后 JOIN 聚合，保证按店铺的总成本与比率归属正确
