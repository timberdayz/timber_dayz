# 字段映射流程简化方案

## 核心问题

**用户问题**：既然标准字段（field_code）已经是全英文了，那数据库列名不是重复的工作了吗？

**答案**：是的，**如果field_code和数据库列名完全一致，确实不需要转换层**。

## 当前情况

### 需要转换的字段（仅2个）
- `order_ts` → `order_time_utc`
- `account_id` → `account`

### 一致的字段（大部分）
- `order_id` = `order_id`
- `platform_code` = `platform_code`
- `shop_id` = `shop_id`
- `total_amount` = `total_amount`
- `currency` = `currency`

## 简化方案

### 方案：统一使用数据库列名作为field_code

**理由**：
1. ✅ **简化流程**：减少一层转换
2. ✅ **减少错误**：field_code和数据库列名一致，不会出现映射错误
3. ✅ **清晰明确**：field_code就是数据库列名
4. ✅ **零维护**：不需要维护转换映射表

### 实施步骤

1. **更新辞典生成逻辑**
   - 生成`field_code`时，直接使用数据库列名
   - 如"日期" → `metric_date`（而不是`date`）
   - 如"订单时间" → `order_time_utc`（而不是`order_ts`）
   - 如"账号" → `account`（而不是`account_id`）

2. **修复现有辞典**
   - 将`order_ts`改为`order_time_utc`
   - 将`account_id`改为`account`

3. **简化ETL流程**
   - 字段映射后，`field_code`直接作为数据库列名使用
   - `upsert_orders_v2`可以直接使用`field_code`作为键

4. **删除或简化转换层**
   - `field_to_column_converter.py`可以删除
   - 或者仅作为向后兼容层（处理旧的field_code）

## 简化后的流程

```
原始字段 → 字段映射 → 标准字段(field_code=数据库列名) → 直接入库
```

**不再需要**：
```
标准字段 → 数据库列名转换
```

## 优势

- ✅ **减少一层转换**：简化代码逻辑
- ✅ **减少出错可能**：field_code和数据库列名一致
- ✅ **代码更清晰**：field_code就是数据库列名
- ✅ **维护成本更低**：不需要维护转换映射表

## 结论

**您的理解完全正确**：如果`field_code`已经是英文，并且与数据库列名一致，那么确实不需要额外的转换层。

**建议**：
1. **统一命名**：让`field_code`直接使用数据库列名
2. **简化流程**：删除`field_to_column_converter.py`
3. **更新辞典**：确保所有`field_code`都是数据库列名

这样流程就变成：
```
原始字段 → 字段映射 → 标准字段(field_code=数据库列名) → 入库
```

**不再需要**：`标准字段 → 数据库列名`这一步转换！

