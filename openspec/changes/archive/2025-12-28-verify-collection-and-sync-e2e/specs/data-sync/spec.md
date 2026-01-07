## ADDED Requirements

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
