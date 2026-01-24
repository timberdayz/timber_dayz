# 数据库设计规范 - 企业级ERP标准

**版本**: v4.4.1  
**更新**: 2025-01-XX  
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

## 📝 SQL编写规范（Metabase Model SQL）

**版本**: v1.0.0  
**更新**: 2025-01-XX  
**参考标准**: GitLab、Mozilla、Meltano、dbt、SQLFluff 等业界主流规范  
**适用场景**: Metabase Model SQL、数据仓库查询、BI 报表 SQL

### 1. 命名规范
- ✅ **表名/字段名**: 使用 `snake_case`（全小写+下划线）
- ✅ **别名**: 必须使用 `AS` 关键字，别名与标准字段名一致
- ✅ **CTE命名**: 使用 `all_{data_domain}` 格式，有语义

### 2. 格式规范
- ✅ **关键字**: 统一使用**小写**（`select`、`from`、`where`）
- ✅ **缩进**: 使用**2个空格**（不使用Tab）
- ✅ **字段列表**: 每个字段一行，逗号在行尾
- ✅ **行长度**: 控制在120字符以内（横屏编辑友好）
- ✅ **COALESCE格式**: 
  - **短COALESCE**（≤120字符）：推荐一行内，便于横屏查看和维护
  - **长COALESCE**（>120字符）：多行格式，每个参数一行，参数对齐

### 3. 字段映射规范
- ✅ **字符串字段**: 使用 `COALESCE()` 支持多平台字段名（至少3-5个候选）
  - **推荐格式**（横屏友好）：`coalesce(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'order_id') as order_id,`
  - **长格式**（>120字符时）：多行格式，参数对齐
- ✅ **数值字段**: 使用 `NULLIF(field, '')::numeric` 处理空字符串，默认值 `0`
  - **普通数值字段**（横屏友好）：`coalesce(nullif(replace(replace(raw_data->>'销售额', ',', ''), ' ', ''), '')::numeric, nullif(replace(replace(raw_data->>'销售金额', ',', ''), ' ', ''), '')::numeric, 0) as sales_amount,`
  - **处理规则**：移除千分位（`,`）和空格，再转换为 numeric
- ✅ **百分比字段**: 必须移除百分号、处理欧洲格式（逗号→点号），并除以100（如果原始数据是百分比格式）
  - **推荐格式**（横屏友好）：`coalesce(nullif(replace(replace(replace(raw_data->>'转化率', '%', ''), ',', '.'), ' ', ''), '')::numeric / 100.0, nullif(replace(replace(replace(raw_data->>'conversion_rate', '%', ''), ',', '.'), ' ', ''), '')::numeric / 100.0, 0) as conversion_rate,`
  - **处理规则**：
    1. 移除百分号（`%`）
    2. 替换逗号为点号（欧洲格式：`0,00` → `0.00`）
    3. 移除空格
    4. 转换为 numeric
    5. 除以 100.0（如果原始数据是百分比格式，如 `"0,00%"` = 0.0000）
  - **常见百分比字段**：`click_rate`（点击率）、`conversion_rate`（转化率）、`bounce_rate`（跳出率）、`positive_rate`（好评率）
- ✅ **时间字段**: 提供降级策略（`raw_data` → `period_start_time` → `metric_date`）
  - **必须使用 NULLIF**：先使用 `NULLIF(field, '')` 处理空字符串，再类型转换（避免空字符串转换错误）
  - **推荐格式**（横屏友好）：`coalesce(nullif(raw_data->>'下单时间', '')::timestamp, nullif(raw_data->>'订单时间', '')::timestamp, period_start_time) as order_time,`
  - **错误示例**：`coalesce((raw_data->>'下单时间')::timestamp, ...)` - 空字符串会导致转换错误

### 4. CTE使用规范（CTE分层架构）⭐⭐⭐
- ✅ **强制使用CTE分层**：所有 Metabase Model SQL 必须使用 CTE 分层架构
- ✅ **分层结构**：`字段映射 → 数据清洗 → 去重 → 最终输出`
- ✅ **性能说明**：PostgreSQL 12+ 默认内联 CTE（单次引用），性能影响为零，甚至可能提升（查询优化器更容易优化）
- ✅ **CTE注释**：每个CTE前必须有注释说明用途和层级

#### 4.1 CTE分层架构（4层结构）

