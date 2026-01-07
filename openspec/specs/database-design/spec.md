# 数据库设计规范

**版本**: v1.0  
**创建时间**: 2025-11-19  
**最后更新**: 2025-01-31  
**状态**: 正式（Formal）  
**适用范围**: 西虹ERP系统所有数据库设计  
**生效日期**: 2025-11-19

---

## Purpose

本文档定义西虹ERP系统的数据库设计规范，包括数据归属规则、字段必填规则、主键设计规则、事实表和物化视图设计规则等。这些规则旨在确保数据库设计与源数据匹配，提高数据同步可靠性。

**核心原则**：
- 数据库设计必须与源数据匹配
- 主键字段必须能从源数据或文件元数据中获取
- 字段映射输出必须符合事实表结构
- 物化视图必须与字段映射输出匹配
- B类数据表必须按平台分表，表名包含platform_code信息，便于用户通过表名直接识别数据归属

---
## Requirements
### Requirement: 数据归属规则
系统 SHALL 明确定义数据归属规则，包括shop_id、account_id等归属字段的使用规则。

#### Scenario: 数据归属规则定义
- **WHEN** 系统设计数据库表结构
- **THEN** 系统应根据数据归属规则确定是否需要shop_id、account_id等归属字段
- **THEN** 系统应明确数据归属字段的来源（源数据、文件元数据、默认值等）
- **AND** **B类数据表必须按平台分表，表名包含platform_code信息**
- **AND** **用户可以通过表名直接识别数据归属（平台-数据域-子类型-粒度）**

### Requirement: 字段必填规则
系统 SHALL 明确定义字段必填规则，包括哪些字段必填，哪些可选。

#### Scenario: 主键字段必填规则
- **WHEN** 字段是主键的一部分
- **THEN** 字段必须NOT NULL（除非明确允许NULL，如inventory域的shop_id）
- **WHEN** 字段是唯一索引的一部分
- **THEN** 字段必须NOT NULL（除非明确允许NULL）

#### Scenario: 业务标识字段必填规则
- **WHEN** 字段是业务标识（如platform_code、order_id、platform_sku）
- **THEN** 字段必须NOT NULL
- **WHEN** 字段是可选业务标识（如shop_id、account_id）
- **THEN** 字段允许NULL（根据数据归属规则）

#### Scenario: 金额字段必填规则
- **WHEN** 字段是金额字段（如total_amount、quantity）
- **THEN** 字段必须NOT NULL，默认值为0.0（避免NULL计算问题）

#### Scenario: 金额字段默认值规则
- **WHEN** 金额字段为NULL或缺失
- **THEN** 系统应使用默认值0.0
- **WHEN** 金额字段为0
- **THEN** 系统应保留0值（不转换为NULL）

#### Scenario: 业务时间字段必填规则
- **WHEN** 字段是业务时间字段（如order_date、metric_date）
- **THEN** 字段允许NULL（如果源数据没有时间信息）
- **WHEN** 字段是审计时间字段（如created_at、updated_at）
- **THEN** 字段必须NOT NULL，默认值为当前时间

#### Scenario: 业务时间字段获取优先级规则
- **WHEN** 业务时间字段缺失
- **THEN** 系统应按以下优先级获取：
  1. 优先级1：从源数据行中获取时间字段
  2. 优先级2：从文件元数据（file_record）中获取时间信息
  3. 优先级3：从文件名中提取时间信息（如orders_2025-01-01.xlsx）
  4. 优先级4：使用当前时间作为默认值（仅作为兜底）

### Requirement: 主键设计规则
系统 SHALL 明确定义主键设计规则，包括何时使用复合主键，何时允许NULL。

#### Scenario: 经营数据主键设计规则
- **WHEN** 设计经营数据事实表（如FactOrder、FactOrderItem、FactProductMetric）
- **THEN** 系统应使用自增ID作为主键，业务标识字段（platform_code、shop_id、platform_sku等）作为唯一索引
- **WHEN** 业务标识字段组合能唯一标识记录
- **THEN** 系统应创建唯一索引（如FactOrderItem的(platform_code, shop_id, order_id, item_id)）
- **WHEN** 业务标识字段可能为NULL
- **THEN** 系统应评估是否调整唯一索引设计，或使用部分索引

