# 手动入库 vs 自动同步数据差异问题分析

**发现时间**: 2025-11-08  
**问题严重性**: 🔴 高（影响数据完整性）

---

## 🔍 问题描述

用户发现：
- **手动入库**：miaoshou平台产品数据域文件，可以看到1094个产品的详细信息
- **自动同步**：同样的文件，数据量明显减少

---

## 📊 诊断结果

### 数据库状态检查

```
miaoshou products文件状态：
- pending: 4个文件
- ingested: 1个文件（手动入库）

已入库的数据量：
- fact_product_metrics: 1094行
- dim_products: 0行

手动入库的文件：
- miaoshou_products_snapshot_20250926_183503.xlsx: ingested
  (处理时间: 2025-11-08 19:19:04)
```

---

## 🔴 根本原因

### 问题1：自动同步调用ingest API参数不完整

**手动入库**（前端调用）：
```javascript
{
  fileId: selectedFile.value,
  platform: selectedPlatform.value,
  domain: selectedDomain.value,
  mappings: mappingsObj,
  rows: previewData.value,
  header_row: headerRow.value || 0
}
```

**自动同步**（修复前）：
```python
{
  'file_id': file_id,
  'field_mapping': field_mapping  # ❌ 参数名错误，且缺少其他参数
}
```

**问题**：
1. ❌ 参数名错误：`field_mapping` → 应该是 `mappings`
2. ❌ 缺少 `platform` 参数
3. ❌ 缺少 `domain` 参数
4. ❌ 缺少 `header_row` 参数

**影响**：
- ingest API虽然会从文件记录中获取platform和domain，但可能不准确
- header_row未传递，可能导致表头行识别错误
- 参数名错误可能导致映射数据无法正确应用

---

## ✅ 修复方案

### 修复代码

```python
# backend/services/auto_ingest_orchestrator.py

# 修复前：
json={
    'file_id': file_id,
    'field_mapping': field_mapping
}

# 修复后：
json={
    'file_id': file_id,
    'platform': catalog_file.platform_code or catalog_file.source_platform or '',
    'domain': catalog_file.data_domain or '',
    'mappings': field_mapping,  # ✅ 使用正确的参数名
    'header_row': header_row  # ✅ 传递header_row参数
}
```

---

## 🎯 修复效果

### 修复前
- 自动同步可能因为参数不完整导致：
  - 字段映射无法正确应用
  - 表头行识别错误
  - 数据域识别不准确
  - 入库数据量减少

### 修复后
- 自动同步与手动入库使用完全相同的参数
- 确保字段映射正确应用
- 确保表头行正确识别
- 确保数据域正确识别
- 入库数据量一致

---

## 📝 验证步骤

1. **清理数据库**
   ```bash
   # 点击"清理数据库"按钮
   ```

2. **手动入库测试**
   - 选择miaoshou平台产品文件
   - 手动入库
   - 记录入库数据量

3. **自动同步测试**
   - 清理数据库
   - 点击"全部平台"数据同步
   - 检查入库数据量
   - 对比手动入库结果

4. **验证数据一致性**
   ```sql
   -- 检查fact_product_metrics数据量
   SELECT COUNT(*) FROM fact_product_metrics WHERE platform_code='miaoshou';
   
   -- 检查dim_products数据量
   SELECT COUNT(*) FROM dim_products WHERE platform_code='miaoshou';
   ```

---

## 🔧 其他潜在问题

### 问题2：自动同步只处理pending状态的文件

**当前逻辑**：
```python
stmt = select(CatalogFile).where(CatalogFile.status == 'pending')
```

**影响**：
- 如果文件已经被手动入库（status='ingested'），自动同步会跳过
- 这是**正常行为**，因为文件已经入库，不需要重复处理

**建议**：
- ✅ 保持当前逻辑（避免重复入库）
- ✅ 如果需要重新入库，先清理数据库或重置文件状态

### 问题3：模板匹配可能失败

**当前逻辑**：
- 如果找不到模板，文件会被跳过（`skipped_no_template`）
- 如果模板匹配失败，文件会被跳过（`skipped`，`no_mapping`）

**影响**：
- 如果模板配置不正确，文件会被跳过
- 需要检查模板配置和匹配逻辑

**建议**：
- ✅ 检查模板覆盖度（`scripts/generate_template_checklist.py`）
- ✅ 检查模板质量（`scripts/verify_template_quality.py`）
- ✅ 优化模板匹配算法（提高匹配准确性）

---

## 📚 相关文档

- [核心流程图](docs/CORE_PROCESS_FLOW_DIAGRAM.md)
- [批量同步详细流程](docs/BATCH_SYNC_DETAILED_FLOW.md)
- [字段映射系统指南](docs/FIELD_MAPPING_COMPLETE_SUMMARY_20251105.md)

---

**修复状态**: ✅ 已修复  
**修复时间**: 2025-11-08  
**修复文件**: `backend/services/auto_ingest_orchestrator.py`

