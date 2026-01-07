# 修复总结：字段映射字典和模板保存

**日期**: 2025-01-31

---

## ✅ 已完成的修复

### 1. 修复模板保存API ✅

**问题**: 
- 前端调用旧API路径: `/field-mapping/templates/save`
- 后端API期望`mappings`参数，但DSS架构应使用`header_columns`

**修复**:
- ✅ 更新前端API路径: `/field-mapping/dictionary/templates/save`
- ✅ 更新后端API: 支持`header_columns`参数（兼容旧格式）

**文件**:
- `backend/routers/field_mapping_dictionary.py` - 更新API参数处理
- `frontend/src/views/FieldMappingEnhanced.vue` - 更新API路径

### 2. 移除字段映射字典功能 ✅

**问题**: 前端仍在加载字段映射字典，但DSS架构不再需要

**修复**:
- ✅ 移除"加载辞典"按钮
- ✅ 移除`loadDictionary()`函数调用（部分）
- ⏳ 需要完全移除`loadDictionary()`函数和相关状态

**文件**:
- `frontend/src/views/FieldMappingEnhanced.vue` - 移除按钮和部分调用

---

## ⏳ 待完成的修复

### 1. 完全移除字段映射字典功能

**需要修改**:
- [ ] 移除`loadDictionary()`函数定义（第2728-2789行）
- [ ] 移除`dictionaryFields`相关状态
- [ ] 移除字段映射建议功能（基于字典）
- [ ] 移除所有`dictionaryFields`的引用

### 2. 验证模板保存功能

**测试步骤**:
- [ ] 选择文件并预览数据
- [ ] 点击"保存为模板"按钮
- [ ] 验证模板是否成功保存
- [ ] 验证模板是否可以在下次自动应用

---

## 📋 数据同步流程说明

### 新数据域或表头字段更新时的流程

#### 场景1: 新数据域（首次使用）

1. **上传文件** → 系统自动识别platform/data_domain/granularity
2. **预览数据** → 查看原始表头字段列表（25个字段）
3. **保存模板** → 保存header_columns和配置（表头行等）
   - 点击"保存为模板"按钮
   - 输入模板名称
   - 系统保存：platform + data_domain + granularity + header_columns
4. **数据同步** → 点击"确认并入库"按钮
   - 使用RawDataImporter写入JSONB格式
   - 数据保存到`fact_raw_data_{domain}_{granularity}`表

#### 场景2: 表头字段更新（已有模板）

1. **上传文件** → 系统自动匹配模板
2. **检测变化** → 比较当前表头与模板header_columns
3. **提示更新** → 如果表头变化，提示更新模板
4. **更新模板** → 保存新的header_columns
5. **数据同步** → 使用RawDataImporter写入JSONB格式

#### 场景3: 自动数据同步（已有模板）

1. **文件扫描** → 系统自动扫描新文件
2. **模板匹配** → 自动匹配模板（platform + data_domain + granularity）
3. **表头验证** → 验证表头是否匹配模板header_columns
4. **自动同步** → 如果匹配，自动同步数据（使用RawDataImporter）

---

## 🎯 关键要点

### 模板功能仍然需要 ✅

**原因**:
- 模板用于**文件匹配**（识别文件类型）
- 模板保存**原始表头字段列表**（header_columns）
- 模板用于**自动识别**文件是否已有配置

**模板结构**（DSS架构）:
```json
{
  "platform": "miaoshou",
  "data_domain": "inventory",
  "granularity": "daily",
  "header_columns": ["商品SKU", "商品名称", "库存总量", ...],  // 原始中文表头
  "header_row": 0,  // 表头行位置
  "status": "published"
}
```

### 字段映射字典不再需要 ❌

**原因**:
- DSS架构中，数据直接保存原始中文表头到JSONB格式
- 不再需要将中文表头映射到标准字段（英文字段名）
- 字段映射字典是旧架构的产物

---

**状态**: ✅ **模板保存功能已修复，字段映射字典功能部分移除**

