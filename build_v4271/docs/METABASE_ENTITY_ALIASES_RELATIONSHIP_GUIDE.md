# Metabase Entity Aliases 表关联配置指南

## 概述

本文档说明如何在Metabase中配置`entity_aliases`表与其他表的关联关系，实现账号和店铺的统一对齐。

## 关联关系设计

### entity_aliases表结构

**关键字段**：
- `source_platform` - 源平台代码
- `source_type` - 源类型（account/shop/store）
- `source_name` - 源名称
- `target_type` - 目标类型（account/shop）
- `target_id` - 目标ID（统一标识）
- `target_platform_code` - 目标平台代码

### 关联关系

#### 1. B类数据表关联

**关联字段**：
- `fact_raw_data_*.shop_id` = `entity_aliases.target_id`
- `fact_raw_data_*.platform_code` = `entity_aliases.target_platform_code`

**适用表**：
- `fact_raw_data_orders_daily/weekly/monthly`
- `fact_raw_data_products_daily/weekly/monthly`
- `fact_raw_data_traffic_daily/weekly/monthly`
- `fact_raw_data_services_daily/weekly/monthly`
- `fact_raw_data_inventory_snapshot`

#### 2. A类数据表关联

**关联字段**：
- `sales_targets_a."店铺ID"` = `entity_aliases.target_id`
- `sales_campaigns_a."店铺ID"` = `entity_aliases.target_id`
- `operating_costs."店铺ID"` = `entity_aliases.target_id`

**注意**：中文字段名需要使用双引号。

#### 3. C类数据表关联

**关联字段**：
- `shop_commissions."店铺ID"` = `entity_aliases.target_id`
- `performance_scores_c."店铺ID"` = `entity_aliases.target_id`

## 配置步骤

### 步骤1：进入表管理页面

1. 登录Metabase
2. 点击左侧菜单 "Admin" → "Databases"
3. 选择 "xihong_erp" 数据库
4. 点击 "Tables" 标签

### 步骤2：配置entity_aliases表关联

1. 找到 `entity_aliases` 表
2. 点击表名进入表详情页
3. 点击右上角 "Edit metadata" 按钮

### 步骤3：添加外键关联

#### 关联B类数据表

1. 在 "Foreign Keys" 部分，点击 "Add a foreign key"
2. 配置关联：
   - **Foreign Table**: 选择 `fact_raw_data_orders_daily`（或其他B类表）
   - **Foreign Key Column**: `target_id`
   - **Referenced Table Column**: `shop_id`
3. 点击 "Save" 保存
4. 重复以上步骤，为所有B类数据表配置关联

#### 关联A类数据表

1. 在 "Foreign Keys" 部分，点击 "Add a foreign key"
2. 配置关联：
   - **Foreign Table**: 选择 `sales_targets_a`（或其他A类表）
   - **Foreign Key Column**: `target_id`
   - **Referenced Table Column**: `店铺ID`（注意使用双引号）
3. 点击 "Save" 保存
4. 重复以上步骤，为所有A类数据表配置关联

### 步骤4：验证关联

1. 创建一个测试Question：
   - 选择任意B类或A类数据表
   - 添加筛选器：选择 `shop_id` 或 `店铺ID`
   - 添加关联表：选择 `entity_aliases`
   - 查看是否能正确关联显示店铺信息

## 使用示例

### 示例1：查询订单数据并关联店铺信息

```sql
SELECT 
    o.*,
    e.target_name as shop_name,
    e.source_name as original_shop_name
FROM fact_raw_data_orders_daily o
LEFT JOIN entity_aliases e 
    ON o.shop_id = e.target_id 
    AND o.platform_code = e.target_platform_code
WHERE o.metric_date >= '2025-01-01'
LIMIT 100;
```

### 示例2：查询销售目标并关联店铺信息

```sql
SELECT 
    s."店铺ID",
    s."年月",
    s."目标销售额",
    e.target_name as shop_name,
    e.source_name as original_shop_name
FROM sales_targets_a s
LEFT JOIN entity_aliases e 
    ON s."店铺ID" = e.target_id
WHERE s."年月" = '2025-01'
```

## 注意事项

1. **中文字段名**：在SQL查询中使用中文字段名时，必须使用双引号包裹
2. **关联方向**：关联是双向的，可以从任意一方查询另一方
3. **性能优化**：Metabase会自动使用关联关系优化查询，无需手动JOIN
4. **空值处理**：如果`target_id`为空，关联将返回NULL

## 验证清单

- [ ] entity_aliases表已同步到Metabase
- [ ] 所有B类数据表已配置关联
- [ ] 所有A类数据表已配置关联
- [ ] 测试查询能正确关联店铺信息
- [ ] 中文字段名关联配置正确

