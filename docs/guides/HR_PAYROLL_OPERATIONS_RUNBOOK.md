# HR Payroll Operations Runbook

## 1. Scope

本文档面向 HR、管理员和维护人员，说明当前系统中“绩效重算 -> 工资单生成 -> 我的收入展示 -> 工资单流转”的实际运行方式、页面入口、排障步骤和审计定位方法。

当前手册基于仓库中的现行实现，而不是历史设计草案。

## 2. Current Source Of Truth

员工最终收入口径统一以 `a_class.payroll_records` 为准。

相关层次如下：

- 配置层
  - `a_class.salary_structures`
  - `a_class.employee_shop_assignments`
  - `a_class.shop_commission_config`
  - `a_class.target_breakdown`
  - `a_class.sales_targets`
  - `a_class.performance_config`
- 中间计算层
  - `c_class.performance_scores`
  - `c_class.employee_commissions`
  - `c_class.employee_performance`
- 最终结算层
  - `a_class.payroll_records`

说明：

- “我的收入”页面只读取工资单。
- 提成表和个人绩效表保留为计算中间结果，不再作为员工最终收入展示口径。

## 3. Main Entry Points

### Backend routes

- `POST /performance/scores/calculate`
  - 重算店铺绩效、个人提成、个人绩效，并继续生成/更新工资单
- `GET /api/hr/me/income`
  - 返回当前用户当月工资单口径收入
- `GET /api/hr/payroll-records`
  - 查询工资单列表
- `GET /api/hr/payroll-records/{employee_code}/{year_month}`
  - 查询单张工资单
- `PUT /api/hr/payroll-records/{record_id}`
  - 编辑草稿工资单中的人工字段
- `POST /api/hr/payroll-records/{record_id}/confirm`
  - 将工资单标记为已确认
- `POST /api/hr/payroll-records/{record_id}/reopen`
  - 将已确认工资单退回草稿
- `POST /api/hr/payroll-records/{record_id}/pay`
  - 将已确认工资单标记为已发放
  - 当前只允许管理员执行

### Frontend pages

- `frontend/src/views/hr/PerformanceManagement.vue`
  - 发起月度绩效重算
  - 接收并展示工资单锁定冲突
- `frontend/src/views/HumanResources.vue`
  - 查询工资单
  - 编辑草稿
  - 确认工资单
  - 退回草稿
  - 标记已发放
- `frontend/src/views/hr/MyIncome.vue`
  - 只展示工资单口径的完整工资单明细

## 4. Monthly Operation Flow

### Step 1. 发起绩效重算

入口：

- HR 绩效管理页
- 或直接调用 `POST /performance/scores/calculate?period=YYYY-MM`

系统动作：

1. 重算店铺绩效，写入 `performance_scores`
2. 重算个人提成，写入 `employee_commissions`
3. 重算个人绩效，写入 `employee_performance`
4. 调用 `PayrollGenerationService.generate_month(period)` 生成或更新 `payroll_records`

### Step 2. 查看工资单锁定冲突

如果当月存在 `confirmed` 或 `paid` 状态的工资单，并且上游重算结果会改变自动字段：

- 系统不会覆盖该工资单
- 接口返回：
  - `payroll_locked_conflicts`
  - `payroll_locked_conflict_details`
- 前端绩效管理页会弹出“工资单锁定冲突”提示

当前前端展示的是 HR 可读文案，例如：

- `EMP001（已确认）: 基本工资、实发工资、公司总成本`

### Step 3. 处理冲突工资单

推荐处理方式：

1. 在工资单列表中找到冲突员工对应月份
2. 如果需要接受最新重算结果：
   - 先执行“退回草稿”
   - 再次发起绩效重算
3. 如果要保留当前已确认版本：
   - 不做操作
   - 保持工资单锁定

### Step 4. 审核草稿工资单

草稿工资单允许：

- 编辑人工字段
  - 加班费
  - 奖金
  - 个人社保
  - 个人公积金
  - 个税
  - 其他扣款
  - 公司社保
  - 公司公积金
  - 发薪日期
  - 备注

保存后系统会重新计算：

- `gross_salary`
- `total_deductions`
- `net_salary`
- `total_cost`

### Step 5. 确认工资单

执行“确认”后：

- 状态从 `draft` -> `confirmed`
- 后续月度重算不再自动覆盖该工资单
- 如需再次接受重算，只能先退回草稿

