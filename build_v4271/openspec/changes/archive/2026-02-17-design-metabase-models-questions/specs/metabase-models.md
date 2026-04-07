# Spec: Metabase Models 设计规范

## 概述

Metabase Models用于整合不同平台、不同粒度的数据，统一字段名，为Question提供标准化的数据源。

## Model设计原则

### 1. 数据整合

- **跨粒度整合**：使用UNION ALL合并日度、周度、月度数据
- **跨平台整合**：使用UNION ALL合并不同平台的数据（shopee, tiktok, miaoshou等）
- **统一字段名**：使用COALESCE统一不同平台的字段名

### 2. 字段标准化

- **标准字段映射**：在Model SQL中定义标准字段名
- **多平台兼容**：支持不同平台的字段名变体
- **数据类型统一**：确保相同字段的数据类型一致

### 3. 关联账号管理表

- **shop_id关联**：通过shop_id关联core.platform_accounts表
- **获取店铺名称**：获取store_name和account_alias
- **支持手动对齐**：支持用户手动对齐的shop_id

## Model列表

### Orders Model

**数据源**：
- `b_class.fact_shopee_orders_daily`
- `b_class.fact_shopee_orders_weekly`
- `b_class.fact_shopee_orders_monthly`
- `b_class.fact_tiktok_orders_daily`
- `b_class.fact_tiktok_orders_weekly`
- `b_class.fact_tiktok_orders_monthly`
- （其他平台的订单表）

**标准字段**：
- `order_id` - 订单号
- `order_status` - 订单状态
- `sales_amount` - 销售额
- `order_date` - 订单日期
- `buyer_count` - 买家数
- `order_count` - 订单数

**字段映射**：
- `order_id`: `COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'order_id')`
- `sales_amount`: `COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV')`
- `order_status`: `COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status')`

### Products Model

**数据源**：
- `b_class.fact_shopee_products_daily`
- `b_class.fact_shopee_products_weekly`
- `b_class.fact_shopee_products_monthly`
- （其他平台的产品表）

**标准字段**：
- `product_id` - 产品ID
- `platform_sku` - 平台SKU
- `product_name` - 产品名称
- `product_title` - 产品标题

### Traffic Model

**数据源**：
- `b_class.fact_shopee_traffic_daily`
- `b_class.fact_shopee_traffic_weekly`
- `b_class.fact_shopee_traffic_monthly`
- （其他平台的流量表）

**标准字段**：
- `visitor_count` - 访客数
- `page_view` - 浏览量
- `conversion_rate` - 转化率
- `click_rate` - 点击率

### Services Model

**数据源**：
- `b_class.fact_shopee_services_agent_daily`
- `b_class.fact_shopee_services_agent_weekly`
- `b_class.fact_shopee_services_agent_monthly`
- `b_class.fact_shopee_services_ai_assistant_daily`
- （其他平台的服务表）

**标准字段**：
- `service_id` - 服务ID
- `service_type` - 服务类型（agent/ai_assistant）
- `response_time` - 响应时间

### Inventory Model

**数据源**：
- `b_class.fact_shopee_inventory_snapshot`
- `b_class.fact_tiktok_inventory_snapshot`
- （其他平台的库存表）

**标准字段**：
- `stock_quantity` - 库存数量
- `warehouse_id` - 仓库ID
- `stock_value` - 库存金额

### Analytics Model

**数据源**：
- `b_class.fact_shopee_analytics_daily`
- `b_class.fact_shopee_analytics_weekly`
- `b_class.fact_shopee_analytics_monthly`
- （其他平台的分析表）

**标准字段**：
- （根据实际数据域定义）

## Model SQL模板

```sql
-- Orders Model示例
SELECT 
    platform_code,
    shop_id,
    data_domain,
    granularity,
    period_start_date,
    period_end_date,
    period_start_time,
    period_end_time,
    -- 标准字段
    COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'order_id') AS order_id,
    COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV')::numeric AS sales_amount,
    COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status') AS order_status,
    -- 关联账号管理表
    pa.store_name,
    pa.account_alias,
    -- 其他字段
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp
FROM b_class.fact_shopee_orders_daily
LEFT JOIN core.platform_accounts pa 
    ON fact_shopee_orders_daily.shop_id = pa.shop_id 
    AND fact_shopee_orders_daily.platform_code = pa.platform
UNION ALL
SELECT 
    -- 相同字段结构
    ...
FROM b_class.fact_shopee_orders_weekly
LEFT JOIN core.platform_accounts pa 
    ON fact_shopee_orders_weekly.shop_id = pa.shop_id 
    AND fact_shopee_orders_weekly.platform_code = pa.platform
UNION ALL
-- 继续添加其他粒度和平台...
```

## 注意事项

1. **性能优化**：使用period_start_date和period_end_date进行日期范围查询
2. **NULL值处理**：使用COALESCE处理NULL值
3. **数据类型转换**：确保数据类型一致（如numeric, date, timestamp）
4. **索引利用**：利用表级别的索引（period_start_date, period_end_date, shop_id等）

