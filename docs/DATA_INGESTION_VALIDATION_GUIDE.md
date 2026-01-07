# 数据入库流程验证指南

**版本**: v4.12.0  
**创建时间**: 2025-11-20  
**状态**: ✅ 已完成

---

## 📋 概述

数据入库流程验证工具用于验证数据入库流程是否符合数据库设计规范。

---

## 🎯 验证规则

### 1. shop_id获取规则

**规则**:
1. 优先从源数据获取shop_id
2. 使用AccountAlias映射非标准店铺名称
3. 从文件元数据获取shop_id
4. 默认值处理

**验证点**:
- AccountAlias表是否存在
- AccountAlias表结构是否正确
- 数据入库代码是否正确使用AccountAlias

---

### 2. platform_code获取规则

**规则**:
1. 从文件元数据获取platform_code
2. 验证平台代码有效性

**验证点**:
- DimPlatform表是否存在
- 平台代码是否在DimPlatform表中

---

### 3. AccountAlias映射规则

**规则**:
- AccountAlias表必须包含以下字段：
  - `platform`: 平台代码（如'miaoshou'）
  - `data_domain`: 数据域（如'orders'）
  - `store_label_raw`: 原始店铺名（如"菲律宾1店"）
  - `target_id`: 标准店铺ID（如"shopee_ph_1"）

**验证点**:
- AccountAlias表结构完整性
- 必需字段是否存在

---

## 🔧 使用方法

### 1. Python脚本

```python
from backend.models.database import get_db
from backend.services.data_ingestion_validator import validate_data_ingestion_process

db = next(get_db())
result = validate_data_ingestion_process(db)

print(f"有效性: {result.is_valid}")
print(f"总问题数: {len(result.issues)}")
for issue in result.issues:
    print(f"  [{issue.severity}] {issue.category}: {issue.issue}")
```

### 2. API端点

**端点**: `GET /api/database-design/validate/data-ingestion`

**响应格式**:
```json
{
    "success": true,
    "is_valid": true,
    "summary": {
        "total_issues": 0,
        "error_count": 0,
        "warning_count": 0,
        "info_count": 0,
        "category_counts": {}
    },
    "issues": []
}
```

### 3. 测试脚本

```bash
python scripts/test_data_ingestion_validator.py
```

---

## 📊 验证结果

### 问题级别

- **error**: 严重问题，必须修复
- **warning**: 警告问题，建议修复
- **info**: 信息提示，可选修复

### 问题分类

- **shop_id**: shop_id获取相关问题
- **platform_code**: platform_code获取相关问题
- **field_mapping**: 字段映射相关问题
- **validation**: 数据验证相关问题
- **account_alias**: AccountAlias映射相关问题

---

## ✅ 验证通过标准

- **error_count = 0**: 无严重问题
- **warning_count ≤ 5**: 警告问题不超过5个
- **所有必需表存在**: AccountAlias表、DimPlatform表等

---

## 🔍 常见问题

### 1. AccountAlias表不存在

**问题**: `AccountAlias表不存在`

**解决方案**:
1. 检查`modules/core/db/schema.py`中是否定义了`AccountAlias`类
2. 运行Alembic迁移创建表

### 2. AccountAlias表缺少必需字段

**问题**: `AccountAlias表缺少必需字段: platform`

**解决方案**:
1. 检查`AccountAlias`类定义
2. 确保包含所有必需字段：`platform`, `data_domain`, `store_label_raw`, `target_id`
3. 运行Alembic迁移更新表结构

### 3. DimPlatform表不存在

**问题**: `DimPlatform表不存在`

**解决方案**:
1. 检查`modules/core/db/schema.py`中是否定义了`DimPlatform`类
2. 运行Alembic迁移创建表

---

## 📝 相关文档

- [数据库设计规范验证指南](VALIDATION_TEST_RESULTS.md)
- [数据库设计检查清单](DEVELOPMENT_RULES/DATABASE_DESIGN_CHECKLIST.md)
- [数据入库流程规范](openspec/changes/establish-database-design-rules/specs/database-design/spec.md)

---

**最后更新**: 2025-11-20  
**维护**: AI Agent Team  
**状态**: ✅ 已完成

