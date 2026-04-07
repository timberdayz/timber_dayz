## MODIFIED Requirements

### Requirement: Metabase 模型与 Question 中金额/数量保留符号
Metabase 模型（`sql/metabase_models/*.sql`）与 Question（`sql/metabase_questions/*.sql`）中，凡从 raw_data 或事实表解析出的金额、数量等可能为负的字段 SHALL 保留负号（不清除 ASCII `-`，正则允许负号），以便区分成交单与退款/退货单；仅清除千分位、空格、Unicode 破折号等。若某列业务上确定仅非负，SHALL 在 SQL 注释中明确说明。

#### Scenario: 订单模型金额列保留符号
- **WHEN** 系统从订单事实表或 raw_data 解析 sales_amount、paid_amount、profit、purchase_amount、order_original_amount、warehouse_operation_fee 等金额/数量列
- **THEN** 清洗逻辑 SHALL 不清除负号（不使用 REPLACE(..., '-', '')），正则 SHALL 允许负号（如 [^0-9.-]）
- **AND** 退款/退货在金额上 SHALL 体现为负数，可与订单状态等字段联合区分成交单与退货单

#### Scenario: 其他模型与 Question 统一约定
- **WHEN** 系统在 analytics、products、inventory、services 模型或任意 Metabase Question 中解析金额/数量
- **THEN** 同一约定 SHALL 适用：保留符号，或在该列旁注释「仅非负」及理由
- **AND** 汇总时 SUM 即净额（含退款/冲销的负值），与事实层语义一致

#### Scenario: 文档化约定
- **WHEN** 开发者新增或修改 Metabase 模型/Question 的金额清洗逻辑
- **THEN** 项目文档 SHALL 包含「金额/数量符号约定」：事实层保留负号；允许负的列与（若有）仅非负的列及理由
- **AND** 避免后续新 SQL 再次去除负号导致成交/退款混淆

### Requirement: 单一数据源（不重复解析）
金额/数量的「raw → 数值」解析逻辑 SHALL 仅在 Metabase 模型中定义并维护。后端不直接执行模型 SQL；后端 KPI、聚合等 SHALL **通过 Metabase Question 查询模型**（即调用 Metabase API 执行以模型为数据源的 Question，获取结果再为前端/缓存提供数据），或使用与模型约定完全一致的规则并在文档中引用；SHALL NOT 在服务层重复实现 REGEXP_REPLACE、REPLACE、NULLIF 等对 raw_data 的解析逻辑，避免双重维护与口径分裂。

#### Scenario: 后端不重复解析
- **WHEN** 后端需要年度 KPI（总成本、GMV、成本产出比等）或任意依赖订单金额的聚合
- **THEN** 数据 SHALL 来自**通过 Metabase API 执行以模型为数据源的 Question** 所得结果，或使用与「金额/数量与解析约定」文档完全一致的解析规则并在文档中明确引用
- **AND** 服务层 SHALL NOT 对事实表 raw_data 再次实现金额/数量解析（如 REGEXP_REPLACE、REPLACE 千分位/负号等），除非已文档注明「与 xxx 模型一致，待改为通过 Question 获取」

#### Scenario: 约定为唯一规范来源
- **WHEN** 任何组件（后端、Question、看板）需要金额/数量数值
- **THEN** 解析规则 SHALL 以模型及「金额/数量与解析约定」文档为唯一规范来源
- **AND** 新增逻辑 SHALL NOT 引入与模型不一致的解析，避免后续出现两套口径

### Requirement: 非法与畸形数据处理
模型层对金额/数量的解析 SHALL 遵循统一的畸形数据处理策略：无法解析时该列输出 NULL，不中断整行；支持前导与尾随负号；多负号或明显非法 SHALL 兜底为 NULL；策略 SHALL 在项目文档中明确并落地到各模型。

#### Scenario: 无法解析不中断整行
- **WHEN** 某单元格经清洗与正则后无法转为合法数值（空串、纯符号、非数字主导等）
- **THEN** 该列 SHALL 输出 NULL（或约定文档允许的 COALESCE 为 0 仅在最终输出层）
- **AND** 该行 SHALL 仍可输出，不因单格解析失败而抛错导致整行丢失

#### Scenario: 支持尾随负号与非法兜底
- **WHEN** 原始值包含前导负号（-123.45）或尾随负号（123.45-）或畸形（如 --5、1-2-3）
- **THEN** 前导/尾随负号 SHALL 被保留并正确解析为负数（PostgreSQL ::numeric 支持）
- **AND** 多负号或明显非法 SHALL 通过 CASE、NULLIF 或先校验再 ::numeric 等安全转换（PostgreSQL 无 TRY_CAST）兜底为 NULL，不向上抛错

#### Scenario: 策略文档化
- **WHEN** 开发者修改或新增金额/数量解析逻辑
- **THEN** 「金额/数量与解析约定」文档 SHALL 包含畸形数据策略：无法解析→NULL、不中断整行、支持尾随负号、多负号/非法→NULL
- **AND** 各模型清洗逻辑 SHALL 与该策略一致

### Requirement: Orders 模型内店铺别称→shop_id 映射
Orders 模型 SHALL 在模型内通过 raw_data 店铺别称与 core.platform_accounts 的 JOIN 解析 shop_id，输出 `shop_id = COALESCE(映射得到的 shop_id, 原 fact.shop_id)`。映射表 SHALL 使用 core.platform_accounts（store_name / account_alias、platform、shop_id）；raw_data 中店铺别称键名、多匹配取数规则及未匹配归属 SHALL 在约定文档中明确。按店铺下钻与年度按店铺成本数据 SHALL 以解析后的 shop_id 及店铺键（如 platform_code|shop_id）为准，与成本文档一致。

#### Scenario: 模型内映射不改同步
- **WHEN** 订单事实表 shop_id 为空或需与账号管理对齐
- **THEN** Orders 模型 SHALL 从 raw_data 取店铺别称（键名以约定文档为准），以 platform_code + 别称 LEFT JOIN core.platform_accounts（store_name 或 account_alias）得到映射的 shop_id
- **AND** 输出 SHALL 为 COALESCE(映射结果, 原 shop_id)，同步/采集代码 SHALL NOT 因本映射而修改

#### Scenario: 年度与按店铺成本数据来源
- **WHEN** 年度 KPI 或按店铺下钻需要成本与 GMV
- **THEN** A 类成本 SHALL 来自 a_class.operating_costs 等约定表；B 类成本 SHALL 通过 Metabase Question 查询 Orders 模型获得（或与模型约定一致的临时方案）
- **AND** 按店铺维度 SHALL 以解析后的 shop_id（含 raw_data 映射）与店铺键（如 platform_code|shop_id）为准，与 docs/COST_DATA_SOURCES_AND_DEFINITIONS.md 一致
