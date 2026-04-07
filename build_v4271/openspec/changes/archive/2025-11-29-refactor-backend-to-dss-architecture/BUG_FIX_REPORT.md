# Bug修复报告：入库失败和模板保存问题

**日期**: 2025-01-31  
**问题**: 入库失败 + 模板保存无响应

---

## 🔍 问题分析

### 问题1: 入库失败

**错误信息**: "服务器内部错误 - 数据入库失败"

**根本原因**:
1. **后端代码错误**: `batch_calculate_data_hash`接收字典列表，但代码传入DataFrame
2. **逻辑错误**: DSS架构入库成功后，没有正确设置`staged`变量，导致后续逻辑混乱
3. **缩进错误**: 降级逻辑的缩进不正确，导致代码执行错误

### 问题2: 模板保存无响应

**错误信息**: 保存模板失败，没有成功提示

**根本原因**:
1. **API路径错误**: 前端调用`/field-mapping/templates/save`（旧API），应该调用`/field-mapping/dictionary/templates/save`
2. **参数不匹配**: 后端API期望`header_columns`，但前端可能没有正确传递

---

## ✅ 已修复的问题

### 修复1: 后端入库逻辑 ✅

**文件**: `backend/routers/field_mapping.py`

**修复内容**:
1. ✅ 修复`batch_calculate_data_hash`调用（传入字典列表而非DataFrame）
2. ✅ 修复DSS架构入库成功后的逻辑（正确设置`staged`并跳过旧逻辑）
3. ✅ 修复降级逻辑的缩进问题

**关键代码**:
```python
# 修复前（错误）:
df_valid = pd.DataFrame(valid_rows)
data_hashes = deduplication_service.batch_calculate_data_hash(df_valid).tolist()

# 修复后（正确）:
data_hashes = deduplication_service.batch_calculate_data_hash(valid_rows)
```

### 修复2: 前端API调用 ✅

**文件**: `frontend/src/api/index.js`

**修复内容**:
1. ✅ 添加`header_columns`参数到`ingestFile()`方法
2. ✅ 更新`saveTemplate()`方法使用正确的API路径和参数

**文件**: `frontend/src/views/FieldMappingEnhanced.vue`

**修复内容**:
1. ✅ 更新模板保存API路径为`/field-mapping/dictionary/templates/save`
2. ✅ 确保传递`header_columns`参数

### 修复3: 后端模板保存API ✅

**文件**: `backend/routers/field_mapping_dictionary.py`

**修复内容**:
1. ✅ 支持`header_columns`参数（DSS架构）
2. ✅ 兼容旧格式（从`mappings`提取`header_columns`）

---

## 🧪 测试步骤

### 测试1: 数据入库

1. 选择文件并预览数据
2. 点击"确认并入库"按钮
3. **预期结果**: 
   - ✅ 数据成功入库
   - ✅ 显示成功消息
   - ✅ 数据写入到`fact_raw_data_{domain}_{granularity}`表（JSONB格式）

### 测试2: 模板保存

1. 选择文件并预览数据
2. 点击"保存为模板"按钮
3. 输入模板名称
4. **预期结果**:
   - ✅ 显示成功消息
   - ✅ 模板保存到数据库
   - ✅ 下次同类文件可以自动应用模板

---

## 📋 验证清单

- [ ] 数据入库功能正常
- [ ] 模板保存功能正常
- [ ] 数据以JSONB格式存储
- [ ] 中文字段名正确保存
- [ ] 模板可以自动应用

---

## ⚠️ 注意事项

1. **后端服务**: 确保后端服务正在运行（端口8001）
2. **数据库**: 确保PostgreSQL服务正常运行
3. **表结构**: 确保`fact_raw_data_*`表已创建（Alembic迁移）

---

**状态**: ✅ **代码修复完成，待测试验证**