#### Scenario: 运营数据主键设计规则
- **WHEN** 设计运营数据事实表（如FactTraffic、FactService、FactAnalytics）
- **THEN** 系统应使用自增ID作为主键，业务标识字段（platform_code、shop_id、metric_date等）作为唯一索引
- **WHEN** 业务标识字段组合能唯一标识记录
- **THEN** 系统应创建唯一索引（如FactTraffic的(platform_code, shop_id, metric_date, granularity, metric_type)）
- **WHEN** shop_id可能为NULL
- **THEN** 系统应允许shop_id为NULL，唯一索引应包含account字段作为替代

#### Scenario: 主键字段生成规则
- **WHEN** 主键字段是自增ID
- **THEN** 系统应使用数据库自增机制生成
- **WHEN** 主键字段是业务标识字段
- **THEN** 系统应确保字段能从源数据或文件元数据中获取
- **WHEN** 主键字段无法获取
- **THEN** 系统应隔离数据，并记录错误信息

#### Scenario: 复合主键使用规则
- **WHEN** 业务需要多个字段组合唯一标识一条记录
- **THEN** 系统应使用复合主键（如FactOrder的(platform_code, shop_id, order_id)）
- **WHEN** 业务只需要单个字段唯一标识一条记录
- **THEN** 系统应使用单字段主键（如FactProductMetric的id）

#### Scenario: 主键字段NULL规则
- **WHEN** 字段是主键的一部分
- **THEN** 字段通常必须NOT NULL
- **WHEN** 业务需要支持NULL值（如平台级数据）
- **THEN** 系统应评估是否调整主键设计，或使用替代方案（如使用account_id替代shop_id）

#### Scenario: 主键字段选择规则
- **WHEN** 选择主键字段
- **THEN** 系统应优先选择业务标识字段（如platform_code、shop_id、order_id）
- **WHEN** 业务标识字段可能为NULL
- **THEN** 系统应评估是否使用自增ID作为主键，业务标识字段作为唯一索引

### Requirement: 事实表设计规则
系统 SHALL 明确定义事实表设计规则，确保事实表结构与源数据匹配。

#### Scenario: 经营数据事实表设计规则
- **WHEN** 设计经营数据事实表（如FactOrder、FactOrderItem、FactProductMetric）
- **THEN** 系统应使用SKU作为业务标识核心（platform_code、shop_id、platform_sku）
- **WHEN** 表包含product_id字段
- **THEN** 系统应将product_id作为冗余字段，允许NULL，用于直接查询
- **WHEN** 表包含金额字段
- **THEN** 系统应确保金额字段NOT NULL，默认值为0.0

#### Scenario: 运营数据事实表设计规则
- **WHEN** 设计运营数据事实表（如FactTraffic、FactService、FactAnalytics）
- **THEN** 系统应使用shop_id作为业务标识核心（platform_code、shop_id）
- **WHEN** shop_id无法获取
- **THEN** 系统应使用account字段作为替代，允许shop_id为NULL
- **WHEN** 表包含metric_value字段
- **THEN** 系统应使用Numeric类型存储，确保精度

#### Scenario: 事实表字段设计规则
- **WHEN** 设计事实表字段
- **THEN** 系统应确保字段与源数据匹配，或提供明确的转换规则
- **WHEN** 源数据没有某个字段
- **THEN** 系统应允许字段为NULL，或从文件元数据中获取

#### Scenario: 事实表主键设计规则
- **WHEN** 设计事实表主键
- **THEN** 系统应确保主键字段都能从源数据或文件元数据中获取
- **WHEN** 主键字段可能为NULL
- **THEN** 系统应评估是否调整主键设计，或使用替代方案

#### Scenario: 事实表索引设计规则
- **WHEN** 设计事实表索引
- **THEN** 系统应确保索引字段都能从源数据或文件元数据中获取
- **WHEN** 索引字段可能为NULL
- **THEN** 系统应评估是否调整索引设计，或使用部分索引

