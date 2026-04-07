## MODIFIED Requirements

### Requirement: 单文件数据同步
系统 SHALL 支持单个Excel文件的数据同步，包括模板查找和配置、数据预览、去重处理和数据入库到B类数据表，**确保所有唯一行都被正确导入**。

#### Scenario: 单文件同步成功流程（DSS架构）- 完整导入
- **WHEN** 用户请求同步单个文件（file_id）
- **THEN** 系统查找文件记录，检查文件状态，查找匹配的模板（TemplateMatcher），使用模板的header_row和header_columns，预览文件数据，补充元数据（platform_code, shop_id），计算data_hash进行去重，调用DataIngestionService入库到B类数据表（fact_raw_data_*，JSONB格式），更新文件状态为ingested，并返回同步结果
- **AND** 系统验证数据完整性（行数、字段完整性、data_hash唯一性）
- **AND** 系统记录统计信息（staged, imported, quarantined=0）
- **AND** 系统跳过字段映射、数据标准化、业务逻辑验证和数据隔离（DSS架构原则）
- **AND** **系统确保所有唯一行都被导入（imported行数应等于源文件唯一行数，排除合法重复）**
- **AND** **系统使用模板配置的核心字段（deduplication_fields）计算data_hash，如果模板未配置则使用默认配置**

#### Scenario: 数据行数验证（B类数据表）- 完整导入
- **WHEN** 数据同步完成后
- **THEN** 系统验证B类数据表（fact_raw_data_*）数据行数与文件行数一致性
- **AND** 系统记录数据行数统计（total_rows, imported, quarantined=0）
- **AND** 系统验证数据以JSONB格式存储（保留原始中文表头）
- **AND** **系统验证imported行数等于源文件唯一行数（排除合法重复，允许5%误差）**
- **AND** **如果imported行数显著少于源文件行数（>5%差异），系统记录警告并提示用户检查去重配置**

#### Scenario: data_hash唯一性验证（去重）- 正确去重
- **WHEN** 数据入库时
- **THEN** 系统验证data_hash唯一性（基于SHA256计算）
- **AND** 系统处理data_hash冲突（ON CONFLICT DO NOTHING，自动去重）
- **AND** 系统记录去重统计（重复数据不重复入库）
- **AND** **系统确保data_hash计算包含足够的唯一标识字段（如product_id, order_id, SKU等）**
- **AND** **系统使用模板配置的deduplication_fields（如果存在）来计算data_hash**
- **AND** **系统记录用于hash计算的字段列表（用于调试和验证）**
- **AND** **如果核心字段在数据中不存在，系统记录警告但继续处理（使用NULL值）**

#### Scenario: 批量插入完整性验证
- **WHEN** 批量插入数据到B类数据表时
- **THEN** 系统确保所有行都被处理（不遗漏任何行）
- **AND** 系统使用批量插入优化性能（对于普通索引）或逐行插入（对于表达式索引）
- **AND** 系统验证实际插入行数（通过比较插入前后的记录数）
- **AND** **系统确保批量插入循环处理所有行，不提前退出**
- **AND** **系统记录插入过程的详细日志（总行数、已处理行数、成功插入行数、跳过行数）**

### Requirement: 批量数据同步
系统 SHALL 支持批量文件的数据同步，包括文件筛选、并发处理和进度跟踪，**确保每个文件的所有唯一行都被正确导入**。

#### Scenario: 批量同步文件处理完整性
- **WHEN** 用户请求批量同步，指定平台、数据域、粒度、时间范围等筛选条件
- **THEN** 系统查询catalog_files表，筛选出符合条件的pending状态文件，创建进度跟踪任务，提交后台异步处理，立即返回task_id和文件总数
- **AND** 系统验证文件元数据完整性（platform_code, shop_id, data_domain, granularity, date_range）
- **AND** **系统确保每个文件的所有唯一行都被导入（不遗漏任何文件的数据）**
- **AND** **系统记录每个文件的导入统计（总行数、导入行数、跳过行数）**

