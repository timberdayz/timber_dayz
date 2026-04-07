# v4.14.0 JSONB转换修复文档

**日期**: 2025-01-31  
**版本**: v4.14.0  
**问题**: 表达式索引插入时，`raw_data`和`header_columns`未转换为JSONB格式，导致`can't adapt type 'dict'`错误

---

## 问题描述

### 问题现象
- 单文件同步失败，前端显示"数据入库失败:准备入库1218行,但实际入库0行"
- 后端日志显示：`sqlalchemy.exc.ProgrammingError: (psycopg2.ProgrammingError) can't adapt type 'dict'`
- pgAdmin显示表头正确（系统字段+动态列），但数据为0行

### 错误详情
```
sqlalchemy.exc.ProgrammingError: (psycopg2.ProgrammingError) can't adapt type 'dict'
INSERT INTO "fact_raw_data_inventory_snapshot" 
(platform_code, shop_id, data_domain, granularity, metric_date, file_id, raw_data, header_columns, data_hash, ingest_timestamp)
VALUES (:platform_code, :shop_id, :data_domain, :granularity, :metric_date, :file_id, :raw_data, :header_columns, :data_hash, :ingest_timestamp)
ON CONFLICT (platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash) DO NOTHING

[parameters: {
    'raw_data': {'*商品SKU': 'XH-TD-004-silver-s', ...},  # Python字典
    'header_columns': ['*商品SKU', '商品图片', ...],  # Python列表
    ...
}]
```

### 根本原因
1. **表达式索引插入使用原始SQL**：`text()`函数执行原始SQL语句
2. **psycopg2无法直接适配Python对象**：`raw_data`是Python字典，`header_columns`是Python列表
3. **ORM插入会自动转换**：SQLAlchemy ORM会自动将dict/list转换为JSONB，但原始SQL不会
4. **类型不匹配**：PostgreSQL期望JSONB类型，但收到Python dict/list对象

---

## 修复方案

### 核心思路
在表达式索引插入前，将`raw_data`（dict）和`header_columns`（list）转换为JSON字符串，使用`json.dumps()`。

### 修复代码位置
- **文件**: `backend/services/raw_data_importer.py`
- **方法**: `batch_insert_raw_data()`
- **关键修改**: 表达式索引插入循环中添加JSONB转换

---

## 修复实现

### 修复前
```python
for i, record in enumerate(insert_data_orm):
    try:
        self.db.execute(insert_sql_template, record)  # ❌ record包含Python dict/list
    except Exception as e:
        # 错误处理
```

### 修复后
```python
for i, record in enumerate(insert_data_orm):
    # ⭐ v4.14.0修复：表达式索引插入前，将raw_data和header_columns转换为JSON字符串
    # psycopg2无法直接将Python dict/list适配为JSONB，需要先转换为JSON字符串
    record_copy = record.copy()  # 避免修改原始记录
    
    # 转换raw_data（dict -> JSON字符串）
    if 'raw_data' in record_copy and isinstance(record_copy['raw_data'], dict):
        record_copy['raw_data'] = json.dumps(record_copy['raw_data'], ensure_ascii=False)
    elif 'raw_data' in record_copy and record_copy['raw_data'] is None:
        record_copy['raw_data'] = None
    
    # 转换header_columns（list -> JSON字符串）
    if 'header_columns' in record_copy and isinstance(record_copy['header_columns'], list):
        record_copy['header_columns'] = json.dumps(record_copy['header_columns'], ensure_ascii=False)
    elif 'header_columns' in record_copy and record_copy['header_columns'] is None:
        record_copy['header_columns'] = None
    
    try:
        self.db.execute(insert_sql_template, record_copy)  # ✅ record_copy包含JSON字符串
    except Exception as e:
        # 错误处理
```

---

## 修复效果

### 修复前
- ❌ `can't adapt type 'dict'`错误
- ❌ 数据无法插入，实际插入0行
- ❌ 前端显示"数据入库失败"

### 修复后
- ✅ JSONB字段正确转换为JSON字符串
- ✅ 数据成功插入，实际插入数准确
- ✅ 前端显示"数据入库成功"

---

## 技术细节

### 为什么需要转换？

1. **psycopg2的限制**：
   - psycopg2是PostgreSQL的Python适配器
   - 它无法直接将Python dict/list对象适配为PostgreSQL的JSONB类型
   - 需要先转换为JSON字符串，然后PostgreSQL会自动转换为JSONB

2. **ORM vs 原始SQL**：
   - **ORM插入**：SQLAlchemy ORM会自动处理类型转换（dict/list → JSONB）
   - **原始SQL插入**：需要手动转换（dict/list → JSON字符串 → JSONB）

3. **为什么使用`json.dumps()`**：
   - `json.dumps()`将Python对象转换为JSON字符串
   - `ensure_ascii=False`确保中文字符正确编码（不转义为Unicode）
   - PostgreSQL的`::jsonb`或自动类型转换会将JSON字符串转换为JSONB

### 转换示例

**转换前**：
```python
record = {
    'raw_data': {'*商品SKU': 'XH-TD-004-silver-s', '商品图片': ''},  # Python dict
    'header_columns': ['*商品SKU', '商品图片', ...],  # Python list
    ...
}
```

**转换后**：
```python
record_copy = {
    'raw_data': '{"*商品SKU": "XH-TD-004-silver-s", "商品图片": ""}',  # JSON字符串
    'header_columns': '["*商品SKU", "商品图片", ...]',  # JSON字符串
    ...
}
```

**PostgreSQL接收**：
```sql
INSERT INTO ... VALUES (..., '{"*商品SKU": "XH-TD-004-silver-s"}'::jsonb, '["*商品SKU", ...]'::jsonb, ...)
```

---

## 相关文档

- [v4.14.0 表达式索引修复文档](V4_14_0_EXPRESSION_INDEX_FIX.md)
- [v4.14.0 动态列实现文档](V4_14_0_DYNAMIC_COLUMNS_IMPLEMENTATION.md)

---

## 总结

本次修复解决了表达式索引插入时的JSONB类型转换问题，通过在使用原始SQL插入前将Python dict/list转换为JSON字符串，确保了：

1. **类型兼容性**：psycopg2能够正确处理JSON字符串
2. **数据完整性**：中文字符通过`ensure_ascii=False`正确编码
3. **性能优化**：只在表达式索引插入时转换（普通索引使用ORM，自动转换）

修复后，系统能够正确处理Inventory域（表达式索引）和Orders/Products域（普通索引）的数据入库。

