# 数据同步能力规范变更

## MODIFIED Requirements

### Requirement: 表头更新处理流程
系统 SHALL 检测文件表头变化，并智能识别货币代码变体，避免误报。

#### Scenario: 表头更新处理流程
- **WHEN** 文件表头发生变化（新增字段、删除字段、重命名字段）
- **THEN** 系统检测表头变化（detect_header_changes()）
- **AND** 系统计算表头匹配率（match_rate）
- **AND** 系统智能识别货币代码变体（如"销售额（已付款订单）(BRL)" vs "销售额（已付款订单）(COP)"）
- **AND** 如果只有货币代码差异，系统视为匹配（不触发变化检测）
- **AND** 如果匹配率<80%或存在其他字段变化，系统提示用户更新模板
- **AND** 用户更新模板时，系统创建新版本（version+1）并归档旧版本（status='archived'）
- **AND** 系统使用新模板同步后续文件

#### Scenario: 货币代码变体识别
- **WHEN** 文件表头包含货币代码变体（如"销售额（已付款订单）(BRL)" vs "销售额（已付款订单）(COP)"）
- **THEN** 系统使用正则表达式识别货币代码模式（`\(([A-Z]{3})\)`）
- **AND** 系统验证货币代码是否在ISO 4217标准列表中
- **AND** 系统将字段名归一化（移除货币代码部分）
- **AND** 系统比较归一化后的字段名
- **AND** 如果归一化后字段相同，系统视为匹配（不触发表头变化检测）
- **AND** 系统保留原始字段名用于前端显示（用户仍能看到货币代码）

### Requirement: 数据入库去重策略
系统 SHALL 根据数据域选择适当的去重策略，确保数据准确性。

#### Scenario: 库存数据UPSERT策略
- **WHEN** 库存数据（inventory域）入库时发生唯一约束冲突（data_hash已存在）
- **THEN** 系统使用UPSERT策略（INSERT ... ON CONFLICT ... DO UPDATE）
- **AND** 系统更新数量字段（通过更新raw_data JSONB字段）
- **AND** 系统更新raw_data字段（包含最新数据）
- **AND** 系统更新ingest_timestamp和file_id字段
- **AND** 系统保留metric_date字段（不更新，保持业务日期一致性）
- **AND** 系统保留维度字段（platform_code, shop_id, data_domain, granularity, data_hash）
- **AND** 系统不更新data_hash字段（它是唯一约束的一部分）

#### Scenario: 其他数据域INSERT策略
- **WHEN** 订单数据（orders域）或产品数据（products域）入库时发生唯一约束冲突
- **THEN** 系统使用INSERT策略（INSERT ... ON CONFLICT DO NOTHING）
- **AND** 系统跳过重复数据（不更新）
- **AND** 系统记录去重统计（重复数据不重复入库）

#### Scenario: 去重策略配置
- **WHEN** 数据入库时
- **THEN** 系统根据数据域获取去重策略（deduplication_fields_config.py）
- **AND** inventory域使用UPSERT策略
- **AND** orders/products/traffic/services/analytics域使用INSERT策略
- **AND** 系统根据策略执行相应的SQL语句

#### Scenario: 更新字段配置统一性
- **WHEN** 系统配置更新字段列表时
- **THEN** 系统为所有数据域统一配置更新字段列表（即使不使用UPSERT）
- **AND** 更新字段包括：raw_data, ingest_timestamp, file_id, header_columns
- **AND** 保留字段包括：metric_date, platform_code, shop_id, data_domain, granularity, data_hash
- **AND** 系统保持配置一致性，降低维护成本

