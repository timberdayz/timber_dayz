# 月度冻结快照与我的收入口径设计

## 目标

在不推翻现有“绩效管理 -> 提成 -> 工资单 -> 我的收入 -> 月结中心”主链路的前提下，补齐两件事：

1. 为月结批准后的历史月份提供稳定、可审计、不可漂移的冻结快照机制。
2. 梳理“我的收入”模块当前真实显示口径、计算来源和设计问题，避免结果可看但来源不可解释。

本文只定义冻结快照与展示口径，不重写现有薪资、绩效、提成计算引擎。

## 当前链路摘要

### 运行态主链路

```text
employee_shop_assignments
+ shop_commission_config
+ shop_profit_basis
+ performance_scores
-> employee_commissions

performance_scores
+ attendance / manual adjustments
-> employee_performance

salary_structures
+ employee_commissions
+ employee_performance
-> payroll_records

payroll_records
-> 我的收入
-> 月结人员成本
```

### 当前最终真源

- 员工最终收入真源：`a_class.payroll_records`
- 月结人员成本真源：`a_class.payroll_records.total_cost`
- 中间计算层：
  - `c_class.employee_commissions`
  - `c_class.employee_performance`
  - `c_class.performance_scores`

## 现有规则基线

当前系统已收口为以下规则：

1. 店铺绩效系数只影响提成，不影响绩效工资。
2. 个人绩效得分只认店铺绩效继承 + 调整项，不再缺失时回退为 `achievement_rate * 100`。
3. 同店同月人员提成比例总和不得超过 `100%`。
4. `supervisor / operator` 当前仅作为业务标签，不再承担唯一主管约束。
5. 工资单是员工最终收入展示与结算真源。

## 月度冻结快照设计

### 冻结目标

冻结的是“某次月结批准时采用的结算解释口径”，而不是把所有运行表彻底锁死。

批准后：

- 历史已批准月份必须稳定可追溯
- 上游业务表仍允许继续编辑
- 若要让上游修改影响历史月，必须先 `reopen -> 重算 -> 重新批准`

### 冻结边界

#### 进入 snapshot 的层

1. 店铺利润基数快照
   - 来源：`finance.shop_profit_basis`
2. 员工提成快照
   - 来源：`c_class.employee_commissions`
3. 员工绩效快照
   - 来源：`c_class.employee_performance`
4. 工资单快照
   - 来源：`a_class.payroll_records`

#### 不直接冻结、继续保持运行态的层

1. `a_class.employee_shop_assignments`
2. `a_class.shop_commission_config`
3. `a_class.salary_structures`
4. `a_class.performance_config`
5. `a_class.sales_targets`
6. `a_class.target_breakdown`

原因：

- 这些表是配置层或过程层，应继续服务未来月份与重算流程
- 历史月份解释应依赖 snapshot，而不是依赖“当前配置仍长什么样”

## Snapshot 表设计

### 统一公共字段

所有 snapshot 表建议统一包含：

- `id`
- `settlement_id`
- `period_month`
- `snapshot_version`
- `snapshot_status`
  - `active`
  - `superseded`
- `created_at`
- `created_by`

### 1. 店铺利润基数快照

表名建议：

- `finance.monthly_profit_shop_basis_snapshots`

字段建议：

- `platform_code`
- `shop_id`
- `shop_name`
- `basis_version`
- `orders_profit_amount`
- `a_class_cost_amount`
- `profit_basis_amount`

唯一键建议：

- `(settlement_id, snapshot_version, platform_code, shop_id)`

### 2. 员工提成快照

表名建议：

- `finance.monthly_profit_employee_commission_snapshots`

字段建议：

- `employee_code`
- `employee_name`
- `platform_code`
- `shop_id`
- `shop_name`
- `sales_amount`
- `commission_rate`
- `commission_amount`

唯一键建议：

- `(settlement_id, snapshot_version, employee_code, platform_code, shop_id)`

说明：

- 建议按“员工-店铺”粒度冻结，而不是只存员工月汇总
- 这样可以解释某员工当月提成由哪些店构成

### 3. 员工绩效快照

表名建议：

- `finance.monthly_profit_employee_performance_snapshots`

字段建议：

- `employee_code`
- `employee_name`
- `actual_sales`
- `achievement_rate`
- `performance_score`
- `attendance_adjustment_score`
- `manual_adjustment_score`

唯一键建议：

- `(settlement_id, snapshot_version, employee_code)`

说明：

- 如果第一阶段无法拆出调整项明细，可先只冻结：
  - `actual_sales`
  - `achievement_rate`
  - `performance_score`

### 4. 工资单快照

表名建议：

- `finance.monthly_profit_payroll_snapshots`

字段建议：

- `payroll_record_id`
- `employee_code`
- `employee_name`
- `base_salary`
- `position_salary`
- `performance_salary`
- `commission`
- `allowances`
- `bonus`
- `overtime_pay`
- `gross_salary`
- `social_insurance_personal`
- `housing_fund_personal`
- `income_tax`
- `other_deductions`
- `total_deductions`
- `net_salary`
- `social_insurance_company`
- `housing_fund_company`
- `total_cost`
- `payroll_status`
- `pay_date`
- `remark`

唯一键建议：

- `(settlement_id, snapshot_version, employee_code)`

## 批准 / 回退 / 重建规则

### draft

- 读运行态
- 允许重建
- 允许修改月结参数
- 允许上游继续重算

### approved

- 读 snapshot
- 不允许直接重建
- 不允许直接修改月结参数
- 不允许静默覆盖历史解释口径

### reopen

推荐语义：

- `approved -> draft`
- 不删除历史 snapshot
- 把当前 `active` snapshot 标记为 `superseded`
- 下次重新批准时生成新版本 `snapshot_version`

