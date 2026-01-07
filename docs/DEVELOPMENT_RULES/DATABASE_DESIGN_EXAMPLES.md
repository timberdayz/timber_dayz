# 数据库设计规则示例

**版本**: v4.12.0  
**创建时间**: 2025-11-20  
**状态**: ✅ 已完成

---

## 📋 概述

本文档提供数据库设计规则的正确和错误示例，帮助开发人员理解并遵循设计规范。

---

## 1. 主键设计规则

### ✅ 正确示例

#### 示例1：运营数据主键（SKU为主键）

```python
class FactProductMetric(Base):
    """商品指标事实表"""
    __tablename__ = "fact_product_metrics"
    
    # ✅ 正确：使用业务标识作为主键（运营数据）
    platform_code = Column(String(32), nullable=False, primary_key=True)
    shop_id = Column(String(64), nullable=False, primary_key=True)
    platform_sku = Column(String(128), nullable=False, primary_key=True)
    metric_date = Column(Date, nullable=False, primary_key=True)
    granularity = Column(String(16), default="daily", nullable=False, primary_key=True)
    data_domain = Column(String(64), nullable=True, primary_key=True)
    
    # 业务字段
    product_name = Column(String(512), nullable=True)
    price = Column(Float, nullable=True, default=0.0)
    sales_volume = Column(Integer, default=0)
    
    __table_args__ = (
        # ✅ 正确：业务唯一索引
        UniqueConstraint(
            "platform_code", "shop_id", "platform_sku", "metric_date", 
            "granularity", "data_domain",
            name="uq_product_metric"
        ),
    )
```

**说明**:
- ✅ 使用业务标识（platform_code, shop_id, platform_sku）作为主键
- ✅ 支持同一SKU在同一天有多个数据域的数据
- ✅ 使用UniqueConstraint确保业务唯一性

---

#### 示例2：订单数据主键（SKU为主键）

```python
class FactOrderItem(Base):
    """订单明细表"""
    __tablename__ = "fact_order_items"
    
    # ✅ 正确：使用业务标识作为主键（运营数据）
    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    order_id = Column(String(128), primary_key=True)
    platform_sku = Column(String(128), primary_key=True)
    
    # ✅ 正确：冗余字段，支持product_id查询
    product_id = Column(Integer, ForeignKey("dim_product_master.product_id", ondelete="SET NULL"), nullable=True, index=True)
    
    # 业务字段
    quantity = Column(Integer, default=1, nullable=False)
    unit_price = Column(Float, default=0.0, nullable=False)
    
    __table_args__ = (
        # ✅ 正确：业务唯一索引
        Index("ix_fact_items_plat_shop_order", "platform_code", "shop_id", "order_id"),
        Index("ix_fact_items_plat_shop_sku", "platform_code", "shop_id", "platform_sku"),
        Index("ix_fact_items_product_id", "product_id"),  # ✅ 支持product_id查询
    )
```

**说明**:
- ✅ 使用业务标识（platform_code, shop_id, order_id, platform_sku）作为主键
- ✅ 添加product_id冗余字段，支持product_id原子级查询
- ✅ 创建索引优化查询性能

---

### ❌ 错误示例

#### 示例1：使用自增ID作为主键（运营数据）

```python
class FactProductMetric(Base):
    """商品指标事实表"""
    __tablename__ = "fact_product_metrics"
    
    # ❌ 错误：使用自增ID作为主键（运营数据不应使用自增ID）
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    metric_date = Column(Date, nullable=False)
    
    # ❌ 错误：缺少业务唯一索引
    # 应该使用UniqueConstraint确保业务唯一性
```

**问题**:
- ❌ 运营数据不应使用自增ID作为主键
- ❌ 缺少业务唯一索引，可能导致重复数据
- ❌ 无法直接通过业务标识查询

---

#### 示例2：主键字段允许NULL

```python
class FactOrder(Base):
    """订单表"""
    __tablename__ = "fact_orders"
    
    # ❌ 错误：主键字段允许NULL
    platform_code = Column(String(32), nullable=True, primary_key=True)
    shop_id = Column(String(64), nullable=True, primary_key=True)
    order_id = Column(String(128), nullable=True, primary_key=True)
```

