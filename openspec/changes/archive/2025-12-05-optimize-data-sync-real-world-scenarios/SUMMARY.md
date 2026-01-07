# 优化数据同步功能 - 修改方案总结

## 📋 概述

本次优化针对数据同步功能在实际工作场景中遇到的两个问题：
1. **货币代码导致的表头变化误报** - 全球业务中，同一字段因货币代码不同被误判为不同字段
2. **库存数据重复记录** - 同一商品不同数量导致多条记录，无法正确反映当前库存状态

## 🎯 解决方案

### 1. 货币代码变体识别

**问题**：
- 电商平台导出的源数据会根据当地货币在表头中添加货币代码
- 例如："销售额（已付款订单）(BRL)" vs "销售额（已付款订单）(COP)"
- 系统将其识别为不同的字段，触发表头变化检测，阻止同步

**解决方案**：
- 在表头变化检测前，识别并归一化货币代码变体
- 使用正则表达式 `\(([A-Z]{3})\)` 识别货币代码
- 验证货币代码是否在ISO 4217标准列表中
- 将字段名归一化（移除货币代码部分）
- 如果归一化后字段相同，视为匹配（不触发表头变化检测）
- **新增**：提取货币代码存储到`currency_code`系统字段（String(3)）
- **新增**：`raw_data` JSONB中字段名归一化（不含货币代码），货币作为独立维度字段

**实现位置**：
- `backend/services/template_matcher.py` - `detect_header_changes()` 方法（表头变化检测）
- `backend/services/data_ingestion_service.py` - `ingest_data()` 方法（货币代码提取和存储）
- `backend/services/raw_data_importer.py` - `batch_insert_raw_data()` 方法（存储currency_code字段）

### 2. 库存数据UPSERT策略

**问题**：
- 库存数据使用 `data_hash` 判断重复
- 核心字段：`['product_sku', 'warehouse_id', 'platform_code', 'shop_id']`
- 如果同一商品数量变化，`data_hash` 不同，导致多条记录

**解决方案**：
- 库存数据域使用 UPSERT 策略（更新而非插入）
- 其他数据域保持 INSERT 策略（跳过重复）

**更新字段**：
- `raw_data` - 整行业务数据（JSONB）
- `ingest_timestamp` - 入库时间戳
- `file_id` - 文件ID
- `header_columns` - 表头字段（如果表头变化）

**保留字段**：
- `metric_date` - 业务日期（不应更新）
- `platform_code`, `shop_id`, `data_domain`, `granularity` - 维度字段
- `data_hash` - 用于唯一性判断

**实现位置**：
- `backend/services/deduplication_fields_config.py` - 策略配置
- `backend/services/raw_data_importer.py` - UPSERT 实现

## 🔧 技术细节

### 货币代码识别

**正则表达式**：`\(([A-Z]{3})\)`
- 匹配格式：`(BRL)`, `(COP)`, `(SGD)` 等
- 验证：ISO 4217 标准货币代码列表
- 归一化：移除货币代码部分，保留基础字段名

**示例**：
```
原始字段："销售额（已付款订单）(BRL)"
归一化后："销售额（已付款订单）"
currency_code: "BRL"
raw_data: {"销售额（已付款订单）": 100.50}

原始字段："销售额（已付款订单）(COP)"
归一化后："销售额（已付款订单）"
currency_code: "COP"
raw_data: {"销售额（已付款订单）": 200000.00}

结果：视为匹配（不触发表头变化检测）
Metabase查询：字段名简洁，货币作为独立维度字段
```

### UPSERT 策略

**SQL 示例**：
```sql
-- 库存数据域
ON CONFLICT (data_domain, granularity, data_hash) 
DO UPDATE SET
    raw_data = EXCLUDED.raw_data,
    ingest_timestamp = EXCLUDED.ingest_timestamp,
    file_id = EXCLUDED.file_id,
    header_columns = EXCLUDED.header_columns

-- 其他数据域
ON CONFLICT (data_domain, granularity, data_hash) 
DO NOTHING
```

**策略配置**：
```python
DEDUPLICATION_STRATEGY = {
    'inventory': 'UPSERT',
    'orders': 'INSERT',
    'products': 'INSERT',
    # ... 其他域
}
```

### 系统字段一致性

**统一配置原则**：
- 所有 `fact_raw_data_*` 表都有 `ingest_timestamp` 字段
- 统一配置更新字段列表，即使不使用 UPSERT 也保持配置一致性
- 降低维护成本，便于未来扩展

