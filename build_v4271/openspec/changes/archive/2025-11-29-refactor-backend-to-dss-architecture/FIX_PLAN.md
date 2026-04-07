# 修复计划：字段映射字典和模板保存

**日期**: 2025-01-31

---

## 🔍 问题分析

### 问题1: 字段映射字典不再需要

**现状**: 前端仍在加载字段映射字典（"加载辞典"按钮）

**原因**: DSS架构中不再需要字段映射字典（不再映射到标准字段）

**需要修改**:
1. 移除"加载辞典"按钮
2. 移除`loadDictionary()`函数调用
3. 移除字段映射建议功能

### 问题2: 保存模板失败

**现状**: 点击"保存为模板"按钮失败

**原因分析**:
1. **API路径不匹配**: 
   - 前端调用: `/field-mapping/save-template`（旧API，已废弃）
   - 后端新API: `/field-mapping/dictionary/templates/save`
2. **参数不匹配**:
   - 前端发送: `mappings`（旧参数）
   - 后端需要: `header_columns`（DSS架构新参数）

**需要修改**:
1. 更新前端API调用路径
2. 更新前端请求参数（使用header_columns而非mappings）

---

## 🔧 修复方案

### 修复1: 移除字段映射字典功能

**文件**: `frontend/src/views/FieldMappingEnhanced.vue`

**修改内容**:
1. 移除"加载辞典"按钮（第82-86行）
2. 移除`loadDictionary()`函数（第2728-2789行）
3. 移除`handleDomainChange()`中的自动加载辞典调用（第2808行）
4. 移除`dictionaryFields`相关状态和UI

### 修复2: 修复模板保存功能

**文件**: `frontend/src/views/FieldMappingEnhanced.vue`

**修改内容**:
1. 更新`handleSaveTemplate()`函数（第3582行）
   - 使用正确的API路径: `/field-mapping/dictionary/templates/save`
   - 使用正确的参数: `header_columns`而非`mappings`

**文件**: `frontend/src/api/index.js`

**修改内容**:
1. 更新`saveTemplate()`方法（第236行）
   - 使用正确的API路径
   - 使用正确的参数格式

---

## 📝 详细修改

### 修改1: 移除字段映射字典

```vue
<!-- 移除按钮 -->
<!-- <el-button @click="loadDictionary">加载辞典</el-button> -->

<!-- 移除函数调用 -->
// const loadDictionary = async () => { ... }  // 删除

// 移除自动加载
// await loadDictionary()  // 删除
```

### 修改2: 修复模板保存

```javascript
// 前端API调用
const response = await api._post('/field-mapping/dictionary/templates/save', {
  platform: selectedPlatform.value,
  data_domain: selectedDomain.value,
  granularity: fileInfo.value.granularity || selectedGranularity.value,
  header_columns: previewColumns.value,  // ✅ 使用header_columns
  template_name: value,
  created_by: 'web_ui',
  header_row: headerRow.value || 0,
  sub_domain: subDomain,
  sheet_name: fileInfo.value.sheet_name || null
  // ❌ 不再发送mappings参数
})
```

---

## ✅ 验证清单

- [ ] 移除"加载辞典"按钮
- [ ] 移除字段映射字典相关代码
- [ ] 修复模板保存API路径
- [ ] 修复模板保存参数格式
- [ ] 测试模板保存功能
- [ ] 测试数据同步功能

---

**状态**: ⏳ **准备开始修复**

