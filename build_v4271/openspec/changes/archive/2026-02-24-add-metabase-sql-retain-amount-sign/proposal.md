# Change: Metabase SQL 编写优化（保留符号、单一数据源、畸形数据处理）

## 当前状态（实施进展）

- **Models**：5 个模型（Orders、Analytics、Products、Inventory、Services）已全部完成保留符号、Unicode→CHR、**安全数值转换**（先校验再 ::numeric，畸形数据兜底为 NULL）、Orders 内 shop_id 映射；正则统一为 `$$[^0-9.-]$$`；**模型均可正常使用**，已通过 `scripts/init_metabase.py` 同步。
- **Questions**：12 个 Question 已同步且无报错；年度 KPI、by_shop、trend 等成本 Question 已确认 total_cost = A + B、店铺键与文档一致。
- **验收**：7.2、8.1–8.8、9.1–9.13 已全部勾选完成（含用户确认负号展示正确、Orders 利润负值及年度总结 ROI 等正常）。**8.8** 已新增 `tests/test_amount_parsing_convention.py` 回归测试；**5.5** 已在约定文档 2.1 节补充迁移计划。

## Why

1. **源表带负号**：订单事实表等源数据中，金额与数量存在负值（退款、退货、亏损、费用冲回等）。若在模型层去除负号，则无法从数值上区分「成交单」与「退货/退款单」，易被误认为均为成交单，影响分析与决策。
2. **当前实现去除负号**：部分 Metabase SQL（如 `orders_model.sql`）通过 `REPLACE(..., '-', '')` 及仅允许 `[^0-9.]` 的正则清洗金额/数量，导致负值变为正值，与源表语义不一致。
3. **业界惯例**：事实层保留符号，汇总时 `SUM` 即净额，与 SAP/Oracle 等 ERP 及主流电商中台一致。
4. **双重维护**：后端（如 `annual_cost_aggregate.py`）直接查事实表并自行实现一套金额解析（REGEXP_REPLACE 等），与模型逻辑重复且可 diverged，导致口径不一致、后续改动需改两处。
5. **畸形数据**：金额/数量解析未统一约定「无法解析时」的处理方式（NULL vs 0、是否支持尾随负号、多负号等），不利于可维护性与排查。

因此，本变更为**架构/数据约定类**：在**保留符号**的基础上，确立**单一数据源（不重复解析）**与**非法/畸形数据**处理约定，并全量落地到 Metabase 模型、Question 与后端，避免后续双重维护与口径分裂。

## What Changes

### 1. 保留符号

- 凡从 `raw_data` 或事实表解析出的金额、数量等可能为负的字段，不清除 ASCII `-`，正则允许负号（如 `[^0-9.-]`）；仅清除千分位、空格、Unicode 破折号（CHR(8212)/CHR(8211)）等。
- 若某列业务上确定仅非负，需在 SQL 注释中明确说明「本列仅非负，故意去除负号」。
- 双总费用列（derived/itemized）及依赖金额的聚合逻辑需在有符号语义下仍正确。

### 2. 单一数据源 / 不重复解析（重点）

- **原则**：金额/数量的「raw → 数值」解析逻辑**仅在一处**定义并维护：Metabase 模型（`sql/metabase_models/*.sql`）。下游（Question、后端 API、看板）**不得**在自身代码中再次实现 REGEXP_REPLACE、REPLACE、NULLIF 等同一套解析；应**基于模型查询结果**或基于与模型约定完全一致的共享规则（若暂时无法查模型，则必须文档引用并计划迁移）。
- **后端如何查模型**：后端不直接执行模型 SQL。设计为**通过 Metabase Question 查询模型**——以模型为数据源的 Question（如年度 KPI、按店铺下钻等）由 Metabase 执行，后端通过 **Metabase API 执行相应 Question** 获取已解析的金额/数量结果，再为前端或缓存提供数据；解析逻辑仅在模型中维护，后端不再对 `raw_data` 做重复解析。若某接口短期内仍直接查事实表，则解析规则须与模型约定完全一致，并在约定文档中注明「与 xxx 模型一致，待改为通过 Question 获取」。
- **文档**：在「金额/数量与解析约定」文档中写明：模型为金额解析的**唯一规范来源**；后端通过 **Question 查模型**（Metabase API 执行 Question）消费数据，或引用该约定；禁止在服务层重复实现解析。

### 3. 非法与畸形数据处理

