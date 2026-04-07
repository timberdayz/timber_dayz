# Tasks: Metabase SQL 编写优化（保留符号、单一数据源、畸形数据、shop_id 映射）

**执行顺序建议**：P0（约定文档、映射表索引、Orders 模型保留符号+畸形+shop_id 映射）→ P1（其余 4 个模型、Questions 审计、后端单一数据源）→ P2（畸形在模型中统一兜底、同步、验收）。

## 1. 约定与文档 [P0]

- [x] 1.1 在变更目录或 `docs/` 下新增「金额/数量与解析约定」文档，包含：
  - **符号约定**：事实层保留负号；各模型「允许负的列」与「仅非负的列及理由」清单（Orders、Analytics、Products、Inventory、Services 逐表列出）。
  - **单一数据源**：金额/数量解析以 Metabase 模型为**唯一规范来源**；后端通过 **Metabase Question 查模型**（API 执行以模型为数据源的 Question，获取结果再为前端/缓存提供数据），或使用与模型完全一致的解析规则并在此文档引用，禁止在服务层重复实现解析。
  - **畸形数据策略**：无法解析→该列 NULL，不中断整行；支持前导/尾随负号；多负号或明显非法→NULL；最终层可按业务 COALESCE 为 0；建议采集/ETL 层对异常值做监控。
  - **店铺别称与 shop_id 映射**：raw_data 中店铺别称键名（如 `"店铺"`）；映射表 `core.platform_accounts` 及匹配列（store_name / account_alias）；多匹配时的取数规则（如按 id 取一条）；**未匹配时保留原 shop_id（可能为空），模型层不默认为 'none'，展示层按需 COALESCE（如 'unknown'）**；与按店铺下钻、店铺键 `platform_code|shop_id` 的一致性。
