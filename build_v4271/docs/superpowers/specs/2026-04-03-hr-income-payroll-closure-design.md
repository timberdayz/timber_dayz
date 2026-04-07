# HR Income Payroll Closure Design

## Goal

收口“绩效管理”和“我的收入”链路，使员工收入统一以 `a_class.payroll_records` 为最终结算口径，并明确当前已经落地的能力、仍待扩展的边界和后续治理方向。

## Status Snapshot

### 已实现

- `a_class.payroll_records` 已具备完整工资单字段以及 `draft / confirmed / paid` 状态字段。
- `PayrollGenerationService` 已可基于 `salary_structures + employee_commissions + employee_performance` 生成或更新工资单。
- `POST /performance/scores/calculate` 已在店铺绩效、个人提成、个人绩效重算后继续生成工资单。
- 工资单路由已落地：
  - `GET /api/hr/payroll-records/{employee_code}/{year_month}`
  - `PUT /api/hr/payroll-records/{record_id}`
  - `POST /api/hr/payroll-records/{record_id}/confirm`
  - `POST /api/hr/payroll-records/{record_id}/reopen`
  - `POST /api/hr/payroll-records/{record_id}/pay`
- `GET /api/hr/me/income` 已只读工资单，不再回退拼装旧链路。
- 绩效重算响应已返回：
  - `payroll_locked_conflicts`
  - `payroll_locked_conflict_details`
- 前端已落地：
  - My Income 工资单完整明细展示
  - HumanResources 工资单内部流转
  - 锁定冲突弹窗摘要
  - 已发放按钮管理员可见
  - payroll pay 后端管理员权限与审计

### 仍未扩展

- `paid` 仍只代表系统内部“已发放记录”，尚未联动外部支付或财务系统。
- 锁定冲突目前以重算后的弹窗摘要为主，尚未提供专门列表页。
- 权限模型当前以管理员可执行 `pay` 为主，尚未细化到更细颗粒度的工资单职责拆分。

## Single Source of Truth

### 最终结算层

- `a_class.payroll_records`

### 中间计算层

- `c_class.employee_commissions`
- `c_class.employee_performance`

### 店铺绩效结果层

- `c_class.performance_scores`

原则：

- 员工最终收入口径只认工资单。
- 提成和个人绩效继续保留为中间结果，不直接作为最终收入展示口径。

## Payroll Candidate Set

当月工资单生成范围采用并集规则：

- 存在 `active` 的 `salary_structures`
- 当月存在 `employee_commissions`
- 当月存在 `employee_performance`
- 当月已存在 `payroll_records`

这样可以保证：

- 正常员工会生成工资单草稿。
- 已有历史工资单的员工不会因上游暂时缺数而被排除出当月工资单集合。
- 草稿工资单的人工字段在重算时可被保留。

## Payroll Composition

### Auto-calculated fields

- `base_salary <- salary_structures.base_salary`
- `position_salary <- salary_structures.position_salary`
- `allowances <- housing_allowance + transport_allowance + meal_allowance + communication_allowance + other_allowance`
- `commission <- employee_commissions.commission_amount`
- `performance_salary <- (base_salary + position_salary) * performance_ratio * (performance_score / 100)`

### Manual-preserved fields

以下字段当前无稳定自动来源，工资单处于 `draft` 时保留 HR 已填值：

- `overtime_pay`
- `bonus`
- `social_insurance_personal`
- `housing_fund_personal`
- `income_tax`
- `other_deductions`
- `social_insurance_company`
- `housing_fund_company`
- `pay_date`
- `remark`

### Derived totals

- `gross_salary = base_salary + position_salary + performance_salary + overtime_pay + commission + allowances + bonus`
- `total_deductions = social_insurance_personal + housing_fund_personal + income_tax + other_deductions`
- `net_salary = gross_salary - total_deductions`
- `total_cost = gross_salary + social_insurance_company + housing_fund_company`

### Calculation contract

- 金额字段统一按两位小数处理。
- 舍入规则使用 `ROUND_HALF_UP`。
- 缺失金额按 `0` 参与计算。
- `performance_ratio` 与 `performance_score` 视为自动字段，重算时允许覆盖。

