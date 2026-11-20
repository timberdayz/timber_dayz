# Monthly Profit Settlement Runbook

> 涉及店铺赛马、黄牌/红牌、淘汰评估与挂店人提成继承口径时，请优先参见 `docs/guides/PERFORMANCE_RACING_POLICY.md`。历史“观察池”结果仅作兼容展示。

## 1. 目的

本文说明“月度利润看板”的实际使用方式，用于把当月店铺结算利润、员工侧分配额、人工调整额与公司留存统一汇总为公司级月结结果。

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

### 2.3 月度利润看板总公式

> 2026-11 口径变更：看板改为只读聚合后，总公式不再含「跟投收益」，
> 「人员成本总额」改为**员工侧分配额**（只取提成后金额）。
> 详见第 17 节「业务口径变更签字记录」。

月度利润看板采用如下总公式：

```text
公司留存总额 = 公司月度净利润 - 员工侧分配额 - 人工调整额
```

等价地：

```text
公司月度净利润 = 员工侧分配额 + 人工调整额 + 公司留存总额
```

其中：

- **公司月度净利润** = `SUM(shop_profit_basis.profit_basis_amount)`（见 2.2）
- **员工侧分配额** = 人力成本分摊表的 `Σ(performance_amount + commission_amount)`（见第 7 节）
- **人工调整额** = 人工调整项表金额合计（正数减少公司留存）

### 2.4 看板如何读取上游利润基数（2026-11 追加说明）

> 本节只说明**看板怎么读**，**不改动上游公式**。
> 上游口径的 SSOT 是 `backend/services/labor_cost_policy_service.py` 的
> `LaborCostPolicyService`。

- 看板读 `finance.shop_profit_basis`，**只取非 legacy `A_ONLY_V1` 口径行**
  （当前口径 `SETTLEMENT_BASIS_V1`；历史口径行保留以保审计可追溯，但不参与看板计算）。
- 看板**不重算**利润基数，也**不回写**该表。
- `b_class_cost_amount`（B 类成本）当前仍不计入正式月结，与 2.1 一致。

## 3. 当前系统来源模块

月度利润看板本身不是利润计算源，而是只读汇总与展示入口。

上游来源如下：

- 店铺结算利润：
  - `finance.shop_profit_basis`
- 员工侧分配额（绩效工资 + 提成）：
  - `finance.employee_labor_cost_allocations`
  - 按 `calculation_version` 严格等值过滤（当前口径 `LABOR_COST_ALLOC_V1`）
- 人工调整项：
  - `finance.monthly_profit_adjustments`
- 工资单（**不再**作为人员成本结算口径）：
  - `a_class.payroll_records`
  - 工资单 `total_cost` 含提成前人力成本，该部分已在利润基数里扣过，见第 7 节
- 提成中间结果：
  - `c_class.employee_commissions`
  - 该表用于生成工资单中的 `commission` 字段，是中间层，不单独汇总

### 3.1 冻结事实源

当前结算链路中，以下对象视为冻结事实源，结算模块只能读取，不能反向改写：

- `PayrollRecord`
- `MonthlyProfitPayrollSnapshot`
- `EmployeeCommission`
- `EmployeePerformance`
- `ShopProfitBasis`
- `EmployeeLaborCostAllocation`

## 4. 当前范围

> 2026-11：本模块正由「月度利润结算中心」改造为只读的「月度利润看板」。
> **口径已定版**（见第 2、7 节与第 17 节）；**流程细节**（重建 / 目标比例 / 审批 / 回退草稿）
> 随看板改造逐步下线，以看板聚合层的只读结果为准。

本阶段已经实现：

- 公司级月结主表
- 调整项表
- 月结查询
- 前端财务页中的月度利润看板入口

本阶段尚未完全落地：

- 调整项细粒度录入界面（看板只提供人工调整项的录入与列表）
- 员工侧分配额的店铺 / 人级下钻展示
- 绩效系数治理（提成用逐店 min、绩效工资用加权平均，两套系数尚未收敛；
  收敛方案见 `docs/superpowers/plans/2026-11-21-finance-dashboard-post-launch-v2.md`）
- 跟投 `approved` / `paid` 最终业务口径定版 —— 跟投模块已下线，本条作废

## 5. 页面入口

前端入口：

- `财务管理 -> 利润分配基准 -> 月度利润看板`

对应页面：

- `frontend/src/domains/business/views/FinancialManagement.vue`

