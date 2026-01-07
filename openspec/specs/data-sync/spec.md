# 数据同步能力

## Purpose

系统 SHALL 支持将采集的Excel文件数据同步到数据库，包括模板匹配、数据预览、字段映射应用和数据入库，确保数据完整性和质量。
## Requirements
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

### Requirement: 异步处理和并发控制
系统 SHALL 使用FastAPI BackgroundTasks实现异步处理，并控制并发数量以避免资源耗尽。

#### Scenario: 异步任务提交
- **WHEN** 用户请求批量同步
- **THEN** 系统创建进度跟踪任务，提交BackgroundTask后台处理，API立即返回task_id，不阻塞用户请求

#### Scenario: 并发控制
- **WHEN** 批量同步后台处理开始
- **THEN** 系统使用asyncio.Semaphore限制最多10个并发文件处理，避免资源耗尽

#### Scenario: 并发处理完成
- **WHEN** 所有文件处理完成
- **THEN** 系统释放并发控制资源，更新任务状态为completed，记录完成时间和统计信息

### Requirement: 进度跟踪和历史记录
系统 SHALL 提供数据库持久化的进度跟踪，支持任务查询和历史记录，并确保查询的可靠性和一致性。

#### Scenario: 进度任务创建
- **WHEN** 批量同步任务启动
- **THEN** 系统在sync_progress_tasks表中创建进度记录，包含task_id、任务类型、总文件数、状态为processing

#### Scenario: 进度实时更新
- **WHEN** 文件处理完成
- **THEN** 系统更新进度记录，增加processed_files计数，更新file_progress百分比，记录当前处理的文件名

#### Scenario: 进度查询
- **WHEN** 用户查询任务进度（task_id）
- **THEN** 系统从sync_progress_tasks表查询进度记录，返回任务状态、文件进度、当前文件、有效行数、隔离行数、错误行数等信息

#### Scenario: 进度查询可靠性（v4.12.3新增）
- **WHEN** 用户查询任务进度（task_id）
- **THEN** 系统从sync_progress_tasks表查询进度记录，返回任务状态、文件进度、当前文件、有效行数、隔离行数、错误行数等信息
- **AND** 如果遇到数据库事务错误（InFailedSqlTransaction），系统自动回滚事务并重试查询（最多3次）
- **AND** 如果查询失败，系统返回null，前端应显示"正在查询进度..."状态，并继续轮询

#### Scenario: 进度查询错误处理（v4.12.3新增）
- **WHEN** 进度查询遇到数据库事务错误
- **THEN** 系统自动回滚事务，等待一小段时间后重试查询（最多3次）
- **AND** 如果重试后仍然失败，系统返回null，前端应使用备用方案（从任务列表获取进度信息）
- **AND** 系统记录错误日志，但不影响后台任务的执行

#### Scenario: 进度查询API错误处理（v4.12.3新增）
- **WHEN** API查询进度时遇到异常
- **THEN** 系统确保异常时回滚事务，返回统一的错误响应格式
- **AND** 错误响应包含错误码、错误类型、错误详情和恢复建议
- **AND** 前端应区分"查询失败"（HTTP 500/数据库错误）和"任务失败"（HTTP 404/任务不存在），显示相应的错误消息
- **AND** 如果错误类型为"任务不存在"（HTTP 404），前端应停止轮询并提示用户刷新页面
- **AND** 如果错误类型为"数据库错误"（HTTP 500），前端应继续轮询并使用备用方案

#### Scenario: 任务历史记录
- **WHEN** 用户查询任务列表
- **THEN** 系统返回历史任务列表，支持按状态筛选（processing、completed、failed），支持分页和限制数量

#### Scenario: 服务重启后恢复进度
- **WHEN** 服务重启且任务未完成
- **THEN** 系统可以从sync_progress_tasks表恢复任务进度，继续处理剩余文件

### Requirement: 数据质量Gate检查
系统 SHALL 在批量同步完成后自动进行数据质量检查，计算平均质量评分并识别缺失字段。

#### Scenario: 批量同步完成后质量检查
- **WHEN** 批量同步所有文件处理完成
- **THEN** 系统自动调用CClassDataValidator进行质量检查，计算平均质量评分，识别缺失字段，将结果保存到任务详情中