## Payroll Status Rules

- `draft`
  - 允许系统重算覆盖自动字段
  - 保留人工字段
  - 允许 HR 编辑人工字段
- `confirmed`
  - 不允许系统自动覆盖
  - 上游重算导致变化时记为锁定冲突
  - 允许 HR 退回 `draft`
- `paid`
  - 只读
  - 不允许系统自动改写
  - 当前只做内部状态记录与审计留痕

## Runtime Flow

### 已实现的 recalculation flow

`POST /performance/scores/calculate`

1. 重算店铺绩效并写入 `performance_scores`
2. 重算个人提成并写入 `employee_commissions`
3. 重算个人绩效并写入 `employee_performance`
4. 调用 `PayrollGenerationService.generate_month(period)` 生成或更新当月 `payroll_records`
5. 返回：
   - 店铺绩效 upsert 数
   - 个人提成 upsert 数
   - 个人绩效 upsert 数
   - 工资单 upsert 数
   - 被 `confirmed/paid` 锁住的工资单冲突数
   - 锁定冲突明细

### My Income flow

`GET /api/hr/me/income`

当前行为：

1. 根据当前用户找到员工档案
2. 只读取当月 `payroll_records`
3. 若不存在工资单：
   - 返回 `linked=True`
   - 返回空态
4. 若存在工资单：
   - 顶层收入使用 `net_salary`
   - 明细直接展示完整工资单字段

## API Scope

### 已落地

- `POST /performance/scores/calculate`
  - 已包含工资单重算
  - 已返回 `payroll_upserts`
  - 已返回 `payroll_locked_conflicts`
  - 已返回 `payroll_locked_conflict_details`
- `GET /api/hr/payroll-records/{employee_code}/{year_month}`
- `PUT /api/hr/payroll-records/{record_id}`
- `POST /api/hr/payroll-records/{record_id}/confirm`
- `POST /api/hr/payroll-records/{record_id}/reopen`
- `POST /api/hr/payroll-records/{record_id}/pay`

### 后续独立议题

- `paid` 与外部支付 / 财务联动
- 锁定冲突专门列表页
- 更细粒度的工资单权限模型

## UI Rollout

### MyIncome.vue

- 只展示工资单口径
- 顶部卡片显示 `net_salary`
- 明细显示完整工资单字段

### HumanResources.vue

- 复用现有“工资单记录”tab
- 暴露 `draft` 编辑
- 暴露 `confirm`
- 暴露 `reopen`
- 对管理员暴露 `pay`
- 其他角色不显示“已发放”按钮

### PerformanceManagement.vue

- 发起月度重算
- 对锁定工资单弹出冲突摘要
- 冲突文案已翻译为 HR 可读中文字段名

## Open Decisions

以下问题需要产品/业务确认后再继续扩展：

1. 是否需要正式的 `paid` 发薪流转对外接口。
2. 没有 `salary_structure` 但存在提成/绩效/历史工资单的员工，是否继续生成工资单草稿。
3. 是否需要为锁定冲突增加专门的 HR 列表页，而不是仅在绩效重算后弹窗提示。

## Compatibility Notes

- 保留 `employee_commissions` / `employee_performance` 作为计算中间层，避免一次性拆掉现有绩效与提成链路。
- 不引入额外状态如 `stale/outdated`，避免把本轮问题扩散成更大的状态机改造。
- 不在本轮实现自动个税/社保计算，只保留字段和人工录入能力。
- 本文档默认以后续外部联动和治理增强为主，不重复设计已经存在的工资单生成、状态流转和收入展示逻辑。

## Testing Strategy

1. 保留并补强现有失败测试：
   - 绩效重算后会自动 upsert 工资单
   - `confirmed/paid` 工资单不会被自动覆盖
   - 草稿工资单重算时保留人工字段
   - 工资单编辑/确认/退回/已发放接口状态约束正确
2. 保持 `/api/hr/me/income` 收口测试：
   - 存在工资单时严格返回工资单口径
   - 不存在工资单时返回空态
3. 保持前端交互验证：
   - MyIncome 展示完整工资单字段
   - HumanResources 工资单 tab 能完成 draft 编辑与内部流转
