# 业务概览（/business-overview）上线前数据审查报告（成本/利润/净利润重点）

日期：2026-05-13（Asia/Hong_Kong）

目标：说明业务概览页面最终呈现的数据由哪些数据组成；并重点审查**成本、利润、净利润**链路是否合理、是否存在口径风险。

本报告基于代码/SQL追溯（PostgreSQL Dashboard 路由），不依赖 Metabase（Metabase 视为历史路径）。

---

## 1. 页面最终数据由哪些模块组成（前端 -> API -> api视图 -> mart/semantic -> b_class/a_class）

前端页面：
- `frontend/src/domains/business/views/BusinessOverview.vue`

后端路由（PostgreSQL Dashboard）：
- `backend/routers/dashboard_api_postgresql.py`

业务概览页面调用的核心 API（按页面模块）：

### 1.1 核心 KPI 卡片（汇总）
- API：`GET /api/dashboard/business-overview/kpi`
- 数据源：`api.business_overview_kpi_module`
- SQL：`sql/api_modules/business_overview_kpi_module.sql`
- 上游：
  - `mart.platform_month_kpi`（`sql/mart/platform_month_kpi.sql`）
  - `semantic.fact_orders_monthly_atomic`（`sql/semantic/orders_monthly_atomic.sql` -> 优先使用 MV：`sql/semantic/orders_monthly_atomic_mv.sql`）
  - `semantic.fact_analytics_monthly_atomic`（`sql/semantic/analytics_monthly_atomic.sql`）
- 字段（页面最终看到的核心聚合口径）：
  - `gmv`：月 GMV（来自订单 paid_amount 聚合）
  - `order_count`：月订单数（distinct order_id 聚合）
  - `visitor_count`：月访客/浏览（`COALESCE(page_views, visitor_count)` 再聚合）
  - `conversion_rate`：`order_count / visitor`（百分比）
  - `avg_order_value`：`gmv / order_count`
  - `attach_rate`：`total_items / order_count`
  - `profit`：月利润/毛利（来自订单 profit 聚合，语义需确认，见第 3 节）

> 注：KPI 层面没有“成本/净利润”的拆解，成本/净利润主要出现在“经营指标”模块。

### 1.2 对比折线（日/周/月）
- API：`GET /api/dashboard/business-overview/comparison`
- 数据源：`api.business_overview_comparison_module`
- SQL：`sql/api_modules/business_overview_comparison_module.sql`
- 上游：
  - `mart.shop_day_kpi` / `mart.shop_week_kpi` / `mart.shop_month_kpi`
  - 月粒度目标：`a_class.sales_targets_a`（注意：这与经营指标里“目标”的优先来源不同，存在口径分裂风险）

### 1.3 经营指标（重点：目标/毛利/费用/净利润）
- API：`GET /api/dashboard/business-overview/operational-metrics`
- 数据源：`api.business_overview_operational_metrics_module`
- SQL：`sql/api_modules/business_overview_operational_metrics_module.sql`
- 上游：
  - `mart.shop_month_kpi`（月 GMV、月订单数、profit）
  - `mart.shop_day_kpi`（用于“今日销售额/今日单数”，取 anchor_date）
  - 目标（视图层）：`a_class.sales_targets_a`
  - 费用（视图层）：`a_class.operating_costs`
- **服务层二次汇总/兜底**：
  - `backend/services/postgresql_dashboard_service.py::get_business_overview_operational_metrics`
  - 目标兜底：`_load_target_summary()`（优先 `a_class.sales_targets + a_class.target_breakdown`，失败才回退 `a_class.sales_targets_a`）
  - 费用兜底：`_load_operating_expenses_summary()`（按月份全表求和）

### 1.4 店铺竞速 / 流量排名 / 库存积压
这三块不直接影响“成本/净利润”口径，但同属业务概览数据组成：
- 店铺竞速：`api.business_overview_shop_racing_module`（`sql/api_modules/business_overview_shop_racing_module.sql`）
- 流量排名：`api.business_overview_traffic_ranking_module`（`sql/api_modules/business_overview_traffic_ranking_module.sql`）
- 库存积压：`api.business_overview_inventory_backlog_module`（`sql/api_modules/business_overview_inventory_backlog_module.sql`）

---

## 2. 成本 / 利润 / 净利润：链路与计算口径

