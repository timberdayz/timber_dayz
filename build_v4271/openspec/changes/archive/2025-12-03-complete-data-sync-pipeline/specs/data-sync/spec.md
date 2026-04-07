## MODIFIED Requirements

### Requirement: 单文件数据同步
系统 SHALL 支持单个Excel文件的数据同步，包括模板查找和配置、数据预览、去重处理和数据入库到B类数据表。

#### Scenario: 单文件同步成功流程（DSS架构）
- **WHEN** 用户请求同步单个文件（file_id）
- **THEN** 系统查找文件记录，检查文件状态，查找匹配的模板（TemplateMatcher），使用模板的header_row和header_columns，预览文件数据，补充元数据（platform_code, shop_id），计算data_hash进行去重，调用DataIngestionService入库到B类数据表（fact_raw_data_*，JSONB格式），更新文件状态为ingested，并返回同步结果
- **AND** 系统验证数据完整性（行数、字段完整性、data_hash唯一性）
- **AND** 系统记录统计信息（staged, imported, quarantined=0）
- **AND** 系统跳过字段映射、数据标准化、业务逻辑验证和数据隔离（DSS架构原则）

#### Scenario: 文件不存在处理
- **WHEN** 用户请求同步不存在的文件ID
- **THEN** 系统返回错误信息，状态为failed，消息为"文件不存在"

#### Scenario: 文件已处理跳过（DSS架构）
- **WHEN** 用户请求同步已入库的文件（status为ingested）
- **THEN** 系统返回跳过信息，状态为skipped，消息为"文件已入库"
- **AND** 注意：DSS架构下不再有partial_success状态，所有数据都成功入库

#### Scenario: 文件正在处理中
- **WHEN** 用户请求同步正在处理中的文件（status为processing）
- **THEN** 系统返回跳过信息，状态为skipped，消息为"文件正在处理中"

#### Scenario: 无模板文件处理（新数据域）
- **WHEN** 用户请求同步文件且only_with_template为true，但文件没有匹配的模板
- **THEN** 系统返回跳过信息，状态为skipped，消息为"无模板"
- **AND** 系统提示用户需要先创建模板（选择表头行和保存表头字段列表）
- **AND** 如果only_with_template为false，系统使用默认配置（header_row=0，从文件读取header_columns）继续同步

### Requirement: 批量数据同步
系统 SHALL 支持批量文件的数据同步，包括文件筛选、并发处理和进度跟踪。

#### Scenario: 批量同步请求处理
- **WHEN** 用户请求批量同步，指定平台、数据域、粒度、时间范围等筛选条件
- **THEN** 系统查询catalog_files表，筛选出符合条件的pending状态文件，创建进度跟踪任务，提交后台异步处理，立即返回task_id和文件总数
- **AND** 系统验证文件元数据完整性（platform_code, shop_id, data_domain, granularity, date_range）

#### Scenario: 批量同步文件筛选
- **WHEN** 用户指定平台、数据域、粒度、时间范围等筛选条件
- **THEN** 系统根据筛选条件查询catalog_files表，只处理符合条件的pending状态文件，限制数量不超过limit参数

#### Scenario: 无文件可处理
- **WHEN** 批量同步查询结果为空（没有符合条件的文件）
- **THEN** 系统返回成功响应，total_files为0，processed_files为0，提示"没有待处理的文件"

## ADDED Requirements

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
- **AND** 系统处理data_hash冲突（ON CONFLICT DO NOTHING，自动去重）
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
- **AND** 系统计算表头匹配率（match_rate）
- **AND** 如果匹配率<80%，系统提示用户更新模板
- **AND** 用户更新模板时，系统创建新版本（version+1）并归档旧版本（status='archived'）
- **AND** 系统使用新模板同步后续文件

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