#### Scenario: 质量检查结果记录
- **WHEN** 质量检查完成
- **THEN** 系统在任务详情中记录平均质量评分、缺失字段列表、质量等级（excellent/good/fair/poor）等信息

### Requirement: 错误处理和重试机制
系统 SHALL 提供完善的错误处理，记录错误详情，支持重试机制。

#### Scenario: 文件处理错误
- **WHEN** 文件处理过程中发生错误（如文件格式错误、模板应用失败、数据验证失败）
- **THEN** 系统记录错误详情到日志，更新文件状态为failed，记录错误原因到文件元数据，继续处理下一个文件

#### Scenario: 隔离数据记录
- **WHEN** 文件处理过程中有数据被隔离（allow_quarantine为true）
- **THEN** 系统记录隔离行数到进度跟踪，更新文件状态为partial_success（如果有有效数据）或quarantined（如果全部隔离）

#### Scenario: 重试机制
- **WHEN** 文件处理失败
- **THEN** 系统记录尝试次数到文件元数据（auto_ingest.attempts），记录最后尝试时间，用户可以重新请求同步进行重试

#### Scenario: 批量任务失败处理
- **WHEN** 批量同步任务处理过程中发生严重错误（如数据库连接失败）
- **THEN** 系统更新任务状态为failed，记录错误信息到任务详情，不影响已处理的文件

### Requirement: 与现有系统集成
系统 SHALL 正确集成数据采集、字段映射和数据入库系统，复用现有服务。

#### Scenario: 模板匹配集成
- **WHEN** 同步文件时查找模板
- **THEN** 系统调用TemplateMatcher.find_best_template，使用文件的platform_code、data_domain、granularity、sub_domain进行匹配

#### Scenario: 数据入库集成
- **WHEN** 模板应用成功，准备入库数据
- **THEN** 系统调用DataIngestionService.ingest_data，传入映射后的数据和文件元数据，由入库服务处理数据验证和入库

#### Scenario: 产品ID自动关联
- **WHEN** 订单明细数据入库时（FactOrderItem）
- **THEN** 系统应通过BridgeProductKeys自动关联product_id字段（冗余字段，便于直接查询）
- **WHEN** BridgeProductKeys中找不到对应的product_id
- **THEN** 系统应允许product_id为NULL，记录警告信息，但不影响数据入库

#### Scenario: 文件状态更新
- **WHEN** 数据入库完成
- **THEN** 系统更新catalog_file.status为ingested（全部成功）或partial_success（部分成功），记录入库时间和统计信息到文件元数据

### Requirement: 前端进度显示和错误处理（v4.12.3新增）
前端 SHALL 可靠地显示同步进度，并正确处理各种错误情况。

#### Scenario: 进度条更新
- **WHEN** 前端轮询同步进度
- **THEN** 前端使用正确的字段名（total_files/processed_files）计算进度百分比
- **AND** 如果查询返回null，前端应显示"正在查询进度..."状态，并继续轮询
- **AND** 如果查询失败，前端应使用备用方案（从任务列表获取进度信息）

#### Scenario: 启动同步错误处理
- **WHEN** 前端启动同步时收到响应
- **THEN** 前端检查response是否为null，如果是null则显示错误消息并停止
- **AND** 前端使用response.total_files初始化总文件数（不使用response.summary?.total_files）
- **AND** 前端使用response.task_id开始轮询进度

#### Scenario: 同步完成消息显示
- **WHEN** 同步完成（status为completed或failed）
- **THEN** 前端使用正确的字段名显示完成消息
  - **字段映射关系**：后端返回`valid_rows` → 前端使用`succeeded`（成功行数）
  - **字段映射关系**：后端返回`quarantined_rows` → 前端使用`quarantined`（隔离行数）
  - **字段映射关系**：后端返回`error_rows` → 前端使用`failed`（错误行数）
  - **注意**：前端API客户端（`getAutoIngestProgress`）已自动完成字段映射，前端代码直接使用`succeeded/quarantined/failed`即可
- **AND** 前端自动刷新数据治理概览和文件列表
- **AND** 前端显示用户友好的完成消息（成功/隔离/失败数量）

### Requirement: 数据治理概览刷新（v4.12.3新增）
系统 SHALL 在同步完成后自动刷新数据治理概览，确保统计数据准确显示。