本节以“经营指标模块（operational-metrics）”为准，因为它是页面内唯一直接输出“预估费用/经营结果”的模块。

### 2.1 利润（页面字段：`estimated_gross_profit`）

页面显示名称：预估毛利（但实际上字段叫 gross_profit，且上游字段名为 profit）

链路（从源到页面）：
1) 订单原始数据（B 类）：
   - `b_class.fact_*_orders_monthly.raw_data` 内的 profit/利润/毛利字段
2) 语义层映射（关键点：profit 取自 raw_data 字段的数值化）：
   - `semantic.fact_orders_monthly_atomic_mv`（`sql/semantic/orders_monthly_atomic_mv.sql`）
   - profit 字段取值（节选）：`COALESCE(raw_data->>'利润(RMB)', raw_data->>'profit_rmb', raw_data->>'利润', raw_data->>'profit', raw_data->>'毛利', raw_data->>'Profit')`
3) mart 月聚合：
   - `mart.shop_month_kpi.profit = SUM(semantic.fact_orders_monthly_atomic.profit)`
4) api 经营指标：
   - `api.business_overview_operational_metrics_module.estimated_gross_profit = mart.shop_month_kpi.profit`
5) 服务层汇总：
   - `get_business_overview_operational_metrics()` 把多行（平台/店铺）做 sum 汇总，返回单行给前端

结论（合理性）：
- 数学上链路是通的：profit 从订单原始字段一路聚合到月/平台/店铺再汇总。
- 但**语义存在重大不确定性**：
  - raw_data 里的 `profit/利润/毛利` 在不同平台导出里可能语义不一致（毛利 vs 净利 vs 订单利润）。
  - 当前系统没有对“profit 的定义”做二次校验（例如：是否已经扣除了平台费用/采购成本/退款等）。
  - 因此页面“预估毛利”是否真是“毛利”，必须由业务口径确认（见第 4 节的必确认项）。

### 2.2 成本（页面字段：`estimated_expenses`）

页面显示名称：预估费用

链路（从源到页面）：
1) A 类费用表：
   - `a_class.operating_costs`
2) api 经营指标视图层（按月 + 店铺聚合）：
   - `estimated_expenses = SUM(rent + marketing_fee + utilities + other_costs)`
   - 视图层 SQL：`sql/api_modules/business_overview_operational_metrics_module.sql`
3) 服务层汇总：
   - `get_business_overview_operational_metrics()` 将多行相加汇总
4) 服务层兜底（非常重要）：
   - 当视图层汇总后 `estimated_expenses` 为 `None/0` 时：
     - 直接调用 `_load_operating_expenses_summary(period_month)`，按月份对 `operating_costs` **全表求和** 作为费用兜底。

结论（合理性）：
- 合计公式本身合理（租金 + 营销/薪资 + 水电 + 其他）。
- 但存在两类上线风险：
  1) **“营销费用 vs 薪资”字段语义漂移风险**：
     - 仓库存在迁移：把 `operating_costs.salary` 重命名为 `operating_costs.marketing_fee`（以及中文列同义重命名）。
     - 如果你们实际希望拆分“薪资”与“营销费用”，当前实现会把它们混为一类。
  2) **平台/店铺过滤时的兜底风险**：
     - 服务层兜底是“按月份全表费用”，不带 platform/shop 过滤。
     - 这在只看单个平台（甚至未来按店铺）时可能导致费用被错误放大（把不相关店铺费用也算进来）。

### 2.3 净利润（页面字段：`operating_result`）

页面显示名称：经营结果（盈利/亏损）

计算口径（当前实现）：
- `operating_result = estimated_gross_profit - estimated_expenses`
- `operating_result_text = '盈利' if operating_result > 0 else '亏损'`

结论（合理性）：
- 若 `profit` 确认是“毛利”（未扣运营费用），那么该净利润口径合理：**净利润 = 毛利 - 运营费用**。
- 若 `profit` 实际已经是“净利/订单利润（已扣部分费用）”，再减 `estimated_expenses` 可能出现**重复扣减**，导致净利润偏低。

---

## 3. 成本/利润/净利润链路“正常性”检查点（上线前必须核对）

### 3.1 利润字段一致性（profit 语义校验）
必须回答清楚的问题（否则净利润口径不可判定）：
- 订单导出里的 `利润/毛利/profit` 是：
  - (A) 毛利（= 销售额 - 商品成本 - 平台成本等）？
  - (B) 订单净利（已扣了大部分费用）？
  - (C) 仅平台侧“预估利润”（口径不稳定）？

