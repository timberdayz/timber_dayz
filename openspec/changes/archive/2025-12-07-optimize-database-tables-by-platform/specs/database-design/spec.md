## ADDED Requirements

### Requirement: B类数据表按平台分表规则
系统 SHALL 按照平台-数据域-子类型-粒度分表，确保用户可以通过表名直接识别数据归属。

#### Scenario: 表名格式规范
- **WHEN** 系统创建B类数据表时
- **THEN** 系统使用PlatformTableManager动态创建表
- **AND** 表名格式：
  - 无sub_domain：`fact_{platform}_{data_domain}_{granularity}`（如`fact_shopee_orders_daily`）
  - 有sub_domain：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`（如`fact_shopee_services_ai_assistant_monthly`）
- **AND** 平台代码（platform）必须小写（如`shopee`、`tiktok`、`miaoshou`）
- **AND** 数据域（data_domain）必须小写（如`orders`、`products`、`services`、`analytics`）
- **AND** 粒度（granularity）必须小写（如`daily`、`weekly`、`monthly`、`snapshot`）
- **AND** 子类型（sub_domain）必须小写（如`ai_assistant`、`agent`）
- **AND** 表名由PlatformTableManager.get_table_name()方法生成，确保格式统一
- **AND** **所有B类数据表存储在`b_class` schema中，便于Metabase中清晰区分和管理**

#### Scenario: 表结构规范
- **WHEN** 系统创建B类数据表时
- **THEN** 表必须包含以下系统字段：
  - `id` (BIGSERIAL PRIMARY KEY)
  - `platform_code` (VARCHAR(32) NOT NULL)
  - `shop_id` (VARCHAR(256))
  - `data_domain` (VARCHAR(64) NOT NULL)
  - `granularity` (VARCHAR(32) NOT NULL)
  - `sub_domain` (VARCHAR(64)) - services域必须NOT NULL，其他域可为NULL
  - `metric_date` (DATE NOT NULL)
  - `file_id` (INTEGER REFERENCES catalog_files(id))
  - `template_id` (INTEGER REFERENCES field_mapping_templates(id))
  - `raw_data` (JSONB NOT NULL)
  - `header_columns` (JSONB)
  - `data_hash` (VARCHAR(64) NOT NULL)
  - `ingest_timestamp` (TIMESTAMP NOT NULL DEFAULT NOW())
  - `currency_code` (VARCHAR(3))
- **AND** 表必须包含以下索引：
  - `platform_code`索引
  - `shop_id`索引
  - `data_domain`索引
  - `granularity`索引
  - `metric_date`索引
  - `file_id`索引
  - `data_hash`索引
  - `currency_code`索引
  - `raw_data` GIN索引
  - `sub_domain`索引（services域）

#### Scenario: 唯一约束规范
- **WHEN** 系统创建B类数据表时
- **THEN** 表必须包含唯一约束，基于以下字段：
  - services域：`data_domain, sub_domain, granularity, data_hash`
  - 其他域：`platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash`
- **AND** 唯一约束名称格式：`uq_{table_name}_hash`
- **AND** 由于shop_id可能为NULL，使用COALESCE处理（PostgreSQL唯一索引支持表达式）
- **AND** 唯一约束确保同一平台、同一店铺、同一数据域、同一粒度、同一data_hash的数据不重复

#### Scenario: 动态表管理
- **WHEN** 系统创建B类数据表时
- **THEN** 系统使用PlatformTableManager动态创建表（如果不存在）
- **AND** **所有B类数据表创建在`b_class` schema中，使用`CREATE TABLE IF NOT EXISTS b_class."{table_name}"`格式**
- **AND** 系统使用DynamicColumnManager根据模板字段添加动态列
- **AND** 动态列类型根据字段数据类型自动推断（VARCHAR、INTEGER、DECIMAL、DATE等）
- **AND** 动态列名称使用归一化的字段名（不含货币代码）
- **AND** 表创建后，系统使用PlatformTableManager.sync_table_columns()同步表列
- **AND** **所有索引创建也在`b_class` schema中**

#### Scenario: 动态表名查询
- **WHEN** 系统查询B类数据表时
- **THEN** 系统使用PlatformTableManager.get_table_name()生成表名
- **AND** 系统使用SQLAlchemy的text()函数执行原始SQL查询
- **AND** 表名作为字符串参数传入（用双引号包裹，避免大小写问题）
- **AND** 使用参数化查询（`:platform_code`），防止SQL注入
- **AND** PostgreSQL完全支持这种动态表名查询
- **AND** **查询时使用`b_class."{table_name}"`格式，或依赖`search_path`自动查找（向后兼容）**
- **AND** **跨平台查询：从`dim_platforms`表查询所有平台，使用UNION ALL合并查询结果**

## MODIFIED Requirements

### Requirement: 数据归属规则
系统 SHALL 明确定义数据归属规则，包括shop_id、account_id等归属字段的使用规则。

#### Scenario: 数据归属规则定义
- **WHEN** 系统设计数据库表结构
- **THEN** 系统应根据数据归属规则确定是否需要shop_id、account_id等归属字段
- **THEN** 系统应明确数据归属字段的来源（源数据、文件元数据、默认值等）
- **AND** **B类数据表必须按平台分表，表名包含platform_code信息**
- **AND** **用户可以通过表名直接识别数据归属（平台-数据域-子类型-粒度）**

