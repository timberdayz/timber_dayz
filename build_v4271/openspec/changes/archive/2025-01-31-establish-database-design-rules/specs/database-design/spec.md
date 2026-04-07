# 数据库设计规范

**版本**: v1.0  
**创建时间**: 2025-11-19  
**状态**: 正式（Formal）  
**适用范围**: 西虹ERP系统所有数据库设计  
**生效日期**: 2025-11-19

---

## 概述

本文档定义西虹ERP系统的数据库设计规范，包括数据归属规则、字段必填规则、主键设计规则、事实表和物化视图设计规则等。这些规则旨在确保数据库设计与源数据匹配，提高数据同步可靠性。

**核心原则**：
- 数据库设计必须与源数据匹配
- 主键字段必须能从源数据或文件元数据中获取
- 字段映射输出必须符合事实表结构
- 物化视图必须与字段映射输出匹配

---

## ADDED Requirements

### Requirement: 数据归属规则
系统应明确定义数据归属规则，包括shop_id、account_id等归属字段的使用规则。

#### Scenario: 数据归属规则定义
- **WHEN** 系统设计数据库表结构
- **THEN** 系统应根据数据归属规则确定是否需要shop_id、account_id等归属字段
- **THEN** 系统应明确数据归属字段的来源（源数据、文件元数据、默认值等）

#### Scenario: shop_id字段使用规则
- **WHEN** 数据需要归属到店铺（如orders、products、traffic域）
- **THEN** 系统应使用shop_id字段，shop_id必须从源数据或文件元数据中获取
- **WHEN** 数据是平台级数据（不需要归属到店铺，如inventory域的仓库级数据）
- **THEN** 系统应允许shop_id为NULL
- **WHEN** shop_id无法从源数据或文件元数据中获取
- **THEN** 系统应隔离数据，并记录错误信息

#### Scenario: shop_id获取优先级规则
- **WHEN** 数据入库时shop_id缺失
- **THEN** 系统应按以下优先级获取shop_id：
  1. 优先级1：从源数据行中获取shop_id字段
  2. 优先级2：从文件元数据（file_record）中获取shop_id
  3. 优先级3：通过AccountAlias表映射（如果account字段有值）
  4. 优先级4：从文件名或其他标识符提取（仅作为兜底）
  5. 优先级5：根据数据域规则决定是否允许NULL（inventory域允许NULL，其他域隔离数据）
- **WHEN** 使用AccountAlias映射获取shop_id
- **THEN** 系统应调用AccountAlignmentService进行账号对齐
- **WHEN** AccountAlias映射成功
- **THEN** 系统应使用映射后的shop_id，并记录映射关系
- **WHEN** AccountAlias映射失败
- **THEN** 系统应记录警告信息，支持后续手动添加映射关系

#### Scenario: account_id字段使用规则
- **WHEN** 数据需要归属到账号
- **THEN** 系统应使用account_id字段，account_id必须从源数据或文件元数据中获取
- **WHEN** 数据不需要归属到账号
- **THEN** 系统应允许account_id为NULL

#### Scenario: platform_code字段使用规则
- **WHEN** 数据需要标识平台
- **THEN** 系统应使用platform_code字段，platform_code必须从源数据或文件元数据中获取
- **WHEN** platform_code无法从源数据或文件元数据中获取
- **THEN** 系统应使用默认值"unknown"，并记录警告信息

#### Scenario: platform_code获取优先级规则
- **WHEN** 数据入库时platform_code缺失
- **THEN** 系统应按以下优先级获取platform_code：
  1. 优先级1：从源数据行中获取platform_code字段
  2. 优先级2：从文件元数据（file_record）中获取platform_code
  3. 优先级3：从文件路径或文件名中提取平台信息（如shopee_orders_xxx.xlsx）
  4. 优先级4：使用默认值"unknown"，并记录警告信息
- **WHEN** platform_code从文件元数据获取
- **THEN** 系统应确保file_record.platform_code存在且有效
- **WHEN** platform_code使用默认值"unknown"
- **THEN** 系统应记录警告信息，支持后续数据修复

### Requirement: 字段必填规则
系统应明确定义字段必填规则，包括哪些字段必填，哪些可选。

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
- **THEN** 系统应使用默认值0.0，而不是NULL
- **WHEN** 金额字段为负数（如退款金额）
- **THEN** 系统应允许负数，但应验证业务逻辑合理性
- **WHEN** 金额字段需要货币转换
- **THEN** 系统应同时存储原币金额和人民币金额（如total_amount和total_amount_rmb）

#### Scenario: 时间字段必填规则
- **WHEN** 字段是审计字段（如created_at、updated_at）
- **THEN** 字段必须NOT NULL，默认值为当前时间
- **WHEN** 字段是业务时间字段（如order_date、metric_date）
- **THEN** 字段允许NULL（如果源数据没有时间信息），但应记录警告信息