**问题**:
- ❌ 主键字段不能为NULL
- ❌ 违反数据库设计规范
- ❌ 可能导致数据完整性问题

---

## 2. 字段NULL规则

### ✅ 正确示例

#### 示例1：关键业务字段不允许NULL

```python
class FactOrderItem(Base):
    """订单明细表"""
    __tablename__ = "fact_order_items"
    
    # ✅ 正确：关键业务字段不允许NULL，使用默认值
    quantity = Column(Integer, default=1, nullable=False)
    unit_price = Column(Float, default=0.0, nullable=False)
    unit_price_rmb = Column(Float, default=0.0, nullable=False)
```

**说明**:
- ✅ 关键业务字段（quantity, unit_price）不允许NULL
- ✅ 使用默认值（default=1, default=0.0）
- ✅ 确保数据完整性

---

#### 示例2：可选字段允许NULL

```python
class FactProductMetric(Base):
    """商品指标事实表"""
    __tablename__ = "fact_product_metrics"
    
    # ✅ 正确：可选字段允许NULL（inventory域可能没有价格）
    price = Column(Float, nullable=True, default=0.0)
    price_rmb = Column(Float, nullable=True, default=0.0)
    
    # ✅ 正确：描述性字段允许NULL
    product_name = Column(String(512), nullable=True)
    category = Column(String(128), nullable=True)
```

**说明**:
- ✅ 可选字段允许NULL（如inventory域可能没有价格）
- ✅ 使用默认值（default=0.0）提供兜底值
- ✅ 描述性字段允许NULL

---

### ❌ 错误示例

#### 示例1：关键业务字段允许NULL

```python
class FactOrder(Base):
    """订单表"""
    __tablename__ = "fact_orders"
    
    # ❌ 错误：关键业务字段允许NULL
    subtotal = Column(Float, nullable=True)  # ❌ 应该不允许NULL
    total_amount = Column(Float, nullable=True)  # ❌ 应该不允许NULL
```

**问题**:
- ❌ 关键业务字段（金额字段）不应允许NULL
- ❌ 可能导致计算错误（NULL + 数值 = NULL）
- ❌ 违反数据库设计规范

---

#### 示例2：缺少默认值

```python
class FactOrderItem(Base):
    """订单明细表"""
    __tablename__ = "fact_order_items"
    
    # ❌ 错误：缺少默认值
    quantity = Column(Integer, nullable=False)  # ❌ 应该添加default=1
    unit_price = Column(Float, nullable=False)  # ❌ 应该添加default=0.0
```

**问题**:
- ❌ 缺少默认值，插入数据时必须显式提供值
- ❌ 增加代码复杂度
- ❌ 违反数据库设计规范

---

## 3. 物化视图设计规则

### ✅ 正确示例

#### 示例1：主视图设计（Hub视图）

```sql
-- ✅ 正确：主视图包含数据域的所有核心字段
CREATE MATERIALIZED VIEW mv_order_summary AS
SELECT
    -- ========== 订单标识 ==========
    fo.platform_code,
    fo.shop_id,
    fo.order_id,
    
    -- ========== 订单时间 ==========
    fo.order_date_local AS order_date,
    fo.order_time_utc,
    
    -- ========== 订单金额 ==========
    fo.currency,
    fo.subtotal,
    fo.subtotal_rmb,
    fo.total_amount,
    fo.total_amount_rmb,
    
    -- ========== 订单状态 ==========
    fo.order_status,
    fo.payment_status,
    
    -- ========== 买家信息 ==========
    fo.buyer_id,
    fo.buyer_name,
    
    -- ========== 商品信息汇总 ==========
    COUNT(DISTINCT foi.platform_sku) AS item_count,
    SUM(foi.quantity) AS total_quantity,
    
    CURRENT_TIMESTAMP AS refreshed_at
FROM
    fact_orders fo
    INNER JOIN fact_order_items foi ON (
        fo.platform_code = foi.platform_code AND
        fo.shop_id = foi.shop_id AND
        fo.order_id = foi.order_id
    )
WHERE
    fo.order_date_local IS NOT NULL
GROUP BY
    fo.platform_code, fo.shop_id, fo.order_id, ...;

-- ✅ 正确：创建唯一索引
CREATE UNIQUE INDEX idx_mv_order_summary_unique 
ON mv_order_summary(platform_code, shop_id, order_id);
```

