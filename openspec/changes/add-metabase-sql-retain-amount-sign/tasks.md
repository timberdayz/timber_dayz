# Tasks: Metabase SQL 编写优化（保留符号、单一数据源、畸形数据、shop_id 映射）

**执行顺序建议**：P0（约定文档、映射表索引、Orders 模型保留符号+畸形+shop_id 映射）→ P1（其余 4 个模型、Questions 审计、后端单一数据源）→ P2（畸形在模型中统一兜底、同步、验收）。

## 1. 约定与文档 [P0]

- [ ] 1.1 在变更目录或 `docs/` 下新增「金额/数量与解析约定」文档，包含：
  - **符号约定**：事实层保留负号；各模型「允许负的列」与「仅非负的列及理由」清单（Orders、Analytics、Products、Inventory、Services 逐表列出）。
  - **单一数据源**：金额/数量解析以 Metabase 模型为**唯一规范来源**；后端通过 **Metabase Question 查模型**（API 执行以模型为数据源的 Question，获取结果再为前端/缓存提供数据），或使用与模型完全一致的解析规则并在此文档引用，禁止在服务层重复实现解析。
  - **畸形数据策略**：无法解析→该列 NULL，不中断整行；支持前导/尾随负号；多负号或明显非法→NULL；最终层可按业务 COALESCE 为 0；建议采集/ETL 层对异常值做监控。
  - **店铺别称与 shop_id 映射**：raw_data 中店铺别称键名（如 `"店铺"`）；映射表 `core.platform_accounts` 及匹配列（store_name / account_alias）；多匹配时的取数规则（如按 id 取一条）；**未匹配时保留原 shop_id（可能为空），模型层不默认为 'none'，展示层按需 COALESCE（如 'unknown'）**；与按店铺下钻、店铺键 `platform_code|shop_id` 的一致性。
