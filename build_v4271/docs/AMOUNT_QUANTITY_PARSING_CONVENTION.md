# 金额/数量与解析约定

本文档为变更 `add-metabase-sql-retain-amount-sign` 的权威交付物，约定 Metabase 模型与 Question 中金额、数量的符号、单一数据源、畸形数据处理及店铺别称与 shop_id 映射规则。

---

## 1. 符号约定

- **事实层保留负号**：凡从 `raw_data` 或事实表解析出的金额、数量等可能为负的字段，不清除 ASCII `-`，正则允许负号（如 `[^0-9.-]`）；仅清除千分位、空格、Unicode 破折号（CHR(8212)/CHR(8211)）等。
- **仅非负列**：若某列业务上确定仅非负，需在 SQL 注释中明确说明「本列仅非负，故意去除负号」。
- **各模型列清单**：
  - **Orders**：允许负 — sales_amount、paid_amount、product_original_price、estimated_settlement_amount、profit、purchase_amount、order_original_amount、warehouse_operation_fee、平台费用六项、platform_total_cost_derived/itemized；数量 buyer_count、order_count、product_quantity 可为负（退货等）。
  - **Analytics**：允许负 — gmv、order_count 等与金额/数量相关列（依实际列名）；仅非负列需注释。
  - **Products**：允许负 — price、gmv、sales_amount 等；仅非负列需注释。
  - **Inventory**：允许负 — unit_cost、inventory_value、各类库存数量（若业务有调整/冲销）；仅非负列需注释。
  - **Services**：允许负 — gmv、order_count 等；仅非负列需注释。

---

## 2. 单一数据源（不重复解析）

- **唯一规范来源**：金额/数量的「raw → 数值」解析逻辑**仅在一处**定义并维护：Metabase 模型（`sql/metabase_models/*.sql`）。下游（Question、后端 API、看板）不得在自身代码中再次实现 REGEXP_REPLACE、REPLACE、NULLIF 等同一套解析；应**基于模型查询结果**或基于与模型约定完全一致的共享规则（若暂时无法查模型，则必须文档引用并计划迁移）。
- **后端消费方式**：后端不直接执行模型 SQL。设计为**通过 Metabase Question 查询模型**——以模型为数据源的 Question（如年度 KPI、按店铺下钻等）由 Metabase 执行，后端通过 **Metabase API 执行相应 Question** 获取已解析的金额/数量结果，再为前端或缓存提供数据；解析逻辑仅在模型中维护，后端不再对 `raw_data` 做重复解析。
- **年度 KPI 数据源**：年度 KPI（总成本、GMV、比率）数据源为**通过 Metabase Question 查询 Orders 模型**所得结果（或与模型约定一致的临时方案），避免后续新增重复解析。若某接口短期内仍直接查事实表，则解析规则须与模型约定完全一致，并在本文档注明「与 xxx 模型一致，待改为通过 Question 获取」。

### 2.1 迁移计划（年度 KPI 后端）

- **当前**：`backend/services/annual_cost_aggregate.py` 的 `get_annual_cost_aggregate`、`get_annual_cost_aggregate_by_shop` 仍直接查事实表并对 `raw_data` 做与 Orders 模型一致的解析（保留符号、正则 `[^0-9.-]`），模块 docstring 已注明「待改为通过 Question 获取」。
- **目标**：在后续变更中改为通过 **Metabase API 执行 Question**（`annual_summary_kpi`、`annual_summary_by_shop`、`annual_summary_trend`）获取总成本与 GMV，删除上述两处对 `raw_data` 的解析，实现单一数据源。
- **时机**：在 Metabase Question 与模型已稳定、且后端可依赖 Metabase 服务可用性的前提下实施，避免临时方案长期化。

---

## 3. 畸形数据策略

- **无法解析**：经清洗与正则后仍无法转为合法数值的单元格（如空串、纯符号、多负号、非数字主导等），该列输出 **NULL**；在最终 SELECT 层若业务需要可 COALESCE 为 0，但中间 cleaned 层保持 NULL 以区分「解析失败」与「真零」；**不因单格解析失败而中断整行**（不抛错导致整行丢失）。
- **前导/尾随负号**：支持 `-123.45` 与 `123.45-`（PostgreSQL `::numeric` 支持）；正则允许负号时保留，不做额外截断。
- **多负号或明显非法**：如 `--5`、`1-2-3` 等，经当前正则后若 `::numeric` 报错或结果不可接受，应在模型中用 **CASE、NULLIF 或先校验再 ::numeric 等安全转换**兜底为 NULL（PostgreSQL 无 TRY_CAST），不向上抛错。
- **约定**：NULL = 解析失败，0 = 业务零或报表默认；建议采集/ETL 层对异常值做监控。

---

## 4. 店铺别称与 shop_id 映射

- **raw_data 键名**：店铺别称以 `raw_data->>'店铺'` 为主键名；可扩展 COALESCE( raw_data->>'店铺', raw_data->>'店铺名称' )，以实际采集/字段映射为准。
- **映射表**：`core.platform_accounts`；匹配列：`store_name`、`account_alias`；关联键：`platform`（与订单 `platform_code` 一致）、输出列 `shop_id`。
- **多匹配取数规则**：多条匹配时按 `id` 取一条（如 ORDER BY id LIMIT 1）。
- **未匹配时**：**保留原 fact.shop_id**（可能为空），模型层**不默认为 'none'**；展示层（Question/接口）可按需 COALESCE（如 `'unknown'`）。
- **与按店铺下钻一致性**：按店铺下钻与店铺键使用 `platform_code|shop_id`（使用模型解析后的 shop_id），与 `docs/COST_DATA_SOURCES_AND_DEFINITIONS.md` 一致。

---

**文档版本**：与变更 `add-metabase-sql-retain-amount-sign` 一致。
