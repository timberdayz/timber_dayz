# 订单数据域物化视图问题诊断报告

**诊断时间**: 2025-11-09  
**问题**: Shopee和TikTok订单数据域的物化视图缺失

---

## 🔍 问题诊断结果

### 1. 物化视图创建状态

**数据库中实际存在的物化视图**（14个）:
- ✅ `mv_daily_sales` - 日度销售汇总（查询`fact_sales_orders`表）
- ✅ `mv_weekly_sales` - 周度销售汇总
- ✅ `mv_monthly_sales` - 月度销售汇总
- ✅ `mv_profit_analysis` - 利润分析
- ✅ `mv_product_management` - 产品管理
- ✅ `mv_product_sales_trend` - 产品销售趋势（只查询`fact_product_metrics`）
- ✅ `mv_top_products` - TopN产品
- ✅ `mv_shop_product_summary` - 店铺产品汇总
- ✅ `mv_inventory_summary` - 库存汇总
- ✅ `mv_inventory_by_sku` - SKU级库存明细
- ✅ `mv_financial_overview` - 财务总览
- ✅ `mv_pnl_shop_month` - 店铺月度P&L
- ✅ `mv_vendor_performance` - 供应商表现
- ✅ `mv_shop_traffic_day` - 店铺流量

**缺失的物化视图**:
- ❌ `mv_sales_day_shop_sku` - 日粒度销售聚合（从订单明细聚合）**已创建但数据为0**

### 2. 订单数据入库状态

**fact_orders表**:
- ✅ tiktok订单数: **622条**（已成功入库）
- ✅ shopee订单数: **0条**（暂无数据）

**fact_order_items表**:
- ❌ **0条记录**（订单明细数据未入库）

### 3. 根本原因

**问题**: 订单数据入库逻辑只入库到`fact_orders`表，**没有入库到`fact_order_items`表**！

**代码位置**: `backend/services/data_importer.py::upsert_orders_v2()`
- ✅ 只入库订单级别数据到`fact_orders`表
- ❌ **没有入库订单明细数据到`fact_order_items`表**

**影响**:
- `mv_sales_day_shop_sku`视图需要`fact_order_items`表的数据
- 由于`fact_order_items`表为空，视图查询结果为0

---

## ✅ 解决方案

### 方案1：创建基于fact_orders的物化视图（推荐）

由于订单明细数据（`fact_order_items`）未入库，我们可以创建基于`fact_orders`表的物化视图：

```sql
CREATE MATERIALIZED VIEW mv_order_sales_summary AS
SELECT 
    platform_code,
    shop_id,
    order_date_local AS sale_date,
    
    -- 订单统计
    COUNT(DISTINCT order_id) AS order_count,
    SUM(total_amount_rmb) AS total_gmv_rmb,
    SUM(total_amount) AS total_gmv,
    
    -- 平均指标
    AVG(total_amount_rmb) AS avg_order_value_rmb,
    
    -- 元数据
    MAX(currency) AS currency,
    
    -- 时间戳
    CURRENT_TIMESTAMP AS refreshed_at
FROM fact_orders
WHERE is_cancelled = false
  AND order_date_local IS NOT NULL
GROUP BY 
    platform_code,
    shop_id,
    order_date_local;
```

### 方案2：完善订单明细入库逻辑（长期方案）

需要修改`upsert_orders_v2`函数，同时入库订单明细数据到`fact_order_items`表。

---

## 📋 当前状态总结

1. **订单数据已入库**: ✅ `fact_orders`表有622条tiktok订单
2. **订单明细未入库**: ❌ `fact_order_items`表为空
3. **物化视图已创建**: ✅ `mv_sales_day_shop_sku`视图已创建
4. **视图数据为空**: ❌ 由于`fact_order_items`表为空，视图查询结果为0

---

## 🎯 建议

**立即方案**: 创建基于`fact_orders`表的订单物化视图（`mv_order_sales_summary`）

**长期方案**: 完善订单明细入库逻辑，确保订单明细数据入库到`fact_order_items`表

