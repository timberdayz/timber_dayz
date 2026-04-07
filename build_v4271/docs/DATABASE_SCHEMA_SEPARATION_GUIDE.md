# 数据库Schema分离指南

**创建时间**: 2025-11-26  
**状态**: ✅ 已完成  
**目的**: 按数据分类组织表，便于Metabase中清晰区分A类、B类、C类数据

---

## 📊 Schema分离结果

### Schema结构

```
PostgreSQL数据库 (xihong_erp)
├── a_class/          # A类数据（用户配置数据）- 7张表
├── b_class/          # B类数据（业务数据）- 15张表
├── c_class/          # C类数据（计算数据）- 4张表
├── core/             # 核心ERP表（系统必需）- 20张表
├── finance/          # 财务域表（可选）- 待迁移
└── public/           # 其他表（视图、物化视图等）
```

### 各Schema表统计

| Schema | 表数量 | 说明 |
|--------|--------|------|
| `a_class` | 7张 | A类数据：用户配置数据 |
| `b_class` | 15张 | B类数据：业务数据 |
| `c_class` | 4张 | C类数据：计算数据 |
| `core` | 18张 | 核心ERP表 |
| `finance` | 0张 | 财务域表（待迁移） |
| `public` | 剩余表 | 视图、物化视图等 |

---

## 📋 表分类详情

### A类数据表（a_class schema）- 7张

**定义**: 用户手动配置的业务规则和策略数据

- `sales_targets_a` - 销售目标配置
- `sales_campaigns_a` - 销售战役配置
- `operating_costs` - 运营成本配置
- `employees` - 员工信息
- `employee_targets` - 员工目标配置
- `attendance_records` - 考勤记录
- `performance_config_a` - 绩效配置

### B类数据表（b_class schema）- 15张

**定义**: 从外部平台采集的业务交易数据

**订单数据（3张）**:
- `fact_raw_data_orders_daily` - 订单数据（日度）
- `fact_raw_data_orders_weekly` - 订单数据（周度）
- `fact_raw_data_orders_monthly` - 订单数据（月度）

**产品数据（3张）**:
- `fact_raw_data_products_daily` - 产品数据（日度）
- `fact_raw_data_products_weekly` - 产品数据（周度）
- `fact_raw_data_products_monthly` - 产品数据（月度）

**流量数据（3张）**:
- `fact_raw_data_traffic_daily` - 流量数据（日度）
- `fact_raw_data_traffic_weekly` - 流量数据（周度）
- `fact_raw_data_traffic_monthly` - 流量数据（月度）

**服务数据（3张）**:
- `fact_raw_data_services_daily` - 服务数据（日度）
- `fact_raw_data_services_weekly` - 服务数据（周度）
- `fact_raw_data_services_monthly` - 服务数据（月度）

**其他（3张）**:
- `fact_raw_data_inventory_snapshot` - 库存快照
- `entity_aliases` - 实体别名表
- `staging_raw_data` - 原始数据暂存表

### C类数据表（c_class schema）- 4张

**定义**: 基于A类和B类数据计算得出的指标和评分

- `employee_performance` - 员工绩效
- `employee_commissions` - 员工佣金
- `shop_commissions` - 店铺佣金
- `performance_scores_c` - 绩效评分

### 核心ERP表（core schema）- 20张

**定义**: 系统必需的管理表和维度表

**文件管理**:
- `catalog_files` - 文件目录表
- `data_files` - 数据文件表
- `data_records` - 数据记录表

**字段映射**:
- `field_mapping_templates` - 字段映射模板表
- `field_mapping_template_items` - 字段映射模板明细表
- `field_mapping_dictionary` - 字段映射辞典表
- `mapping_sessions` - 映射会话表

**维度表**:
- `dim_platform` - 平台维度表
- `dim_shop` - 店铺维度表
- `dim_product` - 产品维度表
- `dim_metric_formulas` - 指标公式维度表

**事实表**:
- `fact_sales_orders` - 销售订单事实表
- `fact_product_metrics` - 产品指标事实表

**管理表**:
- `accounts` - 账号表
- `collection_tasks` - 采集任务表
- `data_quarantine` - 数据隔离表
- `staging_orders` - 订单暂存表
- `staging_product_metrics` - 产品指标暂存表
- `sales_targets` - 销售目标表
- `alembic_version` - Alembic版本表

