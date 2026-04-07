# 物化视图字段验证文档

**版本**: v4.6.0+  
**创建日期**: 2025-01-31

---

## 概述

本文档说明如何使用物化视图字段验证功能，确保视图查询的字段存在性和一致性。

---

## 功能说明

### 1. 视图字段列表查询

获取物化视图的所有字段：

```python
from backend.services.materialized_view_service import MaterializedViewService
from backend.models.database import SessionLocal

db = SessionLocal()
columns = MaterializedViewService.get_view_columns(db, "mv_inventory_by_sku")
print(f"视图字段: {columns}")
```

### 2. 查询字段验证

在执行查询前验证字段是否存在：

```python
# 验证SELECT字段
validation_result = MaterializedViewService.validate_query_fields(
    db,
    view_name="mv_inventory_by_sku",
    select_fields=["metric_date", "platform_code", "platform_sku"],
    order_by_fields=["metric_date DESC"]
)

if not validation_result["valid"]:
    print(f"字段验证失败: {validation_result['error']}")
    print(f"缺失字段: {validation_result['missing_fields']}")
    print(f"可用字段: {validation_result['available_fields']}")
```

### 3. 视图定义验证

验证视图是否包含必需字段（如metric_date）：

```python
definition_result = MaterializedViewService.validate_view_definition(
    db,
    view_name="mv_inventory_by_sku"
)

if definition_result["valid"]:
    print(f"视图定义验证通过，包含 {len(definition_result['columns'])} 个字段")
    print(f"包含metric_date字段: {definition_result['has_metric_date']}")
else:
    print(f"视图定义验证失败: {definition_result['error']}")
```

---

## 使用脚本

### 刷新物化视图

```bash
# 刷新所有视图
python scripts/refresh_materialized_views.py

# 刷新指定视图
python scripts/refresh_materialized_views.py mv_inventory_by_sku
```

### 测试视图字段

```bash
# 测试所有视图
python scripts/test_materialized_view_fields.py

# 测试指定视图
python scripts/test_materialized_view_fields.py mv_inventory_by_sku
```

---

## CI/CD集成

### GitHub Actions

已创建 `.github/workflows/validate_data_flow.yml`，包含：

1. **API契约验证**: 验证API响应格式
2. **前端API方法验证**: 验证前端API调用
3. **数据库字段验证**: 验证数据库字段定义
4. **物化视图验证**: 验证物化视图字段

### Git Hooks

已创建 `.git/hooks/pre-commit.template`，包含：

1. API契约验证
2. 前端API方法验证
3. 代码审查检查清单生成

**使用方法**:
```bash
cp .git/hooks/pre-commit.template .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

---

## 验证结果格式

### validate_query_fields返回格式

```json
{
    "valid": true,
    "missing_fields": [],
    "available_fields": ["metric_date", "platform_code", "shop_id", "platform_sku", ...],
    "error": null
}
```

### validate_view_definition返回格式

```json
{
    "valid": true,
    "has_metric_date": true,
    "columns": ["metric_date", "platform_code", "shop_id", "platform_sku", ...],
    "error": null
}
```

---

## 最佳实践

1. **查询前验证**: 在执行复杂查询前，先验证字段存在性
2. **错误处理**: 如果字段验证失败，返回清晰的错误消息
3. **定期检查**: 使用测试脚本定期检查所有视图的字段定义
4. **CI/CD集成**: 在CI/CD流程中自动验证视图字段

---

## 相关文档

- [API契约标准](API_CONTRACTS.md)
- [代码审查检查清单](CODE_REVIEW_CHECKLIST.md)
- [物化视图开发规范](../docs/AGENT_START_HERE.md#物化视图开发规范)