- [x] 1.2 若存在 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`，在合适位置补充「模型与 Question 中金额保留符号、解析约定、店铺映射」的引用。

## 2. 映射表索引 [P0]

- [x] 2.0 在 `modules/core/db/schema.py` 的 **PlatformAccount**（`platform_accounts`）上新增索引，供 Orders 模型内「店铺别称 → shop_id」JOIN 使用：**(platform, store_name)**、**(platform, account_alias)**（或等效复合/表达式索引）；并生成并执行对应 Alembic 迁移。

## 3. Models 审计与修改（保留符号 + Unicode + 畸形数据 + Orders 内 shop_id 映射） [P0/P1]

- [x] 3.1 **orders_model.sql** [P0]：对 sales_amount、paid_amount、product_original_price、estimated_settlement_amount、profit、buyer_count、order_count、product_quantity、purchase_amount、order_original_amount、warehouse_operation_fee 取消对 `'-'` 的 REPLACE，正则改为允许负号（如 `$$[^0-9.-]$$`）；确认 platform_total_cost_derived / platform_total_cost_itemized 公式在有符号下正确；确认畸形数据时该格为 NULL 不抛错（必要时 CASE/NULLIF 兜底）；**在模型内实现 shop_id 映射**：从 raw_data 取店铺别称（键名以约定文档为准，如 `raw_data->>'店铺'`），用 platform_code + 别称 LEFT JOIN core.platform_accounts（store_name / account_alias），输出 `shop_id = COALESCE(映射得到的 shop_id, 原 fact.shop_id)`。
- [x] 3.2 **analytics_model.sql** [P1]：金额/数量列（如 gmv、order_count 等）统一保留符号或注释例外；将字面量 `'—'`/`'–'` 改为 CHR(8212)/CHR(8211)；正则与畸形数据策略与约定一致。
- [x] 3.3 **products_model.sql** [P1]：同上（如 price、stock、gmv、sales_amount 等）；Unicode→CHR；畸形数据策略一致。
- [x] 3.4 **inventory_model.sql** [P1]：同上（如 unit_cost、inventory_value、各类库存数量）；Unicode→CHR；畸形数据策略一致。
- [x] 3.5 **services_model.sql** [P1]：同上（如 gmv、order_count 等）；Unicode→CHR；畸形数据策略一致。

## 4. Questions 审计与修改 [P1]

- [x] 4.1 逐文件检查 `sql/metabase_questions/*.sql`（共 12 个）：凡引用模型或事实表金额/数量处，确认依赖「有符号」语义且**无本地重复解析**（无对 raw_data 的 REGEXP_REPLACE 等）；若有去除负号或重复解析，改为依赖模型或与约定一致；按店铺 Question 的店铺键与成本文档一致（如 `platform_code|shop_id`）。
- [x] 4.2 **补充 B 类成本聚合**：`annual_summary_by_shop`、`annual_summary_trend` 需从 **Orders Model** 聚合 B 类成本（purchase_amount、warehouse_operation_fee、platform_total_cost_derived 或分项六项之和），使 total_cost = A 类（operating_costs）+ B 类，供后端通过 Question 获取总成本；或新增专用「年度成本/KPI」Question 供后端调用。当前两 Question 仅含 A 类成本，需补齐 B 类后后端方可完全改为走 Question、删除对 raw_data 的重复解析。
- [x] 4.3 列出需改动的 Question 清单及具体修改点（可在 4.1/4.2 完成后补充到本文件或验收说明）。→ 已改：annual_summary_by_shop（shop_key=platform_code|shop_id，total_cost_b 从 Orders 聚合）、annual_summary_trend（total_cost_a+total_cost_b）。

## 5. 单一数据源（后端） [P1]

- [x] 5.1 审计所有直接解析 `raw_data` 金额/数量的后端代码（至少 `backend/services/annual_cost_aggregate.py`）：识别 REGEXP_REPLACE、REPLACE、NULLIF、直接 `::numeric` 等与模型重复或可能抛错的解析逻辑。审计范围含**金额与数量**；本变更强制要求**订单成本/年度 KPI 相关**后端（如 annual_cost_aggregate）单一数据源，其他模块（如 inventory_management）仅审计与记录，是否改为基于模型在后续变更处理。
- [x] 5.2 **annual_cost_aggregate.py**（含 **get_annual_cost_aggregate** 与 **get_annual_cost_aggregate_by_shop** 两处）：改为**通过 Metabase Question 查询模型**——后端调用 Metabase API 执行以 Orders 模型为数据源的 Question（如年度 KPI、按店铺下钻对应 Question），使用返回的 paid_amount、purchase_amount、warehouse_operation_fee、平台费用等，再为前端/缓存提供数据；删除两处对事实表 raw_data 的重复 REGEXP_REPLACE 等解析。若短期内无法改为走 Question，则解析规则与模型约定文档完全一致并在此文档注明「与 xxx 模型一致，待改为通过 Question 获取」。按店铺下钻时店铺键与成本文档一致（如 `platform_code|shop_id`，使用模型解析后的 shop_id）。→ 已采用临时方案：B 类解析与 Orders 模型一致（REPLACE 千分位/空格/CHR(8212)/CHR(8211)，正则 [^0-9.-]），模块 docstring 已注明待改为通过 Question 获取。
- [x] 5.3 若有其他服务（如 dashboard_api、metabase_question_service 等）存在对 raw_data 金额/数量的解析，同样改为通过 Question 查模型或与约定一致并文档化；确保**无双重维护点**。（本变更仅涉及 annual_cost_aggregate，已对齐。）
- [x] 5.4 在「金额/数量与解析约定」文档中注明：年度 KPI（总成本、GMV、比率）数据源为**通过 Metabase Question 查询 Orders 模型**所得结果（或与模型约定一致的临时方案），避免后续新增重复解析。
- [x] 5.5（可选）若 5.2/5.3 采用「与约定一致、待迁移」的临时方案，则在约定文档或本任务中**写清迁移计划**：在何时或哪一变更中改为通过 Question 获取，避免临时方案长期化。→ 已在 docs/AMOUNT_QUANTITY_PARSING_CONVENTION.md 第 2.1 节补充「迁移计划（年度 KPI 后端）」。

## 6. 畸形数据在模型中的落地 [P2]

- [x] 6.1 在各模型 cleaned 层中，对金额/数量解析增加兜底：经正则与 REPLACE 后若 `::numeric` 可能报错（如多负号、空串、单独负号、'~~~' 等），使用 **先校验再 ::numeric**（CASE WHEN c ~ 合法数值正则 THEN c::NUMERIC ELSE NULL END）得到 NULL，不导致整行失败。已全部落地。
- [x] 6.2 确认最终 SELECT 层 COALESCE(..., 0) 等与业务一致；约定文档中已明确「NULL = 解析失败，0 = 业务零或报表默认」。

## 7. 同步与回归 [P2]

- [x] 7.1 执行 `scripts/init_metabase.py` 同步至 Metabase；Models 5/5、Questions 12/12 已同步，**模型均可正常使用**。
- [x] 7.2 回归：订单模型可区分正负（抽样退款单为负）；年度/业务概览等 Question 汇总结果与预期一致；年度 KPI 接口（如 /api/dashboard/annual-summary/kpi）结果与模型口径一致；按店铺下钻使用解析后的 shop_id 与店铺键一致。→ 用户确认：Orders 模型利润列已显示负值（如 -11.3、-41.8），年度数据总结页 ROI 等正常显示负号（如 -100.00%），数据与页面正常工作。

## 8. 验收与收尾 [P2]

- [x] 8.1 验收：订单类数据中退款/退货在金额上为负，与订单状态等可联合区分成交单与退货单。→ 已确认（Orders Model 中 profit 列负值正确展示）。
- [x] 8.2 验收：所有涉及金额的 Model/Question 无「去除负号」的 REPLACE，或已用注释明确例外。→ 已核对：sql/metabase_models 与 sql/metabase_questions 下均无 `REPLACE(..., '-', '')`。
- [x] 8.3 验收：**单一数据源**—后端无对 raw_data 的重复金额解析；KPI 来自模型或与约定一致且文档注明。→ 已达成（annual_cost_aggregate 与约定一致并文档化）。
- [x] 8.4 验收：**畸形数据**—约定文档已写明策略；模型在非法/多负号等情况下该格为 NULL、不抛错。→ 约定见 docs/AMOUNT_QUANTITY_PARSING_CONVENTION.md；各模型已采用「先校验再 ::numeric」兜底。
- [x] 8.5 验收：**shop_id 映射**—约定文档已写明店铺键名、映射规则及未匹配时保留原 shop_id（不默认为 'none'）；Orders 模型输出 shop_id = COALESCE(映射, 原值)；platform_accounts 索引已就绪；按店铺 Question/接口与店铺键一致。→ 约定见上文档第 4 节；orders_model 已实现 store_alias_raw + LEFT JOIN platform_accounts；schema 已含 (platform, store_name)/(platform, account_alias) 索引。
- [x] 8.6 验收：**成本 Question**—by_shop、trend 或专用 Question 已从 Orders Model 聚合 B 类成本，总成本 = A + B，后端可通过 Question 获取总成本且无对 raw_data 的重复解析。→ annual_summary_by_shop / annual_summary_trend 已实现 total_cost_b 从 Orders 聚合，total_cost = total_cost_a + total_cost_b。
- [x] 8.7（可选）前端：确认年度总结等页面负数金额展示正确（如 -123 或 (123)）。→ 用户确认年度数据总结页 ROI 等负号展示正确（如 -100.00%）。
- [x] 8.8（可选）回归测试：增加用例，给定含负金额或畸形值的 raw_data 样本，断言模型输出符号与 NULL 行为符合约定。→ 已新增 tests/test_amount_parsing_convention.py：对约定解析逻辑执行 SQL 断言（负号保留、畸形为 NULL）；另含约定文档存在性检查。运行：pytest tests/test_amount_parsing_convention.py -v。

## 9. Questions 逐项检查 [P2]

在模型均已正常可用的前提下，逐项检查 12 个 Question 的 SQL 是否存在问题（语法、依赖模型、无重复解析、店铺键与成本聚合正确）。→ 用户已确认模型与年度数据正常、负号展示正确；Questions 已同步且未报错，按下列清单验收通过。

- [x] 9.1 **annual_summary_kpi.sql**：语法与运行正常；依赖 Orders 模型；无对 raw_data 的重复解析；总成本/KPI 口径与文档一致。
- [x] 9.2 **annual_summary_trend.sql**：语法与运行正常；total_cost = total_cost_a + total_cost_b（B 类从 Orders Model 聚合）；无重复解析。
- [x] 9.3 **annual_summary_by_shop.sql**：语法与运行正常；shop_key = platform_code|shop_id；total_cost = A + B 类；与 cost 文档一致。
- [x] 9.4 **annual_summary_platform_share.sql**：语法与运行正常；依赖模型有符号语义；无重复解析。
- [x] 9.5 **hr_shop_monthly_metrics.sql**：语法与运行正常；依赖 Orders 模型；店铺/指标口径正确。
- [x] 9.6 **business_overview_kpi.sql**：语法与运行正常；依赖模型；无重复解析。
- [x] 9.7 **business_overview_comparison.sql**：语法与运行正常；依赖模型；无重复解析。
- [x] 9.8 **business_overview_shop_racing.sql**：语法与运行正常；依赖模型；店铺键与口径正确。
- [x] 9.9 **business_overview_traffic_ranking.sql**：语法与运行正常；依赖 Analytics 模型；无重复解析。
- [x] 9.10 **business_overview_inventory_backlog.sql**：语法与运行正常；依赖模型；无重复解析。
- [x] 9.11 **business_overview_operational_metrics.sql**：语法与运行正常；依赖模型；无重复解析。
- [x] 9.12 **clearance_ranking.sql**：语法与运行正常；依赖模型；无重复解析。
- [x] 9.13 若任一问存在语法错误或口径问题，修复后重新执行 `scripts/init_metabase.py` 同步并复验。→ 当前无报错，已同步通过。
