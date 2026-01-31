## ADDED Requirements

### Requirement: Public 表 Schema 迁移
系统 SHALL 将 public 中具备计算功能的表迁移至 a_class 或 c_class schema，迁移后目标管理、各 Metabase Question、绩效公示等功能 SHALL 正常运行。

#### Scenario: sales_targets 迁移至 a_class
- **WHEN** 执行迁移脚本
- **THEN** `public.sales_targets` 数据迁移至 `a_class.sales_targets`
- **AND** `a_class.target_breakdown.target_id` 外键指向 `a_class.sales_targets.id`
- **AND** 目标管理 CRUD、目标分解、TargetSyncService 同步至 `a_class.sales_targets_a` 正常

#### Scenario: performance_scores 迁移至 c_class
- **WHEN** 执行迁移脚本
- **THEN** `public.performance_scores` 迁移至 `c_class.performance_scores`（或合并至 performance_scores_c）
- **AND** 绩效公示页面可读取 c_class.performance_scores
- **AND** 绩效计算逻辑写入 c_class.performance_scores

#### Scenario: Metabase Question 引用更新
- **WHEN** business_overview_comparison、business_overview_shop_racing、business_overview_operational_metrics 等 Question 执行
- **THEN** 引用 `a_class.sales_targets`（而非 public.sales_targets）
- **AND** 查询结果与迁移前一致

### Requirement: 绩效公示可用性
系统 SHALL 确保绩效公示页面可正常加载，查询绩效评分列表时无异常报错，无数据时友好展示「暂无数据」。

#### Scenario: 绩效公示加载成功
- **WHEN** 管理员或 HR 访问「绩效公示」页面
- **THEN** 系统调用 `GET /api/performance/scores` 获取数据
- **AND** 异步查询使用 `await db.execute(...)`（禁止缺少 await）
- **AND** 若有数据，展示店铺名称、销售额得分、毛利得分、重点产品得分、运营得分、总分、排名、绩效系数
- **AND** 若无数据，展示「暂无数据」而非报错

#### Scenario: 绩效计算触发
- **WHEN** 管理员选择考核周期并点击「重新计算」（或系统自动计算）
- **THEN** 系统调用 `POST /api/performance/scores/calculate`
- **AND** 基于 a_class.target_breakdown、a_class.sales_targets、Orders Model（或 b_class 订单表）、fact_product_metrics、c_class.shop_health_scores 计算各项得分
- **AND** 禁止引用已删除的 fact_orders
- **AND** 将结果写入 c_class.performance_scores
- **AND** 绩效公示页面刷新后可展示新数据

### Requirement: 我的收入（员工自助）
系统 SHALL 提供「我的收入」能力，使已关联员工的用户可查看本人收入明细，支撑数据公开透明。

#### Scenario: 已关联员工查看收入
- **WHEN** 已关联员工的用户访问「我的收入」页面
- **THEN** 系统根据当前用户的 Employee.user_id 定位员工
- **AND** 优先从 a_class.payroll_records 查询（若有完整工资单）
- **AND** 否则从 a_class.salary_structures、c_class.employee_commissions、c_class.employee_performance 组合展示
- **AND** 展示当月实发、收入明细（底薪、提成、绩效奖金等）、绩效依据（得分、系数、达成率）
- **AND** 支持切换月份查看历史收入

#### Scenario: 未关联员工访问
- **WHEN** 未关联员工的用户访问「我的收入」页面
- **THEN** 系统 `GET /api/hr/me/income` 返回 404 或 `{ linked: false }`
- **AND** 页面显示「您尚未关联员工档案，请联系管理员」
- **AND** 不展示收入明细表单

#### Scenario: 我的收入与绩效公示联动
- **WHEN** 员工在「我的收入」中查看绩效依据
- **THEN** 可下钻或链接到「绩效公示」页面
- **AND** 绩效公示中的绩效系数、得分等与收入计算依据一致
