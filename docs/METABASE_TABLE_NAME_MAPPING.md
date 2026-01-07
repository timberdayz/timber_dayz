# Metabase表名映射参考

## 📋 PostgreSQL表名 vs Metabase显示名

PostgreSQL中的表名是小写加下划线，但Metabase可能显示为不同的格式。

### B类数据表（13张）

| PostgreSQL表名 | Metabase可能显示名 |
|---------------|-------------------|
| `fact_raw_data_orders_daily` | Fact Raw Data Orders Daily |
| `fact_raw_data_orders_weekly` | Fact Raw Data Orders Weekly |
| `fact_raw_data_orders_monthly` | Fact Raw Data Orders Monthly |
| `fact_raw_data_products_daily` | Fact Raw Data Products Daily |
| `fact_raw_data_products_weekly` | Fact Raw Data Products Weekly |
| `fact_raw_data_products_monthly` | Fact Raw Data Products Monthly |
| `fact_raw_data_traffic_daily` | Fact Raw Data Traffic Daily |
| `fact_raw_data_traffic_weekly` | Fact Raw Data Traffic Weekly |
| `fact_raw_data_traffic_monthly` | Fact Raw Data Traffic Monthly |
| `fact_raw_data_services_daily` | Fact Raw Data Services Daily |
| `fact_raw_data_services_weekly` | Fact Raw Data Services Weekly |
| `fact_raw_data_services_monthly` | Fact Raw Data Services Monthly |
| `fact_raw_data_inventory_snapshot` | Fact Raw Data Inventory Snapshot |

### A类数据表（7张）

| PostgreSQL表名 | Metabase可能显示名 |
|---------------|-------------------|
| `sales_targets_a` | Sales Targets A |
| `sales_campaigns_a` | Sales Campaigns A |
| `operating_costs` | Operating Costs |
| `employees` | Employees |
| `employee_targets` | Employee Targets |
| `attendance_records` | Attendance Records |
| `performance_config_a` | Performance Config A |

### C类数据表（4张）

| PostgreSQL表名 | Metabase可能显示名 |
|---------------|-------------------|
| `employee_performance` | Employee Performance |
| `employee_commissions` | Employee Commissions |
| `shop_commissions` | Shop Commissions |
| `performance_scores_c` | Performance Scores C |

### 其他表（2张）

| PostgreSQL表名 | Metabase可能显示名 |
|---------------|-------------------|
| `entity_aliases` | Entity Aliases |
| `staging_raw_data` | Staging Raw Data |

## 🔍 在Metabase中查找表

### 方法1：使用搜索功能

在Metabase的数据库页面，使用搜索框搜索：
- 搜索 "raw data" 找到所有B类表
- 搜索 "employee" 找到员工相关表
- 搜索 "sales" 找到销售相关表
- 搜索 "entity" 找到entity_aliases表

### 方法2：按字母顺序查找

表是按字母顺序排列的，可以：
- 查找 "F" 开头的表（Fact Raw Data...）
- 查找 "E" 开头的表（Employee..., Entity...）
- 查找 "S" 开头的表（Sales..., Shop..., Staging...）
- 查找 "O" 开头的表（Operating...）
- 查找 "P" 开头的表（Performance...）

### 方法3：检查表总数

在Metabase中，数据库详情页应该显示表的总数。如果显示的表数少于PostgreSQL中的表数，说明有表未同步。

## ⚠️ 常见问题

### Q1: 为什么有些表看不到？

**可能原因**：
1. 表过滤设置排除了某些表
2. Schema同步不完整
3. 表名大小写问题导致显示不同

**解决方案**：
1. 检查数据库连接配置中的表过滤规则
2. 重新同步Schema
3. 使用搜索功能查找表

### Q2: 表名显示不正确

**原因**：Metabase会自动将下划线转换为空格，并首字母大写

**解决方案**：这是正常的，不影响使用

### Q3: 如何确认所有表都已同步？

**方法**：
1. 在PostgreSQL中查询表数量：`SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND ...`
2. 在Metabase中查看表列表
3. 对比数量是否一致

---

**最后更新**: 2025-11-26 17:05

