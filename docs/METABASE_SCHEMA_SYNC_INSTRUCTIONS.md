# Metabase Schema同步说明

**创建时间**: 2025-11-26  
**状态**: ✅ Schema分离已完成

---

## 📊 Schema分离结果

数据库表已按数据分类组织到不同Schema：

- **a_class**: 7张表（A类数据：用户配置数据）
- **b_class**: 15张表（B类数据：业务数据）
- **c_class**: 4张表（C类数据：计算数据）
- **core**: 18张表（核心ERP表）
- **public**: 9张表（其他表）

---

## 🔄 在Metabase中同步Schema

### 方法1：自动同步（推荐）

1. **登录Metabase**
   - 访问 http://localhost:3000
   - 使用管理员账号登录

2. **进入数据库管理**
   - 点击左侧菜单 "Admin" → "Databases"
   - 找到 "XIHONG_ERP" 数据库
   - 点击数据库名称进入详情页

3. **同步Schema**
   - 点击右上角 **"Sync database schema now"** 按钮
   - 等待同步完成（通常10-30秒）

4. **验证Schema显示**
   - 在 "Tables" 标签中查看
   - 应该能看到按Schema分组的表：
     - `a_class` (7张表)
     - `b_class` (15张表)
     - `c_class` (4张表)
     - `core` (18张表)
     - `public` (9张表)

### 方法2：使用API同步（可选）

如果需要通过API同步，可以使用以下脚本：

```bash
python scripts/sync_dss_tables_to_metabase.py
```

**注意**: 需要设置正确的Metabase管理员密码。

---

## ✅ 验证Schema显示

### 在Metabase中应该看到

1. **Schema分组**:
   - 表按Schema分组显示
   - 每个Schema显示表数量

2. **表列表**:
   - `a_class` schema下应该看到7张表
   - `b_class` schema下应该看到15张表
   - `c_class` schema下应该看到4张表
   - `core` schema下应该看到18张表
   - `public` schema下应该看到9张表

### 如果看不到Schema分组

1. **检查数据库连接**:
   - 确认Metabase连接到正确的PostgreSQL实例
   - 确认数据库名称是 "XIHONG_ERP"

2. **重新同步Schema**:
   - 点击 "Sync database schema now"
   - 等待同步完成

3. **检查Schema权限**:
   - 确认数据库用户有访问所有Schema的权限

---

## 📋 Schema说明

### a_class - A类数据

**定义**: 用户手动配置的业务规则和策略数据

**表列表**:
- `sales_targets_a` - 销售目标配置
- `sales_campaigns_a` - 销售战役配置
- `operating_costs` - 运营成本配置
- `employees` - 员工信息
- `employee_targets` - 员工目标配置
- `attendance_records` - 考勤记录
- `performance_config_a` - 绩效配置

### b_class - B类数据

**定义**: 从外部平台采集的业务交易数据

**表列表**:
- `fact_raw_data_orders_daily/weekly/monthly` - 订单数据
- `fact_raw_data_products_daily/weekly/monthly` - 产品数据
- `fact_raw_data_traffic_daily/weekly/monthly` - 流量数据
- `fact_raw_data_services_daily/weekly/monthly` - 服务数据
- `fact_raw_data_inventory_snapshot` - 库存快照
- `entity_aliases` - 实体别名表
- `staging_raw_data` - 原始数据暂存表

### c_class - C类数据

**定义**: 基于A类和B类数据计算得出的指标和评分

**表列表**:
- `employee_performance` - 员工绩效
- `employee_commissions` - 员工佣金
- `shop_commissions` - 店铺佣金
- `performance_scores_c` - 绩效评分

### core - 核心ERP表

**定义**: 系统必需的管理表和维度表

**表列表**:
- `catalog_files` - 文件目录表
- `field_mapping_*` - 字段映射相关表
- `dim_*` - 维度表
- `fact_sales_orders`, `fact_product_metrics` - 事实表
- `accounts`, `data_quarantine` - 管理表
- 等

---

## 🎯 使用建议

### 在Metabase中查询数据

1. **选择Schema**:
   - 根据数据分类选择对应的Schema
   - 例如：查询业务数据选择`b_class`

2. **选择表**:
   - 在Schema下选择具体的表
   - 例如：`b_class.fact_raw_data_orders_daily`

3. **创建查询**:
   - 使用Metabase的查询构建器
   - 或直接编写SQL查询

### SQL查询示例

```sql
-- 查询A类数据（用户配置）
SELECT * FROM a_class.sales_targets_a;

-- 查询B类数据（业务数据）
SELECT * FROM b_class.fact_raw_data_orders_daily
WHERE order_date >= '2025-01-01';

-- 查询C类数据（计算数据）
SELECT * FROM c_class.employee_performance;

-- 查询核心表
SELECT * FROM core.catalog_files
WHERE status = 'ingested';
```

---

## ⚠️ 注意事项

1. **搜索路径**: 由于设置了`search_path`，也可以直接使用表名（无需指定Schema）
2. **权限**: 确保Metabase数据库用户有访问所有Schema的权限
3. **同步**: Schema变更后需要在Metabase中重新同步

---

**最后更新**: 2025-11-26  
**状态**: ✅ Schema分离完成，Metabase中已显示Schema分组

