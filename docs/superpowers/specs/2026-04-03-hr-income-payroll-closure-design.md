# HR Income Payroll Closure Design

## Goal

收口“绩效管理”和“我的收入”链路，使员工收入最终统一以 `a_class.payroll_records` 为唯一结算口径，并把当前“绩效/提成重算”和“工资单展示”之间的断点补齐。

## Current Problems

1. `GET /api/hr/me/income` 在工资单缺失时会回退拼装 `salary_structures + employee_commissions + employee_performance`，导致口径不一致。
2. 顶层 `total_income` 当前等于 `base_salary + commission_amount`，不等于工资单 `net_salary`。
3. `payroll_records` 有表、有列表展示，但仓库内没有稳定的自动生成/更新闭环。
4. `POST /performance/scores/calculate` 会重算店铺绩效、个人提成、个人绩效，但不会把结果沉淀为工资单。
5. 工资单页面仅支持查询，不支持 `draft -> confirmed` 的结算流转。

## Target Model

### Single Source of Truth

- 最终结算口径：`a_class.payroll_records`
- 中间计算结果：
  - `c_class.employee_commissions`
  - `c_class.employee_performance`
- 店铺绩效结果：
  - `c_class.performance_scores`

### Payroll Status Rules

- `draft`
  - 允许系统根据绩效/提成重算自动覆盖自动字段
  - 保留 HR 已手工填写的人工字段
- `confirmed`
  - 不允许系统自动覆盖
  - 若上游数据重算后存在变化，返回锁定冲突信息，由 HR 退回 `draft`
- `paid`
  - 只读，不允许系统自动改写

## Payroll Composition

### Auto-calculated fields

- `base_salary` <- `salary_structures.base_salary`
- `position_salary` <- `salary_structures.position_salary`
- `allowances` <- 所有补贴字段求和
- `commission` <- `employee_commissions.commission_amount`
- `performance_salary` <- `(base_salary + position_salary) * performance_ratio * (performance_score / 100)`

### Manual-preserved fields

这些字段当前仓库没有稳定自动来源，工资单 `draft` 中保留 HR 已填值：

- `overtime_pay`
- `bonus`
- `social_insurance_personal`
- `housing_fund_personal`
- `income_tax`
- `other_deductions`
- `social_insurance_company`
- `housing_fund_company`

### Derived totals

- `gross_salary = base_salary + position_salary + performance_salary + overtime_pay + commission + allowances + bonus`
- `total_deductions = social_insurance_personal + housing_fund_personal + income_tax + other_deductions`
- `net_salary = gross_salary - total_deductions`
- `total_cost = gross_salary + social_insurance_company + housing_fund_company`

## Runtime Flow

### Recalculation flow

`POST /performance/scores/calculate`

1. 重算店铺绩效并写入 `performance_scores`
2. 重算个人提成并写入 `employee_commissions`
3. 重算个人绩效并写入 `employee_performance`
4. 生成或更新当月 `payroll_records`
5. 返回：
   - 店铺绩效 upsert 数
   - 个人提成 upsert 数
   - 个人绩效 upsert 数
   - 工资单 upsert 数
   - 被 `confirmed/paid` 锁住的工资单冲突数

### My Income flow

`GET /api/hr/me/income`

1. 根据当前用户找到员工档案
2. 只读取当月 `payroll_records`
3. 若不存在工资单：
   - 返回 `linked=True`
   - 返回“当月工资单未生成”的空态
4. 若存在工资单：
   - 顶层收入使用 `net_salary`
   - 明细直接展示工资单字段

## API Changes

### Existing route changes

- `POST /performance/scores/calculate`
  - 增加工资单重算
  - 增加 `payroll_upserts`
  - 增加 `payroll_locked_conflicts`

- `GET /api/hr/me/income`
  - 移除工资单缺失时的自由回退拼装
  - 顶层金额改为 `net_salary`

### New routes

- `GET /api/hr/payroll-records/{employee_code}/{year_month}`
- `PUT /api/hr/payroll-records/{record_id}`
  - 仅允许编辑人工字段，且仅限 `draft`
- `POST /api/hr/payroll-records/{record_id}/confirm`
- `POST /api/hr/payroll-records/{record_id}/reopen`

## UI Changes

### MyIncome.vue

- 只展示工资单口径
- 顶部卡片显示 `net_salary`
- 明细显示工资单字段
- 移除 `salary_structure / commission / performance` 的混合 breakdown

### HumanResources.vue

- 复用现有“工资单记录”tab，不新开页面
- 增加：
  - `draft` 编辑
  - `confirm`
  - `reopen`
- `paid` 只读

## Compatibility Notes

- 保留 `employee_commissions` / `employee_performance` 作为计算中间层，避免一次性拆掉现有绩效与提成链路。
- 不在本次设计里引入新的状态机，例如 `stale/outdated`，避免额外复杂度。
- 不在本次设计里实现自动个税/社保计算，只保留字段和人工录入能力。

## Testing Strategy

1. 先写失败测试验证：
   - 绩效重算后会自动 upsert 工资单
   - `confirmed/paid` 工资单不会被自动覆盖
   - `/api/hr/me/income` 只走工资单口径
   - 工资单编辑/确认/退回接口状态约束正确
2. 再实现最小代码使测试通过
3. 最后补现有 HR 页面交互验证