- **原则**：本提案将「非法/畸形数据」纳入 SQL 编写约定，保证行为一致、可排查。
- **策略**（在约定文档中明确，并在模型中统一落地）：
  - **无法解析**：经清洗与正则后仍无法转为合法数值的单元格（如空串、纯符号、多负号、非数字主导等），该列输出 **NULL**；在最终 SELECT 层若业务需要可 COALESCE 为 0，但中间 cleaned 层保持 NULL 以区分「解析失败」与「真零」；**不因单格解析失败而中断整行**（不抛错导致整行丢失）。
  - **前导/尾随负号**：支持 `-123.45` 与 `123.45-`（PostgreSQL `::numeric` 支持）；正则允许负号时保留，不做额外截断。
  - **多负号或明显非法**：如 `--5`、`1-2-3` 等，经当前正则后若 `::numeric` 报错或结果不可接受，应在模型中用 **CASE、NULLIF 或先校验再 ::numeric 等安全转换**兜底为 NULL（PostgreSQL 无 TRY_CAST，以可行方式实现），不向上抛错。
  - **日志/监控**：约定「解析失败」可通过后续日志或数据质量监控发现；本变更不强制要求模型内写日志，但文档中注明建议在采集或 ETL 层对异常值做统计。
- **与保留符号的关系**：保留符号与畸形数据处理统一在同一套清洗逻辑中（同一正则、同一 NULL 策略），避免两套规则。

### 4. Orders 模型内 shop_id 映射

- **背景**：订单事实表 `shop_id` 常为空，而 `raw_data` 中常有店铺别称（如「新加坡1店」）。用户希望按店铺下钻时能通过「店铺别称 → 账号管理」在**模型内**解析出 `shop_id`，且**暂不改同步代码**，仅在模型中做映射，减少同步改动与错误面。
- **原则**：在 **Orders 模型**内，从 `raw_data` 取出店铺别称（如 `raw_data->>'店铺'`，键名以约定文档为准），用 **platform_code + 该别称** LEFT JOIN **core.platform_accounts**（匹配 `store_name` 或 `account_alias`），得到映射的 `shop_id`；输出列 `shop_id = COALESCE(映射得到的 shop_id, 原 fact.shop_id)`。**未匹配时仅保留原 fact.shop_id**（可能为空），模型层不默认为 `'none'`；约定文档写明「未匹配时保留原值（可能为空），展示层按需 COALESCE（如 `'unknown'`）」。
- **映射表**：使用 `core.platform_accounts`（`store_name`、`account_alias`、`shop_id`、`platform`）。为保障模型内 JOIN 性能，在 `platform_accounts` 上增加对 **(platform, store_name)**、**(platform, account_alias)** 的索引（或等效复合/表达式索引）。
- **约定文档**：在「金额/数量与解析约定」或成本文档中补充：raw_data 中表示店铺别称的键名（如 `"店铺"`）；映射使用的表与列；多条匹配时的取数规则（如取一条、按 id 排序）；**未匹配时保留原 shop_id（可能为空），不默认为 'none'，展示层可按需 COALESCE**；与按店铺下钻、店铺键 `platform_code|shop_id` 的一致性。

### 5. 范围

| 类型 | 路径 | 说明 |
|------|------|------|
| Models | `sql/metabase_models/orders_model.sql` | 保留符号；畸形数据兜底为 NULL；**shop_id 映射**（raw_data 店铺别称 JOIN core.platform_accounts → COALESCE）；Unicode 已用 CHR，保持 |
| Models | `sql/metabase_models/analytics_model.sql` | 审计金额/数量：保留符号或注释例外；Unicode 改为 CHR(8212)/CHR(8211)；畸形数据策略一致 |
| Models | `sql/metabase_models/products_model.sql` | 同上 |
| Models | `sql/metabase_models/inventory_model.sql` | 同上 |
| Models | `sql/metabase_models/services_model.sql` | 同上 |
| Schema/索引 | `modules/core/db/schema.py`（platform_accounts） | 新增 **(platform, store_name)**、**(platform, account_alias)** 索引，供模型内 JOIN 使用 |
| Questions | `sql/metabase_questions/*.sql`（共 12 个） | 依赖模型有符号语义；无本地重复解析；按店铺 Question 的店铺键与成本文档一致；**annual_summary_by_shop、annual_summary_trend 需从 Orders Model 聚合 B 类成本**（或提供专用成本 Question），使后端可完全通过 Question 获取总成本 |
| 后端 | `backend/services/annual_cost_aggregate.py` 及同类 | 改为**通过 Metabase Question 查询模型**（API 执行 Question 获取结果，再为前端/缓存提供数据），或与模型约定完全一致并文档化；删除重复解析逻辑 |
| 文档 | 变更目录或 docs | 「金额/数量与解析约定」：符号、单一数据源、畸形数据策略、各模型允许负/仅非负列清单；**店铺别称键名与 shop_id 映射约定** |

### 6. 不修改

- 源表结构、采集与入库逻辑不改变；**同步/采集代码不因 shop_id 映射而修改**，映射仅在模型内完成。
- 前端展示逻辑不强制在本变更内修改；若发现负数展示异常，可单独任务处理。

### 7. 文档产出

