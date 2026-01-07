# Tasks: 设计 Metabase 模型和 Question

## 1. 创建 Metabase Models [TODO]

- [ ] 1.1 Orders Model
  - 整合所有平台的订单数据（shopee, tiktok, miaoshou等）
  - 整合所有粒度（daily, weekly, monthly）
  - 统一字段名（销售额、订单号、订单状态等）
  - 关联账号管理表获取店铺名称
  - 使用UNION ALL合并不同平台和粒度的表

- [ ] 1.2 Products Model
  - 整合所有平台的产品数据
  - 整合所有粒度
  - 统一字段名（产品ID、SKU、产品名称等）
  - 关联账号管理表获取店铺名称

- [ ] 1.3 Traffic Model
  - 整合所有平台的流量数据
  - 整合所有粒度
  - 统一字段名（访客数、浏览量、转化率等）
  - 关联账号管理表获取店铺名称

- [ ] 1.4 Services Model
  - 整合所有平台的服务数据
  - 整合所有粒度
  - 区分子类型（agent, ai_assistant）
  - 统一字段名
  - 关联账号管理表获取店铺名称

- [ ] 1.5 Inventory Model
  - 库存快照数据
  - 统一字段名（库存数量、仓库ID等）
  - 关联账号管理表获取店铺名称

- [ ] 1.6 Analytics Model
  - 分析数据域
  - 统一字段名
  - 关联账号管理表获取店铺名称

## 2. 字段标准化映射 [TODO]

- [ ] 2.1 订单字段标准化
  - 销售额：销售额/销售金额/GMV → `sales_amount`
  - 订单号：订单号/订单ID/order_id → `order_id`
  - 订单状态：订单状态/状态/order_status → `order_status`
  - 订单日期：订单日期/日期/order_date → `order_date`
  - 买家数：买家数/买家/buyer_count → `buyer_count`
  - 订单数：订单数/订单数量/order_count → `order_count`

- [ ] 2.2 产品字段标准化
  - 产品ID：产品ID/商品ID/product_id → `product_id`
  - SKU：SKU/平台SKU/platform_sku → `platform_sku`
  - 产品名称：产品名称/商品名称/product_name → `product_name`
  - 产品标题：产品标题/商品标题/product_title → `product_title`

- [ ] 2.3 流量字段标准化
  - 访客数：访客数/访客/visitor_count → `visitor_count`
  - 浏览量：浏览量/浏览/pv → `page_view`
  - 转化率：转化率/转化/conversion_rate → `conversion_rate`
  - 点击率：点击率/点击/click_rate → `click_rate`

- [ ] 2.4 服务字段标准化
  - 服务ID：服务ID/service_id → `service_id`
  - 服务类型：服务类型/service_type → `service_type`
  - 响应时间：响应时间/response_time → `response_time`

- [ ] 2.5 库存字段标准化
  - 库存数量：库存数量/库存/stock_quantity → `stock_quantity`
  - 仓库ID：仓库ID/仓库/warehouse_id → `warehouse_id`
  - 库存金额：库存金额/库存价值/stock_value → `stock_value`

## 3. 创建 Metabase Questions [TODO]

- [ ] 3.1 业务概览KPI Question
  - 指标：GMV、订单数、买家数、转化率
  - 支持：平台筛选、店铺筛选、日期范围筛选
  - 返回格式：单行数据，包含所有KPI指标
  - 参数：`{{platform}}`, `{{shop_id}}`, `{{start_date}}`, `{{end_date}}`

- [ ] 3.2 业务概览数据对比 Question
  - 支持：日/周/月度切换
  - 指标：同比、环比对比
  - 支持：平台筛选、店铺筛选
  - 返回格式：多行数据，每行一个时间粒度
  - 参数：`{{platform}}`, `{{shop_id}}`, `{{granularity}}`, `{{start_date}}`, `{{end_date}}`

- [ ] 3.3 店铺赛马 Question
  - 支持：店铺级/账号级切换
  - 指标：销售额排名、订单数排名
  - 支持：平台筛选、日期范围筛选
  - 返回格式：多行数据，每行一个店铺/账号，包含排名
  - 参数：`{{platform}}`, `{{start_date}}`, `{{end_date}}`, `{{level}}` (shop/account)

- [ ] 3.4 流量排名 Question
  - 指标：访客数排名、浏览量排名
  - 支持：平台筛选、店铺筛选、日期范围筛选
  - 返回格式：多行数据，每行一个店铺，包含排名
  - 参数：`{{platform}}`, `{{shop_id}}`, `{{start_date}}`, `{{end_date}}`

- [ ] 3.5 库存积压 Question
  - 指标：库存数量、库存金额、积压天数
  - 支持：平台筛选、店铺筛选、仓库筛选
  - 返回格式：多行数据，每行一个SKU，包含积压信息
  - 参数：`{{platform}}`, `{{shop_id}}`, `{{warehouse_id}}`

- [ ] 3.6 经营指标 Question
  - 指标：门店经营表格数据（多维度指标）
  - 支持：平台筛选、店铺筛选、日期范围筛选
  - 返回格式：多行数据，每行一个店铺，包含多个经营指标
  - 参数：`{{platform}}`, `{{shop_id}}`, `{{start_date}}`, `{{end_date}}`

- [ ] 3.7 清仓排名 Question
  - 指标：清仓商品排名
  - 支持：平台筛选、店铺筛选
  - 返回格式：多行数据，每行一个商品，包含排名
  - 参数：`{{platform}}`, `{{shop_id}}`

## 4. 配置 Question ID [TODO]

- [ ] 4.1 更新 env.example
  - 添加所有Question ID的环境变量
  - 添加注释说明每个Question的用途
  - 添加Model ID的环境变量（如果需要）

- [ ] 4.2 创建配置验证脚本
  - 验证所有Question ID已配置
  - 验证Question ID对应的Question存在且可访问
  - 验证Question参数与后端API约定一致

- [ ] 4.3 创建配置文档
  - 记录每个Question的ID和用途
  - 记录每个Question的参数说明
  - 提供Question创建步骤指南

## 5. 测试和验证 [TODO]

- [ ] 5.1 测试Model数据完整性
  - 验证所有平台的数据都能正确整合
  - 验证字段标准化映射正确
  - 验证关联账号管理表正确

- [ ] 5.2 测试Question查询性能
  - 验证查询响应时间
  - 验证大数据量下的性能
  - 优化慢查询

- [ ] 5.3 测试Question参数
  - 验证所有参数正确传递
  - 验证参数默认值正确
  - 验证参数筛选正确

- [ ] 5.4 测试前端集成
  - 验证前端能正确调用Question API
  - 验证数据格式与前端期望一致
  - 验证错误处理正确

