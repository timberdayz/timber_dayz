# Monthly Profit Settlement Runbook

## 1. 目的

本文说明“月度利润结算中心”的实际使用方式，用于把当月店铺结算利润、人员成本、跟投收益与公司留存统一汇总为公司级月结结果。

适用角色：

- 财务
- 管理员
- 需要核对月度经营结果的管理层

## 2. 当前系统口径

### 2.1 店铺纯利润口径

当前正式结算口径仍然是：

```text
profit_basis_amount = orders_profit_amount - a_class_cost_amount
```

说明：

- `orders_profit_amount`：店铺月度订单利润
- `a_class_cost_amount`：当月归集到店铺的 A 类费用
- `b_class_cost_amount`：字段保留，但当前 Phase 1 不计入正式月结

### 2.2 公司月度净利润口径

公司月度净利润由当月所有店铺 `profit_basis_amount` 汇总而来：

```text
company_net_profit = SUM(shop_profit_basis.profit_basis_amount)
```

### 2.3 月结总公式

月结中心采用如下总公式：

```text
公司月度净利润 = 人员成本总额 + 跟投收益总额 + 公司留存总额 + 调整项
```

等价地：

```text
公司留存总额 = 公司月度净利润 - 人员成本总额 - 跟投收益总额 - 调整项
```

## 3. 当前系统来源模块

月结中心本身不是利润计算源，而是汇总与审批入口。

上游来源如下：

- 店铺结算利润：
  - `finance.shop_profit_basis`
- 店铺提成：
  - `c_class.employee_commissions`
- 工资和人工成本：
  - `a_class.payroll_records`
- 跟投收益：
  - `finance.follow_investment_settlements`
  - `finance.follow_investment_details`

## 4. 当前 Phase 1 范围

本阶段已经实现：

- 公司级月结主表
- 人员成本明细表
- 跟投收益明细表
- 调整项表
- 月结查询
- 月结重建
- 目标比例更新
- 审批
- 回退草稿
- 前端财务页中的月结中心入口

本阶段尚未完全落地：

- 差异阈值自动拦截审批
- 调整项细粒度录入界面
- 工资成本按店铺回摊
- 绩效系数治理
- 跟投 `approved` / `paid` 最终业务口径定版

## 5. 页面入口

前端入口：

- `财务管理 -> 利润分配基准 -> 月度利润结算中心`

对应页面：

- `frontend/src/views/FinancialManagement.vue`

后端接口：

- `GET /api/finance/monthly-profit-settlement`
- `POST /api/finance/monthly-profit-settlement/rebuild`
- `PUT /api/finance/monthly-profit-settlement/{id}/targets`
- `POST /api/finance/monthly-profit-settlement/{id}/approve`
- `POST /api/finance/monthly-profit-settlement/{id}/reopen`

## 6. 推荐月结顺序

以 `2026-05-10` 处理 `2026-04` 月结为例，建议顺序如下。

### Step 1. 确认利润基础数据完成

先确认 4 月的利润基础已经稳定：

- 订单利润已同步
- 广告等 A 类费用已录入并归集
- `profit_basis_amount` 可查询

若这一步未完成，不应进入月结审批。

### Step 2. 确认店铺归属与提成配置

在“人员店铺归属和提成比”模块中确认：

- 店铺归属关系
- 提成比例
- 可分配净利润率

这一步决定“店铺提成”金额。

### Step 3. 重算绩效

执行绩效重算，保证：

- 店铺绩效
- 个人提成
- 个人绩效
- 工资单自动字段

都是最新结果。

### Step 4. 确认工资和人工字段

在“员工薪资”中确认：

- 固定薪资
- 奖金
- 加班费
- 个税
- 社保、公积金
- 公司承担社保、公积金

这一步保证人工成本总额可用。

### Step 5. 确认跟投收益

确认当月跟投结算已完成审批。

当前 Phase 1 实现中，月结中心按 `approved` 状态的跟投收益明细计入实际值。

### Step 6. 重建月结

在月结中心选择月份，点击“重建月结”。

系统会自动汇总：

- 公司月度净利润
- 人员成本
- 跟投收益
- 公司留存

### Step 7. 调整目标比例

在月结中心设置：

- 人员目标比例
- 跟投目标比例
- 公司目标比例
- 调整项

当前要求：

```text
人员目标 + 跟投目标 + 公司目标 = 100%
```

### Step 8. 对比目标与实际

重点查看：

- 人员目标 / 实际
- 跟投目标 / 实际
- 公司目标 / 实际

若差异明显，应先回到上游核对，不建议直接审批。

### Step 9. 审批月结

确认无误后执行审批。

审批后：

- 状态变为 `approved`
- 再次重建会被拦截
- 再次修改目标比例会被拦截

### Step 10. 如需修改，先回退草稿

如果审批后仍需修改：

- 先执行“回退草稿”
- 再去修正上游数据或调整月结参数
- 最后重新审批

## 7. 当前人员成本组成

当前 Phase 1 中，人员成本来自两类来源：

### 7.1 店铺提成

来源：

- `c_class.employee_commissions`

在月结明细中表现为：

- `detail_type = shop_commission`

### 7.2 工资总成本

来源：

- `a_class.payroll_records.total_cost`

在月结明细中表现为：

- `detail_type = payroll_total_cost`

说明：

- 当前是公司级总成本直接入账
- 尚未回摊到店铺

## 8. 当前跟投收益口径

当前 Phase 1 中，跟投收益来自：

- `finance.follow_investment_settlements.status = approved`
- `finance.follow_investment_details.approved_income`

按投资人粒度汇总进入月结明细。

这意味着：

- 未审批的跟投结果不会计入月结
- 已审批的跟投会计入月结实际值

## 9. 状态语义

### `draft`

- 允许重建
- 允许修改目标比例
- 允许审批

### `approved`

- 不允许直接重建
- 不允许直接修改目标比例
- 如需修改，必须先回退草稿

## 10. 常见问题

### Q1：为什么月结中心看不到数据？

先检查：

- 该月份是否已有 `shop_profit_basis`
- 是否已完成上游费用归集
- 是否已选择正确月份

### Q2：为什么跟投收益是 0？

先检查：

- 该月份是否存在跟投结算
- 结算状态是否为 `approved`
- 是否存在对应 `follow_investment_details`

### Q3：为什么审批后不能再改？

这是当前设计要求。

审批后的月结默认视为锁定状态，若需修改必须先执行回退草稿。

### Q4：为什么人员成本和预期不一致？

先检查：

- 店铺提成配置是否正确
- 工资单是否已重算并确认月度人工字段
- 是否把公司承担社保、公积金计入工资总成本

## 11. 当前已知限制

- 差异阈值尚未强制拦截审批
- 调整项只有基础能力，前端未做完整明细录入
- 工资总成本尚未按店铺回摊
- 绩效系数仍沿用现有系统，不在本轮月结中心内重新定义
- 跟投是否按 `paid` 计入，尚待业务最终确认

## 12. 操作建议

当前建议的使用方式是：

- 先把月结中心当作“总账核对中心”
- 不要跳过上游核对直接审批
- 审批前重点看“目标 / 实际”差异
- 若差异大，优先回查提成、工资单、跟投审批，而不是直接靠调整项抹平