当前前端结构：

- 编排层：`FinancialManagement.vue`
- 公司月结面板：`MonthlySettlementPanel.vue`
- 店铺工作区面板：`SettlementWorkspacePanel.vue`
- 结算专用状态：`frontend/src/stores/financeSettlement.js`

后端接口：

- `GET /api/finance/monthly-profit-settlement`

> 写操作端点（`rebuild` / `targets` / `approve` / `reopen`）随看板改造下线；
> 人工调整项改为看板内的独立写入口。改造完成后以实际路由为准。

## 6. 推荐月结顺序

> ⚠️ **2026-11 口径变更**：看板改为只读后，本节 Step 6 ~ Step 10 的
> 「重建 / 目标比例 / 审批 / 回退草稿」是**旧结算流程**，随看板改造下线。
> 看板时代的实际顺序是：**确认上游口径 → 只读查看结果 → 必要时录人工调整项**。
> 下面的 Step 1 ~ Step 5 仍是**有效的前置核对**，继续按它执行。

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

> ⚠️ 跟投模块已于 2026-11 下线，本步**作废**，不再需要执行。

### Step 6. 重建月结（旧流程，已下线）

> 看板改为只读后不再「重建」，直接按当月数据实时汇总。保留本节仅作历史参考。

系统会自动汇总：

- 公司月度净利润
- 员工侧分配额
- 人工调整额
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
- 当月月结会冻结为 snapshot 版本
- 后续月结详情优先读取 snapshot，而不是继续读运行时中间表
- 再次重建会被拦截
- 再次修改目标比例会被拦截

### Step 10. 如需修改，先回退草稿

如果审批后仍需修改：

- 先执行“回退草稿”
- 当前 active snapshot 会被标记为 `superseded`
- 再去修正上游数据或调整月结参数
- 最后重新审批

## 6.1 当前页面内的推荐操作顺序

当前月度利润看板页面显式提示推荐顺序：

1. 先查或重算利润口径
2. 再查看各店分配分布
3. 再录入 / 核对人工调整项
4. 最后回到公司层核对总账

## 7. 当前员工侧分配额组成

> ⚠️ **2026-11 口径变更**：**推翻**原「月结人员成本以工资单为最终结算口径」。
>
> 现口径：**以人力成本分摊表的「绩效工资 + 提成」为准。**
>
> 作废原因：工资单 `total_cost` 已包含提成前人力成本（底薪等），
> 而这部分在利润基数里**已经扣过一次**，再作为人员成本扣除就是同一笔钱扣两次。

看板的员工侧分配额**只取提成后金额**（绩效工资 + 提成）。

### 7.1 员工侧分配额

来源：

- `finance.employee_labor_cost_allocations`

过滤条件：

- `calculation_version` **严格等值**过滤（当前口径 `LABOR_COST_ALLOC_V1`）
- `allocation_scope` 同时含 `shop`（有店铺归属）与 `company`（总部等无店铺归属）两种范围，**两者都要计入**

公式：

```text
员工侧分配额 = Σ(performance_amount + commission_amount)
```

说明：

- **只取提成后金额**（`performance_amount` 绩效工资 + `commission_amount` 提成）
- **不含提成前人力成本**（底薪、岗位工资、津贴、加班费、奖金、公司承担社保、公司承担公积金）
  —— 这部分已在 `profit_basis_amount` 里扣过，见 2.1
- 因此**不得**再把 `a_class.payroll_records.total_cost` 当作月结人员成本扣除
- `c_class.employee_commissions` 是工资单生成的中间层，成品已落在分摊表的 `commission_amount`，
  不单独汇总
- 看板层**不重算**分摊，直接读分摊表既有结果

### 7.2 旧口径（已作废）

原口径（2026-11 作废）：

```text
月结人员成本 = a_class.payroll_records.total_cost
```

在月结明细中曾表现为 `detail_type = payroll_total_cost`。

作废原因见本节顶部说明与第 17 节签字记录。

## 8. 当前跟投收益口径

> ⚠️ 跟投模块已于 2026-11 下线，本节**作废**，仅作历史参考。
> 看板的总公式（2.3）已不含跟投收益。

当前 Phase 1 中，跟投收益来自：

- `finance.follow_investment_settlements.status = approved`
- `finance.follow_investment_details.approved_income`

按投资人粒度汇总进入月结明细。

这意味着：

