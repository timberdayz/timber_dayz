# 数据同步和物化视图问题诊断报告

**诊断时间**: 2025-11-09  
**平台**: TikTok

---

## 问题1：跳过的文件检查

### 诊断结果
- **skipped状态文件数**: 0
- **ingested状态文件数**: 46
- **pending状态文件数**: 77

### 结论
✅ **正常跳过**：没有文件被标记为`skipped`状态，说明所有文件要么已成功入库，要么仍在待处理队列中。

**说明**：
- 如果文件没有数据或无法解析，系统会：
  1. 尝试处理文件
  2. 如果处理失败，文件状态会变为`failed`或`quarantined`
  3. 如果文件为空或无法解析，可能会被跳过，但当前没有`skipped`状态的文件

---

## 问题2：待入库文件统计

### 诊断结果
- **pending状态文件数**: 77
- **这些文件主要是**: products域和services域的文件

### 原因分析
这些77个pending文件可能是：
1. **缺少模板**：没有对应的字段映射模板
2. **模板匹配失败**：有模板但匹配失败
3. **未在本次批量同步中处理**：可能因为筛选条件（如"仅处理有模板的文件"）而被跳过

### 建议
1. 检查这些pending文件是否有对应的模板
2. 如果没有模板，需要创建模板
3. 如果有模板但匹配失败，需要检查模板配置

---

## 问题3：订单数据在物化视图中看不到

### 诊断结果
- ✅ **fact_orders表中tiktok订单数**: 621（订单数据已成功入库）
- ✅ **mv_product_sales_trend中tiktok数据数**: 108（这是products域数据）
- ❌ **fact_product_metrics表中tiktok products域数据数**: 0

### 根本原因

**`mv_product_sales_trend`视图只查询`fact_product_metrics`表（products域），不查询`fact_orders`表！**

```sql
CREATE MATERIALIZED VIEW mv_product_sales_trend AS
SELECT 
    -- ...
FROM fact_product_metrics  -- ⚠️ 只查询products域数据
WHERE metric_date >= CURRENT_DATE - INTERVAL '90 days'
  AND granularity = 'daily'
  AND COALESCE(data_domain, 'products') = 'products'
```

**订单数据存储位置**：
- 订单数据存储在`fact_orders`表中（621条tiktok订单）
- `mv_product_sales_trend`视图只查询`fact_product_metrics`表（products域）
- 所以订单数据不会出现在`mv_product_sales_trend`视图中

### 解决方案

**方案1：创建订单相关的物化视图**
```sql
CREATE MATERIALIZED VIEW mv_order_sales_trend AS
SELECT 
    platform_code,
    shop_id,
    DATE(order_time_utc) as order_date,
    COUNT(*) as order_count,
    SUM(total_amount_rmb) as total_gmv_rmb,
    -- ...
FROM fact_orders
WHERE order_time_utc >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY platform_code, shop_id, DATE(order_time_utc);
```

**方案2：在数据浏览器中直接查询fact_orders表**
- 使用"数据浏览器"功能，直接查询`fact_orders`表
- 可以查看所有订单数据，包括tiktok平台的订单

### 当前状态
- ✅ 订单数据已成功入库到`fact_orders`表（621条）
- ✅ 可以在数据浏览器中查看订单数据
- ❌ `mv_product_sales_trend`视图不包含订单数据（这是设计如此）

---

## 总结

1. **跳过的文件**：✅ 正常，没有文件被跳过
2. **待入库文件**：⚠️ 有77个pending文件，需要检查是否有模板
3. **订单数据**：✅ 已成功入库，但不在`mv_product_sales_trend`视图中（这是设计如此）

### 建议
1. 检查77个pending文件，确认是否有对应的模板
2. 如果需要查看订单数据，使用数据浏览器查询`fact_orders`表
3. 如果需要订单趋势分析，创建订单相关的物化视图

