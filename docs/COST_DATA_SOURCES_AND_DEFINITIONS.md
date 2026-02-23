# 成本数据来源与口径定义

本文档为「成本数据来源与口径梳理」变更的权威交付物，明确 A 类与 B 类成本的包含项、数据来源、汇总方式及总成本与各比率的计算公式，供年度数据总结、按店铺下钻、趋势图等成本相关实现与验收使用。  
**与字段映射辞典及 `backend/services/field_mapping/standard_fields.py` 中 ORDER_COST_FIELDS 列名保持一致。**

---

## 1. GMV 口径

- **GMV**：本系统成本相关比率均采用 Orders Model 的 **paid_amount（实付金额）** 汇总，与年度数据总结一致。
- **比率分母为 0 时**：展示 **N/A** 或 **「-」**，不展示数值。

---

## 2. A 类成本：定义、项与来源

### 2.1 定义

A 类数据为「用户配置/主数据」，成本侧即**经营成本（运营成本）**，用于按店铺/按年月的人工填报或预估。

### 2.2 包含项与表结构

#### a_class.operating_costs（A 类唯一数据源）

**总成本中的 A 类运营成本仅来自本表**，所有人填的运营/费用（租金、工资、水电、其他、以及后续扩展的广告费等）均在此表填报，避免与 fact_expenses_month 重复定义。

| 库表列名（中文） | ORM 属性名 | 类型 | 含义 |
|-----------------|------------|------|------|
| id | id | bigint | 主键 |
| 店铺ID | shop_id | varchar(256) | 店铺标识 |
| 年月 | year_month | varchar(7) | 年月，格式 YYYY-MM |
| 租金 | rent | numeric(15,2) | 租金 |
| 工资 | salary | numeric(15,2) | 工资 |
| 水电费 | utilities | numeric(15,2) | 水电费 |
| 其他成本 | other_costs | numeric(15,2) | 其他成本 |
| 创建时间 | created_at | timestamp | 创建时间 |
| 更新时间 | updated_at | timestamp | 更新时间 |

- **单条运营成本** = 租金 + 工资 + 水电费 + 其他成本（当前四列之和）；若后续扩展新列（见下），则单条 = **所有成本列之和**。
- **唯一约束**：`(店铺ID, 年月)`，名称 `uq_operating_costs_a_shop_month`。
- **索引**：`ix_operating_costs_a_shop`(店铺ID)、`ix_operating_costs_a_month`(年月)。
- **表位置**：`modules/core/db/schema.py` 中 `OperatingCost`，schema 为 `a_class`。
- **扩展原则（方案 B）**：费用应尽可能**按科目明确列示**，不全部塞入「其他成本」。后续可通过表结构扩展增加明确列（如广告费、行政费等），由单独变更（如「扩展 operating_costs 费用科目」）实现：迁移加列、费用管理 API/前端增加录入项，总成本公式仍为「operating_costs 所有成本列之和」。

#### fact_expenses_month（不纳入总成本）

- **定位**：月度费用事实表，按 period_month、expense_type、成本中心等记录实际发生的费用；**不参与总成本计算**，仅作费用留档或未来分摊/财务明细等用途，避免与 operating_costs 重复定义。
- **period_month**：格式与 `dim_fiscal_calendar.period_code` 一致（如 YYYY-MM）。**base_amt** 为人民币（CNY），供留档或分摊参考。
- **与总成本的关系**：**结论：不纳入总成本。** A 类运营成本仅来自 operating_costs；fact_expenses_month 不并入总成本。

### 2.3 录入入口与汇总方式

- **operating_costs**：来自**费用管理**功能。
  - API：`/api/expenses`（GET/POST/PUT/DELETE 等，见 `backend/routers/expense_management.py`）。
  - 前端：费用管理页，用户按「店铺ID + 年月」录入或导入。
- **汇总方式**：
  - **按周期**：按「年月」汇总 operating_costs **所有成本列之和**（当前为四列：租金、工资、水电费、其他成本；扩展后包含新增列）。
  - **按店铺**：按「店铺ID」汇总上述金额。按店铺下钻时，A 类与订单侧店铺口径一致方案见第 5 节。

---

## 3. B 类成本：定义、项与来源

### 3.1 定义

B 类数据为「业务发生数据」，成本侧即**与订单/商品直接相关的成本**。订单数据来自**妙手 ERP 导出**，各店铺对 orders 数据域已授权，导出含详细费用明细（如 TikTok/Shopee 的商家运费、平台扣费、仓库操作费等）。

### 3.2 五个核心字段（跨平台统一口径）

