# 数据同步能力规范（改进）

## MODIFIED Requirements

### Requirement: 进度跟踪和历史记录
系统应提供数据库持久化的进度跟踪，支持任务查询和历史记录，并确保查询的可靠性和一致性。

#### Scenario: 进度查询可靠性
- **WHEN** 用户查询任务进度（task_id）
- **THEN** 系统从sync_progress_tasks表查询进度记录，返回任务状态、文件进度、当前文件、有效行数、隔离行数、错误行数等信息
- **AND** 如果遇到数据库事务错误（InFailedSqlTransaction），系统自动回滚事务并重试查询（最多3次）
- **AND** 如果查询失败，系统返回null，前端应显示"正在查询进度..."状态，并继续轮询

#### Scenario: 进度查询错误处理
- **WHEN** 进度查询遇到数据库事务错误
- **THEN** 系统自动回滚事务，等待一小段时间后重试查询（最多3次）
- **AND** 如果重试后仍然失败，系统返回null，前端应使用备用方案（从任务列表获取进度信息）
- **AND** 系统记录错误日志，但不影响后台任务的执行

#### Scenario: 进度查询API错误处理
- **WHEN** API查询进度时遇到异常
- **THEN** 系统确保异常时回滚事务，返回统一的错误响应格式
- **AND** 错误响应格式：
  ```json
  {
    "success": false,
    "code": "ERROR_CODE",
    "message": "错误消息",
    "error_type": "DatabaseError|ValidationError|...",
    "detail": "详细错误信息",
    "recovery_suggestion": "恢复建议"
  }
  ```
- **AND** 前端应区分"查询失败"（HTTP 500/数据库错误）和"任务失败"（HTTP 404/任务不存在），显示相应的错误消息
- **AND** 如果错误类型为"任务不存在"（HTTP 404），前端应停止轮询并提示用户刷新页面
- **AND** 如果错误类型为"数据库错误"（HTTP 500），前端应继续轮询并使用备用方案

### Requirement: 前端进度显示和错误处理
前端应可靠地显示同步进度，并正确处理各种错误情况。

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

### Requirement: 数据治理概览刷新
系统应在同步完成后自动刷新数据治理概览，确保统计数据准确显示。

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

## ADDED Requirements

### Requirement: 进度查询备用方案
系统应提供备用方案，当进度查询失败时，前端可以从任务列表获取进度信息。

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

### Requirement: 数据库事务一致性保证
系统应确保进度查询使用干净的事务，避免InFailedSqlTransaction错误。

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

