# Bug修复：FactProductMetric.file_id字段错误

**修复日期**: 2025-11-22  
**问题类型**: 数据库字段错误  
**影响范围**: 任务日志查询API

---

## 问题描述

在查询任务日志时，后端API `/api/field-mapping/auto-ingest/task/{task_id}/logs` 返回500错误：

```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) 
错误: 字段 "file_id" 不存在
LINE 2: SELECT COUNT(*) FROM fact_product_metrics WHERE file_id = ...
```

**根本原因**:
- `FactProductMetric`表没有`file_id`字段
- 应该使用`source_catalog_id`字段来关联`catalog_files`表

---

## 修复内容

### 修复文件: `backend/routers/auto_ingest.py`

**修复位置1**: 第527行（`get_task_logs`函数）
```python
# ❌ 修复前
imported = db.execute(text("""
    SELECT COUNT(*) FROM fact_product_metrics WHERE file_id = :file_id
"""), {"file_id": file_id}).scalar() or 0

# ✅ 修复后
imported = db.execute(text("""
    SELECT COUNT(*) FROM fact_product_metrics WHERE source_catalog_id = :file_id
"""), {"file_id": file_id}).scalar() or 0
```

**修复位置2**: 第627行（`get_file_logs`函数）
```python
# ❌ 修复前
imported = db.execute(text("""
    SELECT COUNT(*) FROM fact_product_metrics WHERE file_id = :file_id
"""), {"file_id": file_id}).scalar() or 0

# ✅ 修复后
imported = db.execute(text("""
    SELECT COUNT(*) FROM fact_product_metrics WHERE source_catalog_id = :file_id
"""), {"file_id": file_id}).scalar() or 0
```

---

## 数据库表结构说明

### FactProductMetric表
- **主键**: 复合主键（`platform_code`, `shop_id`, `platform_sku`, `metric_date`, `metric_type`）
- **文件关联字段**: `source_catalog_id`（关联`catalog_files.id`）
- **没有字段**: `file_id`（这是错误的字段名）

### FactOrder表
- **主键**: 复合主键（`platform_code`, `shop_id`, `order_id`）
- **文件关联字段**: `file_id`（关联`catalog_files.id`）
- **注意**: `FactOrder`表使用`file_id`字段，这是正确的

---

## 影响范围

### 受影响的API端点
1. ✅ `/api/field-mapping/auto-ingest/task/{task_id}/logs` - 已修复
2. ✅ `/api/field-mapping/auto-ingest/file/{file_id}/logs` - 已修复

### 受影响的功能
- ✅ 任务日志查询（显示文件入库统计）
- ✅ 文件日志查询（显示单个文件的入库统计）

---

## 验证方法

### 测试步骤
1. 选择一个已入库的库存文件（data_domain = "inventory"）
2. 调用API：`GET /api/field-mapping/auto-ingest/task/{task_id}/logs`
3. 验证返回的`imported`字段是否正确显示Fact层数据数量

### 预期结果
- ✅ API返回200状态码
- ✅ `imported`字段显示正确的Fact层数据数量
- ✅ 不再出现`UndefinedColumn`错误

---

## 相关修复

此问题与之前修复的`data_flow.py`中的问题相同：
- `backend/routers/data_flow.py`: 已修复3处`FactProductMetric.id`问题
- `backend/routers/auto_ingest.py`: 本次修复2处`FactProductMetric.file_id`问题

**总计修复**: 5处数据库字段错误

---

## 预防措施

1. **代码审查**: 在代码审查时检查所有`FactProductMetric`表的字段引用
2. **单元测试**: 添加单元测试验证数据库查询的正确性
3. **文档更新**: 更新数据库设计文档，明确说明各表的字段命名规范