### approve 流程

建议在一个事务内完成：

1. 校验 `monthly_profit_settlements.status == draft`
2. 计算新 `snapshot_version`
3. 读取运行态数据：
   - `shop_profit_basis`
   - `employee_commissions`
   - `employee_performance`
   - `payroll_records`
4. 写入 4 张 snapshot 表
5. 更新 `monthly_profit_settlements.status = approved`
6. 写 `approved_at / approved_by`

关键原则：

- snapshot 写入失败，则批准失败
- 批准动作只冻结当前运行态结果，不在批准时再次重算

### reopen 流程

建议在一个事务内完成：

1. 校验 `monthly_profit_settlements.status == approved`
2. 将当前 `active` snapshot 更新为 `superseded`
3. 更新 `monthly_profit_settlements.status = draft`
4. 清空或重置 `approved_at / approved_by`

### rebuild 流程

- 当 `status = draft` 时允许 rebuild
- 当 `status = approved` 时拒绝 rebuild
- 若需 rebuild，必须先 `reopen`

## 查询读取规则

### 月结详情

- `draft`：读运行态聚合
- `approved`：优先读 snapshot

### 历史追溯

所有审计、对账、解释页面对已批准月份一律优先读 snapshot，不回读运行态。

关键原则：

- `approved 看快照`
- `draft 看运行态`

## 我的收入模块当前真实行为

### 当前显示内容

当 `GET /api/hr/me/income` 返回有效工资单时，前端会显示：

1. 顶部卡片
   - 当月实发
   - 固定工资
   - 提成
2. 工资单明细
   - 应发项
   - 扣除项
   - 公司成本
3. 工资单状态、发薪日期、备注

页面实现：

- `frontend/src/domains/business/views/hr/MyIncome.vue`

### 当前后端读取逻辑

后端只读：

- 当前用户关联的 `Employee`
- 当月 `a_class.payroll_records`

如果没有工资单：

- 返回空态

如果有工资单：

- `total_income = payroll.net_salary`
- `base_salary = payroll.base_salary + payroll.position_salary`
- `commission_amount = payroll.commission`
- `breakdown.payroll = 工资单明细字段集合`

实现位置：

- `backend/domains/business/routers/hr_employee.py`

### 当前不是如何计算

“我的收入”当前**不会**在接口层重新拼装：

- `salary_structures`
- `employee_commissions`
- `employee_performance`

它已经收口为直接读取工资单结果。

## 从我的收入倒推出来的设计问题

### 1. 结果口径已收口，但解释口径不足

用户可以看到：

- 实发
- 固定工资
- 提成
- 明细

但看不到：

- 提成为什么是这个数
- 绩效工资为什么是这个数
- 是否受店铺绩效系数影响
- 个人绩效分从何而来

这会导致：

- 结果可看
- 来源不透明

### 2. 接口 schema 与真实返回存在脱节

`MyIncomeResponse` 仍保留：

- `commission_rate`
- `performance_score`
- `achievement_rate`

但当前接口实际返回时，这些解释字段没有真正落为有效口径。

### 3. 摘要卡片层级不完整

当前顶部卡片展示：

- 当月实发
- 固定工资
- 提成

但没有单独展示：

- 绩效工资

在当前工资组成里，绩效工资是正式收入项，缺少这张卡片会让解释不完整。

### 4. 历史月份仍直接读运行态工资单

当前“我的收入”直接读 `payroll_records`。  
若后续月结批准后引入 snapshot，应进一步定义：

- 当月草稿阶段读运行态
- 已批准历史月份是否优先读 snapshot

否则员工看到的历史金额与财务月结解释口径可能出现偏差。

## 我的收入模块优化建议

### 结果层

继续展示工资单结果，但建议卡片调整为：

1. 当月实发
2. 固定薪资
3. 绩效工资
4. 提成

### 说明层

新增只读说明，不参与计算：

- 提成来源：
  - 店铺利润分配结果
  - 已含店铺绩效系数
- 绩效工资来源：
  - 固定薪资基座 × 个人绩效得分
- 个人绩效得分来源：
  - 店铺绩效继承 + 调整项

### 历史月份读取建议

- `draft / 当前运行月`：可读运行态工资单
- `approved 历史月`：优先读 payroll snapshot

## 推荐实现顺序

### Phase 1

1. 新增 4 张 snapshot 表
2. 将 approve / reopen / rebuild 行为改为版本化冻结
3. 已批准月结详情优先读 snapshot

### Phase 2

1. 优化“我的收入”摘要卡片
2. 增加收入说明层
3. 清理 `MyIncomeResponse` 中已不再作为正式口径的字段设计

### Phase 3

1. 视业务需要决定“我的收入”历史月份是否完全切到 snapshot
2. 若需要，再扩展 snapshot header / 版本浏览 / 对账页面

## 开放决策

1. “我的收入”是否要允许员工查看历史已批准月份的 snapshot 版本，而不仅是当前工资单状态？
2. `MyIncomeResponse` 是否要正式移除 `commission_rate / performance_score / achievement_rate` 顶层字段，改为纯工资单口径？
3. 员工端是否需要“收入说明”展开区，还是只在 HR / 财务端提供解释能力？

## 结论

推荐采用：

- 运行态继续服务重算与编辑
- 批准时复制出 snapshot 冻结解释口径
- 已批准月份优先读 snapshot
- “我的收入”继续以工资单为结果真源，但补齐解释层，而不是回退到重新拼装中间表

这套方案在不重写现有主链路的前提下，能同时解决：

- 历史月份结果漂移
- 月结审计解释困难
- 员工收入结果可看但来源不透明
