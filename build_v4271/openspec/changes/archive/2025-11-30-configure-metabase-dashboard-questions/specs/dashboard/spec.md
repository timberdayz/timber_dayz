## MODIFIED Requirements

### Requirement: 销售看板
系统 **SHALL** 提供实时销售看板，包含关键绩效指标（KPI）和可视化。

#### Scenario: 销售KPI显示
- **WHEN** 用户打开销售看板
- **THEN** 系统通过 Metabase Question API 查询业务概览 KPI Question，显示GMV、订单数、平均订单价值、转化率和增长率
- **AND** Question ID 通过环境变量 `METABASE_QUESTION_BUSINESS_OVERVIEW_KPI` 配置
- **AND** 如果 Question ID 未配置，系统返回 400 错误，提示"Question ID未配置"

#### Scenario: 销售趋势图
- **WHEN** 用户选择日期范围进行销售分析
- **THEN** 系统通过 Metabase Question API 查询业务概览对比 Question，使用ECharts显示折线图，展示随时间变化的销售趋势，支持日/周/月粒度
- **AND** Question ID 通过环境变量 `METABASE_QUESTION_BUSINESS_OVERVIEW_COMPARISON` 配置
- **AND** 前端通过后端代理 API `/api/dashboard/business-overview/comparison` 调用 Metabase Question

#### Scenario: 店铺赛马数据
- **WHEN** 用户查看店铺排名
- **THEN** 系统通过 Metabase Question API 查询店铺赛马 Question，显示店铺GMV排名
- **AND** Question ID 通过环境变量 `METABASE_QUESTION_BUSINESS_OVERVIEW_SHOP_RACING` 配置
- **AND** 前端通过后端代理 API `/api/dashboard/business-overview/shop-racing` 调用 Metabase Question

#### Scenario: 流量排名数据
- **WHEN** 用户查看流量排名
- **THEN** 系统通过 Metabase Question API 查询流量排名 Question，显示店铺UV和PV排名
- **AND** Question ID 通过环境变量 `METABASE_QUESTION_BUSINESS_OVERVIEW_TRAFFIC_RANKING` 配置
- **AND** 前端通过后端代理 API `/api/dashboard/business-overview/traffic-ranking` 调用 Metabase Question

#### Scenario: 库存积压数据
- **WHEN** 用户查看库存积压
- **THEN** 系统通过 Metabase Question API 查询库存积压 Question，显示积压SKU数和金额
- **AND** Question ID 通过环境变量 `METABASE_QUESTION_BUSINESS_OVERVIEW_INVENTORY_BACKLOG` 配置
- **AND** 前端通过后端代理 API `/api/dashboard/business-overview/inventory-backlog` 调用 Metabase Question

#### Scenario: 经营指标数据
- **WHEN** 用户查看经营指标
- **THEN** 系统通过 Metabase Question API 查询经营指标 Question，显示门店经营表格（GMV、订单数、客单价、退货率等）
- **AND** Question ID 通过环境变量 `METABASE_QUESTION_BUSINESS_OVERVIEW_OPERATIONAL_METRICS` 配置
- **AND** 前端通过后端代理 API `/api/dashboard/business-overview/operational-metrics` 调用 Metabase Question

#### Scenario: 清仓排名数据
- **WHEN** 用户查看清仓排名
- **THEN** 系统通过 Metabase Question API 查询清仓排名 Question，显示折扣率和库存数量排名
- **AND** Question ID 通过环境变量 `METABASE_QUESTION_CLEARANCE_RANKING` 配置
- **AND** 前端通过后端代理 API `/api/dashboard/clearance-ranking` 调用 Metabase Question

