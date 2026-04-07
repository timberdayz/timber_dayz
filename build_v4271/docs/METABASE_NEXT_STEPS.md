# Metabase下一步操作指南

## 当前状态

✅ **已完成**：
- Metabase容器已启动并运行正常
- PostgreSQL数据库已连接（xihong_erp）
- 数据库表/视图已同步到Metabase

⚠️ **重要发现**：
- 数据库中视图/表目前**没有数据**（0行）
- 这是**正常的**，因为还没有导入业务数据
- **可以继续创建Dashboard结构**，数据导入后会自动显示

## 立即需要做的操作

### 步骤1：验证表/视图已同步 ✅

**状态**：表/视图已经同步到Metabase（您已经可以看到它们了）

**重要说明**：
- ✅ 表/视图结构已同步
- ⚠️ 目前**没有数据**（0行）- 这是正常的！
- ✅ 即使没有数据，也可以继续创建Dashboard结构
- ✅ 当业务数据导入后，Dashboard会自动显示数据

**关键表/视图列表**（已同步）：
- ✅ `view_shop_performance_wide` - **核心表！** 店铺综合绩效宽表
- ✅ `view_product_performance_wide` - 产品全景视图
- ✅ `mv_daily_sales_summary` - 每日销售汇总
- ✅ `mv_monthly_shop_performance` - 月度店铺绩效
- ✅ `view_orders_atomic` - 订单原子视图

**为什么显示"没有结果"？**
- 数据库中这些视图目前是空的（0行数据）
- 这是正常的，因为还没有导入业务数据
- 视图结构是正确的，只是没有数据而已
- **可以继续创建Dashboard**，数据导入后会自动显示

### 步骤2：创建业务概览Dashboard

**详细步骤请参考**：`docs/METABASE_DASHBOARD_MANUAL_SETUP.md`

**快速开始**：

1. **创建Dashboard**
   - 点击 "+ 创建" → "Dashboard"
   - 名称：`业务概览`

2. **创建第一个Question：GMV趋势**
   - 在Dashboard中点击 "+ 添加问题"
   - 选择表：`view_shop_performance_wide`
   - X轴：`sale_date`（按日分组）
   - Y轴：`sales_amount`（Sum聚合）
   - 可视化：折线图
   - 保存为：`GMV趋势`

3. **继续创建其他Question**
   - 订单数趋势（`order_count`）
   - 销售达成率趋势（`sales_achievement_rate`）
   - 店铺GMV对比（`shop_name` vs `sales_amount`）
   - 平台对比（`platform_code` vs `sales_amount`）

### 步骤3：添加Dashboard筛选器

1. **日期范围筛选器**
   - 在Dashboard中点击筛选器图标
   - 添加 "日期范围" 筛选器
   - 字段：`sale_date`
   - 默认值：最近30天

2. **平台筛选器**
   - 添加 "多选" 筛选器
   - 字段：`platform_code`
   - 标签：`平台`

3. **店铺筛选器**
   - 添加 "多选" 筛选器
   - 字段：`shop_name`
   - 标签：`店铺`

## 字段名参考

### view_shop_performance_wide 主要字段

**时间维度**：
- `sale_date` - 销售日期（用于时间轴）
- `sale_period` - 销售期间（YYYY-MM）

**店铺维度**：
- `platform_code` - 平台代码
- `shop_id` - 店铺ID
- `shop_name` - 店铺名称

**销售指标**：
- `sales_amount` - 销售额 ⭐（注意：不是total_sales）
- `order_count` - 订单数
- `buyer_count` - 买家数
- `avg_order_value` - 平均订单价值

**KPI指标**：
- `sales_achievement_rate` - 销售达成率
- `profit_margin` - 利润率
- `performance_score` - 绩效得分

## 常见问题

### Q1: 找不到表/视图

**解决方案**：
1. 确保已点击 "同步数据库schema now"
2. 等待同步完成（可能需要几分钟）
3. 刷新页面

### Q2: 字段名不匹配

**解决方案**：
- 使用 `sales_amount` 而不是 `total_sales`
- 使用 `sale_date` 而不是 `order_date`
- 在Metabase中点击表名，查看实际字段列表

### Q3: 如何切换时间粒度（日/周/月）

**解决方案**：
1. 在Question中配置时间分组
2. 或在Dashboard筛选器中添加粒度选择器
3. 使用Metabase的时间分组功能

## 下一步

完成Dashboard创建后：

1. **测试Dashboard功能**
   - 测试筛选器是否正常工作
   - 测试数据是否正确显示

2. **配置前端集成**（Phase 3）
   - 创建 `MetabaseChart.vue` 组件
   - 集成到Vue前端

3. **性能优化**
   - 配置查询缓存
   - 优化物化视图刷新

## 相关文档

- `docs/METABASE_DASHBOARD_MANUAL_SETUP.md` - 详细Dashboard创建指南
- `docs/METABASE_POSTGRESQL_CONNECTION_GUIDE.md` - 数据库连接指南
- `docs/METABASE_TABLE_INIT_GUIDE.md` - 表/视图初始化指南