| 含义 | 导出列名（示例） | Orders 模型列名 | 说明 |
|------|------------------|-----------------|------|
| 采购金额 | 采购价、采购金额 | purchase_amount | 货物实际采购成本（COGS） |
| 利润 | 利润 | profit | 实际销售额 − 采购成本 − 各种仓库/平台扣费 = 毛利润；模型已有 |
| 订单原始金额/产品折后价格 | Shopee: 订单原始金额；TikTok: 产品折后价格/产品折后金额 | order_original_amount | 我们给完折扣后消费者看到的商品售价；需 COALESCE 多平台键名 |
| 实付金额/买家实付金额 | 实付金额、买家实付金额 | paid_amount | 买家在用完平台券等之后最终支付金额；模型已有 |
| 仓库操作费 | 仓库操作费 | warehouse_operation_fee | 第三方仓库贴单等费用，非平台计费 |

### 3.3 恒等式

- **订单原始金额 − (采购金额 + 利润) = 各种成本**  
- **各种成本 = 仓库操作费 + 平台费用**

### 3.4 平台费用分项（6 项，英文列名）

| 含义 | Orders 模型列名 |
|------|-----------------|
| 运费 | shipping_fee |
| 推广费 | promotion_fee |
| 平台佣金 | platform_commission |
| 平台扣费 | platform_deduction_fee |
| 代金券 | platform_voucher |
| 服务费 | platform_service_fee |

### 3.5 平台费用双总费用列（校验与可见管理）

- **平台总费用_倒推**（`platform_total_cost_derived`）  
  **= 订单原始金额 − 采购金额 − 利润 − 仓库操作费**  
  理由：仓库操作费属**第三方**仓库成本，平台属**第二方**，只有减去仓库操作费后才能倒推出纯平台费用。

- **平台总费用_分项合计**（`platform_total_cost_itemized`）  
  **= 运费 + 推广费 + 平台佣金 + 平台扣费 + 代金券 + 服务费**  
  与倒推值比对可校验 raw_data 映射与计算是否正确。

### 3.6 数据来源

- **订单事实表**：`b_class.fact_*_orders_{daily|weekly|monthly}` 的 `raw_data`（JSONB）。各平台（含 Shopee、TikTok、Miaoshou）成本相关**导出列名**与 **raw_data 键名**以实际妙手导出及字段映射为准；标准英文列名与 field_code 见本文档及 `field_mapping_dictionary`（data_domain=orders）、`ORDER_COST_FIELDS`。若某平台暂无成本列，在实现时标注「暂无」或「待补充」。
- **Orders Model**（`sql/metabase_models/orders_model.sql`）：
  - **当前输出列**（与成本/利润相关）：sales_amount、paid_amount、product_original_price、estimated_settlement_amount、profit 等；**未**输出采购金额、仓库操作费、平台费用分项及双总费用列。
  - **建议新增列**：purchase_amount、order_original_amount、warehouse_operation_fee、shipping_fee、promotion_fee、platform_commission、platform_deduction_fee、platform_voucher、platform_service_fee、platform_total_cost_derived、platform_total_cost_itemized（由后续变更「Orders Model 成本列扩展」实现）。
- **库存/产品**：若有 unit_cost，可作为 COGS 备选数据源。

#### 3.6.1 各平台 raw_data 键名约定（速查）

下表为字段映射辞典中与成本相关的 synonyms / platform_synonyms，供 Orders 模型或采集映射时 COALESCE 取数参考；**最终以实际 `b_class.fact_*_orders_*` 的 raw_data 及采集/字段映射配置为准。**

| 标准列名 | Shopee 常见键名 | TikTok 常见键名 | Miaoshou | 备注 |
|----------|-----------------|----------------|----------|------|
| purchase_amount | 采购金额、采购价 | 采购价 | 待补充 | 辞典 synonyms：采购金额、采购价、cogs、产品成本 |
| order_original_amount | 订单原始金额 | 产品折后价格、产品折后金额 | 待补充 | 辞典 synonyms：产品原价等 |
| warehouse_operation_fee | 仓库操作费、贴单费 | 仓库操作费、贴单费 | 待补充 | 两平台导出列名通常一致 |
| shipping_fee | 运费、商家运费等 | 运费等 | 待补充 | 与 ORDER_FIELDS 共用 |
| promotion_fee | 推广费、平台推广费 | 推广费 | 待补充 | 辞典：营销推广费 |
| platform_commission | 平台佣金、佣金 | 平台佣金、TikTok Shop平台佣金 | 待补充 | — |
| platform_deduction_fee | 平台扣费、平台扣款 | 平台扣费、TikTok Shop平台扣费 | 待补充 | — |
| platform_voucher | 代金券、平台代金券 | 代金券、平台优惠券 | 待补充 | — |
| platform_service_fee | 服务费、平台服务费 | 服务费、TikTok Shop平台服务费 | 待补充 | — |

