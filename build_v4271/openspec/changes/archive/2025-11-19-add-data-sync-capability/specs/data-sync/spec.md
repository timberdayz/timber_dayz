# 数据同步能力

## Requirements

### Requirement: 单文件数据同步
系统应支持单个Excel文件的数据同步，包括模板匹配、数据预览、字段映射应用和数据入库。

#### Scenario: 单文件同步成功流程
- **WHEN** 用户请求同步单个文件（file_id）
- **THEN** 系统查找文件记录，检查文件状态，查找匹配的字段映射模板，预览文件数据，应用模板映射，调用DataIngestionService入库数据，更新文件状态为ingested，并返回同步结果

#### Scenario: 文件不存在处理
- **WHEN** 用户请求同步不存在的文件ID
- **THEN** 系统返回错误信息，状态为failed，消息为"文件不存在"

#### Scenario: 文件已处理跳过
- **WHEN** 用户请求同步已入库的文件（status为ingested或partial_success）
- **THEN** 系统返回跳过信息，状态为skipped，消息为"文件已入库"

#### Scenario: 文件正在处理中
- **WHEN** 用户请求同步正在处理中的文件（status为processing）
- **THEN** 系统返回跳过信息，状态为skipped，消息为"文件正在处理中"

#### Scenario: 无模板文件处理
- **WHEN** 用户请求同步文件且only_with_template为true，但文件没有匹配的模板
- **THEN** 系统返回跳过信息，状态为skipped，消息为"未找到匹配的模板"

### Requirement: 批量数据同步
系统应支持批量文件的数据同步，包括文件筛选、并发处理和进度跟踪。

#### Scenario: 批量同步请求处理
- **WHEN** 用户请求批量同步，指定平台、数据域、粒度、时间范围等筛选条件
- **THEN** 系统查询catalog_files表，筛选出符合条件的pending状态文件，创建进度跟踪任务，提交后台异步处理，立即返回task_id和文件总数

#### Scenario: 批量同步文件筛选
- **WHEN** 用户指定平台、数据域、粒度、时间范围等筛选条件
- **THEN** 系统根据筛选条件查询catalog_files表，只处理符合条件的pending状态文件，限制数量不超过limit参数

#### Scenario: 无文件可处理
- **WHEN** 批量同步查询结果为空（没有符合条件的文件）
- **THEN** 系统返回成功响应，total_files为0，processed_files为0，提示"没有待处理的文件"

### Requirement: 异步处理和并发控制
系统应使用FastAPI BackgroundTasks实现异步处理，并控制并发数量以避免资源耗尽。

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
系统应提供数据库持久化的进度跟踪，支持任务查询和历史记录。

#### Scenario: 进度任务创建
- **WHEN** 批量同步任务启动
- **THEN** 系统在sync_progress_tasks表中创建进度记录，包含task_id、任务类型、总文件数、状态为processing

#### Scenario: 进度实时更新
- **WHEN** 文件处理完成
- **THEN** 系统更新进度记录，增加processed_files计数，更新file_progress百分比，记录当前处理的文件名

#### Scenario: 进度查询
- **WHEN** 用户查询任务进度（task_id）
- **THEN** 系统从sync_progress_tasks表查询进度记录，返回任务状态、文件进度、当前文件、有效行数、隔离行数、错误行数等信息

#### Scenario: 任务历史记录
- **WHEN** 用户查询任务列表
- **THEN** 系统返回历史任务列表，支持按状态筛选（processing、completed、failed），支持分页和限制数量

#### Scenario: 服务重启后恢复进度
- **WHEN** 服务重启且任务未完成
- **THEN** 系统可以从sync_progress_tasks表恢复任务进度，继续处理剩余文件

### Requirement: 数据质量Gate检查
系统应在批量同步完成后自动进行数据质量检查，计算平均质量评分并识别缺失字段。

#### Scenario: 批量同步完成后质量检查
- **WHEN** 批量同步所有文件处理完成
- **THEN** 系统自动调用CClassDataValidator进行质量检查，计算平均质量评分，识别缺失字段，将结果保存到任务详情中

#### Scenario: 质量检查结果记录
- **WHEN** 质量检查完成
- **THEN** 系统在任务详情中记录平均质量评分、缺失字段列表、质量等级（excellent/good/fair/poor）等信息

### Requirement: 错误处理和重试机制
系统应提供完善的错误处理，记录错误详情，支持重试机制。

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
系统应正确集成数据采集、字段映射和数据入库系统，复用现有服务。

#### Scenario: 模板匹配集成
- **WHEN** 同步文件时查找模板
- **THEN** 系统调用TemplateMatcher.find_best_template，使用文件的platform_code、data_domain、granularity、sub_domain进行匹配

#### Scenario: 数据入库集成
- **WHEN** 模板应用成功，准备入库数据
- **THEN** 系统调用DataIngestionService.ingest_data，传入映射后的数据和文件元数据，由入库服务处理数据验证和入库

#### Scenario: 文件状态更新
- **WHEN** 数据入库完成
- **THEN** 系统更新catalog_file.status为ingested（全部成功）或partial_success（部分成功），记录入库时间和统计信息到文件元数据