建议上线前做 2 个对照抽样（人工核对 5~10 单即可）：
1) 从原始订单报表中挑选一笔订单，看其 profit 数值与人工计算是否一致。
2) 同一平台同一月份：`SUM(paid_amount)`、`SUM(profit)` 的比例是否在合理区间（例如毛利率 0%~80% 或你们业务的实际范围）。

### 3.2 费用字段一致性（operating_costs 列含义）
必须确认：
- `operating_costs.marketing_fee` 这一列是否被你们当作“营销费用”，还是“薪资”，还是二者合并项。
- 如果你们需要拆分薪资：当前页面与 API 不支持，需要补字段与口径。

### 3.3 服务层兜底是否会误伤（平台过滤）
当前服务层行为（摘要）：
- 先把 `api.business_overview_operational_metrics_module` 返回的多行做 sum。
- 若 sum 后 `estimated_expenses` 为 `None/0`，则用“全公司当月费用”兜底填充。

上线前建议明确一条规则：
- 当请求带 `platform_code` 或 `shop_id` 时，费用兜底是否允许使用“全公司费用”？
  - 若不允许：需要调整兜底逻辑为“同维度兜底”（按 platform/shop 分摊或不兜底）。

---

## 4. “必须确认的口径点”（不确认会导致结论不成立）

1) **profit 定义**（毛利 vs 净利）：决定 `operating_result` 是否重复扣减。
2) **operating_costs.marketing_fee 定义**（营销 vs 薪资）：决定“成本/费用”是否真实反映经营成本结构。
3) **业务概览是否需要“分红”**：
   - 当前业务概览链路没有分红字段/计算；如果要展示，需要新增数据源与口径（不在本报告范围内）。

---

## 5. 建议的上线前 SQL 自检（只读）

以下查询用于快速验证“月利润、月费用、净利润”是否符合直觉（字段名按当前 SQL 口径）：

1) 看某月 profit（按平台/店铺）：
```sql
SELECT period_month, platform_code, shop_id, gmv, order_count, profit
FROM mart.shop_month_kpi
WHERE period_month = DATE '2026-05-01'
ORDER BY platform_code, shop_id;
```

2) 看某月费用（按店铺）：
```sql
SELECT to_date(year_month || '-01', 'YYYY-MM-DD') AS period_month,
       shop_id,
       SUM(rent + marketing_fee + utilities + other_costs) AS expenses
FROM a_class.operating_costs
WHERE year_month = '2026-05'
GROUP BY 1,2
ORDER BY shop_id;
```

3) 看业务概览经营指标模块最终单行（api视图层）：
```sql
SELECT *
FROM api.business_overview_operational_metrics_module
WHERE period_month = DATE '2026-05-01';
```

4) 若只看某个平台，检查“费用兜底是否不合理”：
   - 先看 `api.business_overview_operational_metrics_module` 按平台过滤是否已有费用；
   - 再对照服务层兜底（全表费用）是否会覆盖它。

---

## 6. 审查结论（当前实现是否“合理且正常”）

### 6.1 链路是否正常
- 正常：业务概览成本/利润/净利润链路在 PostgreSQL 路径下是可闭环追溯的（`b_class/a_class -> semantic -> mart -> api -> service -> API -> frontend`）。

### 6.2 口径是否合理（重点风险）
- 利润（profit）：
  - 取自原始订单导出字段并数值化聚合；合理性取决于你们对 `profit/毛利/利润` 的业务定义一致性。
- 成本（estimated_expenses）：
  - 取自 `operating_costs` 的合计；但存在“营销/薪资字段语义漂移”和“平台过滤兜底误伤”的风险。
- 净利润（operating_result）：
  - 当前是 `profit - expenses`；在“profit=毛利”前提下合理，在“profit=净利”前提下可能重复扣减。

---

## 7. 下一步（我建议你们做的最小验收动作）

1) 选定 1 个平台、1 个店铺、1 个月（比如 2026-05），抽样核对：
   - 原始订单导出的 profit 字段到底是什么口径（毛利/净利）。
2) 明确 `operating_costs.marketing_fee` 是“营销”还是“薪资”，并决定业务概览要不要拆分展示。
3) 决定当带 `platform_code` 查询时，费用兜底是否允许使用“全公司费用”。

