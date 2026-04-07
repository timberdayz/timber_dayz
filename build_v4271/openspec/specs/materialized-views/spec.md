# 物化视图语义层能力

## Requirements

### Requirement: 物化视图创建
系统应维护18个物化视图，按业务域组织：产品（5个）、销售（5个）、财务（3个）、库存（3个）和C类数据（2个）。

#### Scenario: 产品域视图
- **WHEN** 系统创建产品物化视图
- **THEN** 系统创建mv_product_summary、mv_product_performance、mv_product_sales_trend、mv_product_inventory_status和mv_product_metrics

#### Scenario: 销售域视图
- **WHEN** 系统创建销售物化视图
- **THEN** 系统创建mv_sales_summary、mv_sales_by_platform、mv_sales_by_shop、mv_sales_trend和mv_order_metrics

#### Scenario: 财务域视图
- **WHEN** 系统创建财务物化视图
- **THEN** 系统创建mv_finance_summary、mv_profit_loss和mv_cash_flow

#### Scenario: 库存域视图
- **WHEN** 系统创建库存物化视图
- **THEN** 系统创建mv_inventory_summary、mv_inventory_by_sku和mv_inventory_movements

#### Scenario: C类数据视图
- **WHEN** 系统创建C类数据视图
- **THEN** 系统创建mv_shop_daily_performance和mv_shop_health_summary

### Requirement: 一键刷新
系统应支持一键刷新所有物化视图，并包含依赖管理。

#### Scenario: 批量刷新执行
- **WHEN** 用户点击"刷新所有视图"按钮
- **THEN** 系统在30-60秒内按依赖顺序刷新所有18个物化视图

#### Scenario: 依赖解析
- **WHEN** 启动刷新
- **THEN** 系统分析视图依赖关系，并在刷新依赖于它们的子视图之前先刷新父视图

#### Scenario: 刷新进度跟踪
- **WHEN** 刷新正在进行中
- **THEN** 系统显示进度条，显示当前正在刷新的视图和完成百分比

### Requirement: 刷新历史记录
系统应维护刷新历史记录，包含时间戳、持续时间和行数。

#### Scenario: 刷新记录创建
- **WHEN** 物化视图刷新完成
- **THEN** 系统在刷新历史中记录刷新时间戳、持续时间、行数和状态

#### Scenario: 刷新历史显示
- **WHEN** 用户查看刷新历史
- **THEN** 系统显示最近10条刷新记录，包含每个视图的时间戳、持续时间和行数

### Requirement: 自动定时刷新
系统应使用APScheduler自动按计划刷新物化视图。

#### Scenario: 每日刷新计划
- **WHEN** 系统正在运行
- **THEN** 系统每天凌晨2:00自动刷新所有物化视图

#### Scenario: 调度器管理
- **WHEN** 系统启动
- **THEN** 系统初始化APScheduler并注册刷新任务

#### Scenario: 调度器关闭
- **WHEN** 系统关闭
- **THEN** 系统优雅地停止调度器并取消待处理的刷新任务

### Requirement: 业务域分类
系统应按业务域组织物化视图，以便于发现。

#### Scenario: 基于域的视图列表
- **WHEN** 用户查看物化视图列表
- **THEN** 系统按域（产品、销售、财务、库存、C类）分组视图并显示域标题

#### Scenario: 域筛选
- **WHEN** 用户选择特定域筛选器
- **THEN** 系统仅显示属于所选域的视图

### Requirement: 视图健康监控
系统应提供健康监控脚本，检查视图状态和数据新鲜度。

#### Scenario: 健康检查执行
- **WHEN** 健康监控脚本运行
- **THEN** 系统检查视图存在性、数据新鲜度（最后刷新时间）、行数和依赖完整性

#### Scenario: 健康检查报告
- **WHEN** 健康检查完成
- **THEN** 系统报告任何缺失、过时（24小时内未刷新）或行数为零的视图

### Requirement: 性能优化
系统应通过适当的索引优化物化视图的查询性能。

#### Scenario: 索引创建
- **WHEN** 创建物化视图
- **THEN** 系统在频繁查询的列（platform_code、shop_id、日期字段）上创建索引

#### Scenario: 查询性能
- **WHEN** 看板查询物化视图
- **THEN** 对于典型的日期范围筛选器，查询在<100ms内完成

### Requirement: 一视图多页面模式
系统应支持一个物化视图服务于多个看板页面的模式。

#### Scenario: 视图重用
- **WHEN** 多个看板页面需要相同的聚合数据
- **THEN** 系统使用单个物化视图（例如，mv_sales_summary）为所有页面提供服务，使用不同的筛选器

#### Scenario: 筛选器应用
- **WHEN** 看板页面使用筛选器查询物化视图
- **THEN** 系统将WHERE子句筛选器应用到物化视图查询，无需为每个页面创建单独的视图
