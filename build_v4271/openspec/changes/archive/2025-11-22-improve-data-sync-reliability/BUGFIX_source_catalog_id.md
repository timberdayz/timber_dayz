# Bug修复：数据流转显示Fact层数据为0的问题

**修复日期**: 2025-11-22  
**问题类型**: 数据血缘字段未设置  
**影响范围**: 数据流转查询和显示

---

## 问题描述

数据已成功入库到Fact层（物化视图中有数据），但数据流转显示Fact层数据为0。

**用户反馈**:
- 数据治理概览显示文件已同步
- 物化视图中有数据
- 但数据流转显示Fact层为0，丢失行数为18240

---

## 问题根源

### 1. 数据入库时未设置source_catalog_id

在`backend/services/data_ingestion_service.py`中，调用`upsert_product_metrics`时：
- 对于inventory数据域，只设置了`data_domain`和`granularity`
- **未设置`source_catalog_id`字段**

### 2. upsert_product_metrics函数缺少fallback逻辑

在`backend/services/data_importer.py`的`upsert_product_metrics`函数中：
- `source_catalog_id`只从行数据中获取：`r.get("source_catalog_id")`
- 如果行数据中没有该字段，则为`None`
- **缺少fallback逻辑**：应该使用`file_record.id`作为默认值

### 3. 数据流转查询依赖source_catalog_id

在`backend/routers/data_flow.py`中，查询Fact层数据时：
```python
fact_count = db.query(func.count(FactProductMetric.platform_code)).filter(
    FactProductMetric.source_catalog_id == file_id
).scalar() or 0
```

如果`source_catalog_id`为`None`，则查询不到数据。

---

## 修复内容

### 修复1: 数据入库服务 (`backend/services/data_ingestion_service.py`)

**修复位置1**: inventory数据域（第416-420行）
```python
# ✅ 修复后
for row in valid_rows:
    row['data_domain'] = 'inventory'
    if not row.get('granularity'):
        row['granularity'] = 'snapshot'
    # ⭐ v4.13.2修复：设置source_catalog_id用于数据流转追踪
    if file_record and not row.get('source_catalog_id'):
        row['source_catalog_id'] = file_record.id
```

**修复位置2**: products/traffic/analytics数据域（第437-441行）
```python
# ✅ 修复后
for row in valid_rows:
    if file_record and not row.get('source_catalog_id'):
        row['source_catalog_id'] = file_record.id
```

### 修复2: 数据导入服务 (`backend/services/data_importer.py`)

**修复位置**: `upsert_product_metrics`函数（第1380行）
```python
# ❌ 修复前
"source_catalog_id": r.get("source_catalog_id"),  # 可选：来源文件ID

# ✅ 修复后
"source_catalog_id": r.get("source_catalog_id") or (file_record.id if file_record else None),  # ⭐ v4.13.2修复：优先使用行数据，否则使用file_record.id
```

**SQLite分支**: 同样修复（第1587行）

### 修复3: 已存在数据的修复脚本 (`scripts/fix_source_catalog_id_final.py`)

**策略**: 使用时间范围匹配
- 查找StagingInventory的创建时间范围
- 更新在同一时间范围内创建的FactProductMetric记录（inventory域，source_catalog_id为NULL）

**修复结果**: 成功修复1092条记录

---

## 验证结果

### 测试1: 数据库检查
```
[INFO] file_id=1106的FactProductMetric记录:
[INFO]   source_catalog_id=1106的记录数: 1092
[INFO]   source_catalog_id为NULL的inventory记录数: 0
[OK] 数据库中已有正确设置source_catalog_id的记录
```

### 测试2: 数据流转API
```
[INFO] Raw层: 18240
[INFO] Staging层: 18240
[INFO] Fact层: 1092  ← 修复后正确显示
[INFO] Quarantine层: 0
[OK] Fact层数据数量正确: 1092
```

---

## 影响范围

### 受影响的API端点
- ✅ `/api/data-flow/trace/file/{file_id}` - 已修复
- ✅ `/api/data-flow/trace/task/{task_id}` - 已修复

### 受影响的功能
- ✅ 数据流转可视化 - 现在可以正确显示Fact层数据
- ✅ 数据丢失分析 - 现在可以正确计算丢失率
- ✅ 对比报告 - 现在可以正确显示Fact层数据统计

---

## 后续建议

1. **新数据**: 修复已应用，新同步的文件会自动设置`source_catalog_id`
2. **已存在数据**: 已修复file_id=1106的数据，其他文件的数据可以使用`scripts/fix_source_catalog_id_final.py`修复
3. **数据验证**: 建议定期检查`source_catalog_id`为NULL的记录，确保数据血缘完整性

---

## 相关文件

- `backend/services/data_ingestion_service.py`：数据入库服务
- `backend/services/data_importer.py`：数据导入服务
- `backend/routers/data_flow.py`：数据流转查询API
- `scripts/fix_source_catalog_id_final.py`：数据修复脚本
- `scripts/test_data_flow_fix.py`：测试脚本

