# 代码修改总结

**日期**: 2025-01-31  
**文件**: `backend/services/data_ingestion_service.py`

---

## ✅ 修改内容

### 1. 导入新服务（第28-30行）

**添加**:
```python
# ⭐ v4.6.0 DSS架构：使用RawDataImporter写入JSONB格式
from backend.services.raw_data_importer import get_raw_data_importer
from backend.services.deduplication_service import DeduplicationService
```

### 2. 保存原始表头字段列表（第238-239行）

**添加**:
```python
# ⭐ v4.6.0 DSS架构：保存原始表头字段列表（用于JSONB存储）
original_header_columns = list(df.columns.tolist())
```

### 3. 替换数据入库逻辑（第372-450行）

**移除**:
- `stage_orders`, `upsert_orders`
- `stage_product_metrics`, `upsert_product_metrics`
- `stage_inventory`
- `upsert_traffic`, `upsert_service`, `upsert_analytics`

**替换为**:
```python
# ⭐ v4.6.0 DSS架构：使用RawDataImporter写入JSONB格式（保留原始中文表头）
raw_importer = get_raw_data_importer(self.db)
dedup_service = DeduplicationService(self.db)

# 计算data_hash（批量计算）
data_hashes = dedup_service.batch_calculate_data_hash(valid_rows)

# 批量插入（使用RawDataImporter）
imported = raw_importer.batch_insert_raw_data(
    rows=valid_rows,  # 原始数据，保留中文字段名
    data_hashes=data_hashes,
    data_domain=domain,
    granularity=granularity,
    platform_code=platform,
    shop_id=getattr(file_record, 'shop_id', None) if file_record else None,
    file_id=file_id,
    header_columns=header_columns  # 原始表头字段列表
)
```

---

## 🎯 关键改进

1. **保留原始中文表头** ✅
   - 数据以JSONB格式存储，中文字段名作为键
   - 不进行字段映射转换

2. **统一使用RawDataImporter** ✅
   - 所有数据域统一使用RawDataImporter
   - 自动选择目标表（fact_raw_data_{domain}_{granularity}）

3. **集成去重逻辑** ✅
   - 批量计算data_hash
   - 使用ON CONFLICT自动去重

4. **移除Staging层** ✅
   - DSS架构不再需要Staging层
   - 直接写入Fact层

---

## ⚠️ 注意事项

1. **向后兼容**: 保留了字段映射逻辑，但如果没有映射，会保留原始列名
2. **订单金额数据**: 保留了Pattern-based Mapping功能（独立功能）
3. **错误处理**: 如果RawDataImporter失败，会记录错误但不抛出异常

---

**状态**: ✅ **代码修改完成，无语法错误**

