# Shopee和TikTok订单数据域的物化视图

**版本**: v4.10.0  
**更新时间**: 2025-11-09

---

## 📊 订单数据域的物化视图

### 核心物化视图

#### 1. `mv_order_sales_summary`（订单销售汇总视图）⭐

**数据源**: `fact_orders`表  
**用途**: 订单级别的销售汇总，用于订单趋势分析  
**文件位置**: `sql/create_finance_materialized_views.sql`（需要创建）

**查询逻辑**:
```sql
FROM fact_orders
WHERE COALESCE(is_cancelled, false) = false
  AND (order_date_local IS NOT NULL OR order_time_utc IS NOT NULL)
GROUP BY platform_code, shop_id, COALESCE(order_date_local, DATE(order_time_utc))
```

**包含字段**:
- `platform_code` - 平台代码（tiktok/shopee）
- `shop_id` - 店铺ID
- `sale_date` - 销售日期（优先使用order_date_local，否则使用order_time_utc的日期部分）
- `order_count` - 订单数
- `total_gmv_rmb` - 总GMV（人民币）
- `total_gmv` - 总GMV（原币）
- `avg_order_value_rmb` - 平均订单价值（人民币）

**状态**: ✅ 已创建，包含tiktok订单数据

---

#### 2. `mv_sales_day_shop_sku`（日粒度销售聚合视图）⚠️

**数据源**: `fact_orders`表（订单明细未入库时）  
**用途**: 日粒度销售聚合，用于TopN分析与P&L  
**文件位置**: `sql/create_finance_materialized_views.sql`

**当前状态**:
- ⚠️ **订单明细数据未入库**: `fact_order_items`表为空（0条记录）
- ✅ **已创建基于fact_orders表的视图**: 使用订单级别数据
- ⚠️ **platform_sku字段为占位符**: 由于没有订单明细，使用'N/A'

**查询逻辑**:
```sql
FROM fact_orders
WHERE COALESCE(is_cancelled, false) = false
  AND (order_date_local IS NOT NULL OR order_time_utc IS NOT NULL)
GROUP BY platform_code, shop_id, COALESCE(order_date_local, DATE(order_time_utc))
```

**状态**: ✅ 已创建，但只包含订单级别数据（不包含SKU级别数据）

---

## ⚠️ 重要说明

### 1. 订单明细数据未入库

**问题**: `fact_order_items`表为空（0条记录）

**原因**: 订单数据入库逻辑（`upsert_orders_v2`）只入库订单级别数据到`fact_orders`表，**没有入库订单明细数据到`fact_order_items`表**。

**影响**:
- `mv_sales_day_shop_sku`视图无法提供SKU级别的销售数据
- 只能提供订单级别的汇总数据

### 2. order_date_local字段为NULL

**问题**: `fact_orders`表中所有订单的`order_date_local`字段都是`NULL`

**解决方案**: 物化视图使用`COALESCE(order_date_local, DATE(order_time_utc))`来提取销售日期

### 3. 其他销售视图

**`mv_daily_sales`、`mv_weekly_sales`、`mv_monthly_sales`**:
- ⚠️ 这些视图查询的是`fact_sales_orders`表
- ⚠️ 如果`fact_sales_orders`表不存在或为空，这些视图将不包含订单数据
- ⚠️ 需要确认`fact_sales_orders`表是否存在以及是否包含订单数据

---

## 📋 总结

**Shopee和TikTok订单数据域的文件入库后，对应的物化视图是**:

1. ✅ **`mv_order_sales_summary`** - 订单销售汇总视图（基于`fact_orders`表）
   - 包含订单级别的销售数据
   - 支持订单趋势分析

2. ✅ **`mv_sales_day_shop_sku`** - 日粒度销售聚合视图（基于`fact_orders`表）
   - ⚠️ 由于订单明细未入库，只包含订单级别数据
   - ⚠️ `platform_sku`字段为占位符'N/A'

**查看订单数据的方法**:
- ✅ 查询`mv_order_sales_summary`视图（推荐）
- ✅ 查询`mv_sales_day_shop_sku`视图（订单级别汇总）
- ✅ 直接查询`fact_orders`表（在数据浏览器中）

---

**注意**: 如果需要SKU级别的销售数据，需要完善订单明细入库逻辑，确保订单明细数据入库到`fact_order_items`表。