#### Scenario: 数据治理概览自动刷新
- **WHEN** 同步完成（status为completed或failed）
- **THEN** 系统自动调用refreshGovernanceStats()刷新数据治理概览（异步执行，不阻塞用户操作）
- **AND** 前端使用正确的响应格式解析统计数据（响应拦截器已提取data字段，直接使用overview）
- **AND** 如果刷新失败，系统记录错误日志，但不影响同步结果
- **AND** 刷新失败时，前端不显示错误提示（避免干扰用户），但会在控制台记录警告日志

#### Scenario: 数据治理概览响应格式解析
- **WHEN** 前端调用getGovernanceOverview API
- **THEN** 响应拦截器已提取data字段，前端直接使用overview（不检查overview.success或overview.data）
- **AND** 前端使用overview.pending_files、overview.template_coverage等字段更新统计数据
- **AND** 如果响应为null或格式错误，前端显示错误消息，但不影响其他功能

### Requirement: 进度查询备用方案（v4.12.3新增）
系统 SHALL 提供备用方案，当进度查询失败时，前端可以从任务列表获取进度信息。

#### Scenario: 任务列表备用查询
- **WHEN** 进度查询返回null或失败
- **AND** 总文件数仍为0
- **THEN** 前端尝试从任务列表获取任务信息（GET /api/data-sync/tasks）
- **AND** 如果找到匹配的任务，前端使用任务信息更新进度显示（total_files、processed_files、status等）
- **AND** 如果任务列表查询失败或找不到匹配任务，前端记录警告日志，但不停止轮询
- **AND** 前端继续轮询进度，不立即停止
- **AND** 如果连续10次查询失败且找不到任务，前端显示"无法获取进度，请刷新页面查看最新状态"并停止轮询

#### Scenario: 备用查询错误处理
- **WHEN** 备用查询（任务列表）也失败
- **THEN** 前端记录警告日志，但不停止轮询
- **AND** 前端继续显示"正在查询进度..."状态
- **AND** 前端等待下次轮询重试

### Requirement: 数据库事务一致性保证（v4.12.3新增）
系统 SHALL 确保进度查询使用干净的事务，避免InFailedSqlTransaction错误。

#### Scenario: 查询前事务回滚
- **WHEN** 系统查询任务进度
- **THEN** 系统在查询前先回滚任何失败的事务，确保使用干净的事务
- **AND** 如果回滚失败（可能没有活动事务），系统忽略错误并继续查询

#### Scenario: 事务错误自动重试
- **WHEN** 进度查询遇到InFailedSqlTransaction错误
- **THEN** 系统自动回滚事务，等待一小段时间后重试查询（最多3次）
- **AND** 每次重试等待时间递增：第1次重试等待0.1秒，第2次重试等待0.2秒，第3次重试等待0.3秒
- **AND** 如果重试后仍然失败，系统返回null，前端应使用备用方案（从任务列表获取进度信息）
- **AND** 系统记录错误日志，但不影响后台任务的执行

#### Scenario: API层面事务管理
- **WHEN** API查询进度时遇到异常
- **THEN** 系统确保异常时回滚事务，避免影响后续查询
- **AND** 系统返回统一的错误响应格式，包含错误码、错误类型、错误详情和恢复建议

### Requirement: 数据库设计规则审查（v4.13.0新增）
系统 SHALL 审查现有数据库设计规则，识别根本性问题，特别是shop_id主键约束、字段必填规则、主键设计规则等。

#### Scenario: 数据库设计规则审查
- **WHEN** 系统进行数据库设计规则审查
- **THEN** 系统分析shop_id主键约束与数据源不匹配的问题，分析事实表和物化视图与源数据不匹配的问题，识别缺少的规则和规范

#### Scenario: 数据库设计规则优化方案
- **WHEN** 系统发现数据库设计规则问题
- **THEN** 系统创建数据库设计规则优化方案文档，记录发现的问题和影响，提出优化方案和迁移计划

### Requirement: OpenSpec规范文档创建（v4.13.0新增）
系统 SHALL 创建数据库设计规范OpenSpec文档，明确数据归属规则、字段必填规则、主键设计规则等。

#### Scenario: 数据库设计规范文档创建
- **WHEN** 系统创建数据库设计规范OpenSpec文档
- **THEN** 系统定义数据归属规则（shop_id、account_id等），定义字段必填规则（哪些字段必填，哪些可选），定义主键设计规则（何时使用复合主键，何时允许NULL），定义事实表和物化视图设计规则