**说明**:
- ✅ 主视图包含数据域的所有核心字段
- ✅ 整合多个表的数据（fact_orders + fact_order_items）
- ✅ 创建唯一索引，支持CONCURRENT刷新

---

#### 示例2：辅助视图设计（Spoke视图）

```sql
-- ✅ 正确：辅助视图依赖主视图或基础数据
CREATE MATERIALIZED VIEW mv_sales_detail_by_product AS
SELECT
    foi.product_id,
    dpm.company_sku,
    foi.platform_sku,
    fo.order_date_local AS sale_date,
    foi.unit_price_rmb,
    foi.quantity,
    ...
FROM
    fact_order_items foi
    INNER JOIN fact_orders fo ON (...)
    LEFT JOIN dim_product_master dpm ON (...)
WHERE
    fo.is_cancelled = false;

-- ✅ 正确：创建唯一索引
CREATE UNIQUE INDEX idx_mv_sales_detail_product_order 
ON mv_sales_detail_by_product(product_id, order_id, platform_sku);
```

**说明**:
- ✅ 辅助视图用于特定分析场景（product_id原子级查询）
- ✅ 依赖主视图或基础数据（fact_order_items, fact_orders）
- ✅ 创建唯一索引，支持CONCURRENT刷新

---

### ❌ 错误示例

#### 示例1：主视图缺少核心字段

```sql
-- ❌ 错误：主视图缺少核心字段
CREATE MATERIALIZED VIEW mv_inventory_summary AS
SELECT
    warehouse,
    COUNT(DISTINCT platform_sku) AS total_products,
    SUM(total_stock) AS total_total_stock
FROM
    fact_product_metrics
WHERE
    data_domain = 'inventory'
GROUP BY
    warehouse;
```

**问题**:
- ❌ 缺少核心字段（platform_code, shop_id, platform_sku, product_name等）
- ❌ 无法提供完整的数据域信息
- ❌ 不符合主视图标准

---

#### 示例2：缺少唯一索引

```sql
-- ❌ 错误：缺少唯一索引
CREATE MATERIALIZED VIEW mv_order_summary AS
SELECT
    platform_code,
    shop_id,
    order_id,
    ...
FROM
    fact_orders;

-- ❌ 错误：没有创建唯一索引
-- 应该创建：CREATE UNIQUE INDEX idx_mv_order_summary_unique ON mv_order_summary(platform_code, shop_id, order_id);
```

**问题**:
- ❌ 缺少唯一索引，无法支持CONCURRENT刷新
- ❌ 可能导致重复数据
- ❌ 违反物化视图设计规范

---

## 4. 字段映射规则

### ✅ 正确示例

#### 示例1：标准字段映射

```python
# ✅ 正确：标准字段映射到事实表字段
field_mapping = {
    "订单号": {
        "standard_field": "order_id",
        "target_table": "fact_orders"
    },
    "商品SKU": {
        "standard_field": "platform_sku",
        "target_table": "fact_order_items"
    },
    "数量": {
        "standard_field": "quantity",
        "target_table": "fact_order_items"
    }
}
```

**说明**:
- ✅ 使用标准字段（order_id, platform_sku, quantity）
- ✅ 明确目标表（fact_orders, fact_order_items）
- ✅ 符合字段映射规范

---

#### 示例2：Pattern-based Mapping