**第1层：字段映射（field_mapping）**
- **职责**：提取所有候选字段，不做格式化
- **优势**：字段映射逻辑集中，易于维护
- **示例**：
```sql
field_mapping AS (
  SELECT 
    platform_code,
    shop_id,
    -- 字段映射：提取所有候选字段（不做格式化）
    COALESCE(
      raw_data->>'访客数',
      raw_data->>'独立访客',
      raw_data->>'unique_visitors',
      raw_data->>'Unique Visitors',
      raw_data->>'uv',
      raw_data->>'visitor_count'
    ) AS visitor_count_raw,
    -- ... 其他字段
  FROM b_class.fact_shopee_analytics_daily
  UNION ALL
  -- ... 其他平台和粒度
)
```

**第2层：数据清洗（cleaned）**
- **职责**：统一格式化逻辑（数值、百分比、时间格式）
- **优势**：格式化逻辑只写一次，易于维护和修改
- **示例**：
```sql
cleaned AS (
  SELECT 
    platform_code,
    shop_id,
    -- 普通数值字段清洗（统一逻辑）
    NULLIF(REPLACE(REPLACE(visitor_count_raw, ',', ''), ' ', ''), '')::NUMERIC AS visitor_count,
    -- 百分比字段清洗（统一逻辑）
    NULLIF(REPLACE(REPLACE(REPLACE(click_rate_raw, '%', ''), ',', '.'), ' ', ''), '')::NUMERIC / 100.0 AS click_rate,
    -- 时间格式字段清洗（处理 "00:00:00" 格式）
    CASE 
      WHEN avg_session_duration_raw ~ '^[0-9]+:[0-9]+:[0-9]+$' THEN
        EXTRACT(EPOCH FROM (avg_session_duration_raw)::INTERVAL)::NUMERIC
      ELSE
        NULLIF(REPLACE(REPLACE(avg_session_duration_raw, ',', ''), ' ', ''), '')::NUMERIC
    END AS avg_session_duration,
    -- ... 其他字段
  FROM field_mapping
)
```

**第3层：去重（deduplicated）**
- **职责**：基于 data_hash 去重，优先级 daily > weekly > monthly
- **优势**：去重逻辑独立，职责清晰
- **示例**：
```sql
deduplicated AS (
  SELECT 
    *,
    ROW_NUMBER() OVER (
      PARTITION BY platform_code, shop_id, data_hash 
      ORDER BY 
        CASE granularity
          WHEN 'daily' THEN 1
          WHEN 'weekly' THEN 2
          WHEN 'monthly' THEN 3
        END ASC,
        ingest_timestamp DESC
    ) AS rn
  FROM cleaned
)
```

**第4层：最终输出（SELECT）**
- **职责**：只保留去重后的数据，设置默认值
- **优势**：输出格式统一，便于前端使用
- **示例**：
```sql
SELECT 
  platform_code,
  shop_id,
  COALESCE(visitor_count, 0) AS visitor_count,
  COALESCE(click_rate, 0) AS click_rate,
  -- ... 其他字段
FROM deduplicated
WHERE rn = 1
```

#### 4.2 CTE分层优势

| 优势 | 说明 |
|------|------|
| **可读性** | 字段映射、数据清洗、去重逻辑分离，职责清晰 |
| **维护性** | 修改格式化逻辑只需修改第2层（cleaned CTE） |
| **代码复用** | 格式化逻辑只写一次，减少90%以上代码重复 |
| **性能** | PostgreSQL 12+ 内联优化，性能影响为零，甚至可能提升 |

#### 4.3 CTE性能说明

- ✅ **PostgreSQL 12+ 默认行为**：单次引用的 CTE 会被内联到主查询中
- ✅ **执行计划**：与不使用 CTE 的查询相同或更好（查询优化器更容易优化）
- ✅ **多次引用**：只有在 CTE 被多次引用时才会物化（我们的场景不适用）
- ✅ **性能验证**：使用 `EXPLAIN ANALYZE` 对比执行计划，确认无性能损失

### 5. 注释规范
- ✅ **文件头**: 包含模型名称、用途、数据源、平台、粒度
- ✅ **字段分组**: 使用注释分组（系统字段、基础字段、金额字段等）
- ✅ **UNION ALL**: 每个块前注释说明平台和粒度

### 6. 性能优化
- ✅ **索引字段**: 优先使用 `period_start_date`、`platform_code`、`shop_id` 过滤
- ✅ **避免函数**: 不在WHERE中对列使用函数（阻止索引使用）
- ✅ **明确字段**: 避免 `SELECT *`，明确列出所有字段

### 7. 示例模板（CTE分层架构）⭐⭐⭐