- **金额/数量与解析约定**（变更目录或 `docs/`）：  
  - 事实层保留负号；各模型「允许负的列」与「仅非负的列及理由」清单。  
  - **单一数据源**：模型为解析唯一规范来源；后端通过 **Metabase Question 查模型**（API 执行 Question）获取数据，或引用本约定。  
  - **畸形数据**：无法解析→NULL、不中断整行；支持尾随负号；多负号/非法→NULL；建议采集/ETL 层监控。  
  - **店铺别称与 shop_id 映射**：raw_data 中店铺别称键名（如 `"店铺"`）；映射表 `core.platform_accounts` 及匹配列（store_name / account_alias）；多匹配时的取数规则；**未匹配时保留原 shop_id（可能为空），模型层不默认为 'none'，展示层可按需 COALESCE（如 'unknown'）**；与按店铺下钻、店铺键 `platform_code|shop_id` 的一致性。  
- 若存在 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md`，在合适位置补充本约定引用及「模型与 Question 中金额保留符号、解析约定、店铺映射」的引用。

## Impact

### 受影响的规格

- **dashboard**：MODIFIED 数据看板依赖的 Metabase 模型/问题中，金额与数量以有符号语义展示与汇总；订单类数据可区分成交单（正）与退款/退货（负）；KPI 等数据源来自模型或与模型一致的约定，无重复解析。

### 受影响的代码与资源

| 类型 | 位置 | 修改内容 |
|------|------|----------|
| SQL 模型 | `sql/metabase_models/orders_model.sql` | 保留符号；畸形数据兜底（NULL）；derived/itemized 公式正确；**shop_id 映射**（raw_data 店铺别称 JOIN core.platform_accounts → COALESCE） |
| SQL 模型 | `sql/metabase_models/analytics_model.sql` 等 4 个 | 保留符号或注释例外；Unicode→CHR；畸形数据策略一致 |
| Schema/索引 | `modules/core/db/schema.py`（PlatformAccount） | 新增 **(platform, store_name)**、**(platform, account_alias)** 索引 |
| SQL 问题 | `sql/metabase_questions/*.sql` | 无重复解析；依赖模型有符号语义；按店铺 Question 店铺键与成本文档一致；**by_shop、trend 从 Orders Model 聚合 B 类成本**（或专用成本 Question），供后端通过 Question 获取总成本 |
| 后端 | `backend/services/annual_cost_aggregate.py` 等 | 改为**通过 Metabase Question 查询 Orders 模型**（API 执行 Question），或与模型约定完全一致并文档引用；删除重复 REGEXP_REPLACE 等解析 |
| 文档 | 变更目录或 docs | 「金额/数量与解析约定」含符号、单一数据源、畸形数据、列清单、**店铺别称键名与 shop_id 映射约定** |

### 依赖关系

- 与变更 `add-orders-model-cost-and-annual-kpi` 无冲突；本变更加强「单一数据源」与「畸形数据」约定并落地后端与文档。

## 验收标准

- **Models 可用**：5 个模型在 Metabase 中可正常打开并运行，无语法错误；畸形数据经「先校验再 ::numeric」兜底为 NULL，不抛错（已达成）。
- **保留符号**：涉及金额/数量的清洗无 `REPLACE(..., '-', '')` 且正则允许负号（或注释例外）；订单类模型退款/退货体现为负数。
- **单一数据源**：后端不再对 `raw_data` 重复实现金额解析；通过 **Metabase Question 查模型**（API 执行 Question）获取 KPI 等数据，或解析与模型约定完全一致且在文档中引用；无双重维护点。
- **畸形数据**：约定文档已写明「无法解析→NULL、不中断整行、支持尾随负号、多负号/非法→NULL」；各模型清洗逻辑按该策略实现（含 NULL 兜底）。
- **shop_id 映射**：约定文档已写明 raw_data 店铺键名、映射表与列、多匹配规则、**未匹配时保留原 shop_id（不默认为 'none'），展示层按需 COALESCE**；Orders 模型输出 `shop_id = COALESCE(映射结果, 原 shop_id)`；platform_accounts 已增加 (platform, store_name)/(platform, account_alias) 索引；按店铺下钻与店铺键 `platform_code|shop_id` 一致。
- **成本 Question**：annual_summary_by_shop、annual_summary_trend 或专用成本 Question 已从 Orders Model 聚合 B 类成本（采购金额+仓库操作费+平台费用），总成本 = A 类 + B 类，后端可通过 Question 获取总成本/KPI，无对 raw_data 的重复解析。
- **同步与结果**：执行 `scripts/init_metabase.py` 后，订单模型与相关 Question 汇总结果与有符号、净额语义一致；年度 KPI 等与模型口径一致。
- **Questions 无问题**：12 个 Question 在 Metabase 中可正常执行，无语法或口径错误；依赖模型、无重复解析；成本类 Question（by_shop、trend）总成本 = A + B，店铺键与文档一致（**下一步重点验收**）。
