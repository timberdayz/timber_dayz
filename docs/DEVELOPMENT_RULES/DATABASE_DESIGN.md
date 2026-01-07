# 数据库设计规范 - 企业级ERP标准

**版本**: v4.4.0  
**更新**: 2025-01-30  
**标准**: 参考SAP/Oracle ERP数据库设计标准

---

## 📋 表设计原则

### 1. 主键设计
- ✅ **所有表必须有主键**（Primary Key）
- ✅ **主键类型**: INTEGER（自增）或BIGINT（大数据量）
- ✅ **主键命名**: `id`（统一命名，便于理解）
- ✅ **复合主键**: 仅在业务需求明确时使用（如fact_order_items的`(order_id, line_id)`）

**示例**:
```python
class FactOrder(Base):
    __tablename__ = "fact_orders"
    id = Column(Integer, primary_key=True, autoincrement=True)  # ✅ 主键
    # ...
```

### 2. 外键约束
- ✅ **外键必须明确声明**（Foreign Key Constraints）
- ✅ **级联策略**: 
  - `ondelete="CASCADE"`: 删除父记录时自动删除子记录（如订单删除时删除订单项）
  - `ondelete="SET NULL"`: 删除父记录时子记录外键设为NULL（如分类删除时产品分类设为NULL）
  - `ondelete="RESTRICT"`: 存在子记录时禁止删除父记录（默认策略）
- ✅ **外键命名**: `fk_表名_字段名`（如`fk_fact_orders_platform_code`）

**示例**:
```python
class FactOrder(Base):
    platform_code = Column(String(32), ForeignKey("dim_platforms.code", ondelete="RESTRICT"), nullable=False)
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="CASCADE"), nullable=True)
```

### 3. 字段类型规范
- ✅ **字符串**: `VARCHAR(n)` - n必须明确，不超过实际需求
  - 平台代码: `VARCHAR(32)`（shopee、tiktok等）
  - 订单号: `VARCHAR(128)`（可能包含前缀）
  - 产品名称: `VARCHAR(512)`（长名称）
  - ❌ **禁止**: `VARCHAR(255)`滥用（应根据实际需求选择）
- ✅ **文本**: `TEXT` - 用于长文本（如description、备注）
- ✅ **数字**: 
  - `INTEGER` - 范围-2,147,483,648到2,147,483,647
  - `BIGINT` - 大数据量（如订单ID、文件大小）
  - `SMALLINT` - 小范围整数（如状态码0-100）
- ✅ **金额**: `DECIMAL(15, 2)` - 精确货币计算（避免浮点数误差）
- ✅ **布尔**: `BOOLEAN` - 而非INTEGER(0/1)
- ✅ **日期**: `DATE` - 仅日期，无时间（如order_date_local）
- ✅ **时间**: `TIMESTAMP`或`TIMESTAMPTZ` - 需要时区用TIMESTAMPTZ（如order_time_utc）
- ✅ **JSON**: `JSONB` - 结构化数据（如attributes字段）

### 4. 必填字段设计
- ✅ **NOT NULL约束**: 关键业务字段必须NOT NULL
- ✅ **业务标识**: platform_code、shop_id、order_id等必须NOT NULL
- ✅ **金额字段**: total_amount、quantity等必须NOT NULL（避免NULL计算问题）
- ✅ **时间字段**: created_at、updated_at必须NOT NULL
- ⚠️ **可选字段**: 允许NULL的字段必须有明确的业务含义

### 5. 默认值设计
- ✅ **状态字段**: 默认值应该是最常见的初始状态（如status='pending'）
- ✅ **时间字段**: created_at默认值`datetime.utcnow`，updated_at默认值`datetime.utcnow`并`onupdate`
- ✅ **数字字段**: 默认值0而非NULL（便于计算）
- ✅ **布尔字段**: 默认值False（明确状态）

### 6. 审计字段（必须）
- ✅ **created_at**: TIMESTAMP，记录创建时间
- ✅ **updated_at**: TIMESTAMP，记录更新时间（自动更新）
- ✅ **created_by**: VARCHAR(64)，记录创建人（可选）
- ✅ **updated_by**: VARCHAR(64)，记录更新人（可选）
- ✅ **deleted_at**: DATE，软删除标记（重要表）

**示例**:
```python
class FactOrder(Base):
    # 业务字段
    order_id = Column(String(128), nullable=False)
    # ...
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(String(64), nullable=True)
    updated_by = Column(String(64), nullable=True)
    deleted_at = Column(Date, nullable=True)  # 软删除
```

---

## 🔍 索引设计原则