### Requirement: 数据同步可靠性增强（v4.13.0修改）
系统 SHALL 确保数据同步的可靠性，包括数据完整性、字段映射准确性、数据流转可追踪性和对比报告准确性。

#### Scenario: 数据丢失自动隔离
- **WHEN** 数据在验证、staging或upsert阶段失败
- **THEN** 系统自动将失败的数据隔离到data_quarantine表，记录错误类型和错误信息

#### Scenario: 数据丢失追踪日志
- **WHEN** 数据同步过程中
- **THEN** 系统记录每个阶段的数据数量（Raw→Staging→Fact），便于追踪数据丢失位置

#### Scenario: 数据丢失预警
- **WHEN** 数据丢失率超过预设阈值（如5%）
- **THEN** 系统发出预警，通知用户数据丢失情况

#### Scenario: 字段映射验证
- **WHEN** 字段映射应用后
- **THEN** 系统验证映射后的数据是否完整，确保所有必填字段都已正确映射

#### Scenario: 字段映射质量评分
- **WHEN** 字段映射完成后
- **THEN** 系统评估字段映射的准确性，返回质量评分和问题列表

#### Scenario: 数据流转完整追踪
- **WHEN** 查询数据流转信息
- **THEN** 系统正确查询所有数据层（Raw→Staging→Fact→Quarantine），显示完整的数据流转情况
- **AND** 系统使用正确的字段关联（如FactProductMetric使用source_catalog_id关联文件）

#### Scenario: 对比报告丢失数据详情
- **WHEN** 用户查看对比报告
- **THEN** 系统显示丢失数据的详细信息，包括丢失位置、丢失原因和丢失数据内容

#### Scenario: 文件注册流程验证
- **WHEN** 文件注册时
- **THEN** 系统验证文件是否正确注册到catalog_files表，确保file_id正确传递到所有数据层（通过source_catalog_id字段）

### Requirement: 数据丢失自动分析（v4.13.0新增）
系统 SHALL 提供数据丢失自动分析功能，分析丢失数据的共同特征，帮助用户定位问题。

#### Scenario: 数据丢失特征分析
- **WHEN** 数据同步完成后发现数据丢失
- **THEN** 系统自动分析丢失数据的共同特征（如字段缺失、格式错误、主键冲突等），返回分析结果

### Requirement: 数据丢失预警机制（v4.13.0新增）
系统 SHALL 提供数据丢失预警机制，当数据丢失率超过阈值时发出预警。

#### Scenario: 数据丢失率超过阈值预警
- **WHEN** 数据同步完成后，数据丢失率超过预设阈值（如5%）
- **THEN** 系统发出预警，通知用户数据丢失情况，并提供丢失数据详情

### Requirement: 字段映射质量评分（v4.13.0新增）
系统 SHALL 提供字段映射质量评分功能，评估字段映射的准确性。

#### Scenario: 字段映射质量评分计算
- **WHEN** 字段映射完成后
- **THEN** 系统计算字段映射质量评分（基于映射覆盖率、映射准确性等指标），返回评分和问题列表

### Requirement: 数据流转异常检测（v4.13.0新增，可选功能）
系统 SHALL 提供数据流转异常检测功能，检测数据流转中的异常情况。

#### Scenario: 数据流转异常检测
- **WHEN** 数据同步完成后
- **THEN** 系统检测数据流转中的异常情况（如数据在某个阶段丢失、数据流转中断等），返回异常报告

### Requirement: 丢失数据导出功能（v4.13.1新增）
系统 SHALL 提供丢失数据导出功能，支持将丢失数据导出到Excel、CSV或JSON格式。

#### Scenario: 丢失数据导出到Excel
- **WHEN** 用户请求导出丢失数据
- **THEN** 系统将丢失数据导出到Excel文件，包含丢失数据的详细信息和错误原因

#### Scenario: 丢失数据导出到CSV
- **WHEN** 用户请求导出丢失数据为CSV格式
- **THEN** 系统将丢失数据导出到CSV文件，包含丢失数据的详细信息和错误原因

#### Scenario: 丢失数据导出到JSON
- **WHEN** 用户请求导出丢失数据为JSON格式
- **THEN** 系统将丢失数据导出到JSON文件，包含丢失数据的详细信息和错误原因

