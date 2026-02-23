# Change: 成本数据来源与口径梳理

## Why

1. **成本是敏感关键板块**：总成本、成本产出比、ROI、毛利率、净利率直接影响经营决策与年度审视；当前年度数据总结、按店铺下钻、趋势图中成本相关指标多为 0 或 N/A，根因是成本数据来源与口径未在系统内统一梳理。
2. **A/B 类成本未显式区分**：提案与代码中约定「总成本 = 运营成本 + 订单成本（含货款、平台费用、贴单费）」，但 A 类（经营/运营成本）与 B 类（货款、平台费用、贴单费等）各自包含哪些项、从哪里来、如何落库与聚合，缺少一份权威梳理，导致实现时不一致或遗漏。
3. **年度模块收尾依赖成本**：年度数据总结模块其余能力已可用，仅成本板块未理清；成本梳理清楚并落地后，方可完成年度模块验收与收尾优化。

因此，本变更**仅做梳理与文档化**：明确 A 类成本有哪些、从哪里来，B 类成本有哪些、从哪里来，以及总成本口径、使用场景与后续实现要点，为后续实现（含 Orders Model 扩展、KPI 成本聚合、按店铺 JOIN 口径）提供单一事实来源。

## What Changes

### 1. A 类成本：定义、项与来源

- **定义**：A 类数据为「用户配置/主数据」，成本侧即**经营成本（运营成本）**，用于按店铺/按年月的人工填报或预估。
- **总成本中的 A 类仅来自 operating_costs**：所有人填的运营/费用（租金、工资、水电、其他及后续扩展的广告费等）均在此表填报；**fact_expenses_month 不纳入总成本**，仅作费用留档或未来分摊等用途，避免与 operating_costs 重复定义。
- **包含项**（以当前系统为准，梳理后固定）：
  - **a_class.operating_costs**：租金、工资、水电费、其他成本（当前四列之和 = 单条记录的运营成本）。后续按**方案 B** 扩展：费用尽可能按科目明确列示，不全部塞入「其他成本」；可通过表结构增加明确列（如广告费、行政费等），由单独变更实现，总成本公式仍为「operating_costs 所有成本列之和」。
- **来源**：
  - operating_costs：来自**费用管理**功能（`/api/expenses`、前端费用管理页），用户按「店铺ID + 年月」录入或导入；表结构见 `modules/core/db/schema.py` 中 `OperatingCost`，库表为 `a_class.operating_costs`（中文字段名：店铺ID、年月、租金、工资、水电费、其他成本）。
  - fact_expenses_month：不参与总成本计算；若存在数据则仅作费用事实留档或分摊参考。
- **使用场景**：年度总结 KPI 总成本（按 period 聚合）、趋势图「经营成本」、按店铺下钻总成本（需与订单侧店铺口径一致，见下）。

### 2. B 类成本：定义、项与来源

- **定义**：B 类数据为「业务发生数据」，成本侧即**与订单/商品直接相关的成本**。订单数据来自**妙手 ERP 导出**，各店铺对 orders 数据域已授权，导出含详细费用明细（如 TikTok/Shopee 的商家运费、平台扣费、仓库操作费等）。
- **五个核心字段**（跨平台统一口径，中文为导出列名，模型内统一用英文列名）：
  - **采购金额**：货物实际采购成本（COGS）。Shopee/TikTok 导出列名如「采购价」「采购金额」。Orders 模型列名：`purchase_amount`。
  - **利润**：实际销售额 − 产品采购成本 − 各种仓库/平台扣费 = 我们获得的毛利润。Orders 模型已有：`profit`。
  - **订单原始金额/产品折后价格**：我们给完折扣后消费者看到的商品售价。Shopee 导出「订单原始金额」，TikTok 导出「产品折后价格」「产品折后金额」。Orders 模型列名：`order_original_amount`（需 COALESCE 多平台键名）。
  - **实付金额/买家实付金额**：买家在用完平台券等之后最终支付的金额。Orders 模型已有：`paid_amount`。
  - **仓库操作费**：第三方仓库贴单等费用，非平台计费，单独成本项。两平台导出列名一致「仓库操作费」。Orders 模型列名：`warehouse_operation_fee`。
- **恒等式**：订单原始金额 − (采购金额 + 利润) = 各种成本（= 仓库操作费 + 平台费用）。
- **平台费用分项**（Orders 模型扩展时从 raw_data 映射，列名全英文）：运费 `shipping_fee`、推广费 `promotion_fee`、平台佣金 `platform_commission`、平台扣费 `platform_deduction_fee`、代金券 `platform_voucher`、服务费 `platform_service_fee`。
- **平台费用双总费用列**（用于校验与可见管理）：
  - **平台总费用_倒推**（`platform_total_cost_derived`）= 订单原始金额 − 采购金额 − 利润 − **仓库操作费**。因仓库操作费属**第三方**仓库成本、平台属**第二方**，只有减去仓库操作费后才能倒推出纯平台费用。
  - **平台总费用_分项合计**（`platform_total_cost_itemized`）= 运费 + 推广费 + 平台佣金 + 平台扣费 + 代金券 + 服务费。与倒推值比对可校验映射与计算是否正确。
- **来源**：
  - **订单事实表**：`b_class.fact_*_orders_{daily|weekly|monthly}` 的 `raw_data`（JSONB），键名取决于各平台导出与字段映射配置；成本梳理文档中固定**各平台**（含 Shopee、TikTok、Miaoshou 等）成本相关列名与 raw_data 键名同 Orders 模型列名的对应关系；若某平台暂无成本列，在文档中标注「暂无」或「待补充」。
  - **Orders Model**：当前仅输出 profit、paid_amount 等，**未**输出采购金额、仓库操作费、平台费用分项及双总费用列；后续变更加入上述英文列。
  - **库存/产品**：若有 unit_cost，可作为 COGS 备选数据源。