### 1. 唯一索引
- ✅ **业务唯一性**: 使用UniqueConstraint，而非唯一索引
- ✅ **复合唯一性**: 多个字段组合唯一（如platform_code + shop_id + order_id）
- ✅ **命名规范**: `uq_表名_字段名`（如`uq_fact_orders_order_id`）

**示例**:
```python
class FactOrder(Base):
    __table_args__ = (
        UniqueConstraint(
            "platform_code",
            "shop_id", 
            "order_id",
            name="uq_fact_orders_order_id"
        ),
    )
```

### 2. 联合索引
- ✅ **最左前缀原则**: 索引列顺序必须匹配查询WHERE条件顺序
- ✅ **查询频率**: 为频繁查询的字段组合创建索引
- ✅ **索引大小**: 避免索引列过多（影响写入性能）

**示例**:
```python
# 查询: WHERE platform_code = ? AND shop_id = ? AND order_date BETWEEN ? AND ?
Index("ix_fact_orders_platform_shop_date", "platform_code", "shop_id", "order_date_local")
```

### 3. 部分索引
- ✅ **WHERE条件过滤**: 只为满足条件的行创建索引
- ✅ **适用场景**: 状态字段（如仅索引status='active'的记录）

**示例**:
```python
# 只为活跃订单创建索引
Index("ix_fact_orders_active", "order_id", postgresql_where=text("status = 'active'"))
```

### 4. GIN索引（JSONB字段）
- ✅ **attributes字段**: 为JSONB字段创建GIN索引以支持查询
- ✅ **性能优化**: 使用GIN索引查询JSONB字段的性能提升显著

**示例**:
```python
class FactOrder(Base):
    attributes = Column(JSONB, nullable=True)
    __table_args__ = (
        Index("ix_fact_orders_attributes", "attributes", postgresql_using="gin"),
    )
```

### 5. 表达式索引
- ✅ **函数查询**: 为函数查询创建表达式索引（如`LOWER(email)`）
- ✅ **性能优化**: 避免全表扫描

**示例**:
```python
Index("ix_users_email_lower", func.lower(User.email))
```

### 6. 索引设计原则
- ❌ **禁止**: 创建过多索引（影响写入性能，单表索引≤10个）
- ❌ **禁止**: 重复索引（索引列组合相同）
- ✅ **最佳实践**: 为WHERE、JOIN、ORDER BY的字段创建索引
- ✅ **监控**: 定期监控索引使用情况，删除未使用的索引

---

## 🔒 约束设计

### 1. CHECK约束
- ✅ **数据范围验证**: 确保数据在合理范围内
- ✅ **业务规则**: 在数据库层面验证业务规则

**示例**:
```python
class FactOrder(Base):
    total_amount = Column(DECIMAL(15, 2), nullable=False)
    quantity = Column(Integer, nullable=False)
    
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_fact_orders_amount_positive"),
        CheckConstraint("quantity > 0", name="ck_fact_orders_quantity_positive"),
    )
```

### 2. NOT NULL约束
- ✅ **必填字段**: 关键业务字段必须NOT NULL
- ✅ **避免NULL问题**: NULL不能参与计算、比较等操作

### 3. FOREIGN KEY约束
- ✅ **引用完整性**: 确保外键引用的记录存在
- ✅ **级联策略**: 根据业务需求选择合适的级联策略

### 4. DEFAULT值
- ✅ **合理默认值**: 默认值应该是最常见的初始值
- ✅ **业务含义**: 默认值必须有明确的业务含义

---

## 📝 命名规范

### 1. 表名
- ✅ **snake_case**: 使用下划线分隔（如`fact_orders`）
- ✅ **复数形式**: 表名使用复数形式（如orders而非order）
- ✅ **前缀规范**: 
  - `fact_`: 事实表（如fact_orders）
  - `dim_`: 维度表（如dim_platforms）
  - `staging_`: 临时表（如staging_orders）

### 2. 字段名
- ✅ **snake_case**: 使用下划线分隔（如`order_time_utc`）
- ✅ **语义清晰**: 字段名必须能清晰表达含义
- ✅ **时间字段**: 使用`_utc`或`_local`后缀区分时区

### 3. 索引名
- ✅ **格式**: `ix_表名_字段名`（如`ix_fact_orders_platform_code`）
- ✅ **联合索引**: `ix_表名_字段1_字段2`（如`ix_fact_orders_platform_shop`）

### 4. 约束名
- ✅ **唯一约束**: `uq_表名_字段名`（如`uq_fact_orders_order_id`）
- ✅ **检查约束**: `ck_表名_字段名_规则`（如`ck_fact_orders_amount_positive`）
- ✅ **外键约束**: `fk_表名_字段名`（如`fk_fact_orders_platform_code`）

---

## 🎯 性能优化建议

