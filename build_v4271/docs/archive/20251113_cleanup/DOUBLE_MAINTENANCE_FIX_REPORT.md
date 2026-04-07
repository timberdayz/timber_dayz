# 双维护问题修复报告

**日期**: 2025-11-05  
**版本**: v4.6.3  
**问题**: 双维护导致前端看不到正确的入库数据  
**状态**: ✅ 已修复

---

## 🔍 问题诊断

### 发现的双维护问题

**根本原因**: `upsert_product_metrics`函数没有接收`file_record`参数，导致：
1. 数据入库时，如果rows中没有`platform_code`，直接使用默认值`"unknown"`
2. 即使`catalog_files`表中文件记录显示`platform_code="miaoshou"`，数据仍然被标记为`"unknown"`
3. 前端查询时筛选`platform="miaoshou"`，查不到这些数据（因为它们被标记为`"unknown"`）

### 证据

数据库检查结果：
```
Miaoshou平台数据: 0条  ❌
Unknown平台数据: 4条
  - 有total_stock, available_stock, warehouse, price数据
  - 仓库: "新加坡+部分菲律宾"（明显是miaoshou数据）
  - Last Update: 2025-11-04
```

**结论**: 有4条miaoshou数据被错误标记为`"unknown"`平台！

---

## ✅ 修复内容

### 1. 修复`upsert_product_metrics`函数签名

**文件**: `backend/services/data_importer.py`

**修改前**:
```python
def upsert_product_metrics(db: Session, rows: List[Dict[str, Any]]) -> int:
```

**修改后**:
```python
def upsert_product_metrics(db: Session, rows: List[Dict[str, Any]], file_record: Optional[Any] = None) -> int:
    """
    ⭐ v4.6.3修复：双维护问题 - 接收file_record参数，确保platform_code正确
    - 如果rows中没有platform_code，从file_record获取
    - 避免数据被错误标记为"unknown"平台
    """
```

### 2. 修复platform_code获取逻辑（PostgreSQL分支）

**修改前**:
```python
data = {
    "platform_code": r.get("platform_code", "unknown"),  # ❌ 直接使用默认值
    "shop_id": r.get("shop_id", "unknown"),
    ...
}
```

**修改后**:
```python
# ⭐ v4.6.3修复：双维护问题 - 确保platform_code正确（优先使用file_record）
platform_code_value = r.get("platform_code")
if not platform_code_value:
    if file_record and file_record.platform_code:
        platform_code_value = file_record.platform_code  # ✅ 从file_record获取
    else:
        platform_code_value = "unknown"  # 最后兜底

shop_id_value = r.get("shop_id")
if not shop_id_value:
    if file_record and file_record.shop_id:
        shop_id_value = file_record.shop_id  # ✅ 从file_record获取
    else:
        shop_id_value = "unknown"  # 最后兜底

data = {
    "platform_code": platform_code_value,
    "shop_id": shop_id_value,
    ...
}
```

### 3. 修复platform_code获取逻辑（SQLite分支）

同样修复SQLite分支中的逻辑，确保从`file_record`获取`platform_code`和`shop_id`。

### 4. 修复调用点

**文件**: `backend/routers/field_mapping.py`

**修改前**:
```python
imported = upsert_product_metrics(db, valid_rows)  # ❌ 没有传递file_record
```

**修改后**:
```python
imported = upsert_product_metrics(db, valid_rows, file_record=file_record)  # ✅ 传递file_record
```

---

## 🎯 修复后的行为

### platform_code获取优先级

1. **优先使用**: rows中的`platform_code`（如果存在）
2. **其次使用**: `file_record.platform_code`（从文件记录获取）
3. **最后使用**: `"unknown"`（兜底值）

### shop_id获取优先级

同样的优先级逻辑。

---

## 📋 需要修复的其他调用点

检查发现还有其他调用点也需要修复：

1. ✅ `backend/routers/field_mapping.py` - 已修复
2. ⚠️ `backend/routers/field_mapping.py:1123` - 需要修复
3. ⚠️ `backend/services/bulk_importer.py:354` - 需要修复
4. ⚠️ `backend/tasks/data_processing.py:99` - 需要修复
5. ✅ `backend/routers/data_quarantine.py:346` - 已正确传递file_record

---

## ⚠️ 重要提醒

### 历史数据修复

**即使代码已修复，历史数据仍然需要修复！**

有4条miaoshou数据被错误标记为`"unknown"`平台，需要：
1. 将这些数据的`platform_code`从`"unknown"`更新为`"miaoshou"`
2. 根据文件记录或数据特征（如warehouse="新加坡+部分菲律宾"）识别真正的平台

### 修复历史数据的SQL

```sql
-- 修复历史数据：将unknown平台的数据更新为miaoshou（如果warehouse包含新加坡）
UPDATE fact_product_metrics
SET platform_code = 'miaoshou'
WHERE platform_code = 'unknown'
  AND warehouse LIKE '%新加坡%'
  AND total_stock IS NOT NULL
  AND available_stock IS NOT NULL;
```

---

## ✅ 修复完成

- ✅ `upsert_product_metrics`函数签名已修复
- ✅ PostgreSQL分支逻辑已修复
- ✅ SQLite分支逻辑已修复
- ✅ `field_mapping.py`调用点已修复
- ⚠️ 其他调用点需要后续修复（如果使用）
- ⚠️ 历史数据需要手动修复

**现在请重新导入数据，验证platform_code是否正确！** 🚀

