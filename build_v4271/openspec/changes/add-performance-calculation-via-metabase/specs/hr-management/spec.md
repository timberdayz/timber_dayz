## ADDED Requirements

### Requirement: 绩效计算通过 Metabase SQL 实现
系统 SHALL 通过 Metabase Question `performance_scores_calculation` 执行绩效计算 SQL，后端调用 Metabase 获取结果并写入 `c_class.performance_scores`。

#### Scenario: Metabase 绩效计算 Question 可用
- **WHEN** 系统执行 `POST /api/performance/scores/calculate?period=YYYY-MM`
- **THEN** 后端调用 Metabase Question `performance_scores_calculation`，传入 `month=YYYY-MM-01`
- **AND** Metabase 执行 SQL，从 `{{MODEL:Orders Model}}`、`a_class.target_breakdown`、`a_class.sales_targets`、`public.performance_config` 读取数据
- **AND** Metabase 返回按店铺聚合的绩效得分（sales_target、sales_achieved、sales_rate、sales_score、profit_*、key_product_*、operation_score、total_score）
- **AND** 后端将结果 INSERT 或 UPDATE 至 `c_class.performance_scores`
- **AND** 后端计算 rank、performance_coefficient 并写入

#### Scenario: 得分规则正确
- **WHEN** 销售额达成率 > 100%
- **THEN** 销售额得分 = sales_max_score（满分）
- **WHEN** 销售额达成率 ≤ 100%
- **THEN** 销售额得分 = 达成率 × sales_max_score
- **AND** 毛利、重点产品、运营得分规则同上（若适用）

#### Scenario: 绩效公示展示计算后数据
- **WHEN** 管理员执行绩效计算后访问绩效公示页面
- **THEN** 系统从 `c_class.performance_scores` 读取数据（与 platform_accounts 合并）
- **AND** 展示非空得分（sales_score、profit_score、key_product_score、operation_score、total_score）
- **AND** 展示排名、绩效系数

#### Scenario: Metabase 不可用时明确报错
- **WHEN** Metabase 服务不可用或 Question 查询失败
- **THEN** `POST /api/performance/scores/calculate` 返回 `HTTP 503` 且 `error_code=PERF_CALC_NOT_READY`
- **AND** 不写入错误数据至 `c_class.performance_scores`

#### Scenario: 历史月份使用该月生效的配置
- **WHEN** 管理员执行 `POST /api/performance/scores/calculate?period=2024-06`
- **THEN** 系统按考核周期筛选 performance_config（effective_from <= 2024-06-30 AND (effective_to IS NULL OR effective_to >= 2024-06-01)）
- **AND** 使用该筛选结果中的配置（而非今日生效的配置）计算绩效

#### Scenario: 考核周期无可用配置
- **WHEN** 管理员执行 `POST /api/performance/scores/calculate?period=YYYY-MM`
- **AND** 系统按考核周期筛选后未找到可用 `public.performance_config`
- **THEN** 接口返回 `HTTP 404` 且 `error_code=PERF_CONFIG_NOT_FOUND`
- **AND** 不写入错误数据至 `c_class.performance_scores`

#### Scenario: 仅写入 dim_shops 中存在的店铺
- **WHEN** Metabase SQL 执行绩效计算
- **THEN** SQL 中 INNER JOIN public.dim_shops，仅返回 (platform_code, shop_id) 存在于 dim_shops 的店铺
- **AND** 后端写入 `c_class.performance_scores` 时不会触发 FK 违反（外键指向 dim_shops）
