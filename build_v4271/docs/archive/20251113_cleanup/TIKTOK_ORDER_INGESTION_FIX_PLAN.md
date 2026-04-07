# TikTok订单数据入库问题诊断和修复方案

## 问题总结

根据诊断结果和用户反馈，核心问题是：

1. **表头行设置正确**：模板中设置了`header_row=1`（Excel第2行），这是正确的
2. **字段映射完整**：用户设置了完整的手动字段映射
3. **文件读取成功**：使用正确的表头行可以成功读取文件，订单明细字段都存在
4. **入库失败**：从图片中看到PostgreSQL事务失败错误，导致数据没有入库
5. **物化视图数据为0**：因为数据没有入库，所以物化视图中`units_sold`、`sales_amount_cny`等都是0

## 根本原因

从错误信息中看到：
- `order_id`字段值是科学计数法：`5.80515433809348e+17`
- 这可能导致PostgreSQL类型转换错误或事务失败
- 订单入库失败后，订单明细也不会入库

## 修复方案

### 1. 修复order_id类型转换问题

在`upsert_orders_v2`函数中，确保`order_id`始终是字符串类型：

```python
# ⭐ v4.10.0修复：确保order_id是字符串类型（避免科学计数法问题）
if not core.get("order_id"):
    # ... 提取逻辑 ...
else:
    # 确保order_id是字符串，不是科学计数法
    order_id_value = core.get("order_id")
    if isinstance(order_id_value, float):
        # 如果是浮点数（科学计数法），转换为整数再转字符串
        core["order_id"] = str(int(order_id_value))
    elif isinstance(order_id_value, (int, float)):
        # 如果是数字，直接转字符串
        core["order_id"] = str(order_id_value)
    else:
        # 已经是字符串，确保不是科学计数法格式
        core["order_id"] = str(order_id_value).strip()
```

### 2. 增强错误处理和事务管理

确保订单明细入库失败不会影响订单入库：

```python
# 订单明细入库（独立事务，失败不影响订单入库）
try:
    # ... 订单明细入库逻辑 ...
except Exception as item_error:
    logger.warning(f"[UpsertOrders] 入库订单明细失败: order_id={core.get('order_id')}, error={item_error}", exc_info=True)
    # ⭐ v4.10.0修复：订单明细入库失败不影响订单级别数据入库
    # 不抛出异常，继续执行
```

### 3. 增强字段提取逻辑

确保从`attributes`中正确提取订单明细字段，支持中文字段名：

```python
# 中文键名映射（已实现）
cn_key_map = {
    "platform_sku": ["平台SKU", "SKU ID", "商品SKU", "产品SKU", "规格货号"],
    "quantity": ["数量", "商品数量", "销售数量", "出库数量", "quantity", "qty"],
    "line_amount": ["金额", "商品金额", "行金额", "采购金额", "line_amount", "total_amount"],
    # ...
}
```

## 验证步骤

1. **修复order_id类型转换问题**
2. **重新入库TikTok订单数据**
3. **验证订单和订单明细是否正确入库**
4. **刷新物化视图，检查销售金额是否非零**

## 预期结果

修复后：
- ✅ 订单数据正确入库到`fact_orders`表
- ✅ 订单明细数据正确入库到`fact_order_items`表
- ✅ 物化视图`mv_sales_day_shop_sku`的`units_sold`、`sales_amount_cny`等字段有非零值