- **使用场景**：总成本（运营成本 + 货款 + 平台费用 + 仓库操作费）、毛利率、净利率、趋势图、按店铺下钻；按店铺时需与 A 类店铺口径一致。

### 3. 总成本口径与比率公式（梳理结论）

- **GMV 口径**：本提案及成本相关比率均采用 Orders Model 的 **paid_amount（实付金额）** 汇总，与年度数据总结一致。
- **总成本** = **A 类运营成本（仅来自 a_class.operating_costs，人工填报，按周期/按店铺汇总所有成本列之和）** + **B 类订单成本（系统采集：采购金额/货款 + 仓库操作费/贴单费 + 平台费用，按周期/按店铺汇总）**。fact_expenses_month 不纳入总成本。年度数据总结等模块中的「货款成本」或「订单成本」均指本梳理中的 B 类订单成本（采购金额 + 仓库操作费 + 平台费用），与上述公式一致。
- **成本产出比** = 总成本 / GMV。
- **ROI** = (GMV − 总成本) / 总成本。
- **毛利率** = (GMV − COGS) / GMV；COGS 即 B 类采购金额（或 GMV−利润 若利润口径一致）。
- **净利率** = (GMV − 总成本) / GMV。
- **比率边界**：分母为 0 时展示 N/A 或「-」。

### 4. 交付物（本变更范围内）

- **成本梳理文档**（已放在 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`）：
  - A 类成本：表、字段、录入入口、汇总方式、按店铺时的店铺ID 含义。
  - B 类成本：五个核心字段中英文与含义、恒等式、平台费用分项（6 项）及双总费用列（倒推 vs 分项合计）的公式与校验用途；各平台（含 Shopee、TikTok、Miaoshou 等）成本相关列名与 raw_data 键名；Orders Model **当前输出列**（如 sales_amount、paid_amount、product_original_price、profit 等）与**建议新增列**清单（见上文 2），作为模型与字段映射的单一事实来源；COGS 取数顺序（订单成本字段优先 vs GMV−利润）。
  - **各平台 raw_data 键名约定**：文档中包含「各平台 raw_data 键名约定（速查）」表，列出标准列名与 Shopee/TikTok/Miaoshou 常见键名（或「待补充」），并注明最终以实际 fact_*_orders_* 与采集/字段映射配置为准。
  - 总成本口径：**A 类仅来自 operating_costs**，fact_expenses_month **不纳入**总成本；A 类可扩展为更多明确费用列（方案 B）。GMV 口径（paid_amount）；**总成本汇总的币种与折算规则**（以系统现有多币种/财务约定为准，未约定时建议以 CNY 汇总展示）。
  - 按店铺下钻时 A 类与订单侧「店铺」口径一致方案（如 operating_costs.店铺ID 与 Orders 的 platform_code+shop_id 的对应规则）；**具体约定由实现时确定并在此文档或配置/代码中固化后引用**。
- **字段映射与辞典同步**：成本梳理文档中约定的 B 类订单成本**英文 field_code**须与系统内**字段映射辞典**及 **ORDER_COST_FIELDS** 一致。本变更**已**将上述 field_code 同步至 `scripts/init_field_mapping_dictionary.py` 与 `backend/services/field_mapping/standard_fields.py`；成本梳理文档定稿后须与上述列名保持一致并在文档中注明。
- **tasks.md**：列出梳理步骤（含 A/B 类文档化、口径、辞典同步），不含 Orders Model SQL 实现；模型扩展放在后续变更（如「年度模块成本落地」）。

## Impact

### 受影响的规格

- **dashboard**：成本与产出依赖本梳理结论；年度数据总结的 4.4、6.1 等验收项在成本落地后完成。
- 若新建「成本」能力规格，可引用本梳理文档为数据源与口径依据。

### 受影响的代码

- 本变更以**梳理与文档**为主；**已同步**字段映射辞典与标准字段：`scripts/init_field_mapping_dictionary.py`（orders 域已含成本相关 field_code）、`backend/services/field_mapping/standard_fields.py`（已新增 ORDER_COST_FIELDS 并纳入 ALL_STANDARD_FIELDS），成本梳理文档定稿后须与上述列名一致并注明。
- 后续变更可能涉及：`sql/metabase_models/orders_model.sql`（新增采购金额、仓库操作费、平台费用分项及双总费用列）、`backend/routers/dashboard_api.py`（KPI 成本聚合）、`sql/metabase_questions/annual_summary_*.sql`（按店铺 JOIN 口径）。Orders Model 列扩展由后续变更（如「年度模块成本落地」或「Orders Model 成本列扩展」）实现。

### 依赖关系

- 依赖现有表结构（a_class.operating_costs、fact_expenses_month、b_class.fact_*_orders_*）与字段映射、Orders Model 的现有定义。
- 年度数据总结模块的「成本落地」依赖本梳理结论。

## 非目标（Non-Goals）

- 不在本变更内实现 KPI 成本聚合、Orders Model 改表或新列、按店铺 JOIN 逻辑的代码修改。
- 不在本变更内新增费用管理或 B 类费用导入功能；仅梳理既有数据来源与口径。
- 口径与科目边界已在文档中明确（A 类仅 operating_costs，fact_expenses_month 不纳入）；5.1 与业务/财务确认为可选，不影响归档。
