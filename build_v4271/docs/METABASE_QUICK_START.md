# Metabase快速开始指南

## 当前状态 ✅

- ✅ Metabase已部署并运行
- ✅ PostgreSQL数据库已连接
- ✅ 表/视图已同步到Metabase
- ⚠️ 数据库中目前没有业务数据（这是正常的）

## 立即可以做的事情

### 1. 创建Dashboard结构（即使没有数据）

即使数据库中没有数据，您也可以创建Dashboard结构：

1. **创建Dashboard**
   - 点击 "+ 创建" → "Dashboard"
   - 名称：`业务概览`
   - 描述：`店铺综合绩效看板`

2. **创建Question（即使显示0行）**
   - 在Dashboard中点击 "+ 添加问题"
   - 选择表：`view_shop_performance_wide`
   - 配置字段和图表类型
   - 保存Question

3. **配置筛选器**
   - 添加日期范围筛选器
   - 添加平台筛选器
   - 添加店铺筛选器

### 2. 验证字段结构

在创建Question时，Metabase会显示所有可用字段：

**时间维度字段**：
- `sale_date` - 销售日期
- `sale_period` - 销售期间
- `sale_year` - 年份
- `sale_month` - 月份

**店铺维度字段**：
- `platform_code` - 平台代码
- `shop_id` - 店铺ID
- `shop_name` - 店铺名称

**销售指标字段**：
- `sales_amount` - 销售额 ⭐
- `order_count` - 订单数
- `buyer_count` - 买家数
- `avg_order_value` - 平均订单价值

**KPI字段**：
- `sales_achievement_rate` - 销售达成率
- `profit_margin` - 利润率
- `performance_score` - 绩效得分

## 创建第一个Question的步骤

### Question 1: GMV趋势（折线图）

1. **创建Question**
   - 点击 "+ 创建" → "问题"
   - 选择 "使用简单编辑器"

2. **选择数据源**
   - 选择数据库：`XIHONG_ERP`
   - 选择表：`view_shop_performance_wide`

3. **配置查询**
   - **分组**：选择 `sale_date` 字段
   - **指标**：选择 `sales_amount` 字段，聚合方式选择 `Sum`（求和）

4. **可视化**
   - 点击 "可视化" 按钮
   - 选择 "折线图"（Line Chart）
   - 调整图表样式（可选）

5. **保存**
   - 点击 "保存"
   - 名称：`GMV趋势`
   - 选择保存位置：`业务概览` Dashboard

### Question 2: 订单数趋势（折线图）

类似步骤，但使用：
- **指标**：`order_count`（Sum聚合）

### Question 3: 店铺GMV对比（柱状图）

1. **创建Question**
   - 选择表：`view_shop_performance_wide`

2. **配置查询**
   - **分组**：`shop_name`
   - **指标**：`sales_amount`（Sum聚合）

3. **可视化**
   - 选择 "柱状图"（Bar Chart）
   - 排序：按销售额降序

## 添加Dashboard筛选器

1. **在Dashboard中点击筛选器图标**（漏斗图标）

2. **添加日期范围筛选器**
   - 类型：日期范围（Date Range）
   - 字段：`sale_date`
   - 默认值：最近30天

3. **添加平台筛选器**
   - 类型：多选（Multi-Select）
   - 字段：`platform_code`
   - 标签：`平台`

4. **添加店铺筛选器**
   - 类型：多选（Multi-Select）
   - 字段：`shop_name`
   - 标签：`店铺`

## 数据导入后的自动更新

当业务数据导入后：

1. **自动显示数据**
   - Dashboard会自动显示数据
   - 无需重新配置

2. **刷新数据**
   - 点击Dashboard的刷新按钮
   - 或等待Metabase自动刷新

3. **测试筛选器**
   - 测试日期范围筛选
   - 测试平台筛选
   - 测试店铺筛选

## 常见问题

### Q1: 为什么显示"没有结果"？

**答案**：数据库中目前没有业务数据，这是正常的。可以继续创建Dashboard结构。

### Q2: 没有数据可以创建Dashboard吗？

**答案**：可以！Metabase会显示字段列表，您可以配置Question和筛选器。数据导入后会自动显示。

### Q3: 如何导入测试数据？

**答案**：参考 `docs/METABASE_EMPTY_DATA_SOLUTION.md` 中的测试数据准备方法。

## 下一步

1. **创建Dashboard结构**（现在就可以做）
2. **等待业务数据导入**
3. **测试Dashboard功能**
4. **配置前端集成**（Phase 3）

## 相关文档

- `docs/METABASE_DASHBOARD_MANUAL_SETUP.md` - 详细Dashboard创建指南
- `docs/METABASE_EMPTY_DATA_SOLUTION.md` - 空数据问题解决方案
- `docs/METABASE_NEXT_STEPS.md` - 下一步操作指南

