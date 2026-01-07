# 代码审查检查清单

**版本**: v4.12.0  
**创建时间**: 2025-11-20  
**状态**: ✅ 已完成

---

## 📋 概述

本文档定义代码审查时检查数据库设计规则的要求，确保新代码符合数据库设计规范。

---

## 🔍 代码审查检查清单

### 1. 数据库模型定义审查

#### 1.1 主键设计审查

**检查项**:
- [ ] 运营数据表是否使用业务标识作为主键（如platform_code, shop_id, order_id, platform_sku）？
- [ ] 业务数据表是否使用自增ID作为主键，业务唯一性通过唯一索引保证？
- [ ] 主键字段是否不允许NULL（除非明确允许，如inventory域的shop_id）？
- [ ] 复合主键是否包含所有必要的业务维度？

**正确示例**:
```python
# ✅ 运营数据：使用业务标识作为主键
class FactOrder(Base):
    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    order_id = Column(String(128), primary_key=True)

# ✅ 业务数据：使用自增ID+唯一索引
class FactProductMetric(Base):
    id = Column(Integer, primary_key=True, autoincrement=True)
    __table_args__ = (
        Index("ix_product_unique", "platform_code", "shop_id", "platform_sku", 
              "metric_date", "granularity", "data_domain", unique=True),
    )
```

**错误示例**:
```python
# ❌ 运营数据不应使用自增ID作为主键
class FactOrder(Base):
    id = Column(Integer, primary_key=True, autoincrement=True)  # ❌ 错误
```

---

#### 1.2 字段NULL规则审查

**检查项**:
- [ ] 关键业务字段（如quantity, unit_price, total_amount）是否不允许NULL，使用默认值？
- [ ] 可选字段是否允许NULL，但提供默认值？
- [ ] 主键字段是否不允许NULL？

**正确示例**:
```python
# ✅ 关键业务字段不允许NULL，使用默认值
quantity = Column(Integer, default=1, nullable=False)
unit_price = Column(Float, default=0.0, nullable=False)
total_amount = Column(Float, default=0.0, nullable=False)
```

**错误示例**:
```python
# ❌ 关键业务字段不应允许NULL
quantity = Column(Integer, nullable=True)  # ❌ 错误
total_amount = Column(Float, nullable=True)  # ❌ 错误
```

---

#### 1.3 唯一索引审查

**检查项**:
- [ ] 使用自增ID作为主键的表是否有业务唯一索引？
- [ ] 业务唯一索引是否包含所有必要的业务维度？
- [ ] 唯一索引字段是否不允许NULL（除非明确允许）？

**正确示例**:
```python
# ✅ 业务唯一索引包含所有业务维度
__table_args__ = (
    Index("ix_product_unique", "platform_code", "shop_id", "platform_sku", 
          "metric_date", "granularity", "data_domain", unique=True),
)
```

---

### 2. 数据入库流程审查

#### 2.1 shop_id获取规则审查

**检查项**:
- [ ] 是否优先从源数据获取shop_id？
- [ ] 是否使用AccountAlias映射非标准店铺名称？
- [ ] 是否从文件元数据获取shop_id？
- [ ] 是否正确处理默认值（允许NULL或使用默认值）？

**正确示例**:
```python
# ✅ 遵循shop_id获取优先级
def get_shop_id(row, file_record, account_alignment_service):
    # 1. 优先从源数据获取
    if row.get("shop_id"):
        return row["shop_id"]
    
    # 2. 使用AccountAlias映射
    if row.get("store_label_raw"):
        aligned_id = account_alignment_service.align_account(...)
        if aligned_id:
            return aligned_id
    
    # 3. 从文件元数据获取
    if file_record and file_record.shop_id:
        return file_record.shop_id
    
    # 4. 默认值处理
    return None  # 允许NULL（inventory域）
```

**错误示例**:
```python
# ❌ 硬编码shop_id
def get_shop_id(row, file_record):
    return "shopee_sg_1"  # ❌ 错误
```

---

#### 2.2 platform_code获取规则审查

**检查项**:
- [ ] 是否从文件元数据获取platform_code？
- [ ] 是否验证平台代码有效性（检查DimPlatform表）？
- [ ] 是否使用默认值"unknown"（如果无法获取）？

**正确示例**:
```python
# ✅ 从文件元数据获取platform_code
if file_record and file_record.platform_code:
    platform_code = file_record.platform_code
else:
    platform_code = "unknown"  # 默认值
```

---

#### 2.3 AccountAlias映射规则审查

**检查项**:
- [ ] 是否使用AccountAlias服务映射非标准店铺名称？
- [ ] 是否正确处理映射失败的情况？
- [ ] 是否记录映射日志？

**正确示例**:
```python
# ✅ 使用AccountAlias映射
from modules.services.account_alignment import AccountAlignmentService

alignment_service = AccountAlignmentService(db)
aligned_account_id = alignment_service.align_account(
    platform_code=platform_code,
    account=account,
    store_label_raw=store_label_raw,
    platform_code=platform_code
)
if aligned_account_id:
    core["aligned_account_id"] = aligned_account_id
```

---

### 3. 字段映射审查

#### 3.1 标准字段映射审查

