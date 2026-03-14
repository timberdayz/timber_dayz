## ADDED Requirements

### Requirement: Public 表完全迁移至 A/C 类 Schema
系统 SHALL 将 public 中相关表完全迁移至 a_class 或 c_class schema，迁移后删除原表，确保目标管理、各 Metabase Question、绩效公示等功能正常运行。

#### Scenario: sales_targets 迁移至 a_class
- **WHEN** 执行迁移脚本
- **THEN** 创建 `a_class.sales_targets`（与 public.sales_targets 结构一致）
- **AND** 迁移 `public.sales_targets` 数据至 `a_class.sales_targets`
- **AND** 更新 `a_class.target_breakdown.target_id` 外键指向 `a_class.sales_targets.id`
- **AND** 删除 `public.sales_targets` 表
- **AND** 目标管理 CRUD、目标分解正常
- **AND** TargetSyncService 同步至 `a_class.sales_targets_a` 正常

#### Scenario: C 类表迁移
- **WHEN** 执行迁移脚本
- **THEN** 创建 `c_class.performance_scores`、`c_class.shop_health_scores`、`c_class.shop_alerts`
- **AND** 迁移对应 public 表数据
- **AND** 删除 `public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts` 表

#### Scenario: Metabase Question 引用更新
- **WHEN** business_overview_comparison、business_overview_shop_racing 等 Question 执行
- **THEN** 引用 `a_class.sales_targets`（而非 public.sales_targets）
- **AND** 查询结果与迁移前一致

#### Scenario: 迁移后 public 表已删除
- **WHEN** 迁移完成后
- **THEN** `public.sales_targets`、`public.performance_scores`、`public.shop_health_scores`、`public.shop_alerts` 不存在
- **AND** 查询 public schema 无上述表

### Requirement: 绩效公示与绩效配置可用性
系统 SHALL 确保绩效公示与绩效配置相关接口在异步环境下正确执行，查询无异常报错，无数据时友好展示「暂无数据」。

#### Scenario: 绩效公示加载成功
- **WHEN** 管理员或 HR 访问「绩效公示」页面
- **THEN** 系统调用 `GET /api/performance/scores` 获取数据
- **AND** 所有异步数据库查询使用 `await db.execute(...)`（禁止在 async 路由内使用未 await 的 db.execute）
- **AND** 若有数据，展示店铺名称、销售额得分、毛利得分、重点产品得分、运营得分、总分、排名、绩效系数
- **AND** 若无数据，展示「暂无数据」而非报错

#### Scenario: 绩效配置接口异步正确
- **WHEN** 调用绩效配置相关接口（列表/详情/创建/更新/删除）
- **THEN** 路由内所有数据库操作均使用 `await db.execute(...)` 或等效异步调用
- **AND** 无同步 `db.execute(...)` 导致的事件循环冲突或查询失败

#### Scenario: 绩效计算触发
- **WHEN** 管理员选择考核周期并点击「重新计算」（或系统自动计算）
- **THEN** 系统调用 `POST /api/performance/scores/calculate`
- **AND** 计算逻辑由 add-performance-calculation-via-metabase 负责（Metabase SQL + 后端写入）；本规格仅要求接口可调用、禁止引用 fact_orders、结果写入 `c_class.performance_scores`
- **AND** 若计算能力未就绪，接口返回 `HTTP 503` 且 `error_code=PERF_CALC_NOT_READY`，禁止写入占位数据到正式绩效表
- **AND** 绩效公示页面刷新后可展示新数据

### Requirement: 我的收入（员工自助）
系统 SHALL 提供「我的收入」能力，使已关联员工的用户可查看本人收入明细，支撑数据公开透明。API 契约（请求/响应 Pydantic 模型）须定义在 `backend/schemas/`，路由使用 `response_model` 引用（Contract-First）。

#### Scenario: 已关联员工查看收入
- **WHEN** 已关联员工的用户访问「我的收入」页面
- **THEN** 系统根据当前用户的 Employee.user_id 定位员工（依赖 add-link-user-employee-management，已闭环）
- **AND** 优先从 `a_class.payroll_records` 查询（若有完整工资单）
- **AND** 否则从 `a_class.salary_structures`、`c_class.employee_commissions`、`c_class.employee_performance` 组合展示
- **AND** 展示当月实发、收入明细（底薪、提成、绩效奖金等）、绩效依据（得分、系数、达成率）
- **AND** 支持切换月份查看历史收入

#### Scenario: 未关联员工访问
- **WHEN** 未关联员工的用户访问「我的收入」页面
- **THEN** 系统 `GET /api/hr/me/income` 返回 `200` 且 `linked=false`
- **AND** 页面显示「您尚未关联员工档案，请联系管理员」
- **AND** 不展示收入明细表单

#### Scenario: 我的收入与绩效公示联动
- **WHEN** 员工在「我的收入」中查看绩效依据
- **THEN** 可下钻或链接到「绩效公示」页面
- **AND** 绩效公示中的绩效系数、得分等与收入计算依据一致

### Requirement: 我的收入数据安全与审计
系统 SHALL 对「我的收入」能力实施最小权限控制与访问审计，防止越权访问和敏感信息泄露。

#### Scenario: 仅允许本人访问
- **WHEN** 任意用户调用 `GET /api/hr/me/income`
- **THEN** 系统仅根据当前登录用户上下文定位关联员工
- **AND** 不接受可用于查询他人收入的 employee_code/user_id 输入参数

#### Scenario: 访问审计与日志脱敏
- **WHEN** 用户访问「我的收入」接口
- **THEN** 系统记录访问审计日志（用户、时间、结果状态）
- **AND** 日志与错误信息中不输出 base_salary、net_salary、commission_amount 等敏感明文字段
