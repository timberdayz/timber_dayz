# 字段映射验证指南

**版本**: v4.12.0  
**创建时间**: 2025-11-20  
**状态**: ✅ 已完成

---

## 📋 概述

字段映射验证工具用于验证字段映射是否符合数据库设计规范。

---

## 🎯 验证规则

### 1. FieldMappingDictionary表结构验证

**规则**:
- FieldMappingDictionary表必须存在
- 必需字段：`field_code`, `cn_name`, `data_domain`

**验证点**:
- 表是否存在
- 必需字段是否存在

---

### 2. 标准字段定义完整性验证

**规则**:
- 标准字段应覆盖所有数据域
- 预期数据域：products, orders, inventory, traffic, services, finance

**验证点**:
- 是否有标准字段定义
- 是否覆盖所有数据域

---

### 3. Pattern-based Mapping规则验证

**规则**:
- Pattern字段必须配置`field_pattern`正则表达式
- Pattern字段必须配置`target_table`目标表
- Pattern字段必须配置`dimension_config`维度提取配置

**验证点**:
- field_pattern是否为空
- target_table是否为空
- dimension_config是否正确

---

### 4. 字段映射模板验证

**规则**:
- FieldMappingTemplate表必须存在
- FieldMappingTemplateItem表必须存在

**验证点**:
- 表是否存在
- 表结构是否正确

---

## 🔧 使用方法

### 1. Python脚本

```python
from backend.models.database import get_db
from backend.services.field_mapping_validator import validate_field_mapping

db = next(get_db())
result = validate_field_mapping(db)

print(f"有效性: {result.is_valid}")
print(f"总问题数: {len(result.issues)}")
for issue in result.issues:
    print(f"  [{issue.severity}] {issue.category}: {issue.issue}")
```

### 2. API端点

**端点**: `GET /api/database-design/validate/field-mapping`

**响应格式**:
```json
{
    "success": true,
    "is_valid": true,
    "summary": {
        "total_issues": 1,
        "error_count": 0,
        "warning_count": 0,
        "info_count": 1,
        "category_counts": {
            "dictionary": 1
        }
    },
    "issues": [
        {
            "severity": "info",
            "category": "dictionary",
            "issue": "缺少数据域的标准字段定义: finance",
            "suggestion": "应在FieldMappingDictionary表中添加finance数据域的标准字段",
            "field_name": null,
            "code_location": "backend/services/field_mapping_validator.py"
        }
    ]
}
```

### 3. 测试脚本

```bash
python scripts/test_field_mapping_validator.py
```

---

## 📊 验证结果

### 问题级别

- **error**: 严重问题，必须修复
- **warning**: 警告问题，建议修复
- **info**: 信息提示，可选修复

### 问题分类

- **dictionary**: FieldMappingDictionary表相关问题
- **mapping**: 字段映射相关问题
- **pattern**: Pattern-based mapping相关问题
- **template**: 字段映射模板相关问题
- **fact_table**: 事实表结构相关问题

---

## ✅ 验证通过标准

- **error_count = 0**: 无严重问题
- **warning_count ≤ 5**: 警告问题不超过5个
- **FieldMappingDictionary表存在**: 表结构完整
- **标准字段覆盖主要数据域**: products, orders, inventory, traffic, services

---

## 🔍 常见问题

### 1. FieldMappingDictionary表不存在

**问题**: `FieldMappingDictionary表不存在`

**解决方案**:
1. 检查`modules/core/db/schema.py`中是否定义了`FieldMappingDictionary`类
2. 运行Alembic迁移创建表

### 2. 缺少数据域的标准字段定义

**问题**: `缺少数据域的标准字段定义: finance`

**解决方案**:
1. 在FieldMappingDictionary表中添加finance数据域的标准字段
2. 确保字段覆盖所有业务需求

### 3. Pattern字段缺少配置

**问题**: `Pattern字段{field_code}缺少field_pattern配置`

**解决方案**:
1. 为Pattern字段配置field_pattern正则表达式
2. 配置target_table目标表
3. 配置dimension_config维度提取配置

---

## 📝 相关文档

- [数据库设计规范验证指南](VALIDATION_TEST_RESULTS.md)
- [数据入库流程验证指南](DATA_INGESTION_VALIDATION_GUIDE.md)
- [数据库设计检查清单](DEVELOPMENT_RULES/DATABASE_DESIGN_CHECKLIST.md)
- [字段映射规范](openspec/changes/establish-database-design-rules/specs/database-design/spec.md)

---

**最后更新**: 2025-11-20  
**维护**: AI Agent Team  
**状态**: ✅ 已完成