#### Scenario: 业务时间字段获取规则
- **WHEN** 业务时间字段（如order_date、metric_date）缺失
- **THEN** 系统应按以下优先级获取：
  1. 优先级1：从源数据行中获取时间字段
  2. 优先级2：从文件名中提取日期（如20250926）
  3. 优先级3：使用文件上传时间或处理时间
  4. 优先级4：允许NULL，但记录警告信息
- **WHEN** 时间字段从文件名提取
- **THEN** 系统应使用正则表达式匹配日期格式（如YYYYMMDD）
- **WHEN** 时间字段无法获取
- **THEN** 系统应记录警告信息，支持后续数据修复

### Requirement: 主键设计规则
系统应明确定义主键设计规则，包括何时使用复合主键，何时允许NULL。

#### Scenario: 复合主键使用规则
- **WHEN** 业务需要多个字段组合唯一标识一条记录
- **THEN** 系统应使用复合主键（如FactOrder的(platform_code, shop_id, order_id)）
- **WHEN** 业务只需要单个字段唯一标识一条记录
- **THEN** 系统应使用单字段主键（如FactProductMetric的id）

#### Scenario: 主键字段NULL规则
- **WHEN** 字段是主键的一部分
- **THEN** 字段通常必须NOT NULL
- **WHEN** 业务需要支持NULL值（如平台级数据）
- **THEN** 系统应评估是否调整主键设计，或使用替代方案（如使用account_id替代shop_id，或使用自增ID作为主键）

#### Scenario: 主键字段选择规则
- **WHEN** 选择主键字段
- **THEN** 系统应优先选择业务标识字段（如platform_code、shop_id、order_id）
- **WHEN** 业务标识字段可能为NULL
- **THEN** 系统应评估是否使用自增ID作为主键，业务标识字段作为唯一索引

#### Scenario: 主键字段来源规则
- **WHEN** 主键字段必须能从源数据或文件元数据中获取
- **THEN** 系统应确保主键字段的来源明确（源数据、文件元数据、默认值等）
- **WHEN** 主键字段无法从源数据或文件元数据中获取
- **THEN** 系统应隔离数据，并记录错误信息

#### Scenario: 经营数据主键设计规则
- **WHEN** 数据是经营数据（如miaoshou ERP提供的商品SKU、产品SKU、库存数量、销售金额等）
- **THEN** 系统应使用SKU作为业务唯一标识的核心字段（如platform_sku或product_sku）
- **WHEN** 经营数据需要区分不同维度（如平台、店铺、日期、数据域）
- **THEN** 系统应使用自增ID作为主键，业务唯一索引包含SKU和其他业务维度（如(platform_code, shop_id, platform_sku, metric_date, data_domain)）
- **WHEN** 经营数据的店铺信息是别名（如"新加坡1店"）
- **THEN** 系统应通过AccountAlias表映射到标准shop_id，业务唯一索引使用映射后的shop_id
- **WHEN** 经营数据是库存快照数据（仓库级数据，不需要shop_id）
- **THEN** 系统应允许shop_id为NULL，业务唯一索引为(platform_code, platform_sku, metric_date, data_domain)
- **WHEN** 设计经营数据表主键
- **THEN** 系统应使用自增ID作为主键（便于外键引用和性能优化），业务唯一性通过唯一索引保证

#### Scenario: 运营数据主键设计规则
- **WHEN** 数据是运营数据（如shopee/tiktok提供的客流量、服务人数、未回复消息等）
- **THEN** 系统应使用shop_id作为业务唯一标识的核心字段
- **WHEN** 运营数据需要区分不同维度（如平台、日期、指标类型、数据域）
- **THEN** 系统应使用自增ID作为主键，业务唯一索引包含shop_id和其他业务维度（如(platform_code, shop_id, metric_date, metric_type, data_domain)）
- **WHEN** shop_id无法从源数据中获取
- **THEN** 系统应从文件元数据（.meta.json）中提取shop_id和account信息
- **WHEN** 某些运营数据没有shop_id（如平台级数据）
- **THEN** 系统应使用account作为替代，业务唯一索引为(platform_code, account, metric_date, metric_type, data_domain)
- **WHEN** 设计运营数据表主键
- **THEN** 系统应使用自增ID作为主键（便于外键引用和性能优化），业务唯一性通过唯一索引保证

### Requirement: 事实表设计规则
系统应明确定义事实表设计规则，确保事实表结构与源数据匹配。

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

