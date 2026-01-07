# 字段映射流程简化分析

## 当前问题

您提出了一个非常好的问题：**既然标准字段（field_code）已经是全英文了，为什么还需要转换为数据库列名？**

## 实际情况分析

### 1. 数据库实际列名 vs field_code

**FactOrder表的实际列名**（从schema.py）：
- `order_time_utc`（不是`order_ts`）
- `order_date_local`
- `account`（不是`account_id`）
- `platform_code`（一致）
- `shop_id`（一致）
- `order_id`（一致）

**当前field_code映射**（从field_to_column_converter.py）：
- `"order_ts" → "order_time_utc"` **需要转换**
- `"account_id" → "account"` **需要转换**
- `"order_id" → "order_id"` 一致
- `"platform_code" → "platform_code"` 一致

### 2. 问题根源

**有两种设计思路**：

**思路A（当前）：field_code是业务语义，数据库列名是技术实现**
- field_code: `order_ts`（业务语义：订单时间戳）
- 数据库列名: `order_time_utc`（技术实现：明确是UTC时间）
- 需要一个转换层：`field_to_column_converter.py`
- **优点**：field_code更简洁，业务语义清晰
- **缺点**：需要额外转换层，增加复杂度

**思路B（简化）：field_code直接使用数据库列名**
- field_code: `order_time_utc`（直接对应数据库列名）
- 数据库列名: `order_time_utc`（一致）
- 不需要转换层：可以直接使用
- **优点**：简化流程，减少一层转换
- **缺点**：field_code可能较长（如`order_time_utc`比`order_ts`长）

## 建议方案（简化）

### 推荐：统一使用数据库列名作为field_code

**理由**：
1. ✅ **简化流程**：减少一层转换，降低复杂度
2. ✅ **减少错误**：field_code和数据库列名一致，不会出现映射错误
3. ✅ **清晰明确**：field_code就是数据库列名，一目了然
4. ✅ **零维护**：不需要维护`field_to_column_converter.py`映射表

**实施步骤**：

1. **更新辞典生成逻辑**：
   - 生成`field_code`时，直接使用数据库列名
   - 如"日期" → `metric_date`（而不是`date`）
   - 如"订单时间" → `order_time_utc`（而不是`order_ts`）

2. **更新映射表**：
   - 确保辞典中的`field_code`都是数据库列名
   - 前端显示时，可以使用`cn_name`作为用户友好的显示

3. **删除或简化转换层**：
   - 如果`field_code`已经是数据库列名，`field_to_column_converter.py`可以删除
   - 或者仅保留作为**向后兼容层**（处理旧的field_code）

4. **更新ETL流程**：
   - 字段映射后，`field_code`直接作为数据库列名使用
   - `upsert_orders_v2`可以直接使用`field_code`作为键

## 简化后的流程

```
原始字段 → 字段映射 → 标准字段(field_code=数据库列名) → 直接入库
```

**优势**：
- ✅ 减少一层转换
- ✅ 减少出错可能
- ✅ 代码更清晰
- ✅ 维护成本更低

## 结论

**您的理解是正确的**：如果`field_code`已经是英文，并且与数据库列名一致，那么确实不需要额外的转换层。

**建议**：
1. **统一命名**：让`field_code`直接使用数据库列名（如`order_time_utc`而不是`order_ts`）
2. **简化流程**：删除`field_to_column_converter.py`，或者仅作为向后兼容层
3. **更新辞典**：确保所有`field_code`都是数据库列名

这样流程就变成：
```
原始字段 → 字段映射 → 标准字段(field_code=数据库列名) → 入库
```

**不再需要**：`标准字段 → 数据库列名`这一步转换！