```python
# ✅ 正确：Pattern-based Mapping配置
{
    "field_code": "销售额（已付款订单）（BRL）",
    "is_pattern_based": True,
    "field_pattern": r"销售额\s*\((?P<status>.+?)\)\s*\((?P<currency>[A-Z]{3})\)",
    "dimension_config": {
        "status": {"已付款订单": "paid", "已下订单": "placed"},
        "currency": "BRL"
    },
    "target_table": "fact_order_amounts",
    "target_columns": {
        "metric_type": "sales",
        "metric_subtype": "{status}",
        "currency": "{currency}"
    }
}
```

**说明**:
- ✅ 使用正则表达式匹配字段名
- ✅ 提取维度信息（status, currency）
- ✅ 映射到维度表（fact_order_amounts）

---

### ❌ 错误示例

#### 示例1：直接使用源字段名

```python
# ❌ 错误：直接使用源字段名，不进行映射
row = {
    "订单号": "12345",  # ❌ 应该映射到order_id
    "商品SKU": "SKU001",  # ❌ 应该映射到platform_sku
    "数量": 10  # ❌ 应该映射到quantity
}
```

**问题**:
- ❌ 直接使用源字段名，不进行标准化
- ❌ 无法保证数据一致性
- ❌ 违反字段映射规范

---

#### 示例2：映射到不存在的字段

```python
# ❌ 错误：映射到不存在的字段
field_mapping = {
    "订单号": {
        "standard_field": "order_number",  # ❌ 应该使用order_id
        "target_table": "fact_orders"
    }
}
```

**问题**:
- ❌ 映射到不存在的字段（order_number）
- ❌ 应该使用标准字段（order_id）
- ❌ 违反字段映射规范

---

## 5. 数据入库流程规则

### ✅ 正确示例

#### 示例1：shop_id获取规则

```python
# ✅ 正确：shop_id获取优先级
def get_shop_id(row, file_record, account_alias_service):
    # 1. 优先从源数据获取
    if row.get("shop_id"):
        return row["shop_id"]
    
    # 2. 使用AccountAlias映射
    if row.get("store_label_raw"):
        aligned_id = account_alias_service.align_account(
            platform_code=file_record.platform_code,
            account=row.get("account"),
            store_label_raw=row.get("store_label_raw")
        )
        if aligned_id:
            return aligned_id
    
    # 3. 从文件元数据获取
    if file_record and file_record.shop_id:
        return file_record.shop_id
    
    # 4. 默认值处理
    return None  # shop_id允许为None（inventory域）
```

**说明**:
- ✅ 遵循shop_id获取优先级
- ✅ 使用AccountAlias映射非标准店铺名称
- ✅ 正确处理默认值

---

### ❌ 错误示例

#### 示例1：硬编码shop_id

```python
# ❌ 错误：硬编码shop_id
def get_shop_id(row, file_record):
    return "shopee_sg_1"  # ❌ 硬编码，不灵活
```

**问题**:
- ❌ 硬编码shop_id，不灵活
- ❌ 无法处理多店铺场景
- ❌ 违反数据入库流程规范

---

## 📝 总结

### 核心原则

1. **主键设计**:
   - ✅ 运营数据使用业务标识作为主键（SKU为主键）
   - ✅ 业务数据使用自增ID + 唯一索引
   - ❌ 运营数据不应使用自增ID作为主键

2. **字段NULL规则**:
   - ✅ 关键业务字段不允许NULL，使用默认值
   - ✅ 可选字段允许NULL，但提供默认值
   - ❌ 关键业务字段不应允许NULL

3. **物化视图设计**:
   - ✅ 主视图包含数据域的所有核心字段
   - ✅ 创建唯一索引，支持CONCURRENT刷新
   - ❌ 主视图不应缺少核心字段

4. **字段映射规则**:
   - ✅ 使用标准字段映射
   - ✅ Pattern-based mapping配置正确
   - ❌ 不应直接使用源字段名

5. **数据入库流程**:
   - ✅ 遵循shop_id获取优先级
   - ✅ 使用AccountAlias映射
   - ❌ 不应硬编码shop_id

---

**最后更新**: 2025-11-20  
**维护**: AI Agent Team  
**状态**: ✅ 已完成