#### Scenario: 经营数据和运营数据分离规则
- **WHEN** 数据是经营数据（如miaoshou ERP提供的商品SKU、产品SKU、商品售价、商品进价、库存数量、退货数量、退款金额、销售店铺信息等）
- **THEN** 系统应使用专门的事实表存储经营数据（如FactProductMetric用于商品指标，FactOrder用于订单数据，FactOrderItem用于订单明细）
- **WHEN** 数据是运营数据（如shopee/tiktok提供的客流量、服务人数、未回复消息等）
- **THEN** 系统应创建专门的事实表存储运营数据（如FactTraffic用于流量数据，FactService用于服务数据，FactAnalytics用于分析数据）
- **WHEN** 经营数据的店铺信息是别名（如"新加坡1店"）
- **THEN** 系统应通过AccountAlias表映射到标准shop_id，确保数据归属正确
- **WHEN** 运营数据的shop_id无法从源数据中获取
- **THEN** 系统应从文件元数据（.meta.json）中提取shop_id和account信息
- **WHEN** 创建新的运营数据表
- **THEN** 系统应确保表结构符合运营数据主键设计规则（自增ID主键+shop_id为核心的唯一索引）
- **WHEN** 经营数据和运营数据需要关联查询
- **THEN** 系统应通过shop_id或account进行关联，确保数据归属一致

#### Scenario: 产品ID冗余字段设计规则
- **WHEN** 设计经营数据事实表（如FactOrderItem）
- **THEN** 系统应在表中添加product_id字段作为冗余字段（便于直接查询，无需通过BridgeProductKeys关联）
- **WHEN** product_id字段为冗余字段
- **THEN** 系统应保持现有主键设计不变（如FactOrderItem的主键仍为(platform_code, shop_id, order_id, platform_sku)）
- **WHEN** 数据入库时
- **THEN** 系统应通过BridgeProductKeys自动关联product_id，如果找不到则product_id为NULL（允许，但应记录警告）
- **WHEN** product_id字段为NULL
- **THEN** 系统应记录警告信息，支持后续数据修复和关联
- **WHEN** 设计product_id字段索引
- **THEN** 系统应创建索引以支持高效查询（如CREATE INDEX idx_fact_order_items_product_id ON fact_order_items(product_id)）

### Requirement: 物化视图设计规则
系统应明确定义物化视图设计规则，确保物化视图结构与字段映射输出匹配。

#### Scenario: 物化视图字段设计规则
- **WHEN** 设计物化视图字段
- **THEN** 系统应确保字段与字段映射输出匹配
- **WHEN** 字段映射输出没有某个字段
- **THEN** 系统应评估是否需要调整字段映射，或使用默认值

#### Scenario: 物化视图聚合规则
- **WHEN** 设计物化视图聚合规则
- **THEN** 系统应确保聚合维度字段都能从源数据或文件元数据中获取
- **WHEN** 聚合维度字段可能为NULL
- **THEN** 系统应评估是否需要调整聚合规则，或使用替代维度

#### Scenario: 物化视图更新规则
- **WHEN** 更新物化视图
- **THEN** 系统应确保物化视图结构与字段映射输出保持一致
- **WHEN** 字段映射输出发生变化
- **THEN** 系统应评估是否需要更新物化视图结构

#### Scenario: 物化视图数据域集中规则
- **WHEN** 设计物化视图
- **THEN** 系统应确保一个数据域的核心信息集中在一个主视图上（如products域的所有商品信息集中在mv_product_management视图）
- **WHEN** 一个数据域的信息分散在多个物化视图中
- **THEN** 系统应评估是否需要合并视图，或明确视图之间的依赖关系（主视图和辅助视图）
- **WHEN** 物化视图包含多个数据域的信息
- **THEN** 系统应评估是否需要拆分视图，确保每个视图只包含一个数据域的信息
- **WHEN** 前端需要查询某个数据域的信息
- **THEN** 系统应确保前端可以从对应的主视图中一次性获取该数据域的所有核心信息，避免多次查询

#### Scenario: 物化视图主视图和辅助视图规则
- **WHEN** 设计数据域的主视图
- **THEN** 系统应创建一个包含该数据域所有核心字段的主视图（如mv_product_management包含SKU、名称、价格、库存、销量、销售额、流量、转化率等）
- **WHEN** 需要特定分析场景的视图
- **THEN** 系统应创建辅助视图（如mv_product_sales_trend用于销售趋势分析，mv_top_products用于TopN排行）
- **WHEN** 辅助视图依赖主视图
- **THEN** 系统应明确视图之间的依赖关系，确保刷新顺序正确（先刷新主视图，再刷新辅助视图）
- **WHEN** 前端需要查询数据域信息
- **THEN** 系统应优先使用主视图，辅助视图仅用于特定分析场景
- **WHEN** 物化视图刷新
- **THEN** 系统应按依赖顺序刷新（先刷新主视图，再刷新依赖主视图的辅助视图）