### Requirement: 数据完整性验证（DSS架构）
系统 SHALL 在数据同步过程中验证数据完整性，确保数据无丢失、字段完整、data_hash唯一，**并验证所有唯一行都被正确导入**。

#### Scenario: 数据行数验证（B类数据表）- 完整导入验证
- **WHEN** 数据同步完成后
- **THEN** 系统验证B类数据表（fact_raw_data_*）数据行数与文件行数一致性
- **AND** 系统记录数据行数统计（total_rows, imported, quarantined=0）
- **AND** 系统验证数据以JSONB格式存储（保留原始中文表头）
- **AND** 系统验证去重机制（data_hash唯一性）
- **AND** **系统验证imported行数等于源文件唯一行数（排除合法重复）**
- **AND** **如果imported行数显著少于源文件行数（>5%差异且非去重导致），系统记录错误并提示用户检查配置**

#### Scenario: data_hash唯一性验证（去重）- 正确去重验证
- **WHEN** 数据入库时
- **THEN** 系统验证data_hash唯一性（基于SHA256计算）
- **AND** 系统处理data_hash冲突（ON CONFLICT DO NOTHING，自动去重）
- **AND** 系统记录去重统计（重复数据不重复入库）
- **AND** **系统确保data_hash计算包含足够的唯一标识字段（如product_id, order_id, SKU等），避免所有行产生相同的hash**
- **AND** **系统使用模板配置的deduplication_fields（如果存在）来计算data_hash，确保去重逻辑正确**
- **AND** **系统记录用于hash计算的字段列表和示例hash值（用于调试和验证）**
- **AND** **如果核心字段在数据中不存在，系统记录警告但继续处理（使用NULL值），如果所有核心字段都是NULL则记录严重警告**

#### Scenario: 批量插入完整性验证
- **WHEN** 批量插入数据到B类数据表时
- **THEN** 系统确保所有行都被处理（不遗漏任何行）
- **AND** 系统使用批量插入优化性能（对于普通索引）或逐行插入（对于表达式索引）
- **AND** 系统验证实际插入行数（通过比较插入前后的记录数）
- **AND** **系统确保批量插入循环处理所有行，不提前退出或跳过行**
- **AND** **系统记录插入过程的详细日志（总行数、已处理行数、成功插入行数、跳过行数、错误行数）**
- **AND** **如果实际插入行数显著少于准备插入行数（>5%差异），系统记录警告并提示用户检查去重配置和唯一约束**

### Requirement: Metabase 集成数据要求（DSS架构）
系统 SHALL 确保B类数据表数据格式符合Metabase查询要求，支持Metabase Question查询B类数据表数据，**并确保数据完整性以支持Metabase外键关系编辑**。

#### Scenario: JSONB数据格式符合要求
- **WHEN** Metabase查询B类数据表数据
- **THEN** 系统确保raw_data字段为有效的JSONB格式
- **AND** 系统确保header_columns字段包含原始表头字段列表
- **AND** 系统确保元数据字段（platform_code, shop_id, metric_date等）符合Metabase要求
- **AND** 系统在Metabase中通过字段映射或计算字段处理数据类型转换
- **AND** **系统确保所有唯一行都被导入，以便Metabase可以正确建立外键关系**

#### Scenario: Metabase数据查询和验证
- **WHEN** Metabase Question查询B类数据表
- **THEN** 系统确保数据可以被Metabase正确查询
- **AND** 系统确保数据行数符合Question要求（所有唯一行都被导入）
- **AND** 系统在Metabase中配置字段映射（原始表头字段 → 标准字段）
- **AND** 系统在Metabase中配置业务逻辑验证规则
- **AND** 系统在Metabase中查询和验证数据质量
- **AND** **系统确保数据完整性，支持Metabase外键关系编辑（所有相关行都存在）**

## ADDED Requirements

### Requirement: 核心字段配置（模板管理）
系统 SHALL 支持用户在模板保存界面配置核心字段（deduplication_fields），用于数据去重的data_hash计算。

