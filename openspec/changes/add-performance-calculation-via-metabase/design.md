# Design: 绩效计算 Metabase 方案

## Context

- 绩效公示页面展示 `c_class.performance_scores` 数据，但当前 `POST /api/performance/scores/calculate` 为 TODO 占位
- 业务概览、人员店铺归属已通过 Metabase Question（`business_overview_comparison`、`hr_shop_monthly_metrics`）实现 SQL 计算
- 用户确认采用**方案 A**：在 Metabase 中编写 SQL，后端调用 Metabase 并写入 `performance_scores`

## Goals / Non-Goals

### Goals
- 复用 Metabase 架构，与 hr_shop_monthly_metrics 一致
- 使用 Orders Model、a_class 表，与业务概览数据约定一致
- 支持 performance_config 中的 sales_max_score、profit_max_score 等得分比例配置
- 实现达成率 > 100% 得满分、≤ 100% 得 达成率 × 满分的规则

### Non-Goals
- 不实现重点产品目标/达成（若暂无数据源，先返回 0）
- 不修改 GET /api/performance/scores 的展示逻辑
- 不迁移 performance_config 或修改其 schema

## Decisions

### 1. Metabase Question 结构与参数

**决策**：沿用 `hr_shop_monthly_metrics` 的模式，单参数 `{{month}}`（YYYY-MM-DD 月初）

**理由**：与 hr_shop_monthly_metrics 一致，后端传 `period + "-01"` 即可

### 2. SQL 数据源

**决策**：
- 销售额/利润：`{{MODEL:Orders Model}}`（与 hr_shop_monthly_metrics 一致）
- 目标：`a_class.target_breakdown` + `a_class.sales_targets`（与 hr_shop_monthly_metrics 一致）
- 得分比例：`public.performance_config`（取考核周期内生效的一条，`effective_from <= period_end AND (effective_to IS NULL OR effective_to >= period_start)`）
- 运营得分：`c_class.shop_health_scores`（可选，月度粒度聚合）
- **dim_shops**：**必须 INNER JOIN**，确保返回的 (platform_code, shop_id) 存在于 dim_shops，满足 `c_class.performance_scores` 外键约束，避免写入时 FK 违反

**备选**：运营得分若无数据可先返回 0

### 3. 得分计算规则（SQL 内实现）

**决策**：
```sql
-- 达成率>100%得满分，<=100%得达成率*满分
case 
  when coalesce(sales_rate, 0) > 100 then sales_max_score
  else (coalesce(sales_rate, 0) / 100.0) * sales_max_score
end as sales_score
```

**备选**：若 performance_config 未在 SQL 中 JOIN，可后端传 max_scores 作为参数（增加 Question 参数复杂度，暂不采用）

### 4. 后端 calculate 流程

**决策**：
1. 查询 `public.performance_config` 校验存在
2. 调用 `metabase_service.query_question("performance_scores_calculation", {"month": period + "-01"})`
3. 遍历返回结果，对每行 UPSERT `c_class.performance_scores`（INSERT 或 UPDATE）
4. 计算 rank、performance_coefficient 并写入
5. 写入 score_details JSON（可选，存储计算明细）

**备选**：Metabase 直接返回 rank 和 performance_coefficient（增加 SQL 复杂度，暂由后端计算）

### 5. 店铺维度与 FK 约束

**决策**：Metabase SQL **必须 INNER JOIN public.dim_shops**，仅返回 (platform_code, shop_id) 存在于 dim_shops 的店铺，以保证 `c_class.performance_scores` 外键约束（FK 至 dim_shops）不被违反

**理由**：Orders Model 可能返回 shop_id='unknown' 或未在 dim_shops 中注册的店铺，直接写入会导致 FK violation；通过 INNER JOIN dim_shops 在 SQL 层过滤，后端无需二次校验

### 6. 考核周期与配置生效

**决策**：获取「当前生效」配置时，使用**考核周期**（period）而非今日日期：`effective_from <= period_end AND (effective_to IS NULL OR effective_to >= period_start)`

**理由**：历史月份（如 2024-06）计算时，应使用当时生效的配置，而非今日生效的配置

### 7. 后端解析列名

**决策**：后端解析 Metabase 返回的每行时，**同时支持英文与中文列名**（如 `platform_code` 或 `平台`、`shop_id` 或 `店铺ID`），与 hr_management 调用 hr_shop_monthly_metrics 的方式一致

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| Metabase 不可用时 calculate 失败 | 后端 try/except，返回明确错误信息 |
| shop_id 不在 dim_shops 导致 FK violation | SQL 中 INNER JOIN dim_shops，仅返回有效店铺 |
| 历史月份使用错误配置 | 按考核周期筛选 effective_from/effective_to |
| Metabase 返回中文列名 | 后端解析兼容英文/中文列名 |
| 重点产品、毛利目标暂无数据源 | 先返回 0，后续迭代补充 |

## 数据流

```
Metabase SQL 读取:
  b_class.fact_*_orders_* (via Orders Model)
  a_class.target_breakdown
  a_class.sales_targets
  public.performance_config
  public.dim_shops (INNER JOIN，保证 FK 有效)
  c_class.shop_health_scores (可选)

         │
         ▼
  Metabase 返回 JSON (per-shop rows)
         │
         ▼
  后端 calculate_performance_scores
         │
         ├─► INSERT/UPDATE c_class.performance_scores
         └─► 计算 rank、performance_coefficient

         │
         ▼
  GET /api/performance/scores 读取
  core.platform_accounts + c_class.performance_scores
```

## Open Questions

- 重点产品目标/达成是否已有数据源（如 target_breakdown 中 breakdown_type）？
- 毛利目标是否与销售额目标共用 target_breakdown，还是需单独配置？