```sql
-- ====================================================
-- {Model Name} Model - {数据域}数据域模型（CTE分层）
-- ====================================================
-- 用途：{模型用途说明}
-- 数据源：b_class schema 下的所有 {数据域} 相关表
-- 平台：{平台列表}
-- 粒度：{粒度列表}
-- 优化：CTE分层架构，提升可读性和维护性
-- ====================================================

WITH 
-- ====================================================
-- 第1层：字段映射（提取所有候选字段，不做格式化）
-- ====================================================
field_mapping AS (
  -- {平台} {粒度} {数据域}数据
  SELECT 
    -- 系统字段（必须）
    platform_code,
    shop_id,
    data_domain,
    granularity,
    metric_date,
    period_start_date,
    period_end_date,
    period_start_time,
    period_end_time,
    
    -- 标准业务字段映射（提取所有候选字段）
    COALESCE(
      raw_data->>'订单号',
      raw_data->>'订单ID',
      raw_data->>'order_id',
      raw_data->>'Order ID'
    ) AS order_id_raw,
    
    COALESCE(
      raw_data->>'销售额',
      raw_data->>'销售金额',
      raw_data->>'sales_amount',
      raw_data->>'Sales Amount'
    ) AS sales_amount_raw,
    
    COALESCE(
      raw_data->>'下单时间',
      raw_data->>'订单时间',
      raw_data->>'order_time',
      raw_data->>'Order Time'
    ) AS order_time_raw,
    
    -- 系统字段（必须，用于去重）
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code
  FROM b_class.fact_{platform}_{data_domain}_{granularity}
  
  UNION ALL
  
  -- 其他平台和粒度...
  SELECT ... FROM b_class.fact_{platform2}_{data_domain}_{granularity2}
  -- ... 更多平台和粒度
),

-- ====================================================
-- 第2层：数据清洗（统一格式化逻辑，只写一次）
-- ====================================================
cleaned AS (
  SELECT 
    -- 系统字段（直接传递）
    platform_code,
    shop_id,
    data_domain,
    granularity,
    metric_date,
    period_start_date,
    period_end_date,
    period_start_time,
    period_end_time,
    
    -- 字符串字段（直接使用）
    order_id_raw AS order_id,
    
    -- 普通数值字段清洗（统一逻辑）
    NULLIF(REPLACE(REPLACE(sales_amount_raw, ',', ''), ' ', ''), '')::NUMERIC AS sales_amount,
    
    -- 时间字段清洗（使用 NULLIF 处理空字符串）
    COALESCE(
      NULLIF(order_time_raw, '')::TIMESTAMP,
      period_start_time,
      metric_date::TIMESTAMP
    ) AS order_time,
    
    -- 系统字段（用于去重）
    raw_data,
    header_columns,
    data_hash,
    ingest_timestamp,
    currency_code
  FROM field_mapping
),

-- ====================================================
-- 第3层：去重（基于 data_hash，优先级 daily > weekly > monthly）
-- ====================================================
deduplicated AS (
  SELECT 
    *,
    ROW_NUMBER() OVER (
      PARTITION BY platform_code, shop_id, data_hash 
      ORDER BY 
        CASE granularity
          WHEN 'daily' THEN 1
          WHEN 'weekly' THEN 2
          WHEN 'monthly' THEN 3
        END ASC,
        ingest_timestamp DESC
    ) AS rn
  FROM cleaned
)

-- ====================================================
-- 第4层：最终输出（只保留去重后的数据，设置默认值）
-- ====================================================
SELECT 
  platform_code,
  shop_id,
  data_domain,
  granularity,
  metric_date,
  period_start_date,
  period_end_date,
  period_start_time,
  period_end_time,
  order_id,
  COALESCE(sales_amount, 0) AS sales_amount,
  order_time,
  raw_data,
  header_columns,
  data_hash,
  ingest_timestamp,
  currency_code
FROM deduplicated
WHERE rn = 1
```

**格式说明**：
- ✅ **CTE分层**：必须使用4层CTE架构（字段映射 → 数据清洗 → 去重 → 最终输出）
- ✅ **字段映射**：第1层只做字段提取，不做格式化
- ✅ **数据清洗**：第2层统一格式化逻辑，只写一次
- ✅ **去重逻辑**：第3层独立处理去重，职责清晰
- ✅ **最终输出**：第4层设置默认值，统一输出格式

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

**最后更新**: 2025-01-XX（v4.4.1：新增SQL编写规范）  
**维护**: AI Agent Team  
**状态**: ✅ 企业级标准

