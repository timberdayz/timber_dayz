# Metabase 模型字段标准定义

**版本**: v1.0.0  
**更新**: 2026-01-24  
**状态**: 已完成（5个B类数据模型）

---

## 一、系统字段（所有模型共有）

### 1.1 核心系统字段（必须）

| 字段名 | 类型 | 说明 | 示例值 |
|-------|------|------|-------|
| `platform_code` | VARCHAR(32) | 平台代码 | shopee/tiktok/miaoshou |
| `shop_id` | VARCHAR(64) | 店铺ID | 唯一标识店铺 |
| `data_domain` | VARCHAR(32) | 数据域 | analytics/orders/products/inventory/services |
| `granularity` | VARCHAR(16) | 粒度 | daily/weekly/monthly/snapshot |

### 1.2 日期时间字段

| 字段名 | 类型 | 说明 | 用途 |
|-------|------|------|------|
| `metric_date` | DATE | 指标日期 | 数据所属日期（单一日期） |
| `period_start_date` | DATE | 周期开始日期 | 周度/月度数据的开始日期 |
| `period_end_date` | DATE | 周期结束日期 | 周度/月度数据的结束日期 |
| `period_start_time` | TIMESTAMP | 周期开始时间 | 精确到时分秒 |
| `period_end_time` | TIMESTAMP | 周期结束时间 | 精确到时分秒 |

### 1.3 元数据字段

| 字段名 | 类型 | 说明 | 用途 |
|-------|------|------|------|
| `raw_data` | JSONB | 原始数据 | 保留原始JSON，用于扩展字段 |
| `header_columns` | JSONB | 原始表头 | 记录Excel原始列名 |
| `data_hash` | VARCHAR(64) | 数据哈希 | 去重唯一标识 |
| `ingest_timestamp` | TIMESTAMP | 入库时间 | 数据同步时间 |
| `currency_code` | VARCHAR(8) | 币种代码 | SGD/MYR/THB/CNY等 |

---

## 二、标准业务字段（按数据域分类）

### 2.1 Analytics（分析数据域）

**数据源**: `b_class.fact_{platform}_analytics_{granularity}`  
**模型文件**: `analytics_model.sql`

| 标准字段名 | 类型 | 中文候选名 | 英文候选名 | 说明 |
|-----------|------|-----------|-----------|------|
| `visitor_count` | NUMERIC | 访客数/独立访客/去重页面浏览次数 | unique_visitors/uv/visitor_count | 访客数量 |
| `page_views` | NUMERIC | 浏览量/页面浏览次数 | page_views/views/page_view | 页面浏览次数 |
| `impressions` | NUMERIC | 曝光次数 | impressions | 曝光次数 |
| `clicks` | NUMERIC | 点击次数 | clicks | 点击次数 |
| `click_rate` | NUMERIC | 点击率 | click_rate/CTR | 点击率（已/100） |
| `conversion_rate` | NUMERIC | 转化率 | conversion_rate/CVR | 转化率（已/100） |
| `order_count` | NUMERIC | 订单数/订单数量 | order_count | 订单数量 |
| `gmv` | NUMERIC | 成交金额/GMV/成交额 | gmv/sales_amount | 成交金额 |
| `bounce_rate` | NUMERIC | 跳出率 | bounce_rate | 跳出率（已/100） |
| `bounce_visitors` | NUMERIC | 跳出访客数 | bounce_visitors | 跳出访客数 |
| `avg_session_duration` | NUMERIC | 平均停留时长/平均会话时长 | avg_session_duration | 平均停留时长（秒） |
| `pages_per_session` | NUMERIC | 平均页面数/平均每会话页面数 | pages_per_session | 每次会话页面数 |

---

### 2.2 Orders（订单数据域）

**数据源**: `b_class.fact_{platform}_orders_{granularity}`  
**模型文件**: `orders_model.sql`

