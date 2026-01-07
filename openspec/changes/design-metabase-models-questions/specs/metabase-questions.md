# Spec: Metabase Questions 设计规范

## 概述

Metabase Questions用于为前端业务概览页面提供数据，支持动态筛选和参数化查询。

## Question设计原则

### 1. 使用Native SQL模式

- **原因**：需要UNION ALL、复杂字段标准化、动态参数、多表关联
- **优势**：灵活、性能好、支持复杂查询

### 2. 参数化查询

- **参数语法**：使用 `{{variable}}` 定义参数
- **参数类型**：Text, Number, Date, Field Filter
- **默认值**：支持参数默认值
- **可选参数**：支持可选参数（使用CASE WHEN处理）

### 3. 返回格式标准化

- **表格格式**：所有Question返回表格格式
- **中文列名**：列名使用中文（便于前端显示）
- **维度字段**：包含必要的维度字段（platform_code, shop_id, store_name等）

## Question列表

### 1. 业务概览KPI Question

**用途**：提供业务概览页面的核心KPI指标

**参数**：
- `{{platform}}` - 平台筛选（可选，默认全部）
- `{{shop_id}}` - 店铺筛选（可选，默认全部）
- `{{start_date}}` - 开始日期（必填）
- `{{end_date}}` - 结束日期（必填）

**返回字段**：
- `gmv` - GMV总额
- `order_count` - 订单总数
- `buyer_count` - 买家总数
- `conversion_rate` - 转化率
- `avg_order_value` - 平均订单价值

**SQL示例**：
```sql
SELECT 
    SUM(sales_amount) AS gmv,
    COUNT(DISTINCT order_id) AS order_count,
    COUNT(DISTINCT buyer_id) AS buyer_count,
    COUNT(DISTINCT buyer_id)::numeric / NULLIF(COUNT(DISTINCT visitor_id), 0) AS conversion_rate,
    AVG(sales_amount) AS avg_order_value
FROM "Orders Model"
WHERE period_start_date >= {{start_date}}
  AND period_end_date <= {{end_date}}
  AND ({{platform}} IS NULL OR platform_code = {{platform}})
  AND ({{shop_id}} IS NULL OR shop_id = {{shop_id}})
```

### 2. 业务概览数据对比 Question

**用途**：提供日/周/月度数据对比

**参数**：
- `{{platform}}` - 平台筛选（可选）
- `{{shop_id}}` - 店铺筛选（可选）
- `{{granularity}}` - 粒度筛选（daily/weekly/monthly，可选，默认全部）
- `{{start_date}}` - 开始日期（必填）
- `{{end_date}}` - 结束日期（必填）

**返回字段**：
- `period` - 期间（日期或日期范围）
- `granularity` - 粒度（daily/weekly/monthly）
- `gmv` - GMV
- `order_count` - 订单数
- `buyer_count` - 买家数
- `gmv_yoy` - 同比GMV
- `gmv_mom` - 环比GMV

### 3. 店铺赛马 Question

**用途**：提供店铺排名数据

**参数**：
- `{{platform}}` - 平台筛选（可选）
- `{{level}}` - 级别筛选（shop/account，可选，默认shop）
- `{{start_date}}` - 开始日期（必填）
- `{{end_date}}` - 结束日期（必填）

**返回字段**：
- `shop_id` - 店铺ID
- `store_name` - 店铺名称
- `platform_code` - 平台代码
- `gmv` - GMV
- `order_count` - 订单数
- `rank` - 排名

### 4. 流量排名 Question

**用途**：提供流量指标排名

**参数**：
- `{{platform}}` - 平台筛选（可选）
- `{{shop_id}}` - 店铺筛选（可选）
- `{{start_date}}` - 开始日期（必填）
- `{{end_date}}` - 结束日期（必填）

**返回字段**：
- `shop_id` - 店铺ID
- `store_name` - 店铺名称
- `visitor_count` - 访客数
- `page_view` - 浏览量
- `conversion_rate` - 转化率
- `rank` - 排名

### 5. 库存积压 Question

**用途**：提供库存预警数据

**参数**：
- `{{platform}}` - 平台筛选（可选）
- `{{shop_id}}` - 店铺筛选（可选）
- `{{warehouse_id}}` - 仓库筛选（可选）

**返回字段**：
- `shop_id` - 店铺ID
- `store_name` - 店铺名称
- `platform_sku` - 平台SKU
- `stock_quantity` - 库存数量
- `stock_value` - 库存金额
- `days_in_stock` - 积压天数

### 6. 经营指标 Question

**用途**：提供门店经营表格数据

**参数**：
- `{{platform}}` - 平台筛选（可选）
- `{{shop_id}}` - 店铺筛选（可选）
- `{{start_date}}` - 开始日期（必填）
- `{{end_date}}` - 结束日期（必填）

**返回字段**：
- `shop_id` - 店铺ID
- `store_name` - 店铺名称
- `platform_code` - 平台代码
- `gmv` - GMV
- `order_count` - 订单数
- `buyer_count` - 买家数
- `conversion_rate` - 转化率
- `avg_order_value` - 平均订单价值
- `profit_margin` - 利润率

### 7. 清仓排名 Question

**用途**：提供清仓商品排名

**参数**：
- `{{platform}}` - 平台筛选（可选）
- `{{shop_id}}` - 店铺筛选（可选）

**返回字段**：
- `shop_id` - 店铺ID
- `store_name` - 店铺名称
- `platform_sku` - 平台SKU
- `product_name` - 产品名称
- `clearance_amount` - 清仓金额
- `rank` - 排名

## Question参数约定

### 参数命名规范

- 使用小写字母和下划线：`platform`, `shop_id`, `start_date`
- 与后端API参数命名一致
- 支持可选参数（使用NULL判断）

### 参数类型

- **Text**：`{{platform}}`, `{{shop_id}}`
- **Date**：`{{start_date}}`, `{{end_date}}`
- **Field Filter**：`{{granularity}}`（可选值：daily, weekly, monthly）

### 参数默认值

- 平台筛选：默认NULL（全部平台）
- 店铺筛选：默认NULL（全部店铺）
- 粒度筛选：默认NULL（全部粒度）

## 性能优化建议

1. **使用日期范围索引**：利用period_start_date和period_end_date索引
2. **避免全表扫描**：使用WHERE子句过滤
3. **限制返回行数**：使用LIMIT限制返回行数（如排名前100）
4. **聚合优化**：使用适当的聚合函数（SUM, COUNT, AVG等）