### 1. 表分区
- ✅ **时间分区**: 按月或按年分区大表（如fact_orders）
- ✅ **查询优化**: 分区剪枝（Partition Pruning）提升查询性能

### 2. 物化视图
- ✅ **聚合查询**: 使用物化视图预计算聚合结果
- ✅ **刷新策略**: 定时刷新或增量刷新

### 3. 查询优化
- ✅ **避免SELECT \***: 只查询需要的字段
- ✅ **使用LIMIT**: 大数据量查询必须使用LIMIT
- ✅ **避免子查询**: 使用JOIN替代子查询（性能更好）

---

## 📚 参考标准

- **SAP数据库设计标准**: 参考SAP ERP数据库设计原则
- **Oracle ERP标准**: 参考Oracle ERP数据库设计规范
- **PostgreSQL最佳实践**: 参考PostgreSQL官方文档

---

---

## 🆕 产品ID原子级设计规则（v4.12.0新增）

### 1. 产品ID冗余字段设计
- ✅ **冗余字段**: 在FactOrderItem等表中添加product_id字段（冗余字段，便于直接查询）
- ✅ **主键不变**: 保持现有主键设计不变（如FactOrderItem的主键仍为(platform_code, shop_id, order_id, platform_sku)）
- ✅ **自动关联**: 数据入库时通过BridgeProductKeys自动关联product_id
- ✅ **允许NULL**: 如果找不到对应的product_id，允许为NULL（记录警告，支持后续修复）

**示例**:
```python
class FactOrderItem(Base):
    # 现有主键保持不变
    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    order_id = Column(String(128), primary_key=True)
    platform_sku = Column(String(128), primary_key=True)
    
    # ⭐ v4.12.0新增：产品ID冗余字段
    product_id = Column(Integer, ForeignKey("dim_product_master.product_id", ondelete="SET NULL"), nullable=True)
    
    # 创建索引支持高效查询
    __table_args__ = (
        Index("ix_fact_items_product_id", "product_id"),
    )
```

### 2. 产品ID与SKU的关系
- **产品ID（product_id/SN）**: 每个产品实例的唯一标识（类似身份证），用于查询具体产品的销售情况
- **SKU（platform_sku）**: 产品类型的标识（类似人种），用于查询整个产品类型的销售情况
- **关系**: 一个SKU可以对应多个product_id（同一产品类型的不同实例）

### 3. 以产品ID为原子级的物化视图
- ✅ **mv_sales_detail_by_product**: 以product_id为原子级的销售明细视图
- ✅ **每行代表一个产品实例**: 类似华为ISRP系统的销售明细表结构
- ✅ **包含完整信息**: 产品信息、订单信息、价格信息、店铺信息等
- ✅ **支持多维度查询**: 通过product_id、SKU、订单ID、日期等查询

**物化视图设计**:
```sql
CREATE MATERIALIZED VIEW mv_sales_detail_by_product AS
SELECT 
    -- 产品标识（原子级）
    foi.product_id,                    -- 产品ID（SN）
    dpm.company_sku,                   -- 公司SKU
    foi.platform_sku,                  -- 平台SKU
    
    -- 订单信息
    fo.order_id,
    fo.order_date_local AS sale_date,
    
    -- 价格和数量
    foi.unit_price_rmb,
    foi.quantity,
    foi.line_amount_rmb,
    
    -- 店铺和平台信息
    foi.platform_code,
    foi.shop_id,
    ds.shop_name,
    
    -- 时间戳
    CURRENT_TIMESTAMP AS refreshed_at
    
FROM fact_order_items foi
INNER JOIN fact_orders fo ON (...)
LEFT JOIN bridge_product_keys bpk ON (...)
LEFT JOIN dim_product_master dpm ON (...)
WHERE fo.is_cancelled = false;
```

### 4. 数据入库流程
- ✅ **自动关联**: 订单明细入库时，通过BridgeProductKeys查找product_id
- ✅ **错误处理**: 如果找不到，product_id为NULL，记录警告信息
- ✅ **数据修复**: 提供数据修复脚本，为历史数据关联product_id

**入库流程示例**:
```python
# 通过BridgeProductKeys查找product_id
bridge = db.query(BridgeProductKeys).filter(
    BridgeProductKeys.platform_code == platform_code,
    BridgeProductKeys.shop_id == shop_id,
    BridgeProductKeys.platform_sku == platform_sku
).first()

product_id = bridge.product_id if bridge else None

# 创建订单明细记录
order_item = FactOrderItem(
    platform_code=platform_code,
    shop_id=shop_id,
    order_id=order_id,
    platform_sku=platform_sku,
    product_id=product_id,  # 冗余字段
    # ... 其他字段
)
```

---

**最后更新**: 2025-11-20（v4.12.0：产品ID原子级设计）  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准

