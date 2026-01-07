# 运营数据验证函数实现文档

## 概述

本文档描述了运营数据（traffic、services、analytics）的验证函数实现，这些函数遵循数据库设计规范中的运营数据验证规则。

## 实现日期

2025-01-31

## 验证函数

### 1. validate_traffic

**功能**: 验证流量数据

**位置**: `backend/services/data_validator.py`

**核心原则**:
- 只验证数据归属字段（shop_id、account、date）
- 只要有归属的数据就不隔离（即使缺少其他字段）
- 隔离区只针对真正有问题的数据（无归属、日期错误等）

**特点**:
- 不需要product_id或SKU（店铺级数据）
- 只要有shop_id和date就可以入库
- 支持平台级数据（shop_id可以为NULL）

**验证逻辑**:
1. 调用`_validate_core_ownership_fields`验证核心归属字段
2. 日期合理性检查（只警告，不隔离）
3. 不验证运营指标字段（有归属即可入库）

### 2. validate_analytics

**功能**: 验证分析数据

**位置**: `backend/services/data_validator.py`

**核心原则**: 与`validate_traffic`相同

**特点**: 与`validate_traffic`相同

**验证逻辑**: 与`validate_traffic`相同

### 3. validate_services

**功能**: 验证服务数据

**位置**: `backend/services/data_validator.py`

**实现状态**: 已存在（v4.6.1）

**核心原则**: 与`validate_traffic`相同

## 集成

### data_ingestion_service.py

在`data_ingestion_service.py`中，已更新验证逻辑：

```python
elif domain == "traffic":
    # ⭐ v4.12.0新增：流量数据验证
    validation_result = validate_traffic(enhanced_rows)
elif domain == "analytics":
    # ⭐ v4.12.0新增：分析数据验证
    validation_result = validate_analytics(enhanced_rows)
```

### 导入语句

```python
from backend.services.data_validator import (
    validate_orders,
    validate_product_metrics,
    validate_services,
    validate_traffic,
    validate_analytics,
)
```

## 设计规范符合性

### 符合的规范

1. **数据归属规则**: 验证核心归属字段（shop_id、account、date）
2. **字段必填规则**: 只验证核心归属字段，其他字段可选
3. **数据隔离规则**: 只隔离真正有问题的数据（无归属、日期错误等）

### 验证策略

- **核心归属字段**: 必须验证（shop_id、account、date）
- **业务字段**: 可选验证（只警告，不隔离）
- **数值字段**: 可选验证（只警告，不隔离）

## 测试

### 导入测试

```python
from backend.services.data_validator import validate_traffic, validate_analytics
# Import successful
```

### 使用示例

```python
rows = [
    {
        "platform_code": "shopee",
        "shop_id": "HXHOME",
        "metric_date": "2025-01-31",
        "metric_type": "uv",
        "metric_value": 1000.0
    }
]

result = validate_traffic(rows)
# result = {"errors": [], "warnings": [], "ok_rows": 1, "total": 1}
```

## 后续改进

1. **AccountAlias映射**: 在`operational_data_importer.py`中集成AccountAlias映射逻辑（当前有TODO注释）
2. **特殊验证规则**: 根据业务需求添加特定验证规则（如metric_value范围检查）

## 相关文档

- [运营数据表设计文档](OPERATIONAL_DATA_TABLES_DESIGN.md)
- [运营数据导入实现文档](OPERATIONAL_DATA_IMPORT_IMPLEMENTATION.md)
- [数据库设计规范](../openspec/changes/establish-database-design-rules/specs/database-design/spec.md)

