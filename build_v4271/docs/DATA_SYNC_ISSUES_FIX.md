# 数据同步问题修复文档

**修复日期**: 2025-12-02  
**问题**: 数据同步显示成功但Metabase中看不到数据

---

## 🔍 问题分析

### 问题1：返回准备插入数量而非实际插入数量

**原因**：
- `raw_data_importer.py` 中 `batch_insert_raw_data()` 方法返回 `len(insert_data)`
- 这是准备插入的数量，不是实际插入的数量
- 如果数据重复（`data_hash`已存在），`ON CONFLICT DO NOTHING`会静默跳过
- 实际插入数可能是0，但代码仍返回准备插入的数量

**修复**：
- 在插入前后查询记录数，计算实际插入数
- 返回实际插入数，而不是准备插入数

### 问题2：清理数据库时失败文件没有重置

**原因**：
- `cleanup_database` API只重置了 `['ingested', 'partial_success', 'processing']` 状态
- 没有包含 `'failed'` 状态
- 导致失败文件无法重新同步

**修复**：
- 在清理数据库时，将 `'failed'` 状态也重置为 `'pending'`

### 问题3：data_hash逻辑分析

**当前逻辑**：
- `data_hash` 只基于 `row` 的业务字段计算（排除元数据字段）
- 唯一约束是 `(data_domain, granularity, data_hash)`
- **不包含** `platform_code` 和 `shop_id`

**潜在问题**：
- 如果不同平台/店铺的数据业务字段完全相同，`data_hash` 会相同
- 第二次插入会被 `ON CONFLICT DO NOTHING` 跳过
- 这可能导致某些平台/店铺的数据无法入库

**验证结果**：
- 数据库查询显示 `fact_raw_data_inventory_snapshot` 表行数为 **0**
- 说明数据确实没有入库
- 可能原因：
  1. 数据重复被 `ON CONFLICT` 跳过
  2. 或者之前的数据已被清理

---

## ✅ 已修复的代码

### 修复1：返回实际插入数量

**文件**: `backend/services/raw_data_importer.py`

**修改内容**：
```python
# ⭐ 修复：插入前查询当前记录数
before_count = self.db.execute(
    select(func.count()).select_from(target_table)
).scalar()

# 执行插入
result = self.db.execute(stmt)
self.db.commit()

# ⭐ 修复：插入后查询实际记录数
after_count = self.db.execute(
    select(func.count()).select_from(target_table)
).scalar()

# ⭐ 修复：计算实际插入数
actual_inserted = after_count - before_count

return actual_inserted  # 返回实际插入数
```

### 修复2：清理数据库包含失败文件

**文件**: `backend/routers/data_sync.py`

**修改内容**：
```python
# ⭐ 修复：包含failed状态
files_to_reset = db.query(CatalogFile).filter(
    CatalogFile.status.in_(['ingested', 'partial_success', 'processing', 'failed'])
).all()

updated_count = db.query(CatalogFile).filter(
    CatalogFile.status.in_(['ingested', 'partial_success', 'processing', 'failed'])
).update({"status": "pending"}, synchronize_session=False)
```

---

## 🔧 验证方法

### 验证1：检查数据库数据

```bash
python temp/development/check_database_data.py
```

### 验证2：重新同步数据

1. 在前端点击"清理数据库"按钮
2. 选择待同步文件，点击"同步"
3. 查看返回的实际插入数量（应该是实际插入数，不是准备插入数）
4. 在Metabase中查询对应表，确认数据存在

### 验证3：检查data_hash重复情况

```sql
-- 在数据库中执行
SELECT 
    data_hash, 
    COUNT(*) as count, 
    COUNT(DISTINCT platform_code) as platforms,
    COUNT(DISTINCT shop_id) as shops
FROM fact_raw_data_inventory_snapshot 
GROUP BY data_hash 
HAVING COUNT(*) > 1;
```

如果发现重复的 `data_hash` 跨越不同平台/店铺，说明 `data_hash` 逻辑可能需要优化。

---

## 📝 后续建议

### 建议1：优化data_hash计算（可选）

如果发现不同平台/店铺的数据被误判为重复，可以考虑：

**方案A**：在 `data_hash` 计算中包含 `platform_code` 和 `shop_id`
```python
# 在计算data_hash时，添加platform_code和shop_id
business_data = {
    'platform_code': platform_code,  # 添加平台代码
    'shop_id': shop_id,  # 添加店铺ID
    **{k: v for k, v in row.items() if k not in exclude_fields and v is not None}
}
```

**方案B**：修改唯一约束，包含 `platform_code` 和 `shop_id`
```python
# 修改唯一约束为：(platform_code, shop_id, data_domain, granularity, data_hash)
UniqueConstraint("platform_code", "shop_id", "data_domain", "granularity", "data_hash", ...)
```

**注意**：这需要数据库迁移，需要谨慎评估。

### 建议2：添加数据同步日志

在数据同步时记录：
- 准备插入数量
- 实际插入数量
- 被跳过的数量（重复数据）
- 失败原因

---

## 🎯 修复完成状态

- ✅ **修复1**: 返回实际插入数量（已完成）
- ✅ **修复2**: 清理数据库包含失败文件（已完成）
- ⚠️ **问题3**: data_hash逻辑需要进一步验证（数据库当前为空，无法验证）

---

## 📚 相关文档

- `docs/DATA_SYNC_TABLE_MAPPING.md` - 数据同步表映射关系
- `docs/DATA_SYNC_PIPELINE_VALIDATION.md` - 数据同步管道验证文档