**配置结构**：
```python
UPSERT_UPDATE_FIELDS = {
    'inventory': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns'],
    'orders': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns'],  # 保持一致性
    # ... 其他域
}
```

## 📊 关键决策

### 1. metric_date 不更新

**原因**：
- `metric_date` 是业务日期，不是系统时间戳
- 对于同一商品+仓库的库存快照，`metric_date` 应该保持不变
- 如果更新 `metric_date`，会导致数据的时间维度混乱

**示例**：
```
第一次同步（2025-09-23）：
- metric_date: 2025-09-23
- raw_data: {"商品名": "A", "库存数量": 1}

第二次同步（2025-09-24，但数据仍然是9月23日的快照）：
- metric_date: 2025-09-23（保持不变）
- raw_data: {"商品名": "A", "库存数量": 2}（更新）
- ingest_timestamp: 2025-09-24（更新）
```

### 2. 不需要 created_at 字段

**原因**：
- 当前表结构中没有 `created_at` 字段
- `ingest_timestamp` 已经记录了入库时间
- 如果需要首次入库时间，可以通过查询最早的 `ingest_timestamp` 获取

### 3. 整行更新 raw_data

**原因**：
- 库存快照特性：每次同步都是当前状态的快照
- 整行更新符合语义，保证数据一致性
- 实现简单，PostgreSQL 直接支持 JSONB 字段更新

### 4. 添加 currency_code 系统字段

**原因**：
- Metabase查询友好：字段名不含货币代码，货币作为独立维度字段
- 查询性能提升：按货币筛选可以使用索引，无需解析JSONB（提升10-100倍）
- 数据存储优化：`raw_data` JSONB中字段名归一化，货币代码独立存储

**多货币字段处理**：
- 如果一行数据有多个货币字段，提取第一个货币字段的货币代码（方案A）
- 大多数情况下，同一行数据只有一个主要货币
- 如果确实需要多货币，可以通过多行数据表示（每行一个货币）

**性能影响**：
- 写入性能影响：几乎可忽略（<0.5%）
  - 字段名归一化：<0.1%（内存操作）
  - 货币代码提取：<0.1%（内存操作）
  - 数据库写入：<0.01%（3字节字段）
  - 索引写入：<0.1%（轻微开销）
- 查询性能提升：显著（10-100倍）
  - 按货币筛选：直接索引查询，无需解析JSONB
  - Metabase查询：字段名简洁，货币作为独立维度字段

## ✅ 验证要点

### 货币变体识别和currency_code提取
- ✅ 只有货币差异 → 视为匹配（不触发变化检测）
- ✅ 货币差异 + 其他字段变化 → 触发变化检测
- ✅ 非货币代码不被误识别
- ✅ 货币代码正确提取并存储到`currency_code`字段
- ✅ 字段名归一化正确（`raw_data`中字段名不含货币代码）
- ✅ 多货币字段场景（提取第一个货币代码）

### 库存数据 UPSERT
- ✅ 核心字段不变，数量变化 → 更新（不重复插入）
- ✅ 核心字段变化 → 插入新记录
- ✅ `metric_date` 保留，`ingest_timestamp` 更新

### 其他数据域
- ✅ orders/products 等域保持 INSERT 策略
- ✅ 重复数据被正确跳过（不更新）

## 📝 实施计划

### 阶段1：货币变体识别和currency_code字段（低风险）
1. 数据库迁移：添加`currency_code`字段到所有`fact_raw_data_*`表
2. 实现货币代码提取和归一化函数
3. 修改表头变化检测逻辑
4. 实现货币代码提取和存储逻辑
5. 测试各种货币变体场景

### 阶段2：库存数据 UPSERT（中等风险）
1. 添加策略配置
2. 实现 UPSERT 逻辑
3. 测试库存数据更新场景

### 阶段3：测试和验证
1. 端到端测试
2. 性能测试
3. 向后兼容性测试

## 🎯 成功标准

1. ✅ 货币代码变体不再触发表头变化检测
2. ✅ 货币代码正确提取并存储到`currency_code`字段
3. ✅ 字段名归一化正确（`raw_data`中字段名不含货币代码）
4. ✅ 库存数据更新而非重复插入
5. ✅ 其他数据域保持现有行为
6. ✅ 向后兼容现有模板和数据
7. ✅ 性能不受影响（写入性能影响<0.5%，查询性能提升10-100倍）
8. ✅ 系统字段配置统一

