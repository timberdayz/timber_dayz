# Follow Investment Profit Sharing Design

## Goal

为西红 ERP 设计一套“店铺跟投收益”方案，服务于“员工或外部人员投入货款/营销资金后，按店铺净利润参与收益分配”的业务场景。方案必须复用现有财务月结、店铺利润、A 类成本录入、会计期间和审批体系，不重建成本利润主线。

## Status Snapshot

### 已存在能力

- 现有财务域按 `period_month` 管理会计期间
- 现有利润分析支持 `platform_code + shop_id` 店铺维度
- 已有 orders 数据域利润口径
- 已有 A 类成本录入，且广告、人工等费用可按店铺归集
- 已有财务管理入口、店铺筛选和审批日志

### 当前缺口

- 没有“店铺跟投本金记录”台账
- 没有“店铺月度跟投收益试算/审批/结算”对象
- 没有投资人查看个人跟投收益的受限视图

## Problem Framing

当前业务中，部分人员不是单纯拿工资，而是向具体店铺投入货款或营销资金，并希望按投入比例参与收益分配。由于投入对象是店铺经营，而非公司股权，因此这里不适合套用“公司股东税后利润分红”模型。更合适的定义是：

- 经营主体：店铺
- 期间主体：月度
- 结算口径：店铺净利润
- 分配对象：店铺跟投人

## Settlement Basis

### 正式结算口径

正式收益分配必须按净利润口径，而不是 orders 数据域里尚未扣除人工、广告等期间费用的利润。

优先规则：

1. 如果现有店铺月度 `contribution_profit` 已完整包含 A 类广告、人工等店铺成本，则直接将其作为分成基准
2. 如果现有 `contribution_profit` 尚未完整覆盖 A 类成本，则在结算层补一层“分成基准净利润”：

```text
profit_basis_amount = orders_profit - a_class_cost_total
```

该层仅作为跟投结算基准，不反向改写现有利润体系。

### 可分配收益

第一版不引入复杂亏损结转或跨店补贴，直接采用保守比例分配：

```text
distributable_amount = max(0, profit_basis_amount × distribution_ratio)
```

其中 `distribution_ratio` 为店铺跟投收益分配比例，由业务或财务配置。

## Capital Allocation Logic

同一店铺、同一期间内，跟投收益按“加权资金占用”分配，而不是按月末静态本金快照分配。

```text
weighted_capital = contribution_amount × occupied_days
```

```text
share_ratio = personal_weighted_capital / total_weighted_capital
```

```text
estimated_income = distributable_amount × share_ratio
```

这样可以处理月中追加投入、提前退出和多人不同持有天数的情况。

## Data Model

新增对象尽量压缩为三层。

### 1. 跟投本金记录

记录谁在哪个店铺投了多少钱。

核心字段：

- `investor_user_id`
- `platform_code`
- `shop_id`
- `contribution_amount`
- `contribution_date`
- `withdraw_date`
- `status`
- `remark`

### 2. 店铺月度跟投结算头

记录该店铺该月使用的分成基准与可分配收益。

核心字段：

- `period_month`
- `platform_code`
- `shop_id`
- `profit_basis_amount`
- `distribution_ratio`
- `distributable_amount`
- `status`
- `approved_by`
- `approved_at`

### 3. 店铺月度跟投结算明细

记录该月每个跟投人的占比和收益。

核心字段：

- `settlement_id`
- `investor_user_id`
- `contribution_amount_snapshot`
- `occupied_days`
- `weighted_capital`
- `share_ratio`
- `estimated_income`
- `approved_income`
- `paid_income`
- `paid_at`

## Integration Boundaries

### 必须复用

- `period_month` 与会计期间状态
- `platform_code + shop_id` 店铺维度
- 现有 orders 数据域利润
- 现有 A 类成本按店铺归集能力
- 现有财务入口与审批日志

### 不在第一版做

- 公司级股权分红
- 多项目/多业务线复合资金池
- 跨店盈亏对冲
- 固定收益或保底收益
- 税务代扣代缴复杂建模
- 自动外部付款打款集成

## Runtime Flow

### 财务端月度流程

1. 完成当月 orders 利润与 A 类成本归集
2. 锁定或确认本月店铺分成基准净利润
3. 读取该店铺当月有效跟投记录
4. 计算每人 `occupied_days` 与 `weighted_capital`
5. 生成试算结果
6. 财务审核通过
7. 人工付款并标记已支付

### 投资人查看流程

投资人只查看自己的跟投收益，不查看全量财务明细。页面展示：

- 本月预计收益
- 本月已批准收益
- 累计已支付收益
- 分店铺收益明细

并明确标注：

- `预计收益仅供参考，以财务审核后的结算结果为准`

## UI Rollout

### 财务管理页

在现有 `FinanceManagement.vue` 新增 `跟投收益` 页签，不新开独立系统页面。

页签内拆为三块：

1. `跟投记录`
2. `月度试算`
3. `结算台账`

### 个人端

新增“我的跟投收益”个人页面，复用现有用户登录体系，不引入游客权限模型。

## Approval Model

继续复用现有 `approval_logs`，只扩展新的 `entity_type`。

状态建议：

- `draft`
- `calculated`
- `approved`
- `paid`

## Compatibility Notes

- 现有 orders 利润仍然保留为分析展示指标
- 正式分钱只认“分成基准净利润”
- A 类成本继续由现有店铺成本录入维护，不复制数据
- 跟投收益是现有财务结算结果的下游应用，不反向写回 P&L

## Open Decisions

1. 现有 `contribution_profit` 是否已完整覆盖用于分成的 A 类成本
2. 员工跟投收益是否需要在个人收入页面并列展示，还是独立入口
3. 审批通过后是否允许二次重算，还是必须先驳回结算单

## Testing Strategy

1. 锁定净利润口径来源测试
2. 锁定加权资金占用分配测试
3. 锁定月度试算与审批状态流转测试
4. 锁定前端财务页跟投收益页签交互测试
