# 订单明细入库逻辑修复说明（v4.10.0）

## 问题描述

用户报告：TikTok订单数据入库后，`mv_sales_day_shop_sku`物化视图中`units_sold`、`sales_amount_cny`、`sales_amount`、`avg_unit_price_cn`等字段都是0，尽管`order_count`有正值。

## 根本原因

1. **`fact_order_items`表为空**：订单明细数据没有被入库到`fact_order_items`表
2. **字段映射问题**：订单明细字段（如`platform_sku`、`quantity`、`line_amount`）可能：
   - 被映射到标准字段（如`platform_sku`、`quantity`），存在于`r`（映射后的数据）中
   - 未被映射，存在于`extras`中，然后被放入`core["attributes"]` JSON中
3. **原始逻辑缺陷**：订单明细入库逻辑只从`r`中提取字段，没有从`attributes`中提取

## 修复方案

修改`backend/services/data_importer.py`中的`upsert_orders_v2`函数，增强订单明细字段提取逻辑：

### 1. 添加`get_from_attrs`辅助函数

从`attributes` JSON中提取字段，支持：
- 多种可能的键名（标准字段名、中文字段名、大小写变体）
- 中文键名映射（如"平台SKU"、"商品数量"、"商品金额"等）
- 空值和无效值过滤

### 2. 增强字段提取逻辑

对于每个订单明细字段（`platform_sku`、`quantity`、`line_amount`、`unit_price`、`product_title`等），按以下优先级提取：
1. **从`r`中提取**（字段映射后的标准字段）
2. **从`attributes`中提取**（未映射的原始字段）

### 3. 支持多种字段名变体

- `platform_sku`: "平台SKU"、"SKU ID"、"商品SKU"、"产品SKU"、"规格货号"
- `quantity`: "数量"、"商品数量"、"销售数量"、"quantity"、"qty"
- `line_amount`: "金额"、"商品金额"、"行金额"、"line_amount"、"total_amount"
- `product_title`: "商品名称"、"产品名称"、"product_name"、"product_title"

## 修复后的数据流

```
原始Excel数据
  ↓
字段映射（field_mapping.py）
  ↓
映射后的数据（r）
  ├─ 标准字段（如platform_sku, quantity）→ 直接使用
  └─ 未映射字段 → 放入extras → 转换为core["attributes"] JSON
  ↓
订单入库（upsert_orders_v2）
  ├─ 订单级别数据 → fact_orders表
  └─ 订单明细数据提取
      ├─ 从r中提取（标准字段）
      └─ 从core["attributes"]中提取（未映射字段）
          ↓
      订单明细数据 → fact_order_items表
```

## 验证步骤

1. **重新入库TikTok订单数据**：
   - 在字段映射界面，选择TikTok订单数据域
   - 确认表头行设置正确（如header_row=1）
   - 点击"入库数据"

2. **验证订单明细入库**：
   ```bash
   python scripts/verify_order_item_ingestion_fix.py
   ```
   - 检查`fact_order_items`表是否有数据
   - 检查`mv_sales_day_shop_sku`物化视图的销售金额是否非零

3. **刷新物化视图**（如果需要）：
   ```bash
   python scripts/update_order_mv.py
   ```

## 预期结果

修复后，重新入库TikTok订单数据后：
- ✅ `fact_order_items`表应该有订单明细数据
- ✅ `mv_sales_day_shop_sku`物化视图的`units_sold`、`sales_amount_cny`等字段应该有非零值
- ✅ 物化视图能够正确显示SKU级别的销售统计

## 相关文件

- `backend/services/data_importer.py` - 订单明细入库逻辑
- `scripts/verify_order_item_ingestion_fix.py` - 验证脚本
- `scripts/update_order_mv.py` - 刷新物化视图脚本

## 注意事项

1. **必须重新入库数据**：修复后的逻辑只对新入库的数据生效，历史数据不会自动更新
2. **字段映射建议**：建议在字段映射界面将订单明细字段映射到标准字段（如`platform_sku`、`quantity`、`line_amount`），这样可以提高数据提取的准确性
3. **物化视图刷新**：如果物化视图数据仍然不正确，可能需要手动刷新物化视图