### Requirement: 丢失数据分析功能（v4.13.0新增）
系统 SHALL 提供丢失数据分析功能，分析丢失数据的原因和模式。

#### Scenario: 丢失数据原因分析
- **WHEN** 用户请求分析丢失数据
- **THEN** 系统分析丢失数据的原因和模式（如字段缺失、格式错误、主键冲突等），返回分析报告

### Requirement: 数据完整性验证（DSS架构）
系统 SHALL 在数据同步过程中验证数据完整性，确保数据无丢失、字段完整、data_hash唯一。

#### Scenario: 数据行数验证（B类数据表）
- **WHEN** 数据同步完成后
- **THEN** 系统验证B类数据表（fact_raw_data_*）数据行数与文件行数一致性
- **AND** 系统记录数据行数统计（total_rows, imported, quarantined=0）
- **AND** 系统验证数据以JSONB格式存储（保留原始中文表头）

#### Scenario: 字段完整性验证（元数据）
- **WHEN** 数据同步完成后
- **THEN** 系统验证元数据字段完整性（platform_code, shop_id, file_id, data_hash）
- **AND** 系统验证元数据字段不为NULL
- **AND** 系统记录字段完整性统计

#### Scenario: data_hash唯一性验证（去重）
- **WHEN** 数据入库时
- **THEN** 系统验证data_hash唯一性（基于SHA256计算）
- **AND** 系统根据数据域处理data_hash冲突：
  - **inventory域**：使用UPSERT策略（ON CONFLICT ... DO UPDATE），更新数据
  - **其他域**：使用INSERT策略（ON CONFLICT DO NOTHING），自动去重
- **AND** 系统记录去重统计（重复数据不重复入库）

#### Scenario: JSONB数据格式验证
- **WHEN** 数据同步完成后
- **THEN** 系统验证raw_data字段为有效的JSONB格式
- **AND** 系统验证header_columns字段包含原始表头字段列表
- **AND** 系统验证数据保留原始列名（中文/英文）

### Requirement: 数据质量验证（Metabase验证）
系统 SHALL 在Metabase中进行数据质量检查，不在数据同步流程中验证业务逻辑。

#### Scenario: Metabase业务逻辑验证
- **WHEN** 数据同步完成后
- **THEN** 系统不在数据同步流程中验证业务逻辑（如"可用库存不能大于实际库存"）
- **AND** 系统将所有数据入库到B类数据表（不隔离数据）
- **AND** 系统在Metabase中配置业务逻辑验证规则
- **AND** 系统在Metabase中查询和验证数据质量

#### Scenario: DSS架构数据入库
- **WHEN** 数据同步时
- **THEN** 系统不执行数据验证（跳过validate_orders, validate_inventory等函数）
- **AND** 系统不隔离数据（quarantined_count始终为0）
- **AND** 系统使用所有数据（不做验证筛选）
- **AND** 系统更新文件状态为ingested（不再有partial_success或quarantined状态）

### Requirement: Metabase 集成数据要求（DSS架构）
系统 SHALL 确保B类数据表数据格式符合Metabase查询要求，支持Metabase Question查询B类数据表数据。

#### Scenario: JSONB数据格式符合要求
- **WHEN** Metabase查询B类数据表数据
- **THEN** 系统确保raw_data字段为有效的JSONB格式
- **AND** 系统确保header_columns字段包含原始表头字段列表
- **AND** 系统确保元数据字段（platform_code, shop_id, metric_date等）符合Metabase要求
- **AND** 系统在Metabase中通过字段映射或计算字段处理数据类型转换

#### Scenario: Metabase数据查询和验证
- **WHEN** Metabase Question查询B类数据表
- **THEN** 系统确保数据可以被Metabase正确查询
- **AND** 系统确保数据行数符合Question要求
- **AND** 系统在Metabase中配置字段映射（原始表头字段 → 标准字段）
- **AND** 系统在Metabase中配置业务逻辑验证规则
- **AND** 系统在Metabase中查询和验证数据质量

### Requirement: 数据同步管道端到端验证
系统 SHALL 提供端到端验证功能，验证数据从采集到入库的完整流程。

