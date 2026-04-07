# Employee Salary Single-Page Design

## Goal

在尽量不增加页面数量的前提下，补齐 HR 薪资链路中缺失的 A 类输入入口，新增一个 HR 侧独立页面 `员工薪资`，将员工固定薪资配置、月度人工录入、工资单结果查看和状态流转统一收口到单页完成。

本设计明确区分：
- 员工自助查看页：`MyIncome.vue`
- HR 基础管理页：`HumanResources.vue`
- HR 薪资业务页：新增 `员工薪资`

## Problem Statement

当前实现已经形成了“绩效重算 -> 工资单生成 -> 我的收入展示”的闭环，但 HR 薪资业务仍存在明显断层：

- `MyIncome.vue` 仅适合员工查看自己的收入，不承担任何录入职责。
- `HumanResources.vue` 当前的 `薪资管理` 更接近工资单列表和草稿编辑，不是完整的薪资主数据维护页。
- `a_class.salary_structures` 已存在数据模型和后端接口，但缺少实际前端录入入口。
- 月度奖金、现金奖励等人工字段目前只能在工资单草稿中零散维护，缺少清晰的业务入口。

因此，系统现状是“结果页完整，A 类输入不完整”。

## Design Principles

1. 页面数量尽量少，但页面职责必须清楚。
2. 员工固定薪资与月度人工录入必须同页，避免 HR 在多个页面之间切换。
3. 固定薪资与月度工资单属于不同语义层，必须分区，不能混成一个表单。
4. 自动计算结果必须与录入区同屏，便于 HR 立即校验影响。
5. 保持现有三态流转：`draft -> confirmed -> paid`，不新增额外状态。

## Recommended Approach

新增一个 HR 侧独立页面 `员工薪资`，采用“按员工为主视角”的单页设计。

推荐原因：
- 底薪、岗位工资、补贴等长期配置天然是按员工维护的。
- 同一个页面内再切月份维护奖金、扣款、工资单状态，符合 HR 实际操作顺序。
- 比继续堆叠在 `HumanResources.vue` 的 `薪资管理` Tab 中更清晰，也比拆成多个薪资子页面更符合“尽量少页面”的目标。

## Page Responsibilities

### 1. My Income

保留现状，仅做员工自助查看：
- 只读
- 仅显示当前员工自己的工资单口径收入
- 不承担任何录入、确认、发放操作

### 2. Human Resources

保留为 HR 基础管理页：
- 员工档案
- 部门
- 职位
- 考勤

从该页剥离核心薪资业务，不再作为固定薪资和月度奖金的主要入口。

### 3. Employee Salary

新增为 HR / 管理员薪资业务页：
- 维护员工固定薪资
- 录入月度奖金、扣款等人工项
- 查看自动计算结果
- 执行工资单状态流转

## Information Architecture

页面采用三栏/双栏变体布局，核心结构固定如下：

### Left Panel: Employee List

用于先选员工，再处理该员工的全部薪资内容。

建议字段：
- 员工姓名
- 员工编号
- 部门
- 职位
- 在职状态

支持：
- 搜索
- 按部门筛选
- 按在职状态筛选

### Right Top: Fixed Salary Section

固定薪资区，属于长期配置，写入 `a_class.salary_structures`。

建议字段：
- `base_salary`
- `position_salary`
- `housing_allowance`
- `transport_allowance`
- `meal_allowance`
- `communication_allowance`
- `other_allowance`
- `performance_ratio`
- `commission_ratio`
- `social_insurance_base`
- `housing_fund_base`
- `effective_date`
- `status`

建议操作：
- 保存固定薪资
- 新建生效版本
- 查看历史版本

### Right Middle: Monthly Input Section

月度录入区，属于某员工某月份的人工结算输入，写入 `a_class.payroll_records`。

建议字段：
- 月份选择器 `year_month`
- `bonus`
- `overtime_pay`
- `social_insurance_personal`
- `housing_fund_personal`
- `income_tax`
- `other_deductions`
- `social_insurance_company`
- `housing_fund_company`
- `pay_date`
- `remark`

建议操作：
- 保存月度草稿
- 复制上月人工项
- 按当前配置刷新结果

### Right Bottom: Payroll Result Section

自动结果区，只展示，不手填。