#### Scenario: 核心字段选择（必填）
- **WHEN** 用户保存模板时
- **THEN** 系统显示核心字段选择器（多选框，从表头字段中选择）
- **AND** 系统要求用户至少选择1个核心字段（必填，不允许使用默认值）
- **AND** 系统显示提示文本："核心字段用于数据去重，请选择能够唯一标识每行数据的字段（如：订单号、产品SKU等）"
- **AND** 系统验证用户选择的字段不为空（前端验证）
- **AND** 系统在保存模板时传递`deduplication_fields`参数到后端API

#### Scenario: 核心字段推荐（可选）
- **WHEN** 用户预览文件数据后
- **THEN** 系统调用API获取默认核心字段推荐（基于数据域和子类型）
- **AND** 系统显示推荐字段列表，但不自动勾选（用户必须手动选择）
- **AND** 系统显示推荐说明："根据数据域，建议选择以下字段作为核心字段"
- **AND** 系统允许用户忽略推荐，自行选择核心字段

#### Scenario: 核心字段验证（软验证）
- **WHEN** 用户选择核心字段后
- **THEN** 系统验证用户选择的字段是否在`headerColumns`中
- **AND** 如果字段不在表头中，系统显示警告："以下字段不在表头中：{字段列表}，可能导致去重失败"
- **AND** 系统允许用户继续保存，但提示风险（不阻止保存）
- **AND** 系统在后端保存时记录警告日志（如果字段不在`header_columns`中）

#### Scenario: 核心字段显示（模板列表和详情）
- **WHEN** 用户查看模板列表
- **THEN** 系统在模板列表表格中显示"核心字段"列
- **AND** 系统显示格式：`3个字段`（显示字段数量）
- **AND** 系统在鼠标悬停时显示完整字段列表（tooltip）
- **WHEN** 用户查看模板详情
- **THEN** 系统在模板详情弹窗中显示完整核心字段列表
- **AND** 系统显示字段说明："用于数据去重，确保每行数据唯一"
- **AND** 系统显示核心字段数量统计

### Requirement: 核心字段API（后端）
系统 SHALL 提供API支持核心字段配置和推荐。

#### Scenario: 获取默认核心字段推荐
- **WHEN** 前端请求获取默认核心字段推荐
- **THEN** 系统提供`GET /api/field-mapping/templates/default-deduplication-fields` API
- **AND** 系统根据`data_domain`和`sub_domain`参数返回默认核心字段列表
- **AND** 系统返回字段说明和推荐原因
- **AND** 系统支持所有数据域（orders, products, inventory, traffic, services, analytics）

#### Scenario: 保存模板时验证核心字段
- **WHEN** 用户保存模板时传递`deduplication_fields`参数
- **THEN** 系统验证`deduplication_fields`不为空（必填）
- **AND** 系统验证`deduplication_fields`必须是列表且至少包含1个字段
- **AND** 系统验证字段格式正确（列表中的元素都是字符串）
- **AND** 系统验证核心字段是否在`header_columns`中（如果不在，记录警告但不阻止保存）
- **AND** 系统支持中英文字段名匹配（如"订单号"和"order_id"）

#### Scenario: 核心字段在数据同步中的使用
- **WHEN** 数据同步时查找模板
- **THEN** 系统从模板读取`deduplication_fields`配置
- **AND** 系统确定最终使用的核心字段（优先级：模板配置 > 默认配置 > 所有字段）
- **AND** 系统使用核心字段计算`data_hash`
- **AND** 系统记录使用的核心字段列表和匹配情况（找到/未找到的字段）
- **AND** 如果核心字段在数据中不存在，系统记录警告但继续处理（使用NULL值）
- **AND** **如果模板没有`deduplication_fields`配置（向后兼容），系统使用默认配置并记录警告**

#### Scenario: 向后兼容性处理（现有模板）
- **WHEN** 数据同步时查找模板，但模板没有`deduplication_fields`字段或字段为空
- **THEN** 系统使用默认核心字段配置（基于数据域和子类型）
- **AND** 系统记录警告："模板未配置核心字段，使用默认配置：{默认字段列表}"
- **AND** 系统继续正常处理数据同步
- **AND** 系统提示用户："建议在下次保存模板时添加核心字段配置"