#### Scenario: 端到端验证流程（DSS架构）
- **WHEN** 用户运行端到端验证脚本
- **THEN** 系统验证数据采集 → 文件注册 → 模板查找和配置 → 数据入库到B类数据表 → Metabase验证的完整流程
- **AND** 系统验证每个步骤的成功状态
- **AND** 系统验证DSS架构流程（跳过字段映射、数据标准化、业务逻辑验证和数据隔离）
- **AND** 系统生成端到端验证报告

#### Scenario: 数据完整性验证（DSS架构）
- **WHEN** 端到端验证运行时
- **THEN** 系统验证数据行数完整性（文件 → B类数据表）
- **AND** 系统验证元数据字段完整性（platform_code, shop_id, data_hash不为NULL）
- **AND** 系统验证JSONB数据格式（raw_data字段有效）
- **AND** 系统验证去重机制（data_hash唯一性）

#### Scenario: Metabase集成验证（DSS架构）
- **WHEN** 端到端验证运行时
- **THEN** 系统验证Metabase可以连接数据库
- **AND** 系统验证Metabase Question可以查询B类数据表（fact_raw_data_*）
- **AND** 系统验证JSONB数据格式符合Metabase要求
- **AND** 系统验证Metabase字段映射配置正确（原始表头字段 → 标准字段）
- **AND** 系统验证Metabase业务逻辑验证规则配置正确

### Requirement: 数据同步验证工具
系统 SHALL 提供数据同步验证工具，支持验证数据同步管道的各个组件。

#### Scenario: 数据采集验证工具
- **WHEN** 用户运行数据采集验证脚本
- **THEN** 系统验证数据采集器可以下载文件
- **AND** 系统验证文件正确注册到catalog_files表
- **AND** 系统验证文件元数据正确性

#### Scenario: 文件扫描验证工具
- **WHEN** 用户运行文件扫描验证脚本
- **THEN** 系统验证catalog_scanner可以扫描文件
- **AND** 系统验证文件注册API正常工作
- **AND** 系统验证文件去重机制正常工作

#### Scenario: 数据同步验证工具（DSS架构）
- **WHEN** 用户运行数据同步验证脚本
- **THEN** 系统验证单文件同步API正常工作
- **AND** 系统验证批量同步API正常工作
- **AND** 系统验证模板查找和配置（表头行和表头字段列表）
- **AND** 系统验证数据入库到B类数据表（fact_raw_data_*，JSONB格式）
- **AND** 系统验证去重处理（data_hash）
- **AND** 系统验证DSS架构（不再执行字段映射、数据标准化、业务逻辑验证和数据隔离）

#### Scenario: 数据完整性验证工具（DSS架构）
- **WHEN** 用户运行数据完整性验证脚本
- **THEN** 系统验证B类数据表（fact_raw_data_*）数据行数
- **AND** 系统验证JSONB数据格式（raw_data字段）
- **AND** 系统验证元数据字段完整性（platform_code, shop_id, data_hash）
- **AND** 系统验证去重机制（data_hash唯一性）
- **AND** 系统验证数据保留原始列名（中文/英文）

#### Scenario: Metabase集成验证工具（DSS架构）
- **WHEN** 用户运行Metabase集成验证脚本
- **THEN** 系统验证Metabase可以连接数据库
- **AND** 系统验证Metabase Question可以查询B类数据表（fact_raw_data_*）
- **AND** 系统验证JSONB数据格式符合Metabase要求
- **AND** 系统验证Metabase字段映射配置正确（原始表头字段 → 标准字段）
- **AND** 系统验证Metabase业务逻辑验证规则配置正确

### Requirement: 空文件处理机制
系统 SHALL 正确处理空文件（全0数据文件），避免重复处理和同步失败。

#### Scenario: 空文件识别（DSS架构）
- **WHEN** 文件数据全部为0或空
- **THEN** 系统识别为空文件（全0数据文件）
- **AND** 系统标记文件状态为ingested，但记录警告信息（[全0数据标识]）
- **AND** 系统跳过数据入库，不写入B类数据表
- **AND** 系统返回成功结果，但提示"该文件已识别为全0数据文件，无需重复入库"
- **AND** 系统不执行数据验证（DSS架构下不验证业务逻辑）

