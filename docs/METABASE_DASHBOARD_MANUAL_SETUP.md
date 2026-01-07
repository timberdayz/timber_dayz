# Metabase Dashboard手动创建指南

## 前提条件

✅ 已完成：
- Metabase已启动并可以访问
- PostgreSQL数据库已连接（xihong_erp）
- 数据库表/视图已同步

## 重要提示：字段名参考

根据 `view_shop_performance_wide` 视图定义，主要字段包括：

### 时间维度字段
- `sale_date` - 销售日期
- `sale_period` - 销售期间（YYYY-MM）
- `sale_year` - 年份
- `sale_month` - 月份

### 店铺维度字段
- `platform_code` - 平台代码
- `shop_id` - 店铺ID
- `shop_name` - 店铺名称
- `shop_country` - 店铺国家

### 销售指标字段（B类数据）
- `order_count` - 订单数
- `buyer_count` - 买家数
- `sales_amount` - 销售额（注意：不是total_sales）
- `avg_order_value` - 平均订单价值
- `total_products_sold` - 销售产品总数
- `total_shipping_fee` - 总运费

### 库存指标字段（B类数据）
- `inventory_value` - 库存价值
- `available_stock` - 可用库存
- `out_of_stock_products` - 缺货产品数
- `low_stock_products` - 低库存产品数

### KPI字段（C类数据）
- `sales_achievement_rate` - 销售达成率
- `profit_margin` - 利润率
- `estimated_profit` - 预估利润
- `performance_score` - 绩效得分

## 第一步：同步数据库Schema（如果未自动同步）

1. **进入数据库管理页面**
   - 点击左侧菜单 "数据" → "数据库"
   - 点击 "XIHONG_ERP" 数据库

2. **手动同步Schema**
   - 在数据库详情页面，点击右上角 "同步数据库schema now"
   - 等待同步完成（可能需要几分钟）
   - 同步完成后，应该能看到所有表/视图

3. **验证关键表/视图是否存在**
   检查以下表/视图是否已同步：
   - ✅ `view_shop_performance_wide` - 店铺综合绩效宽表（核心！）
   - ✅ `view_product_performance_wide` - 产品全景视图
   - ✅ `mv_daily_sales_summary` - 每日销售汇总
   - ✅ `mv_monthly_shop_performance` - 月度店铺绩效
   - ✅ `view_orders_atomic` - 订单原子视图
   - ✅ `view_targets_atomic` - 销售目标

## 第二步：创建业务概览Dashboard

### 2.1 创建Dashboard

1. **创建新Dashboard**
   - 点击左侧菜单 "+ 创建" → "Dashboard"
   - 输入名称：`业务概览`
   - 点击 "创建"

### 2.2 创建Question 1：GMV趋势（折线图）

1. **创建新Question**
   - 在Dashboard中点击 "+ 添加问题"
   - 选择 "使用简单编辑器" 或 "使用自定义问题"

2. **选择数据源**
   - 选择表：`view_shop_performance_wide`

3. **配置查询**
   - **X轴（分组）**：
     - 字段：`sale_date`（或 `metric_date`，根据实际字段名）
     - 分组方式：按日/周/月（可以在Dashboard筛选器中切换）
   - **Y轴（指标）**：
     - 字段：`sales_amount`（或 `total_sales`，根据实际字段名）
     - 聚合方式：`Sum`（求和）

4. **可视化类型**
   - 选择 "折线图"（Line Chart）

5. **保存Question**
   - 点击 "保存"
   - 输入名称：`GMV趋势`
   - 选择保存位置：`业务概览` Dashboard

### 2.3 创建Question 2：订单数趋势（折线图）

1. **创建新Question**
   - 在Dashboard中点击 "+ 添加问题"
   - 选择表：`view_shop_performance_wide`

2. **配置查询**
   - **X轴**：`sale_date`（按日/周/月分组）
   - **Y轴**：`order_count`（Sum聚合）

3. **可视化类型**：折线图

4. **保存**：名称 `订单数趋势`

### 2.4 创建Question 3：销售达成率趋势（折线图）

1. **创建新Question**
   - 选择表：`view_shop_performance_wide`

2. **配置查询**
   - **X轴**：`sale_date`（按日/周/月分组）
   - **Y轴**：`sales_achievement_rate`（Average聚合，平均值）

3. **可视化类型**：折线图

4. **保存**：名称 `销售达成率趋势`

### 2.5 创建Question 4：店铺GMV对比（柱状图）

1. **创建新Question**
   - 选择表：`view_shop_performance_wide`

2. **配置查询**
   - **X轴**：`shop_name`（店铺名称）
   - **Y轴**：`sales_amount`（Sum聚合）

3. **可视化类型**：柱状图（Bar Chart）

4. **排序**：按销售额降序排列

5. **保存**：名称 `店铺GMV对比`

