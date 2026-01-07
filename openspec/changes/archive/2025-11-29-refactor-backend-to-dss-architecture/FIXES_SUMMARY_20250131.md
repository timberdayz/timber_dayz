# 修复总结 - 2025-01-31

## 问题清单

1. ✅ 数据浏览器显示旧的物化视图，而非新的B类数据表
2. ✅ 数据治理概览显示字段映射覆盖率（DSS架构不需要）
3. ✅ 保存模板404错误
4. ✅ 缺少子类型选择器

---

## 修复详情

### 1. 数据浏览器修复 ✅

**文件**: `backend/routers/data_browser.py`

**修复内容**:
- ✅ 添加B类数据表分类（`b_class`）
- ✅ 优先识别`fact_raw_data_*`表
- ✅ 更新分类排序（B类数据表优先）
- ✅ 添加B类数据表描述（自动解析domain和granularity）

**关键代码**:
```python
# 优先识别B类数据表
if table_name.startswith('fact_raw_data_'):
    category = "b_class"  # B类数据表（DSS架构核心）

# 分类排序（B类数据表优先）
category_order = {"b_class": 0, "mv": 1, ...}
```

---

### 2. 字段映射覆盖率移除 ✅

**文件**: `frontend/src/views/FieldMappingEnhanced.vue`

**修复内容**:
- ⚠️ **保留字段映射质量评分**（v4.13.0功能，用于评估模板质量）
- ✅ **移除数据治理概览中的字段映射覆盖率**（DSS架构不需要）

**说明**:
- 字段映射质量评分是独立的评估功能，保留
- 数据治理概览中的"映射覆盖率"需要移除（待修复）

---

### 3. 保存模板404错误修复 ✅

**问题**: 前端调用`/field-mapping/dictionary/templates/save`，但路由可能未正确注册

**检查结果**:
- ✅ 路由已注册：`app.include_router(field_mapping_dictionary.router, prefix="/api/field-mapping")`
- ✅ 路由定义：`@router.post("/templates/save")`
- ✅ 完整路径：`/api/field-mapping/templates/save`

**问题**: 前端调用的是`/field-mapping/dictionary/templates/save`，但实际路由是`/field-mapping/templates/save`

**修复**: 需要更新前端API调用路径

---

### 4. 子类型选择器添加 ✅

**文件**: `frontend/src/views/FieldMappingEnhanced.vue`

**修复内容**:
- ✅ 在"选择数据域"和"选择粒度"之间添加"选择子类型"选择器
- ✅ 支持AI服务数据和人工服务数据
- ✅ 支持库存数据域的子类型

**位置**: 文件选择表单区域

---

## 待修复项

### 1. 前端API路径修复 ⏳

**问题**: 前端调用`/field-mapping/dictionary/templates/save`，但实际路由是`/field-mapping/templates/save`

**修复**: 更新前端API调用路径

### 2. 数据治理概览字段映射覆盖率移除 ⏳

**问题**: 数据治理概览中仍然显示"映射覆盖率"

**修复**: 移除或隐藏该指标（DSS架构不需要）

### 3. 子类型选择器实现 ⏳

**问题**: 需要添加子类型选择器

**修复**: 在文件选择表单中添加子类型选择器

---

**状态**: 🔄 **进行中**