#### Scenario: 产品ID原子级物化视图设计规则
- **WHEN** 设计销售明细物化视图
- **THEN** 系统应创建以product_id为原子级的物化视图（如mv_sales_detail_by_product），每行代表一个产品实例的销售明细
- **WHEN** 物化视图以product_id为原子级
- **THEN** 系统应包含产品信息（product_id、SKU、名称、规格、品类、品牌等）
- **WHEN** 物化视图以product_id为原子级
- **THEN** 系统应包含订单信息（订单ID、日期、时间、状态、买家ID、买家名称等）
- **WHEN** 物化视图以product_id为原子级
- **THEN** 系统应包含价格信息（单价、行金额、成本、利润等，支持原币和人民币）
- **WHEN** 物化视图以product_id为原子级
- **THEN** 系统应包含店铺和平台信息（平台代码、店铺ID、店铺名称等）
- **WHEN** 物化视图以product_id为原子级
- **THEN** 系统应包含数量信息（销售数量等）
- **WHEN** 创建mv_sales_detail_by_product视图
- **THEN** 系统应从fact_order_items、fact_orders、bridge_product_keys、dim_product_master等表关联获取数据
- **WHEN** 物化视图以product_id为原子级
- **THEN** 系统应支持类似华为ISRP系统的销售明细表结构（每行一个产品实例，包含所有销售信息）
- **WHEN** 前端需要查询产品实例的销售明细
- **THEN** 系统应支持通过product_id直接查询mv_sales_detail_by_product视图

### Requirement: 数据入库流程规则
系统应明确定义数据入库流程规则，确保数据入库符合数据库设计规则。

#### Scenario: shop_id获取规则
- **WHEN** 数据入库时shop_id缺失
- **THEN** 系统应从文件元数据（file_record）中获取shop_id
- **WHEN** 文件元数据也没有shop_id
- **THEN** 系统应根据数据归属规则决定是否允许shop_id为NULL，或隔离数据

#### Scenario: platform_code获取规则
- **WHEN** 数据入库时platform_code缺失
- **THEN** 系统应从文件元数据（file_record）中获取platform_code
- **WHEN** 文件元数据也没有platform_code
- **THEN** 系统应使用默认值"unknown"，并记录警告信息

#### Scenario: AccountAlias映射规则
- **WHEN** 数据入库时account字段有值但aligned_account_id为空
- **THEN** 系统应自动调用AccountAlignmentService进行账号对齐
- **WHEN** AccountAlignmentService找到匹配的shop_id
- **THEN** 系统应将aligned_account_id设置为匹配的shop_id
- **WHEN** AccountAlignmentService未找到匹配的shop_id
- **THEN** 系统应允许aligned_account_id为NULL，并记录警告信息
- **WHEN** 源数据中的店铺信息是别名（如"新加坡1店"）
- **THEN** 系统应通过AccountAlias表映射到标准shop_id（如"HXHOME"）
- **WHEN** AccountAlias表中有匹配记录
- **THEN** 系统应使用映射后的shop_id进行数据归属
- **WHEN** AccountAlias表中没有匹配记录
- **THEN** 系统应记录警告信息，支持后续手动添加映射关系
- **WHEN** AccountAlignmentService进行匹配
- **THEN** 系统应优先使用精确匹配（account + site + store_label_raw）
- **WHEN** 精确匹配失败
- **THEN** 系统应尝试宽松匹配（account + store_label_raw，忽略site）
- **WHEN** 宽松匹配失败
- **THEN** 系统应尝试部分匹配（store_label_raw包含account或account包含store_label_raw）

#### Scenario: 数据验证规则
- **WHEN** 数据入库前
- **THEN** 系统应验证主键字段是否存在
- **WHEN** 主键字段缺失
- **THEN** 系统应隔离数据，并记录错误信息

#### Scenario: 数据隔离规则
- **WHEN** 数据无法入库（主键字段缺失、数据类型错误等）
- **THEN** 系统应将数据隔离到data_quarantine表
- **THEN** 系统应记录隔离原因和错误信息
- **THEN** 系统应提供数据修复和重新处理的机制

---

## MODIFIED Requirements

### Requirement: 数据同步可靠性
系统应确保数据同步的可靠性，包括数据完整性、字段映射准确性、数据流转可追踪性和对比报告准确性。

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

## 参考文档

- [数据库设计规则审查报告](../improve-data-sync-reliability/db_design_review_report.md)
- [数据库设计规范文档](../../../docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md)
- [字段映射规范文档](../../../docs/field_mapping_v2/SHOP_AND_DATE_RESOLUTION.md)