实现时：某平台若尚无成本列，在 orders_model 或配置中标注「暂无」或「待补充」；键名以实际上传后的 raw_data 键为准，上表仅作默认映射参考。

### 3.7 COGS 取数顺序

1. **优先**：订单成本字段「采购金额」/`purchase_amount`（若 raw_data 存在且已映射）。
2. **备选**：GMV − 利润（仅当利润口径与业务一致时）；或库存/产品的 unit_cost 通过订单行关联得到 COGS。

---

## 4. 总成本口径与比率公式

- **总成本** = **A 类运营成本（仅来自 a_class.operating_costs，人工填报，按周期/按店铺汇总所有成本列之和）** + **B 类订单成本（系统采集：采购金额 + 仓库操作费 + 平台费用，按周期/按店铺汇总）**。  
  fact_expenses_month 不纳入总成本。年度数据总结等模块中的「货款成本」或「订单成本」均指本梳理中的 **B 类订单成本**（采购金额 + 仓库操作费 + 平台费用），与上述公式一致。

- **成本产出比** = 总成本 / GMV  
- **ROI** = (GMV − 总成本) / 总成本  
- **毛利率** = (GMV − COGS) / GMV；COGS 即 B 类采购金额（或 GMV−利润 若利润口径一致）  
- **净利率** = (GMV − 总成本) / GMV  

**GMV 口径**：paid_amount（实付金额）汇总。  
**比率边界**：分母为 0 时展示 N/A 或「-」。

**总成本汇总的币种与折算**：A 类 operating_costs 未在表结构上固定币种，通常按录入币种或默认 CNY 处理。B 类订单可能为多币种。总成本汇总的**展示币种**及 B 类多币种**折算规则**以系统现有多币种/财务约定为准（若有统一汇率表或折算配置则从其规定）；若未单独约定，建议以 **CNY** 汇总展示，折算来源见系统配置或财务文档。

---

## 5. 按店铺下钻：A 类与订单侧店铺口径一致方案

- **A 类**：`a_class.operating_costs.店铺ID`（即 ORM 的 `shop_id`），与费用管理录入时的「店铺」一致。
- **订单侧**：Orders 及事实表使用 `platform_code`、`shop_id`（或组合 `platform_code + shop_id`）标识店铺。
- **JOIN 一致方案**：按店铺下钻时，须约定「operating_costs.店铺ID」与「Orders 的 platform_code、shop_id」的对应规则（例如：同一业务店铺在 A 类用某字符串 ID，在 B 类用 platform_code+shop_id 组合）。成本聚合与年度按店铺接口实现时，按该约定做 JOIN 或关联查询，保证总成本、比率按店铺正确归属。
- **具体约定（add-orders-model-cost-and-annual-kpi 实现）**：  
  - **店铺键**：订单侧统一使用 `platform_code|shop_id` 作为店铺键（如 `shopee|123`、`tiktok|abc`）。  
  - **A 类与 B 类一致**：在费用管理录入运营成本时，**店铺ID** 填写为 `platform_code|shop_id`（与 dim_shops / 订单事实表一致），则后端按店铺汇总时可将 A 类与 B 类合并到同一店铺键。  
  - **实现位置**：`backend/services/annual_cost_aggregate.py` 中 `get_annual_cost_aggregate_by_shop()`；接口 `GET /api/dashboard/annual-summary/by-shop` 返回按 `shop_key` 的列表，每项含 total_cost_a、total_cost_b、total_cost、gmv、各比率。  
  - 若使用其他店铺ID 格式（如仅 shop_id），需后续扩展映射表并在本节引用。

---

## 6. 后续实现归属

- **Orders Model 成本列扩展**：在 `sql/metabase_models/orders_model.sql` 中新增上述建议列及 raw_data 映射、双总费用列计算公式，由后续变更实现。
- **年度模块成本落地**：KPI 成本聚合、按店铺 JOIN、趋势图数据等，依赖本梳理结论，在年度数据总结相关变更中实现。

---

**文档版本**：与变更 `clarify-cost-data-sources` 一致。  
**字段映射**：B 类订单成本英文 field_code 已同步至 `scripts/init_field_mapping_dictionary.py` 与 `backend/services/field_mapping/standard_fields.py`（ORDER_COST_FIELDS），本文档列名与之一致。