| 标准字段名 | 类型 | 中文候选名 | 英文候选名 | 说明 |
|-----------|------|-----------|-----------|------|
| `order_id` | VARCHAR | 订单号/订单ID/订单编号 | order_id/order_no | 订单唯一标识 |
| `order_status` | VARCHAR | 订单状态/状态 | order_status/Status | 订单状态 |
| `sales_amount` | NUMERIC | 销售额/销售金额/GMV/订单金额/成交金额 | sales_amount | 销售金额 |
| `paid_amount` | NUMERIC | 实付金额/买家实付金额 | paid_amount | 买家实付金额 |
| `product_original_price` | NUMERIC | 产品原价/原价 | product_original_price | 产品原价 |
| `estimated_settlement_amount` | NUMERIC | 预估回款金额 | estimated_settlement | 预估回款金额 |
| `profit` | NUMERIC | 利润/毛利/净利润 | profit | 利润 |
| `order_time` | TIMESTAMP | 下单时间/订单时间 | order_time | 下单时间 |
| `payment_time` | TIMESTAMP | 付款时间/支付时间 | payment_time | 付款时间 |
| `order_date` | DATE | 订单日期/日期 | order_date | 订单日期 |
| `product_name` | VARCHAR | 商品名称/产品名称/商品标题 | product_name | 商品名称 |
| `product_id` | VARCHAR | 产品ID/商品ID | product_id | 产品ID |
| `platform_sku` | VARCHAR | 平台SKU/SKU | platform_sku | 平台SKU |
| `sku_id` | VARCHAR | SKU ID | sku_id | SKU ID |
| `product_sku` | VARCHAR | 商品SKU/商品货号 | product_sku | 商品SKU |
| `product_type` | VARCHAR | 商品类型/类型 | product_type | 商品类型 |
| `outbound_warehouse` | VARCHAR | 出库仓库/仓库 | outbound_warehouse | 出库仓库 |
| `buyer_count` | NUMERIC | 买家数/买家 | buyer_count | 买家数量 |
| `order_count` | NUMERIC | 订单数/订单数量 | order_count | 订单数量 |

---

### 2.3 Products（产品数据域）

**数据源**: `b_class.fact_{platform}_products_{granularity}`  
**模型文件**: `products_model.sql`

| 标准字段名 | 类型 | 中文候选名 | 英文候选名 | 说明 |
|-----------|------|-----------|-----------|------|
| `product_id` | VARCHAR | 商品ID/产品ID | product_id/item_id | 产品ID |
| `product_name` | VARCHAR | 商品名称/产品名称/商品标题 | product_name/title | 产品名称 |
| `platform_sku` | VARCHAR | 平台SKU/SKU | platform_sku/sku | 平台SKU |
| `category` | VARCHAR | 类目/分类 | category | 类目 |
| `item_status` | VARCHAR | 商品状态/状态 | item_status/status | 商品状态 |
| `variation_status` | VARCHAR | 变体状态 | variation_status | 变体状态 |
| `price` | NUMERIC | 价格/单价/售价 | price | 价格 |
| `stock` | NUMERIC | 库存/库存数量 | stock/inventory | 库存数量 |
| `currency` | VARCHAR | 币种/货币 | currency | 币种 |
| `page_views` | NUMERIC | 浏览量/页面浏览次数 | page_views/views/pv | 浏览量 |
| `unique_visitors` | NUMERIC | 访客数/独立访客/去重页面浏览次数 | unique_visitors/uv | 独立访客 |
| `impressions` | NUMERIC | 曝光次数 | impressions | 曝光次数 |
| `clicks` | NUMERIC | 点击次数 | clicks | 点击次数 |
| `click_rate` | NUMERIC | 点击率 | click_rate/CTR | 点击率（已/100） |
| `conversion_rate` | NUMERIC | 转化率 | conversion_rate/CVR | 转化率（已/100） |
| `positive_rate` | NUMERIC | 好评率 | positive_rate | 好评率（已/100） |
| `cart_add_count` | NUMERIC | 加购次数/加购数 | cart_add_count/add_to_cart | 加购次数 |
| `cart_add_visitors` | NUMERIC | 加购访客数 | cart_add_visitors | 加购访客数 |
| `order_count` | NUMERIC | 订单数/订单数量 | order_count/orders | 订单数 |
| `sold_count` | NUMERIC | 成交件数/销量 | sold_count/sales | 成交件数 |
| `gmv` | NUMERIC | 成交金额/GMV | gmv | 成交金额 |
| `sales_amount` | NUMERIC | 销售额/销售金额 | sales_amount/revenue | 销售额 |
| `sales_volume` | NUMERIC | 销量/销售数量 | sales_volume/qty | 销量 |
| `rating` | NUMERIC | 评分 | rating | 评分 |
| `review_count` | NUMERIC | 评价数/评论数 | review_count/reviews | 评价数 |