**检查项**:
- [ ] 是否使用标准字段（从FieldMappingDictionary）？
- [ ] 字段映射输出是否符合事实表结构？
- [ ] 是否处理未映射的字段（进入attributes JSON）？

**正确示例**:
```python
# ✅ 使用标准字段映射
field_mapping = {
    "订单号": {
        "standard_field": "order_id",
        "target_table": "fact_orders"
    },
    "商品SKU": {
        "standard_field": "platform_sku",
        "target_table": "fact_order_items"
    }
}
```

**错误示例**:
```python
# ❌ 直接使用源字段名
row = {
    "订单号": "12345",  # ❌ 应该映射到order_id
    "商品SKU": "SKU001"  # ❌ 应该映射到platform_sku
}
```

---

#### 3.2 Pattern-based Mapping审查

**检查项**:
- [ ] Pattern字段是否配置了field_pattern正则表达式？
- [ ] Pattern字段是否配置了target_table目标表？
- [ ] Pattern字段是否配置了dimension_config维度提取配置？

**正确示例**:
```python
# ✅ Pattern-based Mapping配置完整
{
    "field_code": "销售额（已付款订单）（BRL）",
    "is_pattern_based": True,
    "field_pattern": r"销售额\s*\((?P<status>.+?)\)\s*\((?P<currency>[A-Z]{3})\)",
    "dimension_config": {...},
    "target_table": "fact_order_amounts",
    "target_columns": {...}
}
```

---

### 4. 物化视图设计审查

#### 4.1 主视图设计审查

**检查项**:
- [ ] 主视图是否包含数据域的所有核心字段？
- [ ] 主视图是否创建了唯一索引？
- [ ] 主视图是否整合了多个表的数据？

**正确示例**:
```sql
-- ✅ 主视图包含所有核心字段
CREATE MATERIALIZED VIEW mv_order_summary AS
SELECT
    fo.platform_code,
    fo.shop_id,
    fo.order_id,
    fo.order_date_local AS order_date,
    fo.total_amount_rmb,
    ...
FROM fact_orders fo
INNER JOIN fact_order_items foi ON (...);

-- ✅ 创建唯一索引
CREATE UNIQUE INDEX idx_mv_order_summary_unique 
ON mv_order_summary(platform_code, shop_id, order_id);
```

---

#### 4.2 辅助视图设计审查

**检查项**:
- [ ] 辅助视图是否依赖主视图或基础数据？
- [ ] 辅助视图是否创建了唯一索引？
- [ ] 辅助视图是否用于特定分析场景？

---

### 5. 数据验证审查

#### 5.1 数据类型验证审查

**检查项**:
- [ ] 是否验证数值字段类型（Float, Integer）？
- [ ] 是否验证日期字段格式？
- [ ] 是否处理NULL值和空字符串？

**正确示例**:
```python
# ✅ 验证数值字段类型
if isinstance(value, str):
    try:
        value = float(value.replace(',', '').replace('$', ''))
    except ValueError:
        value = 0.0
```

---

#### 5.2 业务规则验证审查

**检查项**:
- [ ] 是否验证必填字段？
- [ ] 是否验证字段取值范围？
- [ ] 是否验证业务逻辑（如订单金额不能为负数）？

---

## 📝 审查流程

### 1. 提交前自查

**开发人员应在提交代码前完成以下自查**:
1. 运行数据库设计验证工具：`python scripts/review_schema_compliance.py`
2. 运行数据入库流程验证：`GET /api/database-design/validate/data-ingestion`
3. 运行字段映射验证：`GET /api/database-design/validate/field-mapping`
4. 检查代码是否符合本清单的所有检查项

---

### 2. 代码审查

**审查人员应检查**:
1. 数据库模型定义是否符合规范（主键设计、字段NULL规则、唯一索引）
2. 数据入库流程是否符合规范（shop_id获取、AccountAlias映射）
3. 字段映射是否符合规范（标准字段、Pattern-based mapping）
4. 物化视图设计是否符合规范（主视图、辅助视图）
5. 数据验证是否符合规范（数据类型、业务规则）

---

### 3. 审查结果处理

**如果发现问题**:
1. 记录问题（错误级别、警告级别、信息级别）
2. 提供修复建议
3. 要求开发人员修复问题
4. 重新审查修复后的代码

**如果通过审查**:
1. 批准代码合并
2. 记录审查结果

---

## 🔧 审查工具

### 自动化验证工具

1. **数据库设计验证工具**
   - 脚本：`scripts/review_schema_compliance.py`
   - API：`GET /api/database-design/validate`

2. **数据入库流程验证工具**
   - API：`GET /api/database-design/validate/data-ingestion`

3. **字段映射验证工具**
   - API：`GET /api/database-design/validate/field-mapping`

---

## 📚 相关文档

- [数据库设计规范](DATABASE_DESIGN.md)
- [数据库设计规则示例](DATABASE_DESIGN_EXAMPLES.md)
- [数据库设计检查清单](DATABASE_DESIGN_CHECKLIST.md)
- [数据入库流程验证指南](../../DATA_INGESTION_VALIDATION_GUIDE.md)
- [字段映射验证指南](../../FIELD_MAPPING_VALIDATION_GUIDE.md)

---

**最后更新**: 2025-11-20  
**维护**: AI Agent Team  
**状态**: ✅ 已完成