#### Scenario: 空文件重复处理防护
- **WHEN** 用户尝试同步已识别的空文件
- **THEN** 系统检测到文件已标记为全0数据文件（error_message包含[全0数据标识]）
- **AND** 系统跳过处理，返回成功但提示"该文件已识别为全0数据文件，无需重复入库"
- **AND** 系统不重复处理空文件，避免不必要的计算和数据库操作
- **AND** 系统记录跳过原因（skip_reason: "all_zero_data_already_processed"）

#### Scenario: 空文件状态管理（DSS架构）
- **WHEN** 空文件处理完成后
- **THEN** 系统更新文件状态为ingested
- **AND** 系统在文件元数据中记录警告信息（[全0数据标识]）
- **AND** 系统记录处理结果（staged=0, imported=0, quarantined=0）
- **AND** 系统记录跳过标识（skipped=True）
- **AND** 系统不执行数据验证（DSS架构下不验证业务逻辑）

### Requirement: 模板管理与数据同步协同机制
系统 SHALL 支持模板管理与数据同步的协同运作，包括新数据域处理和表头更新处理。

#### Scenario: 新数据域处理流程
- **WHEN** 用户尝试同步新数据域文件且only_with_template为true，但文件没有匹配的模板
- **THEN** 系统返回跳过信息，状态为skipped，消息为"无模板"
- **AND** 系统提示用户需要先创建模板（选择表头行和保存表头字段列表）
- **AND** 用户创建模板后，系统可以正常同步该数据域的文件
- **AND** 如果only_with_template为false，系统使用默认配置（header_row=0，从文件读取header_columns）继续同步

#### Scenario: 表头更新处理流程
- **WHEN** 文件表头发生变化（新增字段、删除字段、重命名字段）
- **THEN** 系统检测表头变化（detect_header_changes()）
- **AND** 系统在比较前进行货币代码归一化：
  - 使用正则表达式`\(([A-Z]{3})\)`识别货币代码（如BRL、COP、SGD）
  - 验证货币代码是否在ISO 4217标准列表中
  - 将字段名归一化（移除货币代码部分）
  - 比较归一化后的字段名
- **AND** 如果只有货币代码差异，视为匹配（不触发表头变化检测）
- **AND** 如果货币差异+其他字段变化，正常触发变化检测
- **AND** 系统计算表头匹配率（match_rate，基于归一化后的字段名）
- **AND** 如果匹配率<80%，系统提示用户更新模板
- **AND** 用户更新模板时，系统创建新版本（version+1）并归档旧版本（status='archived'）
- **AND** 系统使用新模板同步后续文件

#### Scenario: 货币代码提取和存储
- **WHEN** 数据入库时
- **THEN** 系统提取货币代码并存储：
  - 遍历所有字段名，使用正则表达式`\(([A-Z]{3})\)`提取货币代码
  - 验证货币代码是否在ISO 4217标准列表中
  - 如果一行数据有多个货币字段，提取第一个货币字段的货币代码（方案A）
  - 将货币代码存储到`currency_code`系统字段（String(3), nullable=True）
  - 字段名归一化后存储到`raw_data` JSONB中（不含货币代码）
  - 原始字段名（含货币代码）保留在`header_columns`中
- **AND** 错误处理：
  - 如果字段名中没有货币代码，`currency_code`设置为NULL
  - 如果提取的货币代码不在ISO 4217列表中，记录警告日志，`currency_code`设置为NULL，但继续处理
  - 如果一行数据有多个货币字段且货币代码不同，提取第一个，记录警告日志

#### Scenario: 模板查找和配置
- **WHEN** 数据同步开始时
- **THEN** 系统查找匹配的模板（TemplateMatcher.find_best_template()）
- **AND** 系统使用三级智能降级匹配（精确匹配 → 忽略sub_domain → 已禁用）
- **AND** 系统使用模板的header_row读取文件
- **AND** 系统使用模板的header_columns（优先）或从文件读取的columns（兜底）
- **AND** 系统验证表头匹配（仅日志，不阻止同步）

#### Scenario: 模板版本管理
- **WHEN** 用户保存新模板时
- **THEN** 系统检查是否已有同维度的published模板
- **AND** 如果存在，系统创建新版本（version+1）并归档旧版本（status='archived'）
- **AND** 如果不存在，系统创建新模板（version=1）
- **AND** 系统保存模板的header_row和header_columns（不保存字段映射）
- **AND** 系统不执行数据验证（DSS架构下不验证业务逻辑）

