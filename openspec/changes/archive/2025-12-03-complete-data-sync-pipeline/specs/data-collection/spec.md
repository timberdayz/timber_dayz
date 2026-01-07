## MODIFIED Requirements

### Requirement: 文件注册和元数据索引
系统 SHALL 自动将采集的文件注册到catalog_files表，并包含完整的元数据。

#### Scenario: 文件元数据提取
- **WHEN** 从平台下载新的Excel文件
- **THEN** 系统提取platform_code、shop_id、data_domain、granularity、date_range和file_hash，然后将记录插入catalog_files表
- **AND** 系统验证文件元数据完整性（platform_code, shop_id, data_domain, granularity, date_range不为NULL）
- **AND** 系统验证文件路径（file_path）正确且文件存在

#### Scenario: 重复文件检测
- **WHEN** catalog_files表中已存在相同file_hash的文件
- **THEN** 系统跳过注册并将文件标记为重复
- **AND** 系统记录重复文件信息到日志

#### Scenario: 文件注册验证
- **WHEN** 文件注册完成后
- **THEN** 系统验证文件记录已正确插入catalog_files表
- **AND** 系统验证文件状态为pending（待处理）
- **AND** 系统验证文件元数据字段完整且正确

## ADDED Requirements

（这些 Requirement 已在之前的归档中添加，无需重复添加）