**注意**: `field_mapping_templates`和`field_mapping_template_items`表可能不存在或已在其他位置

---

## 🔧 技术实现

### 1. 删除Superset表

**执行脚本**: `sql/cleanup_superset_tables.sql`

**结果**: ✅ 成功删除47张Superset系统表

### 2. 创建Schema

**执行脚本**: `sql/create_data_class_schemas.sql`

**创建的Schema**:
- `a_class` - A类数据
- `b_class` - B类数据
- `c_class` - C类数据
- `core` - 核心ERP表
- `finance` - 财务域表

### 3. 迁移表到Schema

**执行脚本**: `sql/migrate_tables_to_schemas.sql`

**迁移结果**:
- ✅ A类表：7张已迁移
- ✅ B类表：15张已迁移
- ✅ C类表：4张已迁移
- ✅ 核心表：20张已迁移

### 4. 设置搜索路径

**执行脚本**: `sql/set_search_path.sql`

**配置**:
```sql
ALTER DATABASE xihong_erp SET search_path = core, a_class, b_class, c_class, finance, public;
```

**作用**: 保持代码向后兼容，无需修改SQL查询即可访问表

---

## 📊 Metabase中的效果

### Schema分组显示

在Metabase中，表会按Schema分组显示：

```
XIHONG_ERP数据库
├── a_class (7张表)
│   ├── sales_targets_a
│   ├── sales_campaigns_a
│   └── ...
├── b_class (15张表)
│   ├── fact_raw_data_orders_daily
│   ├── fact_raw_data_products_daily
│   └── ...
├── c_class (4张表)
│   ├── employee_performance
│   └── ...
├── core (20张表)
│   ├── catalog_files
│   ├── dim_platform
│   └── ...
└── finance (财务域表)
```

### 优势

1. **清晰分类**: 用户可以立即知道哪些是A类、B类、C类数据
2. **易于查找**: 按数据分类快速定位表
3. **权限管理**: 可以为不同Schema设置不同权限
4. **性能优化**: 可以针对不同Schema设置不同的优化策略

---

## ⚠️ 注意事项

### 1. 代码兼容性

由于设置了`search_path`，现有代码无需修改即可访问表：

```python
# 仍然可以这样查询（无需指定schema）
from modules.core.db import CatalogFile
file = db.query(CatalogFile).filter(CatalogFile.id == 1).first()

# 也可以显式指定schema（推荐）
from sqlalchemy import text
result = db.execute(text("SELECT * FROM core.catalog_files WHERE id = 1"))
```

### 2. 外键约束

如果表之间有外键关系，迁移后外键仍然有效（PostgreSQL会自动处理）。

### 3. 视图和物化视图

视图和物化视图定义中的表引用需要更新为`schema.table`格式。

### 4. Metabase同步

在Metabase中需要重新同步Schema才能看到新的Schema分组。

---

## 🔍 验证命令

### 查看各Schema的表数量

```sql
SELECT 
    schemaname,
    COUNT(*) as table_count
FROM pg_tables
WHERE schemaname IN ('a_class', 'b_class', 'c_class', 'core', 'finance', 'public')
GROUP BY schemaname
ORDER BY schemaname;
```

### 查看各Schema的表列表

```sql
SELECT 
    schemaname,
    tablename
FROM pg_tables
WHERE schemaname IN ('a_class', 'b_class', 'c_class', 'core', 'finance')
ORDER BY schemaname, tablename;
```

### 验证搜索路径

```sql
SHOW search_path;
```

---

## 📚 相关文档

- `sql/cleanup_superset_tables.sql` - 删除Superset表脚本
- `sql/create_data_class_schemas.sql` - 创建Schema脚本
- `sql/migrate_tables_to_schemas.sql` - 迁移表脚本
- `sql/set_search_path.sql` - 设置搜索路径脚本
- `sql/verify_schema_separation.sql` - 验证脚本
- `docs/DATABASE_TABLES_ANALYSIS.md` - 数据库表分析报告
- `docs/CORE_DATA_FLOW.md` - 核心数据流程设计

---

**最后更新**: 2025-11-26  
**状态**: ✅ Schema分离完成，Superset表已删除

