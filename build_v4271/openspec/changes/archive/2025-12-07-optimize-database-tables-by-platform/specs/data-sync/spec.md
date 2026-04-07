## MODIFIED Requirements

### Requirement: 单文件数据同步
系统 SHALL 支持单个Excel文件的数据同步，包括模板查找和配置、数据预览、去重处理和数据入库到B类数据表，**确保所有唯一行都被正确导入**。

#### Scenario: 单文件同步成功流程（DSS架构）- 完整导入
- **WHEN** 用户请求同步单个文件（file_id）
- **THEN** 系统查找文件记录，检查文件状态，查找匹配的模板（TemplateMatcher），使用模板的header_row和header_columns，预览文件数据，补充元数据（platform_code, shop_id），计算data_hash进行去重，调用DataIngestionService入库到B类数据表（**使用动态表名：fact_{platform}_{data_domain}_{sub_domain}_{granularity}，通过PlatformTableManager生成**，JSONB格式），更新文件状态为ingested，并返回同步结果
- **AND** 系统验证数据完整性（行数、字段完整性、data_hash唯一性）
- **AND** 系统记录统计信息（staged, imported, quarantined=0）
- **AND** 系统跳过字段映射、数据标准化、业务逻辑验证和数据隔离（DSS架构原则）
- **AND** **系统确保所有唯一行都被导入（imported行数应等于源文件唯一行数，排除合法重复）**
- **AND** **系统使用模板配置的核心字段（deduplication_fields）计算data_hash，如果模板未配置则使用默认配置**
- **AND** **系统使用PlatformTableManager动态创建表（如果不存在），表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}**

#### Scenario: 动态表名生成
- **WHEN** 数据同步开始时
- **THEN** 系统使用PlatformTableManager.get_table_name()生成表名
- **AND** 表名格式：
  - 无sub_domain：`fact_{platform}_{data_domain}_{granularity}`（如`fact_shopee_orders_daily`）
  - 有sub_domain：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`（如`fact_shopee_services_ai_assistant_monthly`）
- **AND** 平台代码（platform）必须小写（如`shopee`、`tiktok`、`miaoshou`）
- **AND** 数据域（data_domain）必须小写（如`orders`、`products`、`services`、`analytics`）
- **AND** 粒度（granularity）必须小写（如`daily`、`weekly`、`monthly`、`snapshot`）
- **AND** 子类型（sub_domain）必须小写（如`ai_assistant`、`agent`）
- **AND** 系统使用PlatformTableManager.ensure_table_exists()确保表存在（如果不存在则创建）
- **AND** 系统使用PlatformTableManager.sync_table_columns()同步表列（根据模板字段添加动态列）
- **AND** **所有B类数据表创建在`b_class` schema中，使用`CREATE TABLE IF NOT EXISTS b_class."{table_name}"`格式**
- **AND** **查询时使用`b_class."{table_name}"`格式，或依赖`search_path`自动查找**

#### Scenario: 数据行数验证（B类数据表）- 完整导入
- **WHEN** 数据同步完成后
- **THEN** 系统验证B类数据表（**使用动态表名**）数据行数与文件行数一致性
- **AND** 系统记录数据行数统计（total_rows, imported, quarantined=0）
- **AND** 系统验证数据以JSONB格式存储（保留原始中文表头）
- **AND** **系统验证imported行数等于源文件唯一行数（排除合法重复，允许5%误差）**
- **AND** **如果imported行数显著少于源文件行数（>5%差异），系统记录警告并提示用户检查去重配置**

#### Scenario: data_hash唯一性验证（去重）- 正确去重
- **WHEN** 数据入库时
- **THEN** 系统验证data_hash唯一性（基于SHA256计算）
- **AND** 系统根据数据域选择去重策略：
  - **inventory域**：使用UPSERT策略（ON CONFLICT ... DO UPDATE），更新`raw_data`、`ingest_timestamp`、`file_id`、`header_columns`、`currency_code`，保留`metric_date`和维度字段
  - **其他域**：使用INSERT策略（ON CONFLICT DO NOTHING），自动去重
- **AND** 系统记录去重统计（重复数据不重复入库或更新）
- **AND** **系统确保data_hash计算包含足够的唯一标识字段（如product_id, order_id, SKU等）**
- **AND** **系统使用模板配置的deduplication_fields（如果存在）来计算data_hash**
- **AND** **系统记录用于hash计算的字段列表（用于调试和验证）**
- **AND** **如果核心字段在数据中不存在，系统记录警告但继续处理（使用NULL值）**
- **AND** **唯一约束基于platform_code + shop_id + data_domain + granularity + data_hash（使用动态表名）**

### Requirement: 批量数据同步
系统 SHALL 支持批量文件的数据同步，包括文件筛选、并发处理和进度跟踪，**确保每个文件的所有唯一行都被正确导入**。

#### Scenario: 批量同步文件处理完整性
- **WHEN** 用户请求批量同步，指定平台、数据域、粒度、时间范围等筛选条件
- **THEN** 系统查询catalog_files表，筛选出符合条件的pending状态文件，创建进度跟踪任务，提交后台异步处理，立即返回task_id和文件总数
- **AND** 系统验证文件元数据完整性（platform_code, shop_id, data_domain, granularity, date_range）
- **AND** **系统确保每个文件的所有唯一行都被导入（不遗漏任何文件的数据）**
- **AND** **系统记录每个文件的导入统计（总行数、导入行数、跳过行数）**
- **AND** **系统正确处理全部数据重复的文件（标记为"跳过"而非失败，统计为skipped_files）**
- **AND** **系统使用动态表名（fact_{platform}_{data_domain}_{sub_domain}_{granularity}）入库数据**
- **AND** **所有B类数据表存储在`b_class` schema中，便于Metabase中清晰区分**