### Requirement: 端到端同步流程验证
系统 SHALL 提供端到端数据同步流程验证机制，确保从文件注册到数据入库的完整链路正常工作。

#### Scenario: 单文件同步端到端验证
- **WHEN** 执行单文件同步测试
- **THEN** 系统完成文件读取、模板匹配、数据预览、去重处理、数据入库的完整流程
- **AND** 系统使用动态表名（fact_{platform}_{data_domain}_{sub_domain}_{granularity}）入库数据
- **AND** 系统将数据存储到b_class schema中
- **AND** 系统验证数据行数一致性（导入行数与源文件唯一行数匹配，允许5%误差）
- **AND** 系统更新文件状态为ingested
- **AND** 系统记录同步统计（staged, imported, quarantined）

#### Scenario: 批量同步端到端验证
- **WHEN** 执行批量同步测试
- **THEN** 系统查询catalog_files表获取待同步文件列表
- **AND** 系统创建进度跟踪任务（sync_progress_tasks表）
- **AND** 系统使用BackgroundTasks异步处理文件
- **AND** 系统使用asyncio.Semaphore控制并发（最多10个）
- **AND** 系统实时更新进度（processed_files, file_progress）
- **AND** 所有文件处理完成后，任务状态更新为completed

#### Scenario: 去重机制验证
- **WHEN** 同步包含重复数据的文件
- **THEN** 系统使用data_hash检测重复
- **AND** 对于inventory域，使用UPSERT策略更新数据
- **AND** 对于其他域，使用INSERT策略自动去重（ON CONFLICT DO NOTHING）
- **AND** 系统记录去重统计（skipped_duplicates）

#### Scenario: 动态表名生成验证
- **WHEN** 数据同步到不同平台或数据域
- **THEN** 系统使用PlatformTableManager生成正确的表名
- **AND** 无sub_domain时：fact_{platform}_{data_domain}_{granularity}
- **AND** 有sub_domain时：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
- **AND** 所有表名组件使用小写
- **AND** 系统确保表存在（自动创建如果不存在）

### Requirement: 定时同步机制验证
系统 SHALL 验证定时数据同步任务配置正确且可正常触发。

#### Scenario: 物化视图定时刷新验证
- **WHEN** 物化视图刷新定时任务到达触发时间（每天凌晨2点）
- **THEN** 系统自动刷新所有物化视图
- **AND** 系统按依赖顺序刷新（基础视图优先）
- **AND** 系统记录刷新日志和耗时
- **AND** 刷新失败时记录错误但不影响后续视图

#### Scenario: 定时同步任务注册验证
- **WHEN** 系统启动时
- **THEN** 系统在APScheduler中注册物化视图刷新任务
- **AND** 任务使用正确的Cron表达式（0 2 * * *）
- **AND** 任务ID为固定值（materialized_views_refresh）

#### Scenario: 手动触发同步验证
- **WHEN** 管理员手动触发数据同步
- **THEN** 系统支持通过API或前端界面触发同步
- **AND** 系统提供同步进度查询接口
- **AND** 系统返回同步统计结果

### Requirement: 数据完整性验证
系统 SHALL 验证同步后的数据完整性，包括行数一致性、字段完整性和唯一性约束。

#### Scenario: 数据行数一致性验证
- **WHEN** 数据同步完成后
- **THEN** 系统对比Excel文件行数与数据库表行数
- **AND** 导入行数应等于源文件唯一行数（排除合法重复）
- **AND** 如果差异>5%，系统记录警告并提示检查去重配置
- **AND** 系统记录详细统计（total_rows, unique_rows, imported_rows, skipped_rows）

#### Scenario: 唯一性约束验证
- **WHEN** 插入重复数据（相同data_hash）
- **THEN** 数据库唯一性约束生效（ON CONFLICT DO NOTHING或DO UPDATE）
- **AND** 系统不抛出异常，正常完成同步
- **AND** 系统记录跳过的重复行数

#### Scenario: JSONB数据格式验证
- **WHEN** 查询事实表数据
- **THEN** raw_data字段为JSONB格式，保留原始中文表头
- **AND** 可以使用JSONB查询语法访问字段（如 raw_data->>'订单号'）
- **AND** 元数据字段（platform_code, shop_id等）为独立列，便于查询和索引

