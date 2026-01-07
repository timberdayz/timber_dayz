# Data Sync Capability - Delta Specs

## MODIFIED Requirements

### Requirement: File List Refresh

系统 SHALL 支持刷新待同步文件列表，重新扫描采集文件并更新数据库记录。

#### Scenario: 刷新文件列表成功
- **WHEN** 用户点击"刷新"按钮
- **THEN** 系统调用 `/api/field-mapping/scan` API
- **AND** 显示扫描结果消息

### Requirement: File Detail View

系统 SHALL 支持查看任意状态文件的详细信息，包括待同步、已同步、失败等状态。

#### Scenario: 查看已同步文件详情
- **WHEN** 用户点击文件的"查看详情"按钮
- **THEN** 系统查询该文件信息（不限制状态）
- **AND** 显示文件详情页面

### Requirement: Path Resolution

系统 SHALL 支持解析绝对路径和相对路径，兼容不同环境和历史数据。

#### Scenario: 解析相对路径
- **WHEN** 数据库存储的是相对路径（如 `data/raw/2025/file.xlsx`）
- **THEN** 系统从项目根目录解析完整路径
- **AND** 正确读取文件内容

#### Scenario: 解析绝对路径（兼容旧数据）
- **WHEN** 数据库存储的是绝对路径（如 `F:\...\data\raw\2025\file.xlsx`）
- **THEN** 系统尝试直接使用该路径
- **AND** 如果路径不存在，尝试从路径中提取相对部分并重新解析

## ADDED Requirements

### Requirement: Sync Progress Display

系统 SHALL 在同步过程中显示进度信息，让用户了解同步状态。

#### Scenario: 批量同步显示进度
- **WHEN** 用户启动批量同步任务
- **THEN** 系统显示进度信息（已处理/总数、当前文件名）
- **AND** 同步完成后显示结果统计

### Requirement: Cloud Deployment Compatibility

系统 SHALL 支持云端部署，路径存储和解析不依赖本地绝对路径。

#### Scenario: 云端部署文件访问
- **WHEN** 系统部署在云端环境
- **THEN** 通过环境变量配置数据目录
- **AND** 正确访问存储的文件