### Step 6. 标记已发放

执行“已发放”后：

- 状态从 `confirmed` -> `paid`
- 系统自动填写 `pay_date`，如果此前为空
- 当前工资单进入只读状态
- 后端写入审计日志

注意：

- 只有管理员可以调用 `pay` 路由
- 前端也只对管理员显示“已发放”按钮

## 5. Payroll Status Semantics

### `draft`

- 可编辑人工字段
- 可被重算刷新自动字段

### `confirmed`

- 不允许自动覆盖
- 可退回 `draft`
- 可由管理员标记为 `paid`

### `paid`

- 只读
- 不允许自动覆盖
- 不允许退回 `draft`

## 6. My Income Behavior

“我的收入”页面当前行为：

- 若当前账号未关联员工档案：
  - 返回 `linked=false`
- 若已关联员工但当月工资单不存在：
  - 返回空态
- 若当月工资单存在：
  - 顶部金额显示 `net_salary`
  - 明细展示完整工资单字段，分为：
    - 应发项
    - 扣除项
    - 公司成本

说明：

- 当前实现不再回退拼装 `salary_structures + employee_commissions + employee_performance`
- 最终展示严格走工资单

## 7. Audit And Traceability

### 我的收入访问审计

`GET /api/hr/me/income` 会写审计：

- `resource = me/income`
- `details.result_status` 可能为：
  - `linked_false`
  - `payroll_missing`
  - `success`

### 工资单已发放审计

`POST /api/hr/payroll-records/{record_id}/pay` 成功后会写审计：

- `action = pay`
- `resource = payroll_record`
- `resource_id = record_id`
- `details.result_status = paid`
- `details.employee_code`
- `details.year_month`
- `details.pay_date`

### 审计排查建议

如果要追某个员工某月工资单：

1. 先查 `a_class.payroll_records`
2. 再查 `c_class.employee_commissions`
3. 再查 `c_class.employee_performance`
4. 最后看审计日志：
   - 是否有人执行过 `pay`
   - 是否有人访问过 `/me/income`

## 8. Troubleshooting

### 场景 A：重算后工资单没有变化

先检查：

1. 该工资单是否为 `confirmed` 或 `paid`
2. 接口响应里的 `payroll_locked_conflicts`
3. `payroll_locked_conflict_details` 中是否出现该员工

处理：

- 若是锁定导致：
  - 退回草稿
  - 重新发起绩效重算

### 场景 B：我的收入页面显示空态

先检查：

1. 当前账号是否已关联员工档案
2. 当月 `payroll_records` 是否存在
3. 是否已执行当月绩效重算

处理：

- 无员工档案：
  - 联系管理员关联账号与员工
- 无工资单：
  - 发起 `POST /performance/scores/calculate?period=YYYY-MM`

### 场景 C：看不到“已发放”按钮

先检查：

1. 当前工资单状态是否为 `confirmed`
2. 当前登录用户是否为管理员

说明：

- 非管理员即使能看到工资单，也不会看到“已发放”按钮
- 即使前端异常显示，后端仍会做管理员权限校验

### 场景 D：标记已发放失败

先检查：

1. 当前工资单是否为 `confirmed`
2. 当前用户是否为管理员
3. 是否有数据库提交失败

处理：

- 若返回 403：
  - 检查当前用户角色
- 若返回 409：
  - 检查工资单当前状态

## 9. Operational Checklist

月度操作建议按这个顺序执行：

1. 选择月份，发起绩效重算
2. 记录 `shop_performance_upserts / commission_upserts / employee_performance_upserts / payroll_upserts`
3. 检查是否存在 `payroll_locked_conflicts`
4. 若有冲突，逐个处理并决定是否退回草稿
5. 审核草稿工资单的人工字段
6. 确认工资单
7. 由管理员标记已发放
8. 抽查“我的收入”页面是否显示正确的 `net_salary`

## 10. Current Boundaries

当前已闭环：

- 绩效重算
- 工资单生成
- 工资单编辑/确认/退回/已发放
- 我的收入工资单口径展示
- 锁定冲突明细展示
- 已发放审计

当前仍属后续扩展：

- `paid` 与外部支付/财务系统联动
- 更细粒度的工资单权限模型
- 专门的工资单冲突列表页