### 2.6 创建Question 5：平台对比（饼图或柱状图）

1. **创建新Question**
   - 选择表：`view_shop_performance_wide`

2. **配置查询**
   - **分组**：`platform_code`（平台代码）
   - **指标**：`sales_amount`（Sum聚合）

3. **可视化类型**：饼图（Pie Chart）或柱状图

4. **保存**：名称 `平台对比`

## 第三步：添加Dashboard筛选器

### 3.1 添加日期范围筛选器

1. **在Dashboard中点击筛选器图标**（漏斗图标）
2. **添加筛选器** → 选择 "日期范围"（Date Range）
3. **配置筛选器**：
   - 字段：`sale_date`
   - 默认值：最近30天
   - 应用到所有Question

### 3.2 添加平台筛选器

1. **添加筛选器** → 选择 "多选"（Multi-Select）
2. **配置筛选器**：
   - 字段：`platform_code`
   - 标签：`平台`
   - 应用到所有Question

### 3.3 添加店铺筛选器

1. **添加筛选器** → 选择 "多选"（Multi-Select）
2. **配置筛选器**：
   - 字段：`shop_name` 或 `shop_id`
   - 标签：`店铺`
   - 应用到所有Question

### 3.4 添加粒度切换筛选器（可选）

1. **添加筛选器** → 选择 "单选"（Single Select）
2. **配置筛选器**：
   - 字段：自定义字段或使用Question参数
   - 选项：`daily`（日）、`weekly`（周）、`monthly`（月）
   - 注意：粒度切换需要在Question中配置时间分组

## 第四步：配置Question联动和钻取

### 4.1 配置Question联动

1. **在Dashboard中点击Question设置**（三个点图标）
2. **选择 "点击行为"**（Click behavior）
3. **配置联动**：
   - 点击店铺名称 → 筛选所有Question到该店铺
   - 点击平台 → 筛选所有Question到该平台

### 4.2 配置钻取（可选）

1. **在Question中配置钻取**
2. **钻取路径**：
   - GMV趋势 → 店铺级别 → 产品级别
   - 使用Metabase的钻取功能

## 第五步：自定义字段（Custom Fields）

### 5.1 为view_shop_performance_wide添加自定义字段

1. **进入表设置**
   - 数据 → 数据库 → XIHONG_ERP → `view_shop_performance_wide`
   - 点击表名进入表详情

2. **添加自定义字段**
   - 点击 "添加字段" 或 "自定义字段"
   - 创建以下字段：

   **字段1：平均订单价值**
   - 名称：`avg_order_value`
   - 公式：`[sales_amount] / [order_count]`
   - 类型：数字

   **字段2：利润率**
   - 名称：`profit_margin`
   - 公式：`([sales_amount] - [operating_cost]) / [sales_amount] * 100`
   - 类型：百分比
   - 注意：根据实际字段名调整

### 5.2 为view_product_performance_wide添加自定义字段

1. **进入表设置**
   - 数据 → 数据库 → XIHONG_ERP → `view_product_performance_wide`

2. **添加自定义字段**

   **字段：库存周转率**
   - 名称：`stock_turnover`
   - 公式：`[actual_revenue] / [current_stock]`
   - 类型：数字
   - 注意：根据实际字段名调整

## 常见问题

### Q1: 找不到表/视图

**解决方案**：
1. 检查表名是否正确（注意大小写）
2. 在Metabase中手动同步Schema
3. 检查PostgreSQL中表是否存在：`\dt` 或 `SELECT tablename FROM pg_tables`

### Q2: 字段名不匹配

**解决方案**：
1. 在Metabase中查看表的实际字段名
2. 根据实际字段名调整Question配置
3. 参考 `sql/views/wide/view_shop_performance_wide.sql` 查看字段定义

### Q3: 时间分组不工作

**解决方案**：
1. 确保时间字段类型为Date或Timestamp
2. 在Question中配置时间分组（按日/周/月）
3. 使用Dashboard筛选器切换粒度

### Q4: 自定义字段公式错误

**解决方案**：
1. 检查字段名是否正确（使用方括号 `[]`）
2. 检查公式语法（支持基本数学运算）
3. 如果复杂，使用SQL表达式

## 下一步

完成Dashboard创建后：

1. **测试Dashboard功能**
   - 测试筛选器是否正常工作
   - 测试Question联动
   - 测试时间粒度切换

2. **配置前端集成**
   - 参见 Phase 3 任务清单
   - 创建 `MetabaseChart.vue` 组件

3. **性能优化**
   - 配置查询缓存
   - 优化物化视图刷新

## 参考资源

- Metabase官方文档：https://www.metabase.com/docs/
- Metabase Dashboard创建指南：https://www.metabase.com/docs/latest/questions/actions/dashboards
- Metabase自定义字段：https://www.metabase.com/docs/latest/data-modeling/metadata-editing

