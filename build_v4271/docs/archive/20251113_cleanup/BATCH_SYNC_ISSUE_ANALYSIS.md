# 🔍 数据同步问题分析报告

## 📊 问题现象

1. **前端显示**：待入库文件121个
2. **实际查询**：tiktok平台待入库文件0个（所有文件已处理）
3. **批量同步结果**：只处理了1个文件
4. **日志显示**：同一个文件被处理了多次，前几次模板匹配失败（0/38字段匹配）

## 🔍 根本原因分析

### 1. 文件筛选条件问题 ⭐

**问题**：批量同步时，如果用户选择了"当前选择 (tiktok/analytics/weekly)"，筛选条件过于严格：

```python
# backend/services/auto_ingest_orchestrator.py:392-395
if domains:
    stmt = stmt.where(CatalogFile.data_domain.in_(domains))  # ['analytics']
if granularities:
    stmt = stmt.where(CatalogFile.granularity.in_(granularities))  # ['weekly']
```

**结果**：只查询到1个符合条件的文件（`data_domain='analytics'` AND `granularity='weekly'` AND `status='pending'`）

### 2. 文件状态不一致问题 ⭐

**问题**：
- 前端统计的"待入库文件"可能包括所有平台的文件（283个）
- 但批量同步只查询tiktok平台的文件（0个）
- 说明tiktok平台的文件都已经被处理了

**可能原因**：
- 文件在处理过程中状态被更新（从pending变成ingested）
- 或者文件筛选条件不一致（前端使用`platform_code`，后端使用`platform_code`或`source_platform`）

### 3. 模板匹配失败问题 ⭐

**问题**：从日志可以看到，同一个文件被处理了多次：
- 前几次：模板匹配失败（0/38字段匹配）
- 最后一次：自动检测到表头行2，匹配成功（38/38字段匹配）

**原因**：
- 模板的`header_row`可能设置为0，但实际文件表头在第2行
- 自动检测表头行功能在多次尝试后才成功

### 4. 前端统计逻辑问题 ⭐

**问题**：前端显示的"待入库文件：121个"与实际查询结果不一致

**可能原因**：
- 前端统计的是所有平台的文件，而不是当前选择的平台
- 或者前端统计逻辑使用了不同的筛选条件

## ✅ 解决方案

### 1. 修复文件筛选逻辑

**问题**：`get_overview`方法只使用`platform_code`筛选，没有考虑`source_platform`

**修复**：
```python
# backend/services/governance_stats.py:50-51
if platform:
    stmt = stmt.where(
        or_(
            func.lower(CatalogFile.platform_code) == platform.lower(),
            func.lower(CatalogFile.source_platform) == platform.lower()
        )
    )
```

### 2. 优化批量同步筛选逻辑

**问题**：筛选条件过于严格，导致只查询到1个文件

**建议**：
- 如果用户选择了"当前选择"，应该放宽筛选条件
- 或者提示用户当前筛选条件下没有符合条件的文件

### 3. 改进模板匹配逻辑

**问题**：模板匹配失败，需要多次尝试才能成功

**建议**：
- 优化表头行自动检测逻辑
- 提高模板匹配的容错性
- 记录模板匹配失败的详细原因

### 4. 统一前端统计逻辑

**问题**：前端统计的"待入库文件"与实际查询结果不一致

**建议**：
- 确保前端统计使用与后端相同的筛选条件
- 或者明确显示统计范围（当前平台 vs 所有平台）

## 📋 修复步骤

1. ✅ 修复`get_overview`方法，使用`platform_code`或`source_platform`筛选
2. ✅ 优化批量同步筛选逻辑，提供更友好的错误提示
3. ✅ 改进模板匹配逻辑，提高匹配成功率
4. ✅ 统一前端统计逻辑，确保数据一致性

---

**版本**: v4.10.0  
**更新时间**: 2025-11-09  
**状态**: 🔧 待修复

