# Unified Profit Basis And Follow Investment Design

## Goal

为西红 ERP 建立统一的正式利润分配基准 `profit_basis_amount`，并在此基准之上落地“店铺跟投收益”能力。目标是在测试环境阶段一次性收口当前分散的利润口径，避免跟投收益、HR 提成和财务展示各用一套利润字段，导致后续误开发和误结算。

## Status Snapshot

### 已存在能力

- 现有财务域按 `period_month` 管理会计期间
- 现有利润分析支持 `platform_code + shop_id` 店铺维度
- 已有 orders 数据域利润口径
- 已有 A 类成本录入，且广告、人工等费用可按店铺归集
- 已有财务管理入口、店铺筛选和审批日志
- 已有 B 类成本分析视图，可提供额外成本口径参考

### 当前缺口

- 没有“唯一正式结算利润口径”字段
- 没有“店铺月度结算利润快照”对象
- 没有“店铺跟投本金记录”台账
- 没有“店铺月度跟投收益试算/审批/结算”对象
- 没有投资人查看个人跟投收益的受限视图

## Problem Framing

当前系统里至少存在三种利润语义：

- `orders_profit` 或 orders 数据域月利润
- `contribution_profit`
- HR 提成链中当前使用的利润字段

这些字段分别服务分析展示、历史财务页面或局部业务逻辑，但尚未被统一治理为“正式分钱基准”。如果只为跟投收益单独补一个口径，后续仍会出现：

- 跟投收益按一个利润字段
- HR 提成按另一个利润字段
- 财务看板展示第三个利润字段

因此应先建立统一的正式结算层，再让具体分钱规则挂在其上。

## Canonical Settlement Basis

### 正式结算字段

系统新增唯一正式结算字段：

```text
profit_basis_amount
```

它是系统内一切正式利润分配的统一基准，用于：

- 跟投收益
- HR 提成
- 未来其他按利润分钱的模块

### 推荐公式

第一版推荐按 A 类净利润口径定义：

```text
profit_basis_amount = orders_profit - included_a_class_cost
```

其中：

- `orders_profit` 来自现有 orders 数据域店铺月利润
- `included_a_class_cost` 来自现有 A 类成本按店铺、按月分摊结果

如果未来业务确认 B 类成本也必须纳入正式分钱口径，则扩展为：

```text
profit_basis_amount = orders_profit - included_a_class_cost - included_b_class_cost
```

但在 B 类口径未完全治理稳定前，第一版不建议直接全量引入。

## Relationship To Existing Profit Fields

### `orders_profit`

- 保留
- 用于经营分析
- 作为 `profit_basis_amount` 的输入之一

### `contribution_profit`

- 保留
- 用于财务页展示和历史 P&L 参考
- 不再默认视为正式分钱口径

### HR 当前利润字段

- 当前仅代表 HR 提成现状输入
- 不再视为长期正式结算基准
- 后续应迁移到 `profit_basis_amount`

## Profit Basis Governance

系统内利润语义固定为三层：

### 1. 分析展示层

- `orders_profit`
- `contribution_profit`
- B 类成本分析视图中的利润率和参考值

这些字段继续存在，但仅用于分析和展示。

### 2. 统一结算层

- `profit_basis_amount`

这是唯一正式结算字段。

### 3. 分配规则层

不同业务规则调用同一个统一结算层：

- 跟投收益：

```text
profit_basis_amount × distribution_ratio × capital_share_ratio
```

- HR 提成：

```text
profit_basis_amount × allocatable_profit_rate × commission_ratio
```

## Data Model

新增对象分为四层。

### 1. 店铺月度结算利润对象

新增月店铺结算利润快照对象，承接统一结算口径。

核心字段：

- `period_month`
- `platform_code`
- `shop_id`
- `orders_profit_amount`
- `a_class_cost_amount`
- `b_class_cost_amount`
- `profit_basis_amount`
- `basis_version`
- `is_locked`

该对象推荐为快照表而不是临时计算结果，便于审批、追溯和审计。

### 2. 跟投本金记录

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

### 3. 店铺月度跟投结算头

记录该店铺该月使用的正式结算利润基准与可分配收益。

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

### 4. 店铺月度跟投结算明细

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

## Capital Allocation Logic

同一店铺、同一期间内，跟投收益按“加权资金占用”分配，而不是按月末静态本金分配。

```text
weighted_capital = contribution_amount × occupied_days
```

```text
share_ratio = personal_weighted_capital / total_weighted_capital
```

```text
estimated_income = distributable_amount × share_ratio
```

## Integration Boundaries

### 必须复用

- `period_month` 与会计期间状态
- `platform_code + shop_id` 店铺维度
- 现有 orders 数据域利润
- 现有 A 类成本按店铺归集能力
- 现有财务入口与审批日志

### 应统一治理

- HR 提成链中的利润基础字段不再被视为最终口径
- 新的跟投收益与后续 HR 提成都应围绕 `profit_basis_amount`

### 第一版不做

- 公司级股权分红
- 多项目/多业务线复合资金池
- 跨店盈亏对冲
- 固定收益或保底收益
- 税务代扣代缴复杂建模
- 自动外部付款打款集成

## Runtime Flow

### 财务端月度流程

1. 完成当月 orders 利润与 A 类成本归集
2. 生成并锁定本月店铺 `profit_basis_amount`
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

页面需明确标注：

- `预计收益仅供参考，以财务审核后的结算结果为准`

## UI Rollout

### 财务管理页

在现有 `FinanceManagement.vue` 新增：

- `结算利润口径` 区块
- `跟投收益` 页签

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
- `contribution_profit` 仍可保留在财务页展示
- 正式分钱只认 `profit_basis_amount`
- A 类成本继续由现有店铺成本录入维护，不复制数据
- 跟投收益与未来 HR 提成应尽量围绕 `profit_basis_amount` 统一
- 跟投收益是现有财务结算结果的下游应用，不反向写回 P&L

## Open Decisions

1. 第一版 `profit_basis_amount` 是否仅纳入 A 类成本，还是同步纳入已治理完成的 B 类成本
2. HR 提成是否在第一版就切换到 `profit_basis_amount`
3. 员工跟投收益是否需要在个人收入页面并列展示，还是独立入口
4. 审批通过后是否允许二次重算，还是必须先驳回结算单

## Testing Strategy

1. 锁定 `profit_basis_amount` 口径来源测试
2. 锁定加权资金占用分配测试
3. 锁定月度试算与审批状态流转测试
4. 锁定前端财务页跟投收益页签交互测试
5. 锁定 HR 提成对统一利润基准的兼容性测试