#### Scenario: 事实表字段映射规则
- **WHEN** 字段映射输出到事实表
- **THEN** 系统应确保映射后的字段符合事实表结构
- **WHEN** 字段映射输出缺少必填字段
- **THEN** 系统应隔离数据，并记录错误信息
- **WHEN** 字段映射输出包含额外字段
- **THEN** 系统应忽略额外字段，或存储到attributes JSON字段中

### Requirement: 物化视图设计规则
系统 SHALL 明确定义物化视图设计规则，确保物化视图结构与字段映射输出匹配。

#### Scenario: 物化视图主视图设计规则
- **WHEN** 设计数据域主视图（Hub视图）
- **THEN** 系统应确保主视图包含该数据域的所有核心字段
- **WHEN** 主视图用于前端查询
- **THEN** 系统应确保主视图包含前端需要的所有字段，避免多次查询
- **WHEN** 主视图包含聚合数据
- **THEN** 系统应确保聚合维度字段都能从源数据或文件元数据中获取
- **WHEN** 主视图需要唯一索引
- **THEN** 系统应创建唯一索引，确保数据唯一性

#### Scenario: 物化视图辅助视图设计规则
- **WHEN** 设计辅助视图（Spoke视图）
- **THEN** 系统应确保辅助视图依赖主视图或基础数据
- **WHEN** 辅助视图用于特定分析场景
- **THEN** 系统应明确辅助视图的依赖关系，确保刷新顺序正确
- **WHEN** 辅助视图包含聚合数据
- **THEN** 系统应确保聚合维度字段都能从主视图或基础数据中获取

#### Scenario: 物化视图字段设计规则
- **WHEN** 设计物化视图字段
- **THEN** 系统应确保字段与字段映射输出匹配
- **WHEN** 字段映射输出没有某个字段
- **THEN** 系统应评估是否需要调整字段映射，或使用默认值

#### Scenario: 物化视图字段来源规则
- **WHEN** 物化视图字段来自事实表
- **THEN** 系统应确保字段名称和类型与事实表匹配
- **WHEN** 物化视图字段来自维度表
- **THEN** 系统应使用JOIN关联维度表，确保数据完整性
- **WHEN** 物化视图字段需要计算
- **THEN** 系统应确保计算所需的字段都能从源数据中获取

#### Scenario: 物化视图聚合规则
- **WHEN** 设计物化视图聚合规则
- **THEN** 系统应确保聚合维度字段都能从源数据或文件元数据中获取
- **WHEN** 聚合维度字段可能为NULL
- **THEN** 系统应评估是否需要调整聚合规则，或使用替代维度

#### Scenario: 物化视图聚合维度规则
- **WHEN** 物化视图需要按时间维度聚合
- **THEN** 系统应确保时间字段（metric_date、order_date等）能从源数据中获取
- **WHEN** 物化视图需要按店铺维度聚合
- **THEN** 系统应确保shop_id字段能从源数据或文件元数据中获取
- **WHEN** 物化视图需要按SKU维度聚合
- **THEN** 系统应确保platform_sku字段能从源数据中获取

#### Scenario: 物化视图更新规则
- **WHEN** 更新物化视图
- **THEN** 系统应确保物化视图结构与字段映射输出保持一致
- **WHEN** 字段映射输出发生变化
- **THEN** 系统应评估是否需要更新物化视图结构

#### Scenario: 物化视图刷新顺序规则
- **WHEN** 刷新物化视图
- **THEN** 系统应确保主视图（Hub视图）优先刷新
- **WHEN** 刷新辅助视图（Spoke视图）
- **THEN** 系统应确保依赖的主视图已刷新完成
- **WHEN** 辅助视图依赖其他辅助视图
- **THEN** 系统应按依赖顺序刷新，确保数据一致性

### Requirement: 产品ID原子级设计规则
系统 SHALL 支持以product_id为原子级的查询和分析。

