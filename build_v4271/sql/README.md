# PostgreSQL视图层架构文档

## 📚 目录结构

```
sql/
├── deploy_views.sql              # 一键部署脚本（推荐使用）
├── views/                        # 视图定义
│   ├── atomic/                   # Layer 1: 原子视图（6个）
│   │   ├── view_orders_atomic.sql
│   │   ├── view_product_metrics_atomic.sql
│   │   ├── view_inventory_atomic.sql
│   │   ├── view_expenses_atomic.sql
│   │   ├── view_targets_atomic.sql
│   │   └── view_campaigns_atomic.sql
│   ├── aggregate/                # Layer 2: 聚合物化视图（3个）
│   │   ├── mv_daily_sales_summary.sql
│   │   ├── mv_monthly_shop_performance.sql
│   │   └── mv_product_sales_ranking.sql
│   └── wide/                     # Layer 3: 宽表视图（2个）
│       ├── view_shop_performance_wide.sql
│       └── view_product_performance_wide.sql
├── functions/                    # 函数定义
│   └── refresh_superset_materialized_views.sql
└── migrations/                   # 数据库迁移脚本
    ├── 001_create_a_class_data_tables.sql
    └── 002_create_indexes.sql
```

## 🚀 快速开始

### 一键部署（推荐）

```bash
# 1. 连接到数据库并执行部署脚本
psql -h localhost -U your_user -d xihong_erp -f sql/deploy_views.sql

# 2. 更新统计信息
psql -h localhost -U your_user -d xihong_erp -c "VACUUM ANALYZE;"

# 3. 刷新物化视图
psql -h localhost -U your_user -d xihong_erp -c "SELECT * FROM refresh_superset_materialized_views(NULL, FALSE);"
```

### 分步部署（手动）

```bash
# Step 1: 创建A类数据表
psql -h localhost -U your_user -d xihong_erp -f sql/migrations/001_create_a_class_data_tables.sql

# Step 2: 创建原子视图
for file in sql/views/atomic/*.sql; do
    psql -h localhost -U your_user -d xihong_erp -f "$file"
done

# Step 3: 创建聚合物化视图
for file in sql/views/aggregate/*.sql; do
    psql -h localhost -U your_user -d xihong_erp -f "$file"
done

# Step 4: 创建宽表视图
for file in sql/views/wide/*.sql; do
    psql -h localhost -U your_user -d xihong_erp -f "$file"
done

# Step 5: 创建刷新函数
psql -h localhost -U your_user -d xihong_erp -f sql/functions/refresh_superset_materialized_views.sql

# Step 6: 创建索引
psql -h localhost -U your_user -d xihong_erp -f sql/migrations/002_create_indexes.sql
```

## 📊 三层视图架构

### Layer 1: 原子视图（Atomic Views）

**目的**: 标准化单表视图，添加派生字段

| 视图名称 | 说明 | 依赖表 | 主要字段 |
|---------|------|--------|---------|
| `view_orders_atomic` | 订单原子视图 | `fact_orders`, `dim_shops` | 时间维度、价值分级、时间段标签 |
| `view_product_metrics_atomic` | 产品指标原子视图 | `fact_product_metrics`, `dim_products` | CTR、转化率、加购率 |
| `view_inventory_atomic` | 库存原子视图 | `fact_inventory`, `dim_products` | 库存健康度、库存价值 |
| `view_expenses_atomic` | 费用原子视图 | `fact_expenses`, `dim_shops` | 费用类型标准化、审批状态 |
| `view_targets_atomic` | 目标原子视图（A类） | `sales_targets`, `fact_orders` | 达成率、目标差距 |
| `view_campaigns_atomic` | 战役原子视图（A类） | `campaign_targets`, `fact_orders` | 战役进度、ROI |

**示例查询**:
```sql
-- 查询订单原子视图
SELECT * FROM view_orders_atomic 
WHERE order_period = '2025-01' AND order_value_tier = 'High';

-- 查询产品指标原子视图
SELECT product_name, ctr, conversion_rate, sales_amount
FROM view_product_metrics_atomic 
WHERE metric_period = '2025-01' AND conversion_rate > 5;
```

### Layer 2: 聚合物化视图（Aggregate Materialized Views）

**目的**: 预计算聚合指标，提升查询性能

| 视图名称 | 说明 | 刷新策略 | 主要指标 |
|---------|------|---------|---------|
| `mv_daily_sales_summary` | 每日销售汇总 | 增量（每小时） | 订单数、买家数、销售额、时间段分布 |
| `mv_monthly_shop_performance` | 月度店铺绩效 | 全量（每月） | 复购率、活跃天数、平均客单价 |
| `mv_product_sales_ranking` | 产品销售排行榜 | 全量（每日） | TopN排名、销售指标、转化率 |

**刷新命令**:
```sql
-- 刷新所有物化视图
SELECT * FROM refresh_superset_materialized_views(NULL, FALSE);

-- 刷新特定视图
SELECT * FROM refresh_superset_materialized_views(
    ARRAY['mv_daily_sales_summary'],
    FALSE
);

-- 查看刷新日志
SELECT * FROM mv_refresh_log ORDER BY start_time DESC LIMIT 10;
```

### Layer 3: 宽表视图（Wide Views）

**目的**: 整合A+B+C类数据，提供一站式业务全景

| 视图名称 | 说明 | 整合数据 | 主要KPI |
|---------|------|---------|---------|
| `view_shop_performance_wide` | 店铺综合绩效宽表 | 销售+库存+成本+目标 | 销售达成率、利润率、绩效评分 |
| `view_product_performance_wide` | 产品全景视图 | 指标+库存+排名 | 产品综合评分、库存风险、流量效率 |

