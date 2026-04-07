# Metabase DSS架构Dashboard创建指南

## 概述

本文档说明如何在Metabase中基于DSS架构的新表结构创建Dashboard。

## 数据源说明

### B类数据表（原始业务数据）

**订单数据域**：
- `fact_raw_data_orders_daily` - 日度订单数据
- `fact_raw_data_orders_weekly` - 周度订单数据
- `fact_raw_data_orders_monthly` - 月度订单数据

**产品数据域**：
- `fact_raw_data_products_daily` - 日度产品数据
- `fact_raw_data_products_weekly` - 周度产品数据
- `fact_raw_data_products_monthly` - 月度产品数据

**流量数据域**：
- `fact_raw_data_traffic_daily` - 日度流量数据
- `fact_raw_data_traffic_weekly` - 周度流量数据
- `fact_raw_data_traffic_monthly` - 月度流量数据

**服务数据域**：
- `fact_raw_data_services_daily` - 日度服务数据
- `fact_raw_data_services_weekly` - 周度服务数据
- `fact_raw_data_services_monthly` - 月度服务数据

**库存数据域**：
- `fact_raw_data_inventory_snapshot` - 库存快照

### B类数据表结构

所有B类数据表使用JSONB格式存储原始数据：

```sql
CREATE TABLE fact_raw_data_orders_daily (
    id BIGSERIAL PRIMARY KEY,
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(256) NOT NULL,
    data_domain VARCHAR(64) NOT NULL,
    granularity VARCHAR(32) NOT NULL,
    metric_date DATE NOT NULL,
    file_id INTEGER,
    raw_data JSONB NOT NULL,  -- 原始数据（中文字段名作为键）
    header_columns JSONB,     -- 表头字段列表
    data_hash VARCHAR(64) NOT NULL,
    ingest_timestamp TIMESTAMP NOT NULL
);
```

**查询示例**：
```sql
-- 查询订单数据
SELECT 
    metric_date,
    platform_code,
    shop_id,
    raw_data->>'订单号' as order_id,
    raw_data->>'订单金额' as order_amount,
    raw_data->>'订单状态' as order_status
FROM fact_raw_data_orders_daily
WHERE metric_date >= '2025-01-01'
LIMIT 100;
```

### A类数据表（用户配置数据）

- `sales_targets_a` - 销售目标（中文字段名）
- `sales_campaigns_a` - 销售战役（中文字段名）
- `operating_costs` - 运营成本（中文字段名）
- `employees` - 员工档案（中文字段名）
- `employee_targets` - 员工目标（中文字段名）
- `attendance_records` - 考勤记录（中文字段名）
- `performance_config_a` - 绩效权重配置（中文字段名）

**查询示例**：
```sql
-- 查询销售目标
SELECT 
    "店铺ID",
    "年月",
    "目标销售额",
    "目标订单数"
FROM sales_targets_a
WHERE "年月" = '2025-01';
```

### C类数据表（Metabase计算数据）

- `employee_performance` - 员工绩效（中文字段名）
- `employee_commissions` - 员工提成（中文字段名）
- `shop_commissions` - 店铺提成（中文字段名）
- `performance_scores_c` - 店铺绩效（中文字段名）

## 创建Dashboard步骤

### 步骤1：创建Dashboard

1. 登录Metabase
2. 点击左侧菜单 "+ 创建" → "Dashboard"
3. 输入名称：`业务概览（DSS架构）`
4. 点击 "创建"

### 步骤2：创建Question 1 - GMV趋势（折线图）

**数据源**：`fact_raw_data_orders_daily`

**配置**：
1. 选择表：`fact_raw_data_orders_daily`
2. 添加字段：
   - **X轴**：`metric_date`（按日分组）
   - **Y轴**：`raw_data->>'订单金额'`（Sum聚合）
3. 添加筛选器：
   - `platform_code` = 选择平台
   - `shop_id` = 选择店铺
   - `metric_date` >= 日期范围
4. 可视化类型：折线图
5. 保存为：`GMV趋势`

**注意**：如果字段名是中文（如"订单金额"），需要在Metabase中创建自定义字段：
- 字段名：`订单金额`
- 表达式：`raw_data->>'订单金额'`
- 类型：Number

### 步骤3：创建Question 2 - 订单数趋势（折线图）

**数据源**：`fact_raw_data_orders_daily`

**配置**：
1. 选择表：`fact_raw_data_orders_daily`
2. 添加字段：
   - **X轴**：`metric_date`（按日分组）
   - **Y轴**：`raw_data->>'订单数'`（Count聚合，或Sum如果字段是数字）