#### Scenario: 产品ID冗余字段设计规则
- **WHEN** 设计FactOrderItem表
- **THEN** 系统应添加product_id字段作为冗余字段，允许NULL
- **WHEN** product_id字段存在
- **THEN** 系统应创建索引，支持高效查询
- **WHEN** 数据入库时
- **THEN** 系统应通过BridgeProductKeys表自动关联product_id

#### Scenario: 产品ID原子级物化视图设计规则
- **WHEN** 设计销售明细物化视图
- **THEN** 系统应创建mv_sales_detail_by_product视图，以product_id为原子级
- **WHEN** 物化视图包含product_id字段
- **THEN** 系统应确保product_id能从FactOrderItem中获取
- **WHEN** 物化视图需要关联产品信息
- **THEN** 系统应JOIN dim_product_master表，获取产品详细信息

### Requirement: 数据入库规则
系统 SHALL 明确定义数据入库流程规则，确保数据正确入库。

#### Scenario: 字段映射规则
- **WHEN** 字段映射应用到源数据
- **THEN** 系统应确保映射后的字段符合事实表结构
- **WHEN** 字段映射输出缺少必填字段
- **THEN** 系统应隔离数据，并记录错误信息
- **WHEN** 字段映射输出包含额外字段
- **THEN** 系统应忽略额外字段，或存储到attributes JSON字段中

#### Scenario: 字段映射输出验证规则
- **WHEN** 字段映射输出到事实表前
- **THEN** 系统应验证输出字段是否符合事实表结构
- **WHEN** 输出字段类型不匹配
- **THEN** 系统应进行类型转换，或隔离数据
- **WHEN** 输出字段值超出范围
- **THEN** 系统应隔离数据，并记录错误信息

#### Scenario: 数据验证规则
- **WHEN** 数据入库前
- **THEN** 系统应验证主键字段是否存在
- **WHEN** 主键字段缺失
- **THEN** 系统应隔离数据，并记录错误信息
- **THEN** 系统应验证字段数据类型和取值范围

#### Scenario: 数据隔离规则
- **WHEN** 数据不符合规范
- **THEN** 系统应隔离数据到DataQuarantine表
- **WHEN** 数据隔离
- **THEN** 系统应记录隔离原因和错误信息
- **THEN** 系统应提供数据修复和重新处理的机制

### Requirement: 数据同步可靠性
系统 SHALL 确保数据同步的可靠性，包括数据完整性、字段映射准确性、数据流转可追踪性和对比报告准确性。

#### Scenario: shop_id字段处理
- **WHEN** 源数据文件没有shop_id字段
- **THEN** 系统应从文件元数据（file_record）中获取shop_id
- **WHEN** 文件元数据也没有shop_id
- **THEN** 系统应根据数据归属规则决定是否允许shop_id为NULL，或隔离数据
- **THEN** 系统应记录shop_id获取的来源和方式

#### Scenario: 数据入库前验证
- **WHEN** 数据入库前
- **THEN** 系统应验证主键字段是否存在
- **WHEN** 主键字段缺失
- **THEN** 系统应隔离数据，并记录错误信息
- **THEN** 系统应验证字段数据类型和取值范围

---

### Requirement: B类数据表按平台分表规则
系统 SHALL 按照平台-数据域-子类型-粒度分表，确保用户可以通过表名直接识别数据归属。