---

### 2.4 Inventory（库存数据域）

**数据源**: `b_class.fact_{platform}_inventory_snapshot`  
**模型文件**: `inventory_model.sql`  
**特殊说明**: 仅有 `snapshot` 粒度（无 daily/weekly/monthly）

| 标准字段名 | 类型 | 中文候选名 | 英文候选名 | 说明 |
|-----------|------|-----------|-----------|------|
| `product_id` | VARCHAR | 商品ID/产品ID | product_id/item_id | 产品ID |
| `product_name` | VARCHAR | 商品名称/产品名称/商品标题 | product_name/title | 产品名称 |
| `platform_sku` | VARCHAR | 平台SKU/SKU | platform_sku/sku | 平台SKU |
| `sku_id` | VARCHAR | SKU ID | sku_id | SKU ID |
| `product_sku` | VARCHAR | 商品SKU/商品货号 | product_sku | 商品SKU |
| `warehouse_name` | VARCHAR | 仓库/仓库名称 | warehouse/warehouse_name | 仓库名称 |
| `warehouse_code` | VARCHAR | 仓库编码 | warehouse_code | 仓库编码 |
| `available_stock` | NUMERIC | 可用库存 | available_stock/available | 可用库存 |
| `on_hand_stock` | NUMERIC | 在库库存 | on_hand_stock/on_hand | 在库库存 |
| `reserved_stock` | NUMERIC | 锁定库存 | reserved_stock/reserved | 锁定库存 |
| `in_transit_stock` | NUMERIC | 在途库存 | in_transit_stock/in_transit | 在途库存 |
| `stockout_qty` | NUMERIC | 缺货数量 | stockout_qty/stockout | 缺货数量 |
| `reorder_point` | NUMERIC | 补货点 | reorder_point | 补货点 |
| `safety_stock` | NUMERIC | 安全库存 | safety_stock | 安全库存 |
| `currency` | VARCHAR | 币种/货币 | currency | 币种 |
| `unit_cost` | NUMERIC | 成本/成本价 | cost/unit_cost | 单位成本 |
| `inventory_value` | NUMERIC | 库存金额/库存价值 | inventory_value | 库存价值 |

---

### 2.5 Services（服务数据域）

**数据源**: `b_class.fact_{platform}_services_{sub_type}_{granularity}`  
**模型文件**: `services_model.sql`  
**子类型**: `agent`, `ai_assistant`

| 标准字段名 | 类型 | 中文候选名 | 英文候选名 | 说明 |
|-----------|------|-----------|-----------|------|
| `sub_domain` | VARCHAR | - | - | 子类型（agent/ai_assistant） |
| `service_date` | DATE | - | - | 服务日期（锚点日期，使用period_end_date） |
| `service_start_date` | DATE | - | - | 服务开始日期 |
| `service_end_date` | DATE | - | - | 服务结束日期 |
| `visitor_count` | NUMERIC | 访客数/访客 | visitors | 访客数 |
| `chat_count` | NUMERIC | 聊天询问/询问/聊天数 | chats | 聊天数 |
| `order_count` | NUMERIC | 订单/订单数/买家数 | orders | 订单数 |
| `gmv` | NUMERIC | 销售额/成交金额 | gmv/sales | 成交金额 |
| `satisfaction` | NUMERIC | 满意度/用户满意度 | satisfaction | 满意度（已/100） |