- [ ] 1.2 若存在 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`，在合适位置补充「模型与 Question 中金额保留符号、解析约定、店铺映射」的引用。

## 2. 映射表索引 [P0]

- [ ] 2.0 在 `modules/core/db/schema.py` 的 **PlatformAccount**（`platform_accounts`）上新增索引，供 Orders 模型内「店铺别称 → shop_id」JOIN 使用：**(platform, store_name)**、**(platform, account_alias)**（或等效复合/表达式索引）；并生成并执行对应 Alembic 迁移。

## 3. Models 审计与修改（保留符号 + Unicode + 畸形数据 + Orders 内 shop_id 映射） [P0/P1]

- [ ] 3.1 **orders_model.sql** [P0]：对 sales_amount、paid_amount、product_original_price、estimated_settlement_amount、profit、buyer_count、order_count、product_quantity、purchase_amount、order_original_amount、warehouse_operation_fee 取消对 `'-'` 的 REPLACE，正则改为允许负号（如 `$$[^0-9.-]$$`）；确认 platform_total_cost_derived / platform_total_cost_itemized 公式在有符号下正确；确认畸形数据时该格为 NULL 不抛错（必要时 CASE/NULLIF 兜底）；**在模型内实现 shop_id 映射**：从 raw_data 取店铺别称（键名以约定文档为准，如 `raw_data->>'店铺'`），用 platform_code + 别称 LEFT JOIN core.platform_accounts（store_name / account_alias），输出 `shop_id = COALESCE(映射得到的 shop_id, 原 fact.shop_id)`。
- [ ] 3.2 **analytics_model.sql** [P1]：金额/数量列（如 gmv、order_count 等）统一保留符号或注释例外；将字面量 `'—'`/`'–'` 改为 CHR(8212)/CHR(8211)；正则与畸形数据策略与约定一致。
- [ ] 3.3 **products_model.sql** [P1]：同上（如 price、stock、gmv、sales_amount 等）；Unicode→CHR；畸形数据策略一致。
- [ ] 3.4 **inventory_model.sql** [P1]：同上（如 unit_cost、inventory_value、各类库存数量）；Unicode→CHR；畸形数据策略一致。
- [ ] 3.5 **services_model.sql** [P1]：同上（如 gmv、order_count 等）；Unicode→CHR；畸形数据策略一致。

## 4. Questions 审计与修改 [P1]

- [ ] 4.1 逐文件检查 `sql/metabase_questions/*.sql`（共 12 个）：凡引用模型或事实表金额/数量处，确认依赖「有符号」语义且**无本地重复解析**（无对 raw_data 的 REGEXP_REPLACE 等）；若有去除负号或重复解析，改为依赖模型或与约定一致；按店铺 Question 的店铺键与成本文档一致（如 `platform_code|shop_id`）。
- [ ] 4.2 **补充 B 类成本聚合**：`annual_summary_by_shop`、`annual_summary_trend` 需从 **Orders Model** 聚合 B 类成本（purchase_amount、warehouse_operation_fee、platform_total_cost_derived 或分项六项之和），使 total_cost = A 类（operating_costs）+ B 类，供后端通过 Question 获取总成本；或新增专用「年度成本/KPI」Question 供后端调用。当前两 Question 仅含 A 类成本，需补齐 B 类后后端方可完全改为走 Question、删除对 raw_data 的重复解析。
- [ ] 4.3 列出需改动的 Question 清单及具体修改点（可在 4.1/4.2 完成后补充到本文件或验收说明）。

## 5. 单一数据源（后端） [P1]

- [ ] 5.1 审计所有直接解析 `raw_data` 金额/数量的后端代码（至少 `backend/services/annual_cost_aggregate.py`）：识别 REGEXP_REPLACE、REPLACE、NULLIF、直接 `::numeric` 等与模型重复或可能抛错的解析逻辑。审计范围含**金额与数量**；本变更强制要求**订单成本/年度 KPI 相关**后端（如 annual_cost_aggregate）单一数据源，其他模块（如 inventory_management）仅审计与记录，是否改为基于模型在后续变更处理。
- [ ] 5.2 **annual_cost_aggregate.py**（含 **get_annual_cost_aggregate** 与 **get_annual_cost_aggregate_by_shop** 两处）：改为**通过 Metabase Question 查询模型**——后端调用 Metabase API 执行以 Orders 模型为数据源的 Question（如年度 KPI、按店铺下钻对应 Question），使用返回的 paid_amount、purchase_amount、warehouse_operation_fee、平台费用等，再为前端/缓存提供数据；删除两处对事实表 raw_data 的重复 REGEXP_REPLACE 等解析。若短期内无法改为走 Question，则解析规则与模型约定文档完全一致并在此文档注明「与 xxx 模型一致，待改为通过 Question 获取」。按店铺下钻时店铺键与成本文档一致（如 `platform_code|shop_id`，使用模型解析后的 shop_id）。
- [ ] 5.3 若有其他服务（如 dashboard_api、metabase_question_service 等）存在对 raw_data 金额/数量的解析，同样改为通过 Question 查模型或与约定一致并文档化；确保**无双重维护点**。
- [ ] 5.4 在「金额/数量与解析约定」文档中注明：年度 KPI（总成本、GMV、比率）数据源为**通过 Metabase Question 查询 Orders 模型**所得结果（或与模型约定一致的临时方案），避免后续新增重复解析。
- [ ] 5.5（可选）若 5.2/5.3 采用「与约定一致、待迁移」的临时方案，则在约定文档或本任务中**写清迁移计划**：在何时或哪一变更中改为通过 Question 获取，避免临时方案长期化。

## 6. 畸形数据在模型中的落地 [P2]

- [ ] 6.1 在各模型 cleaned 层中，对金额/数量解析增加兜底：经正则与 REPLACE 后若 `::numeric` 可能报错（如多负号、空串外非法），使用 **NULLIF、CASE 或先校验再 ::numeric 等安全转换**（PostgreSQL 无 TRY_CAST）得到 NULL，不导致整行失败。
- [ ] 6.2 确认最终 SELECT 层 COALESCE(..., 0) 等与业务一致；约定文档中已明确「NULL = 解析失败，0 = 业务零或报表默认」。

## 7. 同步与回归 [P2]

- [ ] 7.1 执行 `scripts/init_metabase.py` 同步至 Metabase。
- [ ] 7.2 回归：订单模型可区分正负（抽样退款单为负）；年度/业务概览等 Question 汇总结果与预期一致；年度 KPI 接口（如 /api/dashboard/annual-summary/kpi）结果与模型口径一致；按店铺下钻使用解析后的 shop_id 与店铺键一致。

## 8. 验收与收尾 [P2]

- [ ] 8.1 验收：订单类数据中退款/退货在金额上为负，与订单状态等可联合区分成交单与退货单。
- [ ] 8.2 验收：所有涉及金额的 Model/Question 无「去除负号」的 REPLACE，或已用注释明确例外。
- [ ] 8.3 验收：**单一数据源**—后端无对 raw_data 的重复金额解析；KPI 来自模型或与约定一致且文档注明。
- [ ] 8.4 验收：**畸形数据**—约定文档已写明策略；模型在非法/多负号等情况下该格为 NULL、不抛错。
- [ ] 8.5 验收：**shop_id 映射**—约定文档已写明店铺键名、映射规则及未匹配时保留原 shop_id（不默认为 'none'）；Orders 模型输出 shop_id = COALESCE(映射, 原值)；platform_accounts 索引已就绪；按店铺 Question/接口与店铺键一致。
- [ ] 8.6 验收：**成本 Question**—by_shop、trend 或专用 Question 已从 Orders Model 聚合 B 类成本，总成本 = A + B，后端可通过 Question 获取总成本且无对 raw_data 的重复解析。
- [ ] 8.7（可选）前端：确认年度总结等页面负数金额展示正确（如 -123 或 (123)）。
- [ ] 8.8（可选）回归测试：增加用例，给定含负金额或畸形值的 raw_data 样本，断言模型输出符号与 NULL 行为符合约定。