- 未审批的跟投结果不会计入月结
- 已审批的跟投会计入月结实际值

## 9. 状态语义

> ⚠️ `draft` / `approved` 是**旧结算流程**的状态，随看板改造下线。
> 看板时代不再有「审批锁定」这一层，只保留「人工调整项」这一处写入。
> 本节保留仅作历史参考。

### `draft`

- 允许重建
- 允许修改目标比例
- 允许审批

### `approved`

- 不允许直接重建
- 不允许直接修改目标比例
- 如需修改，必须先回退草稿

## 10. 常见问题

### Q1：为什么月度利润看板看不到数据？

先检查：

- 该月份是否已有 `shop_profit_basis`
- 是否已完成上游费用归集
- 是否已选择正确月份

### Q2：为什么跟投收益是 0？

> ⚠️ 跟投模块已下线，本问**作废**。

历史排查步骤：

- 该月份是否存在跟投结算
- 结算状态是否为 `approved`
- 是否存在对应 `follow_investment_details`

### Q3：为什么审批后不能再改？

> ⚠️ 旧结算流程的设计要求，随看板改造下线。
> 看板时代没有「审批锁定」，人工调整项可随时增删（每次改动留痕）。

### Q4：为什么员工侧分配额和预期不一致？

先检查：

- 店铺提成配置是否正确
- 个人提成是否已先重算并正确写入工资单 `commission`
- 工资单是否已重算并确认月度人工字段
- `finance.employee_labor_cost_allocations` 是否已按当前 `calculation_version`
  （`LABOR_COST_ALLOC_V1`）刷新 —— 历史口径行不参与计算

> ⚠️ 别再拿 `payroll_records.total_cost` 去对：它含提成前人力成本，
> 比看板口径大得多，且那部分在利润基数里已经扣过。

## 11. 当前已知限制

- 调整项只有基础能力，前端未做完整明细录入
- 员工侧分配额直接读人力成本分摊表既有结果，不在看板层重算分摊
- 绩效系数仍沿用现有系统（提成用逐店 min、绩效工资用加权平均，两套系数数值可不同），
  不在本轮看板内重新定义；收敛方案见
  `docs/superpowers/plans/2026-11-21-finance-dashboard-post-launch-v2.md`
- 跟投是否按 `paid` 计入 —— 跟投模块已下线，本条作废

## 12. 操作建议

当前建议的使用方式是：

- 先把月度利润看板当作“总账核对中心”
- 不要跳过上游核对直接下结论
- 重点看「净利润 → 员工侧分配额 → 人工调整额 → 公司留存」的拆解
- 若差异大，优先回查提成、工资单与人力成本分摊表，而不是直接靠调整项抹平

## 13. Performance Racing And Warning Supplement (2026-04-11)

- 月度利润看板继续只汇总上游结果，不重新定义绩效赛马规则。
- 当前上游绩效已引入全公司店铺赛马机制，看板读取到的员工侧分配额（提成部分）已经包含赛马奖惩结果。
- 当前赛马补充规则如下：
  - 经营天数少于 15 天只生成数据覆盖风险提示，不影响正式排名系数；月度数据完整性决定正式资格。
  - 正式赛马池中的店铺会按公司总榜排名生成绩效系数，并叠加绝对分数底线。
  - 绩效低于 70 分生成黄牌预警。
  - 绩效低于 60 分生成红牌预警。
  - 连续两个月历史红牌且本月继续红牌时，系统生成淘汰评估预警。
- 上述预警写入 `c_class.shop_alerts`，但不改变月度利润看板“总账汇总层”的定位。

## 14. Frontend Shop Status Rules (2026-04-11)

月度利润看板页面当前使用以下前端固化口径，供人工联调时对照：

- `已具备结算信号`
  - 同时存在当月跟投记录与当月结算台账
- `可继续结算店铺`
  - 已具备结算信号，可继续进入单店结算处理
- `待补经营数据`
  - 既没有跟投记录，也没有当月结算台账
- `异常店铺`
  - 缺少结算台账，或仍处于待补经营数据状态

当前页面中的状态字段统一来源于前端 `getShopStatus()`：

- `canSettle`
- `pendingData`
- `hasException`
- `hasFollowInvestment`
- `hasSettlement`

当前页面筛选与展示规则：

- `全部店铺`
  - 显示当前平台下所有已启用店铺
- `只看异常店铺`
  - 显示 `hasException = true` 的店铺