**Superset使用示例**:
```sql
-- 店铺销售达成率排名
SELECT shop_name, sales_achievement_rate, profit_margin, performance_score 
FROM view_shop_performance_wide 
WHERE sale_period = '2025-01' 
ORDER BY sales_achievement_rate DESC;

-- 产品综合评分Top 10
SELECT product_name, product_performance_score, revenue_rank, stock_risk_level
FROM view_product_performance_wide 
WHERE metric_period = '2025-01' 
ORDER BY product_performance_score DESC 
LIMIT 10;
```

## 🔧 A类数据管理

### 销售目标（Sales Targets）

```sql
-- 插入销售目标
INSERT INTO sales_targets (shop_id, year_month, target_sales_amount, target_order_count, created_by)
VALUES ('shop_001', '2025-01', 1000000.00, 5000, 'admin');

-- 查询销售目标
SELECT * FROM sales_targets WHERE year_month = '2025-01';

-- 更新销售目标
UPDATE sales_targets 
SET target_sales_amount = 1200000.00 
WHERE shop_id = 'shop_001' AND year_month = '2025-01';
```

### 战役目标（Campaign Targets）

```sql
-- 插入战役目标
INSERT INTO campaign_targets (
    platform_code, campaign_name, start_date, end_date, 
    target_gmv, target_roi, budget_amount, created_by
)
VALUES (
    'shopee', '双十一大促', '2025-11-01', '2025-11-11', 
    5000000.00, 3.5, 1400000.00, 'admin'
);

-- 查询进行中的战役
SELECT * FROM view_campaigns_atomic WHERE campaign_status = 'In Progress';
```

### 经营成本（Operating Costs）

```sql
-- 插入经营成本
INSERT INTO operating_costs (
    shop_id, year_month, rent, salary, marketing, logistics, other, created_by
)
VALUES (
    'shop_001', '2025-01', 50000.00, 200000.00, 100000.00, 80000.00, 30000.00, 'admin'
);

-- 查询成本明细
SELECT * FROM operating_costs WHERE year_month = '2025-01';
```

## 📈 性能优化

### 索引说明

系统已创建以下类型的索引：

1. **联合索引**: 店铺+日期、平台+日期（最常用查询组合）
2. **部分索引**: 已完成订单、缺货产品（节省空间）
3. **GIN索引**: JSONB字段（支持JSON查询）
4. **B-tree索引**: 排序字段（金额、日期）

### 性能监控

```sql
-- 查看索引大小
SELECT
    schemaname || '.' || tablename AS table_name,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;

-- 查看物化视图刷新性能
SELECT 
    view_name,
    AVG(duration_seconds) AS avg_duration,
    MAX(duration_seconds) AS max_duration,
    COUNT(*) AS refresh_count
FROM mv_refresh_log
WHERE start_time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY view_name;
```

### 建议的定时刷新策略

```sql
-- 使用pg_cron（需要先安装扩展）
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 每天凌晨1点刷新所有物化视图
SELECT cron.schedule(
    'refresh-superset-mvs', 
    '0 1 * * *', 
    'SELECT refresh_superset_materialized_views(NULL, FALSE);'
);

-- 每小时刷新每日销售汇总
SELECT cron.schedule(
    'refresh-daily-sales', 
    '0 * * * *', 
    'SELECT refresh_daily_sales_incremental(1);'
);
```

## 🔍 验证和测试

### 验证部署

```sql
-- 查看创建的视图
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND (table_name LIKE 'view_%' OR table_name LIKE 'mv_%')
ORDER BY table_name;

-- 查看创建的函数
SELECT routine_name, routine_type 
FROM information_schema.routines 
WHERE routine_schema = 'public' 
AND routine_name LIKE 'refresh%';

-- 查看创建的A类数据表
SELECT table_name 
FROM information_schema.tables 
WHERE table_name IN ('sales_targets', 'campaign_targets', 'operating_costs');
```

### 测试查询

```sql
-- 测试原子视图
SELECT COUNT(*) FROM view_orders_atomic;
SELECT COUNT(*) FROM view_product_metrics_atomic;

-- 测试物化视图
SELECT COUNT(*) FROM mv_daily_sales_summary;
SELECT COUNT(*) FROM mv_monthly_shop_performance;

-- 测试宽表视图
SELECT COUNT(*) FROM view_shop_performance_wide;
SELECT COUNT(*) FROM view_product_performance_wide;
```

## ⚠️ 注意事项

1. **首次部署**: 物化视图首次创建可能需要较长时间（取决于数据量）
2. **依赖关系**: Layer 3视图依赖Layer 2，请按顺序部署
3. **A类数据表**: 需要手动插入初始数据（目标、成本等）
4. **外键约束**: 如果dim_shops表不存在，部分外键约束会失败（不影响功能）
5. **权限**: 确保数据库用户有CREATE VIEW、CREATE TABLE、CREATE FUNCTION权限

## 📞 故障排除

### 问题1: 视图创建失败

**原因**: 依赖的表不存在  
**解决**: 确认fact_orders、fact_product_metrics等表已存在

### 问题2: 物化视图刷新超时

**原因**: 数据量过大  
**解决**: 使用分批刷新或增加`statement_timeout`参数

### 问题3: 外键约束失败

**原因**: dim_shops表不存在  
**解决**: 先创建dim_shops表，或忽略外键约束（不影响功能）

## 📚 相关文档

- [架构设计文档](../openspec/changes/refactor-backend-to-dss-architecture/design.md)
- [数据库设计规格](../openspec/changes/refactor-backend-to-dss-architecture/specs/database-design/spec.md)
- [实施任务清单](../openspec/changes/refactor-backend-to-dss-architecture/tasks.md)

---

**版本**: 1.0.0  
**创建日期**: 2025-11-22  
**维护者**: AI Agent

