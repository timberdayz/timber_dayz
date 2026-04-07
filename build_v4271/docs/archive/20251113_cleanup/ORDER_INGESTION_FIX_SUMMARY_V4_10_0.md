# TikTok订单数据入库修复总结（v4.10.0）

## 修复内容

### 1. 修复order_id类型转换问题
- **问题**：`order_id`字段值可能是科学计数法（如`5.80515433809348e+17`），导致PostgreSQL类型转换错误
- **修复**：在`upsert_orders_v2`函数中，确保`order_id`始终是字符串类型，正确处理科学计数法

### 2. 修复事务管理问题
- **问题**：所有订单在一个事务中批量提交，如果中间某个订单失败，整个事务都会被终止（`InFailedSqlTransaction`错误）
- **修复**：
  - 改为逐条提交：每个订单入库成功后立即提交
  - 添加错误处理：订单入库失败时回滚并记录错误，但不影响其他订单
  - 移除批量提交：不再在最后统一提交

### 3. 增强订单明细字段提取逻辑
- **问题**：订单明细字段（如`platform_sku`、`quantity`、`line_amount`）可能被放入`attributes` JSON中，原逻辑只从映射后的标准字段中提取
- **修复**：
  - 优先从映射后的标准字段提取
  - 如果找不到，从`attributes` JSON中提取
  - 支持中文字段名（如"平台SKU"、"商品数量"、"采购金额"等）

### 4. 增强错误处理
- **问题**：订单明细入库失败会影响订单入库
- **修复**：
  - 订单明细入库失败时回滚并记录错误，但不影响订单级别数据入库
  - 确保订单明细入库只在订单入库成功后执行

## 修复后的数据流

```
原始Excel数据
  ↓
字段映射（使用用户设置的表头行）
  ↓
映射后的数据（r）
  ├─ 标准字段（如platform_sku, quantity）→ 直接使用
  └─ 未映射字段 → 放入extras → 转换为core["attributes"] JSON
  ↓
订单入库（upsert_orders_v2）
  ├─ 订单级别数据 → fact_orders表（逐条提交）
  │   ├─ 成功 → 继续处理订单明细
  │   └─ 失败 → 回滚并记录错误，跳过此订单
  └─ 订单明细数据提取（仅在订单入库成功后）
      ├─ 从r中提取（标准字段）
      └─ 从core["attributes"]中提取（未映射字段）
          ↓
      订单明细数据 → fact_order_items表（逐条提交）
```

## 验证步骤

1. **重新入库TikTok订单数据**：
   - 在字段映射界面，选择TikTok订单数据域
   - 确认表头行设置正确（如`header_row=1`，即Excel第2行）
   - 确认字段映射完整（特别是订单明细字段）
   - 点击"入库数据"

2. **验证修复**：
   ```bash
   python scripts/verify_order_item_ingestion_fix.py
   ```

3. **检查物化视图**：
   - 刷新`mv_sales_day_shop_sku`物化视图
   - 检查`units_sold`、`sales_amount_cny`等字段是否有非零值

## 预期结果

修复后：
- ✅ 订单数据正确入库到`fact_orders`表
- ✅ 订单明细数据正确入库到`fact_order_items`表
- ✅ 单个订单失败不影响其他订单入库
- ✅ 物化视图`mv_sales_day_shop_sku`的`units_sold`、`sales_amount_cny`等字段有非零值

## 相关文件

- `backend/services/data_importer.py` - 订单入库逻辑
- `scripts/verify_order_item_ingestion_fix.py` - 验证脚本
- `scripts/test_order_ingestion_fix.py` - 自动化测试脚本