主要展示：
- `commission`
- `performance_score`
- `performance_salary`
- `allowances`
- `gross_salary`
- `total_deductions`
- `net_salary`
- `total_cost`
- `status`

建议操作：
- 确认工资单
- 退回草稿
- 标记已发放

## Data Ownership

### Fixed Salary Inputs

由 `a_class.salary_structures` 负责保存长期配置：

- 底薪
- 岗位工资
- 固定补贴
- 绩效比例
- 默认提成比例
- 社保/公积金基数
- 生效日期

### Monthly Manual Inputs

由 `a_class.payroll_records` 负责保存当月人工项：

- 奖金 / 现金奖励
- 加班费
- 扣款
- 社保、公积金
- 发薪日期
- 备注

### Auto-Calculated Outputs

继续由现有链路提供：
- `a_class.salary_structures`
- `c_class.employee_commissions`
- `c_class.employee_performance`
- `a_class.payroll_records`

结果在页面上统一展示，但不允许直接编辑自动字段。

## Interaction Model

推荐操作顺序固定为：

1. 先选员工
2. 加载该员工当前生效的固定薪资配置
3. 选择月份
4. 录入月度奖金/扣款等人工项
5. 刷新或读取自动计算结果
6. 审核后确认工资单
7. 管理员执行发放

这样可以避免：
- 未配置固定薪资就直接维护工资单
- 只看到结果，不知道结果基于哪套固定薪资

## Business Rules

### Fixed Salary Rules

- 若员工不存在生效中的 `salary_structure`，页面应明确提示“未配置固定薪资”。
- 固定薪资变更会影响后续工资单计算。
- 固定薪资采用“生效版本”语义，历史配置需要可追溯。

### Monthly Input Rules

- `bonus` 属于工资单草稿中的月度人工项，不属于固定薪资。
- 月度人工项只影响当前月份，不反写固定薪资配置。
- 复制上月人工项仅复制人工字段，不复制自动计算字段。

### Payroll State Rules

- `draft`
  - 允许编辑人工字段
  - 允许系统重算覆盖自动字段
- `confirmed`
  - 不允许自动覆盖
  - 允许退回草稿
- `paid`
  - 只读
  - 不允许退回草稿

## Permissions

建议保持简单权限模型：

### Employee

- 只能访问 `我的收入`
- 只读查看自己的工资单

### HR / Admin

- 可访问 `员工薪资`
- 可维护固定薪资
- 可编辑月度草稿
- 可确认工资单

### Admin Only

- 可执行“标记已发放”

## Error Handling

页面应明确处理以下场景：

1. 员工没有固定薪资配置
   - 展示显式空状态和引导文案
2. 当月工资单不存在
   - 允许从当前配置初始化或等待重算生成
3. 工资单为 `confirmed` / `paid`
   - 禁止编辑人工字段并提示原因
4. 上游重算与锁定工资单冲突
   - 继续沿用现有锁定冲突提示机制

## Compatibility Notes

- 不改变 `MyIncome.vue` 的只读定位。
- 不废弃现有 `payroll_records` 三态流转。
- 不引入新的工资单状态。
- 不在本轮引入独立“奖金台账”“现金奖励页”“底薪管理页”。
- 继续复用现有工资单生成链路，只补齐前端业务入口和信息架构。

## Testing Strategy

### Backend

- 保持现有工资单生成与状态流转测试通过
- 新增或补充：
  - 固定薪资配置读取/写入接口测试
  - 固定薪资历史版本规则测试
  - 月度人工字段保存与重算保留规则测试

### Frontend

- 员工列表切换后，固定薪资区与月度区正确联动
- 无固定薪资时，空状态清晰
- 月度奖金保存后，结果区正确更新
- `draft / confirmed / paid` 按钮与可编辑状态正确变化

### End-to-End

- 为某员工设置固定薪资
- 为某月录入奖金与扣款
- 刷新结果并确认工资单
- 管理员标记已发放
- 员工在 `我的收入` 中看到最终实发

## Implementation Scope Boundary

本设计仅解决以下问题：

- HR 侧缺失的 A 类薪资输入入口
- 页面职责重新划分
- 单页内的薪资信息架构与交互模型

本设计不在本轮解决：

- 外部支付 / 财务系统联动
- 更细颗粒度的薪资审批流
- 复杂薪资规则引擎
- 自动个税 / 社保规则计算增强
