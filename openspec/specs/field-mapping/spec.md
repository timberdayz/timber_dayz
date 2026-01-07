# 字段映射能力

## Requirements

### Requirement: 智能字段识别
系统应提供AI驱动的字段映射建议，并包含置信度评分。

#### Scenario: 自动字段匹配
- **WHEN** 用户上传包含中文列标题的Excel文件
- **THEN** 系统分析列名，与字段映射辞典进行比较，并建议标准字段映射及置信度评分

#### Scenario: 低置信度映射处理
- **WHEN** 建议的映射置信度评分低于阈值
- **THEN** 系统高亮显示低置信度映射并提示用户进行手动审核

### Requirement: 四层映射架构
系统应支持四层映射：原始字段 → 中文列名层 → 标准字段 → 数据库列名。

#### Scenario: 映射链执行
- **WHEN** 处理Excel文件进行字段映射
- **THEN** 系统应用映射链：读取原始字段名，映射到中文列名，映射到标准字段代码，最后映射到数据库列名

#### Scenario: 手动映射覆盖
- **WHEN** 用户为列手动选择不同的标准字段
- **THEN** 系统更新映射链并将用户偏好保存到字段映射模板

### Requirement: 基于模式的映射
系统应支持使用正则表达式进行基于模式的映射，以处理无限组合。

#### Scenario: 货币变体的模式匹配
- **WHEN** Excel列名匹配模式"销售额\\s*\\((?P<status>.+?)\\)\\s*\\((?P<currency>[A-Z]{3})\\)"
- **THEN** 系统提取状态和货币维度，映射到fact_order_amounts表，包含metric_type和currency字段

#### Scenario: 从模式中提取维度
- **WHEN** 应用基于模式的映射规则
- **THEN** 系统从正则表达式模式中提取命名组，并将它们映射到目标表中的维度列

### Requirement: 全球货币支持
系统应支持180+种货币，并自动识别和转换为CNY本位币。

#### Scenario: 货币符号标准化
- **WHEN** Excel文件包含货币符号如"S$"、"RM"、"R$"
- **THEN** 系统使用CurrencyNormalizer将符号标准化为ISO货币代码（SGD、MYR、BRL）

#### Scenario: 多货币订单金额
- **WHEN** 订单数据包含多种货币的金额
- **THEN** 系统在fact_order_amounts表中同时存储原始货币金额和CNY转换金额

#### Scenario: 汇率转换
- **WHEN** 金额需要转换为CNY
- **THEN** 系统使用CurrencyConverter获取汇率，转换金额，并存储原始金额和CNY金额以及汇率快照

### Requirement: 七个数据域支持
系统应支持七个数据域的字段映射：订单、产品、库存、服务、流量、分析和财务。

#### Scenario: 特定域的标准字段
- **WHEN** 用户选择数据域（例如，库存）
- **THEN** 系统仅显示该域相关的标准字段，来自field_mapping_dictionary表

#### Scenario: 跨域字段重用
- **WHEN** 标准字段存在于多个域中
- **THEN** 系统允许跨域重用相同的field_code，并使用特定域的显示名称

### Requirement: 模板系统
系统应支持保存和重用字段映射模板。

#### Scenario: 模板创建
- **WHEN** 用户完成字段映射配置
- **THEN** 系统允许将映射保存为模板，包含平台、data_domain和granularity元数据

#### Scenario: 模板应用
- **WHEN** 用户为新文件选择现有模板
- **THEN** 如果文件元数据（平台、域、粒度）匹配模板，系统自动应用模板映射

#### Scenario: 模板粒度匹配
- **WHEN** 将模板应用到文件
- **THEN** 系统优先使用文件元数据粒度而非用户选择的粒度进行模板匹配

### Requirement: 数据隔离区
系统应自动隔离未通过质量检查的数据。

#### Scenario: 质量检查失败
- **WHEN** 映射的数据未通过验证规则
- **THEN** 系统将数据移动到data_quarantine表，包含错误详情，并允许用户审核和重新处理

#### Scenario: 隔离数据审核
- **WHEN** 用户查看隔离数据
- **THEN** 系统显示原始数据、映射配置和验证错误以供故障排除

#### Scenario: 隔离数据重新处理
- **WHEN** 用户修复映射配置并重新处理隔离数据
- **THEN** 系统重新应用映射和验证，并将成功记录移动到事实表

### Requirement: 时间字段自动检测
系统应从样本数据中自动检测日期和日期时间字段类型。

#### Scenario: 日期类型检测
- **WHEN** 列中包含>=50%样本的日期值
- **THEN** 系统将字段标记为datetime类型并应用适当的解析

#### Scenario: 时间范围字段拆分
- **WHEN** 列包含时间范围格式如"2025-08-25-15:01~2025-08-29-12:01"
- **THEN** 系统自动拆分为start_time和end_time字段并检测粒度

### Requirement: Excel格式支持
系统应支持多种Excel格式：xlsx、xls（OLE）和xls（HTML伪装）。

#### Scenario: 格式自动检测
- **WHEN** 打开文件进行读取
- **THEN** 系统通过读取文件头魔数字节检测文件格式，并选择适当的解析器

#### Scenario: HTML伪装的Excel解析
- **WHEN** 文件被检测为HTML格式（妙手ERP特殊格式）
- **THEN** 系统使用pandas.read_html解析HTML表结构

### Requirement: 产品ID字段映射支持
系统应支持订单明细数据中的product_id字段映射和自动关联。

#### Scenario: product_id字段映射
- **WHEN** 订单明细数据包含product_id字段（如华为ISRP系统的SN字段）
- **THEN** 系统应支持将product_id映射到FactOrderItem表的product_id字段（冗余字段，便于直接查询）
- **WHEN** 订单明细数据不包含product_id字段，但包含platform_sku
- **THEN** 系统应在数据入库时通过BridgeProductKeys自动关联product_id（冗余字段设计）

#### Scenario: product_id自动关联规则
- **WHEN** 订单明细数据入库时，FactOrderItem表需要product_id字段
- **THEN** 系统应通过BridgeProductKeys查找对应的product_id（基于platform_code、shop_id、platform_sku）
- **WHEN** BridgeProductKeys中找不到对应的product_id
- **THEN** 系统应允许product_id为NULL，记录警告信息，支持后续数据修复和关联

#### Scenario: 产品ID与SKU的关系
- **WHEN** 字段映射涉及product_id和platform_sku
- **THEN** 系统应明确product_id是每个产品实例的唯一标识（类似身份证），platform_sku是产品类型的标识（类似人种）
- **WHEN** 一个SKU对应多个product_id
- **THEN** 系统应支持通过product_id查询单个产品实例的销售明细，通过platform_sku查询整个产品类型的销售情况