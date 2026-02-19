## ADDED Requirements

### Requirement: 年度数据总结
系统 SHALL 在工作台提供「年度数据总结」模块，用于按月度或年度汇总核心 KPI，并支持环比（月度较上月、年度较去年），以支撑年度审视与来年成本配置决策；数据来源仅使用 B 类模型中的**月度粒度**数据；并展示成本与产出区块（总成本、GMV、成本产出比、ROI、毛利率、净利率）。

#### Scenario: 月度汇总与环比
- **WHEN** 用户打开年度数据总结页面并选择粒度=月度、某月（YYYY-MM）
- **THEN** 系统从 Orders Model、Analytics Model 等**仅取 granularity = 'monthly'** 的数据，汇总当月核心 KPI（GMV、订单数、买家数、转化率、客单价、销售单数等）
- **AND** 系统计算并展示较上月的环比

#### Scenario: 年度汇总与同比
- **WHEN** 用户选择粒度=年度、某年（YYYY）
- **THEN** 系统从上述模型仅取 monthly 粒度数据，汇总当年 12 个月的核心 KPI
- **AND** 系统计算并展示较去年的同比

#### Scenario: 数据源约束
- **WHEN** 年度数据总结模块执行任何查询
- **THEN** 所用 B 类模型数据 SHALL 仅包含 `granularity = 'monthly'` 的记录
- **AND** 不得依赖日度粒度数据，以避免历史日度不全与采集成本过高

#### Scenario: 成本与产出展示
- **WHEN** 用户查看年度数据总结页面（任意粒度与周期）
- **THEN** 系统在核心 KPI 区块下方展示「成本与产出」区块，包含：总成本、GMV（产出）、成本产出比（总成本/GMV）、ROI（(GMV−总成本)/总成本）、毛利率（(GMV−COGS)/GMV）、净利率（(GMV−总成本)/GMV）
- **AND** 总成本 SHALL 由运营成本（a_class.operating_costs 与 fact_expenses_month 汇总）与货款成本（COGS）组成；产出口径为 GMV（paid_amount）
- **AND** 若某周期成本数据缺失，系统可展示「暂无数据」或 null，不阻塞页面展示
- **AND** 当比率分母为 0（如总成本=0 或 GMV=0）时，对应比率展示 N/A 或「-」

#### Scenario: 仅管理员可访问
- **WHEN** 用户角色非管理员（如主管、操作员、财务、游客）
- **THEN** 工作台侧栏不显示「年度数据总结」菜单项
- **AND** 若直接访问年度数据总结路由，系统拒绝访问并重定向至与现有无权限路由一致的目标（如 `/business-overview`）
- **WHEN** 用户角色为管理员
- **THEN** 工作台侧栏显示「年度数据总结」，可正常进入页面并查看数据