#### Scenario: 表名格式规范
- **WHEN** 系统创建B类数据表时
- **THEN** 系统使用PlatformTableManager动态创建表
- **AND** 表名格式：
  - 无sub_domain：`fact_{platform}_{data_domain}_{granularity}`（如`fact_shopee_orders_daily`）
  - 有sub_domain：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`（如`fact_shopee_services_ai_assistant_monthly`）
- **AND** 平台代码（platform）必须小写（如`shopee`、`tiktok`、`miaoshou`）
- **AND** 数据域（data_domain）必须小写（如`orders`、`products`、`services`、`analytics`）
- **AND** 粒度（granularity）必须小写（如`daily`、`weekly`、`monthly`、`snapshot`）
- **AND** 子类型（sub_domain）必须小写（如`ai_assistant`、`agent`）
- **AND** 表名由PlatformTableManager.get_table_name()方法生成，确保格式统一
- **AND** **所有B类数据表存储在`b_class` schema中，便于Metabase中清晰区分和管理**

#### Scenario: 表结构规范
- **WHEN** 系统创建B类数据表时
- **THEN** 表必须包含以下系统字段：
  - `id` (BIGSERIAL PRIMARY KEY)
  - `platform_code` (VARCHAR(32) NOT NULL)
  - `shop_id` (VARCHAR(256))
  - `data_domain` (VARCHAR(64) NOT NULL)
  - `granularity` (VARCHAR(32) NOT NULL)
  - `sub_domain` (VARCHAR(64)) - services域必须NOT NULL，其他域可为NULL
  - `metric_date` (DATE NOT NULL)
  - `file_id` (INTEGER REFERENCES catalog_files(id))
  - `template_id` (INTEGER REFERENCES field_mapping_templates(id))
  - `raw_data` (JSONB NOT NULL)
  - `header_columns` (JSONB)
  - `data_hash` (VARCHAR(64) NOT NULL)
  - `ingest_timestamp` (TIMESTAMP NOT NULL DEFAULT NOW())
  - `currency_code` (VARCHAR(3))
- **AND** 表必须包含以下索引：
  - `platform_code`索引
  - `shop_id`索引
  - `data_domain`索引
  - `granularity`索引
  - `metric_date`索引
  - `file_id`索引
  - `data_hash`索引
  - `currency_code`索引
  - `raw_data` GIN索引
  - `sub_domain`索引（services域）

#### Scenario: 唯一约束规范
- **WHEN** 系统创建B类数据表时
- **THEN** 表必须包含唯一约束，基于以下字段：
  - services域：`data_domain, sub_domain, granularity, data_hash`
  - 其他域：`platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash`
- **AND** 唯一约束名称格式：`uq_{table_name}_hash`
- **AND** 由于shop_id可能为NULL，使用COALESCE处理（PostgreSQL唯一索引支持表达式）
- **AND** 唯一约束确保同一平台、同一店铺、同一数据域、同一粒度、同一data_hash的数据不重复

#### Scenario: 动态表管理
- **WHEN** 系统创建B类数据表时
- **THEN** 系统使用PlatformTableManager动态创建表（如果不存在）
- **AND** **所有B类数据表创建在`b_class` schema中，使用`CREATE TABLE IF NOT EXISTS b_class."{table_name}"`格式**
- **AND** 系统使用DynamicColumnManager根据模板字段添加动态列
- **AND** 动态列类型根据字段数据类型自动推断（VARCHAR、INTEGER、DECIMAL、DATE等）
- **AND** 动态列名称使用归一化的字段名（不含货币代码）
- **AND** 表创建后，系统使用PlatformTableManager.sync_table_columns()同步表列
- **AND** **所有索引创建也在`b_class` schema中**

#### Scenario: 动态表名查询
- **WHEN** 系统查询B类数据表时
- **THEN** 系统使用PlatformTableManager.get_table_name()生成表名
- **AND** 系统使用SQLAlchemy的text()函数执行原始SQL查询
- **AND** 表名作为字符串参数传入（用双引号包裹，避免大小写问题）
- **AND** 使用参数化查询（`:platform_code`），防止SQL注入
- **AND** PostgreSQL完全支持这种动态表名查询
- **AND** **查询时使用`b_class."{table_name}"`格式，或依赖`search_path`自动查找（向后兼容）**
- **AND** **跨平台查询：从`dim_platforms`表查询所有平台，使用UNION ALL合并查询结果**

## 非目标

- 不改变现有数据库结构（除非发现根本性问题）
- 不引入新的技术依赖
- 不修改现有API接口（保持向后兼容）

---

## 参考文档

- [数据库设计规则审查报告](../changes/archive/improve-data-sync-reliability/db_design_review_report.md)
- [数据库设计规范文档](../../docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md)
- [字段映射规范文档](../../docs/field_mapping_v2/SHOP_AND_DATE_RESOLUTION.md)