---

## 三、字段类型分类

### 3.1 百分比字段（已除以100，存储为小数）

| 字段名 | 数据域 | 说明 |
|-------|-------|------|
| `click_rate` | Analytics/Products | 点击率 |
| `conversion_rate` | Analytics/Products | 转化率 |
| `bounce_rate` | Analytics | 跳出率 |
| `positive_rate` | Products | 好评率 |
| `satisfaction` | Services | 满意度 |

**注意**: 这些字段在模型SQL中已经除以100.0，查询时直接使用即可。

### 3.2 金额字段（NUMERIC类型）

| 字段名 | 数据域 | 说明 |
|-------|-------|------|
| `sales_amount` | Orders/Products | 销售额 |
| `paid_amount` | Orders | 实付金额 |
| `profit` | Orders | 利润 |
| `gmv` | Analytics/Products/Services | 成交金额 |
| `unit_cost` | Inventory | 单位成本 |
| `inventory_value` | Inventory | 库存价值 |
| `price` | Products | 价格 |
| `product_original_price` | Orders | 产品原价 |
| `estimated_settlement_amount` | Orders | 预估回款金额 |

### 3.3 数量字段（NUMERIC类型）

| 字段名 | 数据域 | 说明 |
|-------|-------|------|
| `visitor_count` | Analytics/Services | 访客数 |
| `unique_visitors` | Products | 独立访客 |
| `page_views` | Analytics/Products | 浏览量 |
| `impressions` | Analytics/Products | 曝光次数 |
| `clicks` | Analytics/Products | 点击次数 |
| `order_count` | Analytics/Orders/Products/Services | 订单数 |
| `buyer_count` | Orders | 买家数 |
| `stock` | Products | 库存 |
| `sold_count` | Products | 销量 |
| `sales_volume` | Products | 销售数量 |
| `chat_count` | Services | 聊天数 |
| `available_stock` | Inventory | 可用库存 |
| `on_hand_stock` | Inventory | 在库库存 |
| `reserved_stock` | Inventory | 锁定库存 |
| `in_transit_stock` | Inventory | 在途库存 |

### 3.4 标识字段（VARCHAR类型）

| 字段名 | 数据域 | 说明 |
|-------|-------|------|
| `order_id` | Orders | 订单号 |
| `product_id` | Orders/Products/Inventory | 产品ID |
| `platform_sku` | Orders/Products/Inventory | 平台SKU |
| `sku_id` | Orders/Products/Inventory | SKU ID |
| `product_sku` | Orders/Products/Inventory | 商品SKU |
| `warehouse_code` | Inventory | 仓库编码 |

---

## 四、数据清洗规则

### 4.1 数值字段清洗

所有数值字段在第2层（cleaned CTE）中统一处理：

```sql
NULLIF(
  REGEXP_REPLACE(
    REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(field_raw, ',', ''), ' ', ''), '—', ''), '–', ''), '-', ''),
    '[^0-9.]',
    '',
    'g'
  ),
  ''
)::NUMERIC AS field_name
```

**处理内容**：
| 处理项 | 方法 | 说明 |
|-------|------|------|
| 千分位逗号 | `REPLACE(field, ',', '')` | 移除 `1,234` 中的逗号 |
| 空格 | `REPLACE(field, ' ', '')` | 移除空格 |
| 全角破折号 | `REPLACE(field, '—', '')` | 移除 `—` |
| 半角长破折号 | `REPLACE(field, '–', '')` | 移除 `–` |
| 半角短破折号 | `REPLACE(field, '-', '')` | 移除 `-` |
| 其他非数字 | `REGEXP_REPLACE(field, '[^0-9.]', '', 'g')` | 只保留数字和小数点 |
| 空字符串转NULL | `NULLIF(field, '')` | 空字符串转为NULL |

