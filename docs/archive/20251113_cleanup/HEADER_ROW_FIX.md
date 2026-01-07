# header_row参数统一修复

**问题**: header_row参数格式不一致，导致表头处理错误

**修复内容**:
1. ✅ 统一默认值：所有API的header_row默认值从1改为0（0-based）
2. ✅ 统一转换逻辑：直接使用header_row，不需要减1
3. ✅ 修复位置：
   - `backend/routers/field_mapping.py` - ingest API
   - `backend/routers/field_mapping.py` - preview API
   - `backend/routers/field_mapping.py` - bulk-ingest API

**修复前**:
```python
header_row = ingest_data.get("header_row", 1)  # ❌ 默认1
if header_row == 0:
    header_param = None  # ❌ 0变成None
else:
    header_param = header_row - 1  # ❌ 减1
```

**修复后**:
```python
header_row = ingest_data.get("header_row", 0)  # ✅ 默认0
if header_row < 0:
    header_param = None  # ✅ 只有负数才是None
else:
    header_param = header_row  # ✅ 直接使用
```

**影响**:
- ✅ 自动同步和手动入库使用相同的header_row格式
- ✅ 预览和入库使用相同的表头行
- ✅ 避免列名不匹配问题