3. 可视化类型：折线图
4. 保存为：`订单数趋势`

### 步骤4：创建Question 3 - 销售目标达成率（折线图）

**数据源**：需要关联`fact_raw_data_orders_daily`和`sales_targets_a`

**配置**：
1. 创建自定义Question（SQL模式）：
```sql
SELECT 
    o.metric_date as "日期",
    SUM((o.raw_data->>'订单金额')::numeric) as "实际销售额",
    t."目标销售额",
    CASE 
        WHEN t."目标销售额" > 0 
        THEN (SUM((o.raw_data->>'订单金额')::numeric) / t."目标销售额" * 100)
        ELSE 0 
    END as "达成率"
FROM fact_raw_data_orders_daily o
LEFT JOIN sales_targets_a t 
    ON o.shop_id = t."店铺ID" 
    AND TO_CHAR(o.metric_date, 'YYYY-MM') = t."年月"
WHERE o.metric_date >= '2025-01-01'
GROUP BY o.metric_date, t."目标销售额"
ORDER BY o.metric_date;
```

2. 可视化类型：折线图
3. 保存为：`销售目标达成率`

### 步骤5：创建Question 4 - 店铺GMV对比（柱状图）

**数据源**：`fact_raw_data_orders_daily` + `entity_aliases`

**配置**：
1. 创建自定义Question（SQL模式）：
```sql
SELECT 
    e.target_name as "店铺名称",
    SUM((o.raw_data->>'订单金额')::numeric) as "GMV"
FROM fact_raw_data_orders_daily o
LEFT JOIN entity_aliases e 
    ON o.shop_id = e.target_id 
    AND o.platform_code = e.target_platform_code
WHERE o.metric_date >= '2025-01-01'
GROUP BY e.target_name
ORDER BY "GMV" DESC
LIMIT 10;
```

2. 可视化类型：柱状图
3. 保存为：`店铺GMV对比`

### 步骤6：创建Question 5 - 平台对比（饼图）

**数据源**：`fact_raw_data_orders_daily`

**配置**：
1. 选择表：`fact_raw_data_orders_daily`
2. 添加字段：
   - **分组**：`platform_code`
   - **指标**：`raw_data->>'订单金额'`（Sum聚合）
3. 可视化类型：饼图
4. 保存为：`平台GMV对比`

## 自定义字段配置

### 为B类数据表创建自定义字段

由于B类数据使用JSONB格式，需要在Metabase中创建自定义字段来访问JSONB中的值。

**示例：订单金额字段**

1. 进入表详情页：`fact_raw_data_orders_daily`
2. 点击 "Edit metadata"
3. 在 "Fields" 部分，点击 "Add a custom field"
4. 配置：
   - **字段名**：`订单金额`
   - **表达式**：`raw_data->>'订单金额'`
   - **类型**：Number
   - **聚合方式**：Sum（用于聚合查询）

**常用自定义字段**：

| 字段名 | 表达式 | 类型 | 说明 |
|--------|--------|------|------|
| 订单金额 | `raw_data->>'订单金额'` | Number | 订单金额 |
| 订单数 | `raw_data->>'订单数'` | Number | 订单数量 |
| 订单状态 | `raw_data->>'订单状态'` | Text | 订单状态 |
| 产品ID | `raw_data->>'产品ID'` | Text | 产品标识 |
| 产品名称 | `raw_data->>'产品名称'` | Text | 产品名称 |
| 日期 | `metric_date` | Date | 指标日期 |

## 表关联配置

### 关联entity_aliases表

1. 进入表详情页：`fact_raw_data_orders_daily`
2. 点击 "Edit metadata"
3. 在 "Foreign Keys" 部分，点击 "Add a foreign key"
4. 配置：
   - **Foreign Table**：`entity_aliases`
   - **Foreign Key Column**：`shop_id`
   - **Referenced Table Column**：`target_id`

## 注意事项

1. **JSONB字段访问**：使用`raw_data->>'字段名'`访问JSONB中的值
2. **中文字段名**：在SQL查询中使用中文字段名时，必须使用双引号
3. **类型转换**：JSONB中的数值需要转换为数字类型：`(raw_data->>'订单金额')::numeric`
4. **空值处理**：使用`COALESCE`处理可能的NULL值
5. **性能优化**：对于大量数据，建议创建物化视图或使用Metabase的缓存功能

## 验证清单

- [ ] Dashboard已创建
- [ ] 所有Question已创建并添加到Dashboard
- [ ] 自定义字段已配置
- [ ] 表关联已配置
- [ ] 筛选器正常工作
- [ ] 数据正确显示

