# HR Income Payroll Closure Design

## Goal

收口“绩效管理”和“我的收入”链路，使员工收入最终统一以 `a_class.payroll_records` 为唯一结算口径，并把当前“绩效/提成重算”和“工资单展示”之间的断点补齐。

## Status Snapshot

### 已实现

- `a_class.payroll_records` 已存在，并具备完整工资单字段与 `draft/confirmed/paid` 状态字段。
- `PayrollGenerationService` 已实现，能够基于 `salary_structures + employee_commissions + employee_performance` 生成或更新工资单草稿。
- `POST /performance/scores/calculate` 已在店铺绩效、个人提成、个人绩效重算后继续调用工资单生成。
- 已有工资单路由：
  - `GET /api/hr/payroll-records/{employee_code}/{year_month}`
  - `PUT /api/hr/payroll-records/{record_id}`
  - `POST /api/hr/payroll-records/{record_id}/confirm`
  - `POST /api/hr/payroll-records/{record_id}/reopen`
  - `POST /api/hr/payroll-records/{record_id}/pay`
- 绩效重算响应已返回：
  - `payroll_locked_conflicts`
  - `payroll_locked_conflict_details`

### 仍未收口

- `GET /api/hr/me/income` 在工资单缺失时仍会回退拼装 `salary_structures + employee_commissions + employee_performance`，口径仍不统一。
- 顶层 `total_income` 仍不是严格的工资单 `net_salary` 口径。
- `paid` 状态已具备内部记录接口，但仍未扩展到外部支付或财务联动。
- 前端 HR 页面虽然已有工资单查询能力，但“我的收入”和工资单页尚未完全统一到工资单口径。

## Single Source of Truth

### 最终结算口径

- `a_class.payroll_records`

### 中间计算层

- `c_class.employee_commissions`
- `c_class.employee_performance`

### 店铺绩效结果层

- `c_class.performance_scores`

原则：

- 员工“已结算收入”只认工资单。
- 提成表与个人绩效表继续保留为中间计算结果，不直接作为员工最终收入展示口径。

## Payroll Candidate Set

当月工资单生成范围采用并集规则：

- 存在 `active` 的 `salary_structures`
- 当月存在 `employee_commissions`
- 当月存在 `employee_performance`
- 当月已存在 `payroll_records`

这样可以保证：

- 正常员工会生成工资单草稿。
- 已有历史工资单的员工不会因上游数据暂时缺失而被“丢出”工资单集合。
- 草稿工资单上的人工字段可在重算时被保留。

## Payroll Composition

### Auto-calculated fields

- `base_salary <- salary_structures.base_salary`
- `position_salary <- salary_structures.position_salary`
- `allowances <- housing_allowance + transport_allowance + meal_allowance + communication_allowance + other_allowance`
- `commission <- employee_commissions.commission_amount`
- `performance_salary <- (base_salary + position_salary) * performance_ratio * (performance_score / 100)`

### Manual-preserved fields

这些字段当前没有稳定自动来源，工资单处于 `draft` 时保留 HR 已填值：

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
- `performance_ratio` 与 `performance_score` 均视为自动字段，重算时允许覆盖。

## Payroll Status Rules

- `draft`
  - 允许系统根据绩效/提成重算自动覆盖自动字段。
  - 保留人工字段。
  - 允许 HR 编辑人工字段。
- `confirmed`
  - 不允许系统自动覆盖。
  - 若上游重算后自动字段发生变化，记为锁定冲突。
  - 允许 HR 退回 `draft`。
- `paid`
  - 只读。
  - 不允许系统自动改写。
  - 当前仓库尚未定义正式的“发薪”接口，`paid` 仍是待补完流程。

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

### 目标中的 My Income flow

`GET /api/hr/me/income`

目标行为：

1. 根据当前用户找到员工档案
2. 只读取当月 `payroll_records`
3. 若不存在工资单：
   - 返回 `linked=True`
   - 返回“当月工资单未生成”的空态
4. 若存在工资单：
   - 顶层收入使用 `net_salary`
   - 明细直接展示工资单字段

当前差异：

- 现代码仍保留工资单缺失时的 fallback 拼装逻辑。
- 本设计的下一步收口重点是移除该 fallback。

## API Scope

### 已落地

- `POST /performance/scores/calculate`
  - 已包含工资单重算
  - 已返回 `payroll_upserts`
  - 已返回 `payroll_locked_conflicts`
- `GET /api/hr/payroll-records/{employee_code}/{year_month}`
- `PUT /api/hr/payroll-records/{record_id}`
- `POST /api/hr/payroll-records/{record_id}/confirm`
- `POST /api/hr/payroll-records/{record_id}/reopen`

### 本次仍需调整

- `GET /api/hr/me/income`
  - 移除工资单缺失时的自由回退拼装
  - 顶层金额切到 `net_salary`
- 锁定冲突返回体
  - 当前只有计数
  - 后续建议增加冲突明细列表

### 后续独立议题

- `paid` 状态的权限、审计、可逆性和财务联动仍可继续细化

## UI Rollout

### MyIncome.vue

目标：

- 只展示工资单口径
- 顶部卡片显示 `net_salary`
- 明细显示工资单字段
- 移除 `salary_structure / commission / performance` 的混合 breakdown

### HumanResources.vue

目标：

- 复用现有“工资单记录”tab，不新开页面
- 暴露 `draft` 编辑
- 暴露 `confirm`
- 暴露 `reopen`
- `paid` 只读

说明：

- 路由能力已经存在，前端重点是把工资单 tab 做成稳定操作入口，而不是重新设计后端模型。

## Open Decisions

以下问题需要产品/业务确认后再继续收口：

1. 是否需要正式的 `paid` 发薪流转接口。
2. 没有 `salary_structure` 但存在提成/绩效/历史工资单的员工，是否继续生成工资单草稿。
3. `/api/hr/me/income` 是否允许短期保留 fallback，还是直接切为工资单空态。
4. 锁定冲突是否需要返回 HR 可读的字段级差异明细。

## Compatibility Notes

- 保留 `employee_commissions` / `employee_performance` 作为计算中间层，避免一次性拆掉现有绩效与提成链路。
- 不引入额外状态如 `stale/outdated`，避免在本轮把问题扩散成更大的状态机改造。
- 不在本轮实现自动个税/社保计算，只保留字段和人工录入能力。
- 本文档默认以后续“工资单读路径收口”为主，不重复设计已经存在的工资单生成与状态更新代码。

## Testing Strategy

1. 保留并补强现有失败测试：
   - 绩效重算后会自动 upsert 工资单
   - `confirmed/paid` 工资单不会被自动覆盖
   - 草稿工资单重算时保留人工字段
   - 工资单编辑/确认/退回接口状态约束正确
2. 增加 `/api/hr/me/income` 收口测试：
   - 存在工资单时严格返回工资单口径
   - 不存在工资单时返回空态而不是旧逻辑拼装
3. 最后补前端交互验证：
   - MyIncome 只展示工资单字段
   - HR 工资单 tab 能完成 draft 编辑与 confirm/reopen