- `只看待补经营数据`
  - 显示 `pendingData = true` 的店铺
- `本平台店铺概览`
  - 汇总当前筛选后平台店铺数、可继续结算店铺、有跟投记录店铺、有结算台账店铺、待补经营数据店铺

说明：
- 这套规则当前是月度利润看板页面的正式前端口径，主要用于联调和人工核对
- 如果后续业务确认需要把“可月结 / 异常”上升为后端统一规则，应再同步到后端接口或看板聚合服务

## 15. Snapshot Read Rules (2026-05-29)

> ⚠️ 快照读取规则属**旧结算流程**，随看板改造下线。
> 看板时代直接按当月运行态数据聚合，不再区分 `draft` / `approved` 两套读路径。

- 已批准月份的月结详情优先读取冻结 snapshot，不再直接回读运行态工资单或中间结果。
- `reopen` 会使当前 active snapshot 失效；重新批准后会生成新的 snapshot 版本。
- `draft` 继续读取运行态聚合结果；`approved` 一律优先看 snapshot。

## 16. 标准真实回归样例（2026-05-30）

> ⚠️ 本样例含跟投项，跟投模块已下线，跟投相关的两行结论不再可复现；
> 其余结论保留作历史回归基线。

当前推荐的标准真实回归样例如下：

- 员工：李四
- 员工编码：`EMP260004`
- 用户名：`lisi`
- 月份：`2026-03`
- 跟投样例店铺：`shopee / 1308200825`

当前已验证结论：

- 李四 `我的收入` 为 `5946.53`
- 李四 `我的跟投收益` approved 值为 `938.5`
- 月结 `approved` 后，`/api/hr/me/income` 读取 `payroll_snapshot`
- 月结 `reopen` 后，`/api/hr/me/income` 回退为 `payroll_record`
- 再次 `rebuild -> approve` 后，会生成新的 active snapshot，并保留 superseded 历史版本

## 17. 业务口径变更签字记录

> 本节记录**看板口径的生效与作废**，用于回溯「某个数为什么和以前不一样」。
> 引用看板金额时，若跨过下面的生效日期，必须同时说明口径。

### 17.1 人员成本口径变更（2026-11 生效）

| 项 | 内容 |
|---|---|
| 变更对象 | 月结「人员成本」的结算口径 |
| 原口径（**作废**） | `a_class.payroll_records.total_cost`（工资单总成本） |
| 新口径（**生效**） | `finance.employee_labor_cost_allocations` 的 `Σ(performance_amount + commission_amount)`（绩效工资 + 提成） |
| 作废原因 | `payroll_records.total_cost` **已包含提成前人力成本**（底薪、岗位工资、津贴、加班费、奖金、公司承担社保、公司公积金），而这部分在 `profit_basis_amount`（店铺利润基数）里**已经扣过一次**；再作为人员成本扣除等于同一笔钱扣两次，会把公司留存系统性低估 |
| 生效范围 | **月度利润看板**（`GET /api/finance/monthly-profit-settlement` 及其人工调整项写入口） |
| 不影响 | 上游利润基数口径（2.1 / 2.2 不变）、`finance.shop_profit_basis` 的写入逻辑、工资单本身的金额构成 |
| 关联指标 | `employee_allocation_amount`（员工侧分配额）、`company_retained_amount`（公司留存）、`allocation_ratio`（分配占比） |

### 17.2 指标登记

本次变更同时把看板的 6 个核心指标登记进指标词典（系统统一口径）：

- `profit_basis_amount`（店铺利润基数）
- `employee_allocation_amount`（员工侧分配额）
- `manual_adjustment_amount`（人工调整额）
- `company_retained_amount`（公司留存）
- `allocation_ratio`（分配占比）
- `over_allocation_flag`（超额分配标记）

登记位置：

- `docs/team-skills/sea-metrics-language/references/metrics-dictionary.md`（正本）
- `docs/team-skills/sea-metrics-language/references/metric-status.md`（状态表，6 项均为 `stable`）
- 副本 `team-skills-bundle/sea-metrics-language/` 由 `python scripts/verify_team_skills_sync.py` 保证字节一致

### 17.3 跨期对比提示

- 2026-11 之前的历史月份若按旧口径（工资单 `total_cost`）出过人侧分配额，
  与看板新口径**不可直接比较**；对比时必须先按新口径重算。
- 人工调整额带符号（正数减少公司留存），引用时必须带符号说明。

