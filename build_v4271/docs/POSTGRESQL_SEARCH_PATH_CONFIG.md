# PostgreSQL search_path 配置指南

## 概述

在DSS架构重构中，我们将数据库表按功能分类到不同的Schema中：
- `public`: 默认Schema（保留兼容性）
- `b_class`: B类数据表（业务数据，按data_domain+granularity分表）
- `a_class`: A类数据表（用户配置数据，中文字段名）
- `c_class`: C类数据表（计算数据，中文字段名）
- `core`: 核心ERP表（管理表、维度表等）
- `finance`: 财务域表（采购、库存、发票等）

为了简化代码，我们配置了PostgreSQL的`search_path`，使应用程序可以访问所有Schema中的表，而无需在SQL查询中显式指定Schema前缀。

---

## 配置位置

### 后端数据库连接配置

**文件**: `backend/models/database.py`

**配置代码**:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 配置search_path
connect_args = {
    "options": "-c statement_timeout=30000 "
               "-c idle_in_transaction_session_timeout=300000 "
               "-c search_path=public,b_class,a_class,c_class,core,finance"
}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)
```

**说明**:
- `search_path=public,b_class,a_class,c_class,core,finance`: 按顺序搜索Schema
- 如果表名在多个Schema中存在，PostgreSQL会使用第一个找到的表
- 建议将最常用的Schema放在前面（如`b_class`）

---

## 使用方式

### 1. SQLAlchemy ORM查询

配置`search_path`后，可以直接使用表名，无需Schema前缀：

```python
# ✅ 正确：直接使用表名
from modules.core.db import FactRawDataOrdersDaily

# 查询B类数据表
orders = db.query(FactRawDataOrdersDaily).filter(
    FactRawDataOrdersDaily.data_domain == 'orders'
).all()

# 查询A类数据表
from modules.core.db import SalesTargetsA
targets = db.query(SalesTargetsA).filter(
    SalesTargetsA.year_month == '2025-01'
).all()
```

### 2. 原生SQL查询

在原生SQL中也可以直接使用表名：

```python
# ✅ 正确：直接使用表名
result = db.execute(
    text("SELECT * FROM fact_raw_data_orders_daily WHERE metric_date >= :date"),
    {"date": "2025-01-01"}
)
```

### 3. 显式指定Schema（可选）

如果需要显式指定Schema（例如避免歧义），仍然可以使用Schema前缀：

```python
# ✅ 也可以：显式指定Schema
result = db.execute(
    text("SELECT * FROM b_class.fact_raw_data_orders_daily WHERE metric_date >= :date"),
    {"date": "2025-01-01"}
)
```

---

## 注意事项

### 1. Schema搜索顺序

`search_path`中的Schema按顺序搜索。如果表名在多个Schema中存在，PostgreSQL会使用第一个找到的表。

**建议**:
- 将最常用的Schema放在前面（如`b_class`）
- 避免在不同Schema中创建同名表（除非有特殊需求）

### 2. 表名冲突

如果不同Schema中有同名表，可能会导致查询结果不符合预期。

**解决方案**:
- 使用显式Schema前缀：`schema.table_name`
- 或者调整`search_path`顺序，将最常用的Schema放在前面

### 3. 性能考虑

`search_path`对性能影响很小，但建议：
- 保持`search_path`中的Schema数量合理（当前6个Schema是合理的）
- 避免频繁修改`search_path`（每次修改需要重新建立连接）

### 4. 安全性

`search_path`配置在连接级别，所有使用该连接的查询都会应用相同的`search_path`。

**安全建议**:
- 确保`search_path`中的Schema都是可信的
- 在生产环境中，考虑使用Row Level Security (RLS)进一步限制数据访问

---

## 验证配置

### 1. 检查当前search_path

在PostgreSQL中执行：
```sql
SHOW search_path;
```

预期输出：
```
search_path
----------------------------------------
public, b_class, a_class, c_class, core, finance
```

### 2. 测试查询

测试是否可以访问不同Schema中的表：

```python
# 测试B类数据表
from modules.core.db import FactRawDataOrdersDaily
orders = db.query(FactRawDataOrdersDaily).first()
print(f"B类数据表查询成功: {orders is not None}")

# 测试A类数据表
from modules.core.db import SalesTargetsA
targets = db.query(SalesTargetsA).first()
print(f"A类数据表查询成功: {targets is not None}")
```

### 3. 验证代码访问

运行以下测试脚本验证代码可以访问所有Schema中的表：

```python
# scripts/test_search_path.py
from backend.models.database import SessionLocal
from modules.core.db import (
    FactRawDataOrdersDaily,  # b_class
    SalesTargetsA,  # a_class
    EmployeePerformance,  # c_class
    CatalogFile,  # core
)

db = SessionLocal()
try:
    # 测试B类数据表
    b_count = db.query(FactRawDataOrdersDaily).count()
    print(f"✅ B类数据表访问成功: {b_count} 条记录")
    
    # 测试A类数据表
    a_count = db.query(SalesTargetsA).count()
    print(f"✅ A类数据表访问成功: {a_count} 条记录")
    
    # 测试C类数据表
    c_count = db.query(EmployeePerformance).count()
    print(f"✅ C类数据表访问成功: {c_count} 条记录")
    
    # 测试core Schema
    core_count = db.query(CatalogFile).count()
    print(f"✅ Core Schema访问成功: {core_count} 条记录")
    
    print("\n✅ 所有Schema访问测试通过！")
finally:
    db.close()
```

---

## 故障排查

### 问题1: 表不存在错误

**错误信息**:
```
relation "fact_raw_data_orders_daily" does not exist
```

**可能原因**:
1. `search_path`未正确配置
2. 表在错误的Schema中
3. 连接未使用配置的`search_path`

**解决方案**:
1. 检查`backend/models/database.py`中的`connect_args`配置
2. 验证表是否存在于正确的Schema中：`SELECT * FROM b_class.fact_raw_data_orders_daily LIMIT 1;`
3. 重新建立数据库连接

### 问题2: 查询到错误的表

**症状**: 查询结果不符合预期

**可能原因**: 多个Schema中有同名表，`search_path`顺序导致查询到错误的表

**解决方案**:
1. 检查是否有同名表：`SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = 'table_name';`
2. 使用显式Schema前缀：`schema.table_name`
3. 调整`search_path`顺序

---

## 相关文档

- [PostgreSQL search_path官方文档](https://www.postgresql.org/docs/current/ddl-schemas.html#DDL-SCHEMAS-PATH)
- [SQLAlchemy连接参数文档](https://docs.sqlalchemy.org/en/14/core/engines.html#sqlalchemy.create_engine.params.connect_args)
- [DSS架构设计文档](docs/DSS_ARCHITECTURE.md)

---

**创建时间**: 2025-11-27  
**最后更新**: 2025-11-27  
**维护**: AI Agent Team