### 4.2 百分比字段清洗

百分比字段额外处理：

```sql
NULLIF(
  REGEXP_REPLACE(
    REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(field_raw, '%', ''), ',', '.'), ' ', ''), '—', ''), '–', ''), '-', ''),
    '[^0-9.]',
    '',
    'g'
  ),
  ''
)::NUMERIC / 100.0 AS field_name
```

**额外处理**：
| 处理项 | 方法 | 说明 |
|-------|------|------|
| 移除百分号 | `REPLACE(field, '%', '')` | 移除 `%` |
| 欧洲格式 | `REPLACE(field, ',', '.')` | `0,00` → `0.00` |
| 除以100 | `/ 100.0` | 转换为小数 |

---

## 五、去重策略

### 5.1 标准去重（daily/weekly/monthly粒度）

```sql
ROW_NUMBER() OVER (
  PARTITION BY platform_code, shop_id, data_hash 
  ORDER BY 
    CASE granularity
      WHEN 'daily' THEN 1
      WHEN 'weekly' THEN 2
      WHEN 'monthly' THEN 3
    END ASC,
    ingest_timestamp DESC
) AS rn
```

**优先级**: `daily > weekly > monthly`，同粒度取最新（`ingest_timestamp DESC`）

### 5.2 快照去重（Inventory模型）

```sql
ROW_NUMBER() OVER (
  PARTITION BY platform_code, shop_id, data_hash 
  ORDER BY ingest_timestamp DESC
) AS rn
```

**策略**: 仅按 `ingest_timestamp DESC` 取最新

---

## 六、模型文件索引

| 模型文件 | 数据域 | 平台 | 粒度 | 数据表数量 |
|---------|-------|------|------|-----------|
| `analytics_model.sql` | analytics | shopee/tiktok/miaoshou | daily/weekly/monthly | 9 |
| `orders_model.sql` | orders | shopee/tiktok/miaoshou | daily/weekly/monthly | 9 |
| `products_model.sql` | products | shopee/tiktok/miaoshou | daily/weekly/monthly | 9 |
| `inventory_model.sql` | inventory | shopee/tiktok/miaoshou | snapshot | 3 |
| `services_model.sql` | services | shopee/tiktok | daily/weekly/monthly (agent+ai_assistant) | 12 |

---

## 七、使用说明

### 7.1 在Metabase Question中引用模型

```sql
-- 引用 Orders Model
SELECT 
  platform_code,
  shop_id,
  SUM(sales_amount) AS total_sales,
  SUM(order_count) AS total_orders
FROM "Orders Model"
WHERE period_start_date >= {{start_date}}
  AND period_end_date <= {{end_date}}
  AND ({{platforms}} IS NULL OR platform_code IN ({{platforms}}))
GROUP BY platform_code, shop_id
```

### 7.2 在Metabase Question中关联A类数据

```sql
-- JOIN A类数据（目标）和B类模型（实际）计算达成率
SELECT 
  o.platform_code,
  o.shop_id,
  t.target_sales_amount AS monthly_target,
  SUM(o.sales_amount) AS monthly_achieved,
  CASE 
    WHEN t.target_sales_amount > 0 
    THEN SUM(o.sales_amount) / t.target_sales_amount * 100
    ELSE 0
  END AS achievement_rate
FROM "Orders Model" o
LEFT JOIN a_class.sales_targets_a t 
  ON o.platform_code = t.platform_code 
  AND o.shop_id = t.shop_id
  AND DATE_TRUNC('month', o.period_start_date) = DATE_TRUNC('month', t.target_date)
WHERE o.period_start_date >= {{start_date}}
GROUP BY o.platform_code, o.shop_id, t.target_sales_amount
```

---

**最后更新**: 2026-01-24  
**维护**: AI Agent Team
